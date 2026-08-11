-- Complete the durable answer-processing path. All worker-only functions are
-- SECURITY INVOKER and executable only by service_role.

alter table public.consent_records
    drop constraint if exists consent_records_consent_type_check;

alter table public.consent_records
    add constraint consent_records_consent_type_check check (
        consent_type in (
            'privacy_notice',
            'resume_processing',
            'interview_recording',
            'external_ai_processing',
            'research_evaluation'
        )
    );

alter table public.deletion_requests
    drop constraint if exists deletion_requests_attempt_id_fkey,
    drop constraint if exists attempt_scope_requires_attempt;

alter table public.deletion_requests
    add constraint deletion_requests_attempt_id_fkey
        foreign key (attempt_id) references public.attempts(id) on delete set null,
    add constraint attempt_scope_requires_attempt check (
        scope <> 'attempt' or attempt_id is not null or status = 'completed'
    );

alter table public.interview_questions
    add column question_package_id text
        references public.question_packages(id) on delete restrict,
    add column question_package_version text,
    add column expected_concepts_snapshot jsonb not null default '[]'::jsonb,
    add column rubric_snapshot jsonb not null default '{}'::jsonb,
    add column source_mapping_snapshot jsonb not null default '{}'::jsonb,
    add column model_id text,
    add column prompt_version text,
    add constraint question_expected_concepts_array check (
        jsonb_typeof(expected_concepts_snapshot) = 'array'
    ),
    add constraint question_rubric_object check (
        jsonb_typeof(rubric_snapshot) = 'object'
    ),
    add constraint question_source_mapping_object check (
        jsonb_typeof(source_mapping_snapshot) = 'object'
    );

create index interview_questions_package_idx
    on public.interview_questions (question_package_id);

create table public.answer_analyses (
    id uuid primary key default gen_random_uuid(),
    answer_id uuid not null unique references public.answers(id) on delete cascade,
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    transcript jsonb not null,
    transcript_text text not null,
    transcript_confidence double precision not null check (
        transcript_confidence between 0 and 1
    ),
    delivery_metrics jsonb not null,
    technical_evaluation jsonb not null,
    base_multimodal_interview_signal double precision not null check (
        base_multimodal_interview_signal between 0 and 1
    ),
    signal_quality double precision not null check (signal_quality between 0 and 1),
    model_run_name text not null,
    model_checkpoint_sha256 text not null check (
        model_checkpoint_sha256 ~ '^[a-f0-9]{64}$'
    ),
    aligned_artifact_storage_key text not null,
    aligned_artifact_sha256 text not null check (
        aligned_artifact_sha256 ~ '^[a-f0-9]{64}$'
    ),
    evaluator_model_id text not null,
    evaluator_prompt_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index answer_analyses_attempt_idx on public.answer_analyses (attempt_id);
alter table public.answer_analyses enable row level security;

create policy answer_analyses_owner_select on public.answer_analyses
for select to authenticated
using ((select public.owns_attempt(attempt_id)));

grant select on table public.answer_analyses to authenticated;
grant all on table public.answer_analyses to service_role;

insert into storage.buckets (id, name, public, file_size_limit)
values (
    'roleready-processing-artifacts',
    'roleready-processing-artifacts',
    false,
    52428800
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit;

create policy processing_artifacts_owner_select on storage.objects
for select to authenticated
using (
    bucket_id = 'roleready-processing-artifacts'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop function if exists public.record_interview_question(
    uuid, text, text, text, boolean, text
);

create function public.record_interview_question(
    p_attempt_id uuid,
    p_question_template_id text,
    p_competency_id text,
    p_prompt_snapshot text,
    p_is_follow_up boolean,
    p_selection_reason text,
    p_question_package_id text default null,
    p_model_id text default null,
    p_prompt_version text default null
)
returns setof public.interview_questions
language plpgsql
security definer
set search_path = ''
as $$
declare
    created_question public.interview_questions;
    selected_package public.question_packages;
    next_sequence integer;
    attempt_status text;
begin
    if not public.owns_attempt(p_attempt_id) then
        raise exception 'Attempt was not found';
    end if;
    select status into attempt_status
    from public.attempts
    where id = p_attempt_id;
    if attempt_status not in ('role_confirmed', 'interviewing') then
        raise exception 'Attempt is not ready for interview questions';
    end if;
    if length(p_prompt_snapshot) < 10 or length(p_prompt_snapshot) > 4000 then
        raise exception 'Invalid question prompt';
    end if;
    if exists (
        select 1
        from public.interview_questions q
        join public.answers a on a.question_id = q.id
        where q.attempt_id = p_attempt_id
          and a.processing_status <> 'complete'
    ) then
        raise exception 'A submitted answer is still awaiting evidence processing';
    end if;

    if p_question_package_id is not null then
        select * into selected_package
        from public.question_packages
        where id = p_question_package_id
          and competency_id = p_competency_id
          and validation_status in (
              'generated_validated_for_practice',
              'faculty_reviewed_research_set'
          );
        if not found then
            raise exception 'Question package is not validated for practice';
        end if;
    end if;

    select coalesce(max(sequence_number), 0) + 1 into next_sequence
    from public.interview_questions
    where attempt_id = p_attempt_id;
    if next_sequence > 12 then
        raise exception 'Maximum interview question count reached';
    end if;

    insert into public.interview_questions (
        attempt_id,
        question_template_id,
        competency_id,
        prompt_snapshot,
        is_follow_up,
        sequence_number,
        selection_reason,
        question_package_id,
        question_package_version,
        expected_concepts_snapshot,
        rubric_snapshot,
        source_mapping_snapshot,
        model_id,
        prompt_version
    )
    values (
        p_attempt_id,
        p_question_template_id,
        p_competency_id,
        p_prompt_snapshot,
        p_is_follow_up,
        next_sequence,
        p_selection_reason,
        p_question_package_id,
        selected_package.version,
        coalesce(selected_package.expected_concepts, '[]'::jsonb),
        coalesce(selected_package.rubric, '{}'::jsonb),
        coalesce(selected_package.source_to_concept_mapping, '{}'::jsonb),
        coalesce(p_model_id, selected_package.model_id),
        coalesce(p_prompt_version, selected_package.prompt_version)
    )
    returning * into created_question;
    return next created_question;
end;
$$;

revoke all on function public.record_interview_question(
    uuid, text, text, text, boolean, text, text, text, text
) from public, anon;
grant execute on function public.record_interview_question(
    uuid, text, text, text, boolean, text, text, text, text
) to authenticated, service_role;

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
    select * into current_attempt
    from public.attempts
    where id = p_attempt_id and user_id = (select auth.uid())
    for update;

    if not found then
        raise exception 'Attempt was not found';
    end if;
    if current_attempt.status not in ('interviewing', 'processing', 'failed') then
        raise exception 'Attempt is not ready for processing';
    end if;
    if not exists (
        select 1
        from public.answers
        where attempt_id = p_attempt_id
          and processing_status in ('pending', 'failed')
    ) then
        raise exception 'No submitted answer is waiting for processing';
    end if;

    for answer_row in
        select *
        from public.answers
        where attempt_id = p_attempt_id
          and processing_status in ('pending', 'failed')
        order by submitted_at
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

        update public.answers
        set processing_status = 'queued'
        where id = answer_row.id
          and processing_status in ('pending', 'failed');
    end loop;

    if current_attempt.status in ('interviewing', 'failed') then
        update public.attempts
        set status = 'processing'
        where id = p_attempt_id;
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

create or replace function public.claim_next_processing_job(p_worker_id text)
returns setof public.processing_jobs
language plpgsql
security invoker
set search_path = ''
as $$
declare
    claimed public.processing_jobs;
begin
    if length(trim(p_worker_id)) < 3 then
        raise exception 'A worker identifier is required';
    end if;

    select * into claimed
    from public.processing_jobs
    where status = 'queued'
      and attempt_count < max_attempts
    order by queued_at, id
    for update skip locked
    limit 1;

    if not found then
        return;
    end if;

    update public.processing_jobs
    set status = 'running',
        stage = 'claimed:' || left(p_worker_id, 80),
        attempt_count = attempt_count + 1,
        started_at = now(),
        finished_at = null,
        error_code = null,
        error_detail = null
    where id = claimed.id
    returning * into claimed;

    if claimed.answer_id is not null then
        update public.answers
        set processing_status = 'running'
        where id = claimed.answer_id;
    end if;

    return next claimed;
end;
$$;

revoke all on function public.claim_next_processing_job(text)
from public, anon, authenticated;
grant execute on function public.claim_next_processing_job(text) to service_role;

create or replace function public.claim_next_deletion_request(p_worker_id text)
returns setof public.deletion_requests
language plpgsql
security invoker
set search_path = ''
as $$
declare
    claimed public.deletion_requests;
begin
    if length(trim(p_worker_id)) < 3 then
        raise exception 'A worker identifier is required';
    end if;
    select * into claimed
    from public.deletion_requests
    where status = 'requested'
    order by requested_at, id
    for update skip locked
    limit 1;
    if not found then
        return;
    end if;
    update public.deletion_requests
    set status = 'processing',
        error_code = null
    where id = claimed.id
    returning * into claimed;
    return next claimed;
end;
$$;

revoke all on function public.claim_next_deletion_request(text)
from public, anon, authenticated;
grant execute on function public.claim_next_deletion_request(text) to service_role;
