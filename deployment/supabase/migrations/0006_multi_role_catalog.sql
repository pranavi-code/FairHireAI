-- Replace the first-release single-role database lock with a versioned,
-- read-only catalog of reviewed role definitions. The API remains responsible
-- for rubric/question content; Postgres validates identity, version, and
-- competency-weight integrity at the durable attempt boundary.

create table public.role_templates (
    role_id text primary key check (role_id ~ '^[a-z][a-z0-9_]{2,79}$'),
    display_name text not null,
    template_version text not null,
    review_status text not null
        check (review_status in ('pending_faculty_review', 'faculty_approved')),
    base_competency_weights jsonb not null
        check (jsonb_typeof(base_competency_weights) = 'object'),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (role_id, template_version)
);

create trigger role_templates_set_updated_at
before update on public.role_templates
for each row execute function public.set_updated_at();

insert into public.role_templates (
    role_id, display_name, template_version, review_status,
    base_competency_weights
)
values
(
    'junior_backend_developer',
    'Junior Backend Developer',
    '1.0.0',
    'pending_faculty_review',
    '{"programming_fundamentals":0.20,"api_design":0.20,"database_reasoning":0.20,"debugging_problem_solving":0.15,"system_design_basics":0.15,"technical_communication":0.10}'::jsonb
),
(
    'junior_frontend_developer',
    'Junior Frontend Developer',
    '1.0.0',
    'pending_faculty_review',
    '{"programming_fundamentals":0.20,"frontend_engineering":0.25,"web_accessibility":0.15,"debugging_problem_solving":0.15,"system_design_basics":0.10,"technical_communication":0.15}'::jsonb
),
(
    'junior_full_stack_developer',
    'Junior Full-Stack Developer',
    '1.0.0',
    'pending_faculty_review',
    '{"programming_fundamentals":0.15,"frontend_engineering":0.20,"api_design":0.20,"database_reasoning":0.15,"debugging_problem_solving":0.15,"technical_communication":0.15}'::jsonb
),
(
    'junior_data_analyst',
    'Junior Data Analyst',
    '1.0.0',
    'pending_faculty_review',
    '{"data_analysis_sql":0.25,"statistics_reasoning":0.20,"data_visualization":0.20,"database_reasoning":0.15,"debugging_problem_solving":0.10,"technical_communication":0.10}'::jsonb
),
(
    'junior_machine_learning_engineer',
    'Junior Machine Learning Engineer',
    '1.0.0',
    'pending_faculty_review',
    '{"programming_fundamentals":0.15,"ml_fundamentals":0.20,"model_evaluation":0.20,"ml_engineering":0.20,"debugging_problem_solving":0.15,"technical_communication":0.10}'::jsonb
),
(
    'junior_devops_cloud_engineer',
    'Junior DevOps / Cloud Engineer',
    '1.0.0',
    'pending_faculty_review',
    '{"cloud_platform":0.20,"cicd_automation":0.20,"observability_reliability":0.20,"system_design_basics":0.15,"debugging_problem_solving":0.15,"technical_communication":0.10}'::jsonb
);

alter table public.role_templates enable row level security;
create policy role_templates_authenticated_read
on public.role_templates for select to authenticated
using (is_active);

revoke all privileges on table public.role_templates from anon;
grant select on table public.role_templates to authenticated;
grant select, insert, update, delete on table public.role_templates to service_role;

alter table public.attempts
drop constraint attempts_role_id_check;

alter table public.attempts
add constraint attempts_role_id_format
check (role_id ~ '^[a-z][a-z0-9_]{2,79}$');

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
security definer
set search_path = public
as $$
declare
    created_attempt public.attempts;
    selected_role public.role_templates;
begin
    if auth.uid() is null then
        raise exception 'Authentication is required';
    end if;

    select * into selected_role
    from public.role_templates
    where role_id = p_role_id
      and template_version = p_role_template_version
      and is_active;

    if not found then
        raise exception 'Unsupported role or role-template version';
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
           from jsonb_object_keys(p_competency_weights) as supplied(key)
           where not selected_role.base_competency_weights ? supplied.key
       )
       or exists (
           select 1
           from jsonb_object_keys(selected_role.base_competency_weights) as expected(key)
           where not p_competency_weights ? expected.key
       ) then
        raise exception 'Invalid competency weights for the selected role';
    end if;

    if p_profile_source = 'approved_role' then
        if p_profile_version <> 'approved-role-selection-v2'
           or num_nonnulls(
               p_storage_key, p_sha256, p_extracted_text, p_mapping_result
           ) <> 0 then
            raise exception 'Approved-role attempts cannot contain JD fields';
        end if;
        if p_competency_weights <> selected_role.base_competency_weights then
            raise exception 'Approved-role attempts require base competency weights';
        end if;
    else
        if p_profile_version <> 'optional-jd-mapper-v2'
           or num_nonnulls(
               p_storage_key, p_sha256, p_extracted_text, p_mapping_result
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
           or p_mapping_result ->> 'role_template_version' <> p_role_template_version
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
            attempt_id, storage_key, sha256, extracted_text, mapping_result
        )
        values (
            created_attempt.id, p_storage_key, p_sha256,
            p_extracted_text, p_mapping_result
        );
    end if;

    return next created_attempt;
end;
$$;

revoke all on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) from public, anon;
grant execute on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) to authenticated, service_role;
