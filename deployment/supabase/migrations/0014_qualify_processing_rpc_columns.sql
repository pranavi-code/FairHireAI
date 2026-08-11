-- PostgreSQL exposes RETURNS TABLE names as PL/pgSQL variables. Qualify every
-- table column so the output variable `attempt_id` cannot collide with an
-- unqualified answers/attempts column during live processing.

create or replace function public.enqueue_attempt_processing(p_attempt_id uuid)
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
    current_attempt public.attempts;
    answer_row public.answers;
    inserted_count integer := 0;
begin
    select a.* into current_attempt
    from public.attempts as a
    where a.id = p_attempt_id
      and a.user_id = (select auth.uid())
    for update;

    if not found then
        raise exception 'Attempt was not found';
    end if;
    if current_attempt.status not in ('interviewing', 'processing', 'failed') then
        raise exception 'Attempt is not ready for processing';
    end if;
    if not exists (
        select 1
        from public.answers as a
        where a.attempt_id = p_attempt_id
          and a.processing_status in ('pending', 'failed')
    ) then
        raise exception 'No submitted answer is waiting for processing';
    end if;

    for answer_row in
        select a.*
        from public.answers as a
        where a.attempt_id = p_attempt_id
          and a.processing_status in ('pending', 'failed')
        order by a.submitted_at
        for update
    loop
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
            answer_row.id,
            'answer_preprocessing',
            'queued',
            'waiting_for_worker',
            'answer-preprocessing:' || answer_row.id::text || ':v2'
        )
        on conflict (idempotency_key) do update
        set status = case
                when public.processing_jobs.status = 'failed' then 'queued'
                else public.processing_jobs.status
            end,
            stage = case
                when public.processing_jobs.status = 'failed'
                    then 'waiting_for_worker'
                else public.processing_jobs.stage
            end,
            error_code = case
                when public.processing_jobs.status = 'failed' then null
                else public.processing_jobs.error_code
            end,
            error_detail = case
                when public.processing_jobs.status = 'failed' then null
                else public.processing_jobs.error_detail
            end,
            queued_at = case
                when public.processing_jobs.status = 'failed' then now()
                else public.processing_jobs.queued_at
            end;

        if found then
            inserted_count := inserted_count + 1;
        end if;

        update public.answers as a
        set processing_status = 'queued'
        where a.id = answer_row.id
          and a.processing_status in ('pending', 'failed');
    end loop;

    if current_attempt.status in ('interviewing', 'failed') then
        update public.attempts as a
        set status = 'processing'
        where a.id = p_attempt_id;
    end if;

    return query
    select
        p_attempt_id,
        true,
        inserted_count,
        format('%s answer-processing job(s) queued.', inserted_count);
end;
$$;

revoke all on function public.enqueue_attempt_processing(uuid)
from public, anon;
grant execute on function public.enqueue_attempt_processing(uuid)
to authenticated, service_role;
