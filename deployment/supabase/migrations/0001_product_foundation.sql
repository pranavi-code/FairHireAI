-- RoleReady AI / FairHireAI product foundation.
-- Apply through the Supabase migration workflow; never execute against an
-- unreviewed production project.

create extension if not exists pgcrypto;

create table public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    parent_attempt_id uuid references public.attempts(id) on delete set null,
    role_id text not null check (role_id = 'junior_backend_developer'),
    role_template_version text not null,
    jd_mapping_version text not null,
    status text not null default 'draft'
        check (status in (
            'draft', 'role_confirmed', 'interviewing', 'processing',
            'completed', 'failed', 'cancelled'
        )),
    competency_weights jsonb not null,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint competency_weights_is_object
        check (jsonb_typeof(competency_weights) = 'object')
);

create table public.job_descriptions (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null unique
        references public.attempts(id) on delete cascade,
    storage_key text not null,
    sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
    extracted_text text,
    mapping_result jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.resume_documents (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null unique
        references public.attempts(id) on delete cascade,
    storage_key text not null,
    sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
    mime_type text not null,
    extractor_name text,
    extractor_version text,
    extraction_status text not null default 'pending'
        check (extraction_status in ('pending', 'running', 'complete', 'failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.resume_claims (
    id text primary key,
    resume_document_id uuid not null
        references public.resume_documents(id) on delete cascade,
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    claim_type text not null
        check (claim_type in (
            'skill', 'project', 'internship', 'certification', 'achievement'
        )),
    normalized_text text not null,
    source_page integer check (source_page is null or source_page >= 1),
    source_start_character integer not null check (source_start_character >= 0),
    source_end_character integer not null,
    source_text text not null,
    confidence double precision not null check (confidence between 0 and 1),
    normalized_skills jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    constraint resume_claim_offsets
        check (source_end_character > source_start_character)
);

create table public.interview_questions (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    question_template_id text not null,
    competency_id text not null,
    prompt_snapshot text not null,
    is_follow_up boolean not null default false,
    sequence_number integer not null check (sequence_number between 1 and 12),
    selection_reason text not null,
    created_at timestamptz not null default now(),
    unique (attempt_id, sequence_number),
    unique (attempt_id, question_template_id)
);

create table public.answers (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    question_id uuid not null unique
        references public.interview_questions(id) on delete cascade,
    private_video_storage_key text not null,
    video_sha256 text not null check (video_sha256 ~ '^[a-f0-9]{64}$'),
    duration_seconds double precision
        check (duration_seconds is null or duration_seconds > 0),
    processing_status text not null default 'pending'
        check (processing_status in (
            'pending', 'queued', 'running', 'complete', 'failed'
        )),
    submitted_at timestamptz not null default now(),
    processed_at timestamptz
);

create table public.processing_jobs (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    answer_id uuid references public.answers(id) on delete cascade,
    job_type text not null
        check (job_type in (
            'resume_extraction', 'answer_preprocessing', 'base_model_inference',
            'graph_update', 'report_generation'
        )),
    status text not null default 'queued'
        check (status in (
            'queued', 'running', 'succeeded', 'failed', 'cancelled'
        )),
    stage text,
    idempotency_key text not null unique,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 10),
    error_code text,
    error_detail text,
    queued_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.evidence_nodes (
    id text primary key,
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    node_type text not null,
    source text not null,
    confidence double precision not null check (confidence between 0 and 1),
    visibility text not null
        check (visibility in ('private', 'student', 'reviewer', 'system')),
    normalized_text text,
    raw_reference text,
    attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table public.evidence_edges (
    id text primary key,
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    edge_type text not null,
    source_node_id text not null
        references public.evidence_nodes(id) on delete cascade,
    target_node_id text not null
        references public.evidence_nodes(id) on delete cascade,
    source text not null,
    confidence double precision not null check (confidence between 0 and 1),
    visibility text not null
        check (visibility in ('private', 'student', 'reviewer', 'system')),
    normalized_text text,
    raw_reference text,
    attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint non_self_edge
        check (source_node_id <> target_node_id or edge_type = 'improves_over')
);

create table public.scorecards (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null unique
        references public.attempts(id) on delete cascade,
    formula_version text not null,
    model_run_name text not null,
    model_checkpoint_sha256 text not null
        check (model_checkpoint_sha256 ~ '^[a-f0-9]{64}$'),
    competency_scores jsonb not null,
    technical_readiness double precision not null
        check (technical_readiness between 0 and 1),
    communication_clarity double precision not null
        check (communication_clarity between 0 and 1),
    interview_response_quality double precision not null
        check (interview_response_quality between 0 and 1),
    placement_readiness double precision
        check (placement_readiness is null or placement_readiness between 0 and 1),
    overall_evidence_confidence double precision not null
        check (overall_evidence_confidence between 0 and 1),
    sufficient_evidence boolean not null,
    insufficiency_reasons jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create table public.learning_resources (
    id text primary key,
    title text not null,
    canonical_url text not null,
    source_organization text not null,
    competency_ids jsonb not null,
    difficulty text not null check (difficulty in ('beginner', 'intermediate')),
    estimated_minutes integer not null check (estimated_minutes > 0),
    description text not null,
    reviewer_status text not null default 'pending'
        check (reviewer_status in ('pending', 'approved', 'retired')),
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.roadmap_items (
    id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null references public.attempts(id) on delete cascade,
    skill_gap_node_id text not null
        references public.evidence_nodes(id) on delete cascade,
    resource_id text not null
        references public.learning_resources(id) on delete restrict,
    priority integer not null check (priority between 1 and 5),
    rationale text not null,
    status text not null default 'recommended'
        check (status in ('recommended', 'started', 'completed', 'dismissed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (attempt_id, skill_gap_node_id, resource_id)
);

create table public.progress_metrics (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    earlier_attempt_id uuid not null
        references public.attempts(id) on delete cascade,
    later_attempt_id uuid not null
        references public.attempts(id) on delete cascade,
    metric_version text not null,
    score_deltas jsonb not null,
    created_at timestamptz not null default now(),
    unique (earlier_attempt_id, later_attempt_id),
    constraint attempts_are_different check (earlier_attempt_id <> later_attempt_id)
);

create index attempts_user_created_idx
    on public.attempts (user_id, created_at desc);
create index resume_claims_attempt_idx on public.resume_claims (attempt_id);
create index questions_attempt_sequence_idx
    on public.interview_questions (attempt_id, sequence_number);
create index answers_attempt_idx on public.answers (attempt_id);
create index jobs_status_queued_idx on public.processing_jobs (status, queued_at);
create index evidence_nodes_attempt_type_idx
    on public.evidence_nodes (attempt_id, node_type);
create index evidence_edges_attempt_type_idx
    on public.evidence_edges (attempt_id, edge_type);
create index roadmap_attempt_priority_idx
    on public.roadmap_items (attempt_id, priority);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger profiles_set_updated_at before update on public.profiles
for each row execute function public.set_updated_at();
create trigger attempts_set_updated_at before update on public.attempts
for each row execute function public.set_updated_at();
create trigger jd_set_updated_at before update on public.job_descriptions
for each row execute function public.set_updated_at();
create trigger resume_set_updated_at before update on public.resume_documents
for each row execute function public.set_updated_at();
create trigger jobs_set_updated_at before update on public.processing_jobs
for each row execute function public.set_updated_at();
create trigger resources_set_updated_at before update on public.learning_resources
for each row execute function public.set_updated_at();
create trigger roadmap_set_updated_at before update on public.roadmap_items
for each row execute function public.set_updated_at();

create or replace function public.owns_attempt(target_attempt_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.attempts
        where id = target_attempt_id
          and user_id = auth.uid()
    );
$$;

revoke all on function public.owns_attempt(uuid) from public;
grant execute on function public.owns_attempt(uuid) to authenticated;

alter table public.profiles enable row level security;
alter table public.attempts enable row level security;
alter table public.job_descriptions enable row level security;
alter table public.resume_documents enable row level security;
alter table public.resume_claims enable row level security;
alter table public.interview_questions enable row level security;
alter table public.answers enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.evidence_nodes enable row level security;
alter table public.evidence_edges enable row level security;
alter table public.scorecards enable row level security;
alter table public.learning_resources enable row level security;
alter table public.roadmap_items enable row level security;
alter table public.progress_metrics enable row level security;

create policy profiles_owner_all on public.profiles
for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create policy attempts_owner_select on public.attempts
for select to authenticated using (user_id = auth.uid());
create policy attempts_owner_insert on public.attempts
for insert to authenticated with check (user_id = auth.uid());
create policy attempts_owner_update on public.attempts
for update to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());
create policy attempts_owner_delete on public.attempts
for delete to authenticated using (user_id = auth.uid());

create policy jd_owner_all on public.job_descriptions
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy resume_documents_owner_all on public.resume_documents
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy resume_claims_owner_all on public.resume_claims
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy questions_owner_all on public.interview_questions
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy answers_owner_all on public.answers
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy jobs_owner_select on public.processing_jobs
for select to authenticated using (public.owns_attempt(attempt_id));
create policy nodes_owner_all on public.evidence_nodes
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy edges_owner_all on public.evidence_edges
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy scorecards_owner_select on public.scorecards
for select to authenticated using (public.owns_attempt(attempt_id));
create policy roadmap_owner_all on public.roadmap_items
for all to authenticated
using (public.owns_attempt(attempt_id))
with check (public.owns_attempt(attempt_id));
create policy resources_approved_read on public.learning_resources
for select to authenticated using (reviewer_status = 'approved');
create policy progress_owner_select on public.progress_metrics
for select to authenticated using (user_id = auth.uid());

-- Atomically create the attempt and its required JD. The private storage key
-- must remain inside the authenticated user's folder.
create or replace function public.create_attempt_with_jd(
    p_parent_attempt_id uuid,
    p_storage_key text,
    p_sha256 text,
    p_extracted_text text,
    p_mapping_result jsonb,
    p_competency_weights jsonb
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
       or p_mapping_result ->> 'role_id' <> 'junior_backend_developer' then
        raise exception 'A supported detected role is required';
    end if;
    if jsonb_typeof(p_competency_weights) <> 'object' then
        raise exception 'Competency weights must be an object';
    end if;
    if p_parent_attempt_id is not null
       and not public.owns_attempt(p_parent_attempt_id) then
        raise exception 'Parent attempt is not owned by the authenticated user';
    end if;

    insert into public.attempts (
        user_id,
        parent_attempt_id,
        role_id,
        role_template_version,
        jd_mapping_version,
        status,
        competency_weights
    )
    values (
        auth.uid(),
        p_parent_attempt_id,
        'junior_backend_developer',
        p_mapping_result ->> 'role_template_version',
        p_mapping_result ->> 'mapping_version',
        'role_confirmed',
        p_competency_weights
    )
    returning * into created_attempt;

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

    return next created_attempt;
end;
$$;

revoke all on function public.create_attempt_with_jd(
    uuid, text, text, text, jsonb, jsonb
) from public;
grant execute on function public.create_attempt_with_jd(
    uuid, text, text, text, jsonb, jsonb
) to authenticated;

-- Serialize lifecycle changes in Postgres so concurrent API calls cannot skip
-- required stages.
create or replace function public.transition_attempt(
    p_attempt_id uuid,
    p_next_status text
)
returns setof public.attempts
language plpgsql
security invoker
set search_path = public
as $$
declare
    current_attempt public.attempts;
    transition_allowed boolean := false;
begin
    select * into current_attempt
    from public.attempts
    where id = p_attempt_id and user_id = auth.uid()
    for update;

    if not found then
        raise exception 'Attempt was not found';
    end if;

    transition_allowed := case current_attempt.status
        when 'draft' then p_next_status in ('role_confirmed', 'cancelled')
        when 'role_confirmed' then p_next_status in ('interviewing', 'cancelled')
        when 'interviewing' then p_next_status in ('processing', 'failed', 'cancelled')
        when 'processing' then p_next_status in ('completed', 'failed', 'cancelled')
        when 'failed' then p_next_status in ('processing', 'cancelled')
        else false
    end;

    if not transition_allowed then
        raise exception 'Invalid attempt transition: % -> %',
            current_attempt.status, p_next_status;
    end if;

    update public.attempts
    set status = p_next_status,
        started_at = case
            when p_next_status = 'interviewing'
                then coalesce(started_at, now())
            else started_at
        end,
        completed_at = case
            when p_next_status = 'completed' then now()
            else null
        end
    where id = p_attempt_id
    returning * into current_attempt;

    return next current_attempt;
end;
$$;

revoke all on function public.transition_attempt(uuid, text) from public;
grant execute on function public.transition_attempt(uuid, text) to authenticated;
