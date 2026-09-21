-- Keep consent and report-enqueue validation inside the database transaction.
-- Authenticated students cannot write worker-owned tables directly after 0016;
-- these narrowly scoped SECURITY DEFINER paths are the only permitted writes.

begin;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create or replace function private.enforce_current_consent()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    caller_id uuid := (select auth.uid());
    request_role text := coalesce(
        nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role',
        ''
    );
    latest_grant boolean;
begin
    -- Trusted service requests and direct migration/maintenance SQL have no
    -- end-user uid. Anonymous Data API requests must never pass this guard.
    if caller_id is null then
        if request_role in ('', 'service_role') then
            return new;
        end if;
        raise exception 'Authentication is required';
    end if;

    if not exists (
        select 1
        from public.attempts as a
        where a.id = new.attempt_id
          and a.user_id = caller_id
    ) then
        raise exception 'Attempt was not found';
    end if;

    select c.granted into latest_grant
    from public.consent_records as c
    where c.user_id = caller_id
      and c.consent_type = tg_argv[0]
      and (c.attempt_id = new.attempt_id or c.attempt_id is null)
    order by c.occurred_at desc, c.id desc
    limit 1;

    if coalesce(latest_grant, false) is not true then
        raise exception '% consent is required', tg_argv[0];
    end if;
    return new;
end;
$$;

revoke all on function private.enforce_current_consent()
from public, anon, authenticated;
grant execute on function private.enforce_current_consent() to service_role;

drop trigger if exists resume_documents_require_consent
on public.resume_documents;
create trigger resume_documents_require_consent
before insert or update of attempt_id on public.resume_documents
for each row execute function private.enforce_current_consent('resume_processing');

drop trigger if exists answers_require_recording_consent
on public.answers;
create trigger answers_require_recording_consent
before insert or update of attempt_id on public.answers
for each row execute function private.enforce_current_consent('interview_recording');

drop trigger if exists processing_jobs_require_external_ai_consent
on public.processing_jobs;
create trigger processing_jobs_require_external_ai_consent
before insert or update of attempt_id, job_type, status on public.processing_jobs
for each row
when (
    new.job_type in ('answer_preprocessing', 'report_generation')
    and new.status = 'queued'
)
execute function private.enforce_current_consent('external_ai_processing');

create or replace function public.request_attempt_report(p_attempt_id uuid)
returns table (
    attempt_id uuid,
    started boolean,
    queued_job_count integer,
    message text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    caller_id uuid := (select auth.uid());
    current_attempt public.attempts;
    existing_job public.processing_jobs;
    latest_grant boolean;
    evaluated_count integer := 0;
    inserted_count integer := 0;
begin
    if caller_id is null then
        raise exception 'Authentication is required';
    end if;

    select a.* into current_attempt
    from public.attempts as a
    where a.id = p_attempt_id
      and a.user_id = caller_id
    for update;

    if not found then
        raise exception 'Attempt was not found';
    end if;

    if current_attempt.status = 'completed' then
        return query select
            p_attempt_id,
            true,
            0,
            'The evidence-backed report is already complete.'::text;
        return;
    end if;

    select j.* into existing_job
    from public.processing_jobs as j
    where j.idempotency_key =
        'report-generation:' || p_attempt_id::text || ':manual-v1'
    for update;

    if current_attempt.status = 'processing' then
        if found and existing_job.status in ('queued', 'running') then
            return query select
                p_attempt_id,
                true,
                0,
                'Evidence-backed report generation is already queued.'::text;
            return;
        end if;
        raise exception 'Finish the current answer processing before submitting the interview';
    end if;

    if current_attempt.status not in ('interviewing', 'failed') then
        raise exception 'Attempt is not ready for report generation';
    end if;

    select c.granted into latest_grant
    from public.consent_records as c
    where c.user_id = caller_id
      and c.consent_type = 'external_ai_processing'
      and (c.attempt_id = p_attempt_id or c.attempt_id is null)
    order by c.occurred_at desc, c.id desc
    limit 1;

    if coalesce(latest_grant, false) is not true then
        raise exception 'external_ai_processing consent is required';
    end if;

    if exists (
        select 1
        from public.answers as a
        where a.attempt_id = p_attempt_id
          and a.processing_status <> 'complete'
    ) then
        raise exception 'Every submitted answer must finish processing before the interview can be submitted';
    end if;

    select count(distinct a.id)::integer into evaluated_count
    from public.answers as a
    join public.answer_analyses as aa on aa.answer_id = a.id
    where a.attempt_id = p_attempt_id
      and aa.attempt_id = p_attempt_id
      and a.processing_status = 'complete';

    if evaluated_count < 6 then
        raise exception 'At least 6 evaluated answers are required before submitting the interview';
    end if;

    if existing_job.id is not null then
        if existing_job.status = 'failed' then
            if existing_job.attempt_count >= existing_job.max_attempts then
                raise exception 'Report generation reached its retry limit';
            end if;
            update public.processing_jobs as j
            set status = 'queued',
                stage = 'waiting_for_worker',
                error_code = null,
                error_detail = null,
                queued_at = now(),
                started_at = null,
                finished_at = null
            where j.id = existing_job.id;
            inserted_count := 1;
        elsif existing_job.status in ('queued', 'running') then
            inserted_count := 0;
        elsif existing_job.status = 'succeeded' then
            raise exception 'Report job state is inconsistent with the attempt';
        else
            raise exception 'The existing report job cannot be restarted';
        end if;
    else
        insert into public.processing_jobs (
            attempt_id,
            answer_id,
            job_type,
            status,
            stage,
            idempotency_key
        )
        values (
            p_attempt_id,
            null,
            'report_generation',
            'queued',
            'waiting_for_worker',
            'report-generation:' || p_attempt_id::text || ':manual-v1'
        )
        on conflict (idempotency_key) do nothing;
        get diagnostics inserted_count = row_count;
    end if;

    update public.attempts as a
    set status = 'processing'
    where a.id = p_attempt_id;

    return query select
        p_attempt_id,
        true,
        inserted_count,
        format(
            'Evidence-backed report generation queued from %s evaluated answers.',
            evaluated_count
        );
end;
$$;

revoke all on function public.request_attempt_report(uuid)
from public, anon;
grant execute on function public.request_attempt_report(uuid)
to authenticated, service_role;

commit;
