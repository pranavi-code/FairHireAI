-- Support both approved-role attempts and optional-JD-adapted attempts.
-- Migrations 0001 and 0002 have not yet been applied to a live project, but
-- this forward migration also keeps the change safe for a reviewed dev project.

alter table public.attempts
rename column jd_mapping_version to assessment_profile_version;

alter table public.attempts
add column assessment_profile_source text not null default 'job_description'
    check (assessment_profile_source in ('approved_role', 'job_description'));

alter table public.attempts
alter column assessment_profile_source drop default;

revoke all on function public.create_attempt_with_jd(
    uuid, text, text, text, jsonb, jsonb
) from authenticated;

create or replace function public.create_assessment_attempt(
    p_parent_attempt_id uuid,
    p_role_id text,
    p_profile_source text,
    p_profile_version text,
    p_role_template_version text,
    p_competency_weights jsonb,
    p_storage_key text,
    p_sha256 text,
    p_extracted_text text,
    p_mapping_result jsonb
)
returns setof public.attempts
language plpgsql
security invoker
set search_path = public
as $$
declare
    created_attempt public.attempts;
begin
    if auth.uid() is null then
        raise exception 'Authentication is required';
    end if;
    if p_role_id <> 'junior_backend_developer' then
        raise exception 'The first release supports only Junior Backend Developer';
    end if;
    if p_role_template_version <> '1.0.0' then
        raise exception 'Unsupported role-template version';
    end if;
    if p_profile_source not in ('approved_role', 'job_description') then
        raise exception 'Invalid assessment-profile source';
    end if;
    if p_parent_attempt_id is not null
       and not public.owns_attempt(p_parent_attempt_id) then
        raise exception 'Parent attempt is not owned by the authenticated user';
    end if;
    if jsonb_typeof(p_competency_weights) <> 'object'
       or abs((
           select coalesce(sum(value::numeric), 0)
           from jsonb_each_text(p_competency_weights)
       ) - 1.0) > 0.000001
       or (
           select count(*) from jsonb_object_keys(p_competency_weights)
       ) <> 6
       or exists (
           select 1
           from jsonb_object_keys(p_competency_weights) as keys(key)
           where key not in (
               'programming_fundamentals',
               'api_design',
               'database_reasoning',
               'debugging_problem_solving',
               'system_design_basics',
               'technical_communication'
           )
       ) then
        raise exception 'Invalid competency weights';
    end if;

    if p_profile_source = 'approved_role' then
        if p_profile_version <> 'approved-role-selection-v1'
           or num_nonnulls(
               p_storage_key,
               p_sha256,
               p_extracted_text,
               p_mapping_result
           ) <> 0 then
            raise exception 'Approved-role attempts cannot contain JD fields';
        end if;
        if p_competency_weights <> '{
            "programming_fundamentals": 0.20,
            "api_design": 0.20,
            "database_reasoning": 0.20,
            "debugging_problem_solving": 0.15,
            "system_design_basics": 0.15,
            "technical_communication": 0.10
        }'::jsonb then
            raise exception 'Approved-role attempts require base competency weights';
        end if;
    else
        if p_profile_version <> 'optional-jd-mapper-v1'
           or num_nonnulls(
               p_storage_key,
               p_sha256,
               p_extracted_text,
               p_mapping_result
           ) <> 4 then
            raise exception 'JD-based attempts require all JD fields';
        end if;
        if p_storage_key not like auth.uid()::text || '/%' then
            raise exception 'Storage key is not scoped to the authenticated user';
        end if;
        if p_sha256 !~ '^[a-f0-9]{64}$' then
            raise exception 'Invalid JD SHA-256';
        end if;
        if length(p_extracted_text) < 40 or length(p_extracted_text) > 50000 then
            raise exception 'Invalid extracted JD length';
        end if;
        if p_mapping_result ->> 'status' <> 'detected'
           or p_mapping_result ->> 'role_id' <> p_role_id
           or p_mapping_result ->> 'mapping_version' <> p_profile_version
           or p_mapping_result -> 'competency_weights' <> p_competency_weights then
            raise exception 'JD mapping does not match the assessment profile';
        end if;
    end if;

    insert into public.attempts (
        user_id,
        parent_attempt_id,
        role_id,
        role_template_version,
        assessment_profile_source,
        assessment_profile_version,
        status,
        competency_weights
    )
    values (
        auth.uid(),
        p_parent_attempt_id,
        p_role_id,
        p_role_template_version,
        p_profile_source,
        p_profile_version,
        'role_confirmed',
        p_competency_weights
    )
    returning * into created_attempt;

    if p_profile_source = 'job_description' then
        insert into public.job_descriptions (
            attempt_id,
            storage_key,
            sha256,
            extracted_text,
            mapping_result
        )
        values (
            created_attempt.id,
            p_storage_key,
            p_sha256,
            p_extracted_text,
            p_mapping_result
        );
    end if;

    return next created_attempt;
end;
$$;

revoke all on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) from public;
grant execute on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) to authenticated;
