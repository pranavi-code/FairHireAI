-- Validated authenticated write paths for the persistent student journey.

create or replace function public.attach_resume_evidence(
    p_attempt_id uuid,
    p_storage_key text,
    p_sha256 text,
    p_mime_type text,
    p_extractor_name text,
    p_extractor_version text,
    p_claims jsonb
)
returns table (
    resume_document_id uuid,
    attempt_id uuid,
    claim_count integer,
    extraction_status text
)
language plpgsql
security definer
set search_path = public
as $$
declare
    created_document public.resume_documents;
    claim jsonb;
begin
    if not public.owns_attempt(p_attempt_id) then
        raise exception 'Attempt was not found';
    end if;
    if p_storage_key not like auth.uid()::text || '/%' then
        raise exception 'Storage key is not scoped to the authenticated user';
    end if;
    if p_sha256 !~ '^[a-f0-9]{64}$' then
        raise exception 'Invalid resume SHA-256';
    end if;
    if jsonb_typeof(p_claims) <> 'array'
       or jsonb_array_length(p_claims) > 300 then
        raise exception 'Resume claims must be an array with at most 300 entries';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(p_claims) item
        group by item ->> 'id'
        having count(*) > 1
    ) then
        raise exception 'Resume claim identifiers must be unique';
    end if;

    delete from public.resume_documents where attempt_id = p_attempt_id;
    insert into public.resume_documents (
        attempt_id, storage_key, sha256, mime_type, extractor_name,
        extractor_version, extraction_status
    )
    values (
        p_attempt_id, p_storage_key, p_sha256, p_mime_type, p_extractor_name,
        p_extractor_version, 'complete'
    )
    returning * into created_document;

    for claim in select value from jsonb_array_elements(p_claims)
    loop
        if claim ->> 'id' !~ '^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$'
           or claim ->> 'claim_type' not in (
               'skill', 'project', 'internship', 'certification', 'achievement'
           )
           or length(claim ->> 'normalized_text') < 2
           or (claim ->> 'source_start_character')::integer < 0
           or (claim ->> 'source_end_character')::integer
                <= (claim ->> 'source_start_character')::integer
           or (claim ->> 'confidence')::double precision not between 0 and 1
        then
            raise exception 'Invalid resume claim';
        end if;
        insert into public.resume_claims (
            id, resume_document_id, attempt_id, claim_type, normalized_text,
            source_page, source_start_character, source_end_character,
            source_text, confidence, normalized_skills
        )
        values (
            claim ->> 'id',
            created_document.id,
            p_attempt_id,
            claim ->> 'claim_type',
            claim ->> 'normalized_text',
            nullif(claim ->> 'source_page', '')::integer,
            (claim ->> 'source_start_character')::integer,
            (claim ->> 'source_end_character')::integer,
            claim ->> 'source_text',
            (claim ->> 'confidence')::double precision,
            coalesce(claim -> 'normalized_skills', '[]'::jsonb)
        );
    end loop;

    return query select
        created_document.id,
        p_attempt_id,
        jsonb_array_length(p_claims),
        'complete'::text;
end;
$$;

create or replace function public.record_interview_question(
    p_attempt_id uuid,
    p_question_template_id text,
    p_competency_id text,
    p_prompt_snapshot text,
    p_is_follow_up boolean,
    p_selection_reason text
)
returns setof public.interview_questions
language plpgsql
security definer
set search_path = public
as $$
declare
    created_question public.interview_questions;
    next_sequence integer;
    attempt_status text;
begin
    if not public.owns_attempt(p_attempt_id) then
        raise exception 'Attempt was not found';
    end if;
    select status into attempt_status from public.attempts where id = p_attempt_id;
    if attempt_status not in ('role_confirmed', 'interviewing') then
        raise exception 'Attempt is not ready for interview questions';
    end if;
    if length(p_prompt_snapshot) < 10 or length(p_prompt_snapshot) > 4000 then
        raise exception 'Invalid question prompt';
    end if;
    if exists (
        select 1 from public.interview_questions q
        join public.answers a on a.question_id = q.id
        where q.attempt_id = p_attempt_id
          and a.processing_status <> 'complete'
    ) then
        raise exception 'A submitted answer is still awaiting evidence processing';
    end if;
    select coalesce(max(sequence_number), 0) + 1 into next_sequence
    from public.interview_questions where attempt_id = p_attempt_id;
    if next_sequence > 12 then
        raise exception 'Maximum interview question count reached';
    end if;
    insert into public.interview_questions (
        attempt_id, question_template_id, competency_id, prompt_snapshot,
        is_follow_up, sequence_number, selection_reason
    )
    values (
        p_attempt_id, p_question_template_id, p_competency_id,
        p_prompt_snapshot, p_is_follow_up, next_sequence, p_selection_reason
    )
    returning * into created_question;
    return next created_question;
end;
$$;

create or replace function public.submit_interview_answer(
    p_attempt_id uuid,
    p_question_id uuid,
    p_video_storage_key text,
    p_video_sha256 text,
    p_duration_seconds double precision
)
returns setof public.answers
language plpgsql
security definer
set search_path = public
as $$
declare
    created_answer public.answers;
begin
    if not public.owns_attempt(p_attempt_id) then
        raise exception 'Attempt was not found';
    end if;
    if not exists (
        select 1 from public.interview_questions
        where id = p_question_id and attempt_id = p_attempt_id
    ) then
        raise exception 'Question does not belong to the attempt';
    end if;
    if p_video_storage_key not like auth.uid()::text || '/%' then
        raise exception 'Video storage key is not scoped to the authenticated user';
    end if;
    if p_video_sha256 !~ '^[a-f0-9]{64}$' then
        raise exception 'Invalid video SHA-256';
    end if;
    if p_duration_seconds < 5 or p_duration_seconds > 600 then
        raise exception 'Answer duration must be between 5 and 600 seconds';
    end if;
    insert into public.answers (
        attempt_id, question_id, private_video_storage_key,
        video_sha256, duration_seconds, processing_status
    )
    values (
        p_attempt_id, p_question_id, p_video_storage_key,
        p_video_sha256, p_duration_seconds, 'pending'
    )
    returning * into created_answer;
    return next created_answer;
end;
$$;

create or replace function public.create_reattempt(p_parent_attempt_id uuid)
returns setof public.attempts
language plpgsql
security definer
set search_path = public
as $$
declare
    parent public.attempts;
    created_attempt public.attempts;
    parent_jd public.job_descriptions;
begin
    select * into parent from public.attempts
    where id = p_parent_attempt_id and user_id = auth.uid();
    if not found then
        raise exception 'Parent attempt was not found';
    end if;
    if parent.status <> 'completed' then
        raise exception 'Only completed attempts can be reattempted';
    end if;
    insert into public.attempts (
        user_id, parent_attempt_id, role_id, role_template_version,
        assessment_profile_source, assessment_profile_version,
        status, competency_weights
    )
    values (
        auth.uid(), parent.id, parent.role_id, parent.role_template_version,
        parent.assessment_profile_source, parent.assessment_profile_version,
        'role_confirmed', parent.competency_weights
    )
    returning * into created_attempt;
    if parent.assessment_profile_source = 'job_description' then
        select * into parent_jd from public.job_descriptions
        where attempt_id = parent.id;
        insert into public.job_descriptions (
            attempt_id, storage_key, sha256, extracted_text, mapping_result
        )
        values (
            created_attempt.id, parent_jd.storage_key, parent_jd.sha256,
            parent_jd.extracted_text, parent_jd.mapping_result
        );
    end if;
    return next created_attempt;
end;
$$;

revoke all on function public.attach_resume_evidence(
    uuid, text, text, text, text, text, jsonb
) from public, anon;
grant execute on function public.attach_resume_evidence(
    uuid, text, text, text, text, text, jsonb
) to authenticated, service_role;

revoke all on function public.record_interview_question(
    uuid, text, text, text, boolean, text
) from public, anon;
grant execute on function public.record_interview_question(
    uuid, text, text, text, boolean, text
) to authenticated, service_role;

revoke all on function public.submit_interview_answer(
    uuid, uuid, text, text, double precision
) from public, anon;
grant execute on function public.submit_interview_answer(
    uuid, uuid, text, text, double precision
) to authenticated, service_role;

revoke all on function public.create_reattempt(uuid) from public, anon;
grant execute on function public.create_reattempt(uuid)
to authenticated, service_role;
