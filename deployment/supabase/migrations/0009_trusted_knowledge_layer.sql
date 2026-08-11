-- Trusted offline knowledge layer for graph-guided contextual hybrid RAG.
-- This migration stores provenance, review gates, full-text indexes, optional
-- local embeddings, versioned question packages, and reviewed resources.

create extension if not exists vector with schema extensions;

create table public.knowledge_sources (
    id text primary key check (id ~ '^SRC-[0-9]{3,}$'),
    title text not null,
    canonical_url text not null unique check (canonical_url ~ '^https://'),
    publisher text not null,
    source_type text not null check (
        source_type in (
            'occupation_taxonomy', 'curriculum', 'technical_documentation',
            'research', 'dataset', 'software', 'learning_resource'
        )
    ),
    license_id text not null,
    license_url text check (license_url is null or license_url ~ '^https://'),
    content_policy text not null check (
        content_policy in (
            'metadata_only', 'reviewer_summary', 'permitted_excerpt',
            'open_content'
        )
    ),
    permitted_use text not null,
    attribution_text text not null,
    version_label text,
    accessed_on date not null,
    retrieval_enabled boolean not null default false,
    review_status text not null default 'pending' check (
        review_status in ('pending', 'approved', 'retired')
    ),
    metadata jsonb not null default '{}'::jsonb
        check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.source_documents (
    id text primary key check (id ~ '^[A-Z0-9][A-Z0-9:_-]{2,119}$'),
    source_id text not null
        references public.knowledge_sources(id) on delete restrict,
    title text not null,
    canonical_url text not null check (canonical_url ~ '^https://'),
    version_label text,
    document_type text not null check (
        document_type in (
            'taxonomy_extract', 'curriculum_area', 'official_page',
            'reviewer_summary', 'team_authored'
        )
    ),
    rights_basis text not null,
    content_sha256 text check (
        content_sha256 is null or content_sha256 ~ '^[a-f0-9]{64}$'
    ),
    ingest_status text not null default 'pending' check (
        ingest_status in ('pending', 'ready', 'rejected')
    ),
    review_status text not null default 'pending' check (
        review_status in ('pending', 'approved', 'retired')
    ),
    retrieved_at timestamptz,
    metadata jsonb not null default '{}'::jsonb
        check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, canonical_url, version_label)
);

create table public.knowledge_chunks (
    id bigint generated always as identity primary key,
    document_id text not null
        references public.source_documents(id) on delete cascade,
    chunk_key text not null check (chunk_key ~ '^[a-z0-9][a-z0-9:_-]{2,119}$'),
    context_prefix text not null,
    content text not null check (length(content) between 20 and 12000),
    chunk_type text not null check (
        chunk_type in ('official_excerpt', 'reviewer_summary', 'team_authored')
    ),
    competency_ids text[] not null default '{}',
    skill_terms text[] not null default '{}',
    technologies text[] not null default '{}',
    seniority text not null default 'all' check (
        seniority in ('intern', 'junior', 'entry_level', 'all')
    ),
    difficulty text not null default 'beginner' check (
        difficulty in ('beginner', 'intermediate')
    ),
    content_sha256 text not null check (content_sha256 ~ '^[a-f0-9]{64}$'),
    embedding extensions.vector(384),
    embedding_model text,
    search_vector tsvector generated always as (
        to_tsvector(
            'english'::regconfig,
            coalesce(context_prefix, '') || ' ' || coalesce(content, '')
        )
    ) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (document_id, chunk_key),
    check (
        (embedding is null and embedding_model is null)
        or (embedding is not null and embedding_model is not null)
    )
);

create table public.skill_concepts (
    id text primary key check (id ~ '^[a-z][a-z0-9_]{2,79}$'),
    preferred_label text not null,
    aliases text[] not null default '{}',
    description text not null,
    concept_type text not null check (
        concept_type in ('skill', 'knowledge', 'technology', 'competency')
    ),
    review_status text not null default 'pending' check (
        review_status in ('pending', 'approved', 'retired')
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.skill_concept_sources (
    concept_id text not null
        references public.skill_concepts(id) on delete cascade,
    source_id text not null
        references public.knowledge_sources(id) on delete restrict,
    external_identifier text,
    evidence_note text not null,
    primary key (concept_id, source_id)
);

create table public.role_skill_links (
    role_id text not null
        references public.role_templates(role_id) on delete cascade,
    concept_id text not null
        references public.skill_concepts(id) on delete cascade,
    competency_id text not null
        check (competency_id ~ '^[a-z][a-z0-9_]{2,79}$'),
    relation_type text not null check (
        relation_type in ('core', 'supporting', 'technology_context')
    ),
    importance double precision not null default 0.5
        check (importance between 0 and 1),
    source_document_id text
        references public.source_documents(id) on delete set null,
    review_status text not null default 'pending' check (
        review_status in ('pending', 'approved', 'retired')
    ),
    created_at timestamptz not null default now(),
    primary key (role_id, concept_id, competency_id)
);

create table public.question_packages (
    id text primary key check (id ~ '^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$'),
    package_key text not null check (
        package_key ~ '^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$'
    ),
    version text not null,
    role_id text references public.role_templates(role_id) on delete restrict,
    competency_id text not null
        check (competency_id ~ '^[a-z][a-z0-9_]{2,79}$'),
    skill_concept_ids text[] not null default '{}',
    seniority text not null check (
        seniority in ('intern', 'junior', 'entry_level', 'all')
    ),
    difficulty text not null check (
        difficulty in ('beginner', 'intermediate')
    ),
    question_type text not null check (
        question_type in ('core', 'follow_up', 'coverage', 'resume_grounded')
    ),
    prompt text not null check (length(prompt) between 20 and 2000),
    expected_concepts jsonb not null check (
        jsonb_typeof(expected_concepts) = 'array'
        and jsonb_array_length(expected_concepts) between 1 and 20
    ),
    rubric jsonb not null check (
        jsonb_typeof(rubric) = 'object'
        and rubric ?& array['1', '2', '3', '4', '5']
    ),
    follow_ups jsonb not null default '[]'::jsonb check (
        jsonb_typeof(follow_ups) = 'array'
        and jsonb_array_length(follow_ups) <= 2
    ),
    reference_explanation text not null,
    source_to_concept_mapping jsonb not null check (
        jsonb_typeof(source_to_concept_mapping) = 'object'
    ),
    author_type text not null check (
        author_type in ('team_authored', 'local_llm_generated')
    ),
    model_id text,
    prompt_version text,
    validation_status text not null default 'pending_automatic_validation'
        check (
            validation_status in (
                'draft', 'pending_automatic_validation',
                'generated_validated_for_practice',
                'faculty_reviewed_research_set', 'rejected', 'retired'
            )
        ),
    automatic_validation jsonb not null default '{}'::jsonb
        check (jsonb_typeof(automatic_validation) = 'object'),
    reviewer_id text,
    reviewed_at timestamptz,
    embedding extensions.vector(384),
    embedding_model text,
    search_vector tsvector generated always as (
        to_tsvector(
            'english'::regconfig,
            coalesce(prompt, '') || ' ' ||
            coalesce(expected_concepts::text, '') || ' ' ||
            coalesce(reference_explanation, '')
        )
    ) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (package_key, version),
    check (
        (author_type = 'team_authored')
        or (model_id is not null and prompt_version is not null)
    ),
    check (
        (embedding is null and embedding_model is null)
        or (embedding is not null and embedding_model is not null)
    ),
    check (
        validation_status <> 'faculty_reviewed_research_set'
        or (reviewer_id is not null and reviewed_at is not null)
    )
);

create table public.question_package_sources (
    question_package_id text not null
        references public.question_packages(id) on delete cascade,
    source_document_id text not null
        references public.source_documents(id) on delete restrict,
    supported_concepts text[] not null default '{}',
    primary key (question_package_id, source_document_id)
);

alter table public.learning_resources
    add column source_id text
        references public.knowledge_sources(id) on delete restrict,
    add column skill_terms text[] not null default '{}',
    add column technologies text[] not null default '{}',
    add column learning_outcomes text[] not null default '{}',
    add column resource_type text not null default 'official_documentation'
        check (
            resource_type in (
                'official_documentation', 'open_tutorial', 'coding_exercise',
                'safe_lab', 'mini_project', 'reattempt_question'
            )
        ),
    add column license_id text,
    add column attribution_text text,
    add column url_status text not null default 'unchecked'
        check (url_status in ('unchecked', 'valid', 'broken', 'retired')),
    add column url_verified_at timestamptz,
    add column original_summary text,
    add column reviewer_id text,
    add column embedding extensions.vector(384),
    add column embedding_model text,
    add column search_vector tsvector generated always as (
        to_tsvector(
            'english'::regconfig,
            coalesce(title, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(original_summary, '')
        )
    ) stored,
    add constraint learning_resources_embedding_pair check (
        (embedding is null and embedding_model is null)
        or (embedding is not null and embedding_model is not null)
    ),
    add constraint learning_resources_approved_metadata check (
        reviewer_status <> 'approved'
        or (
            reviewer_id is not null
            and reviewed_at is not null
            and source_id is not null
            and license_id is not null
            and attribution_text is not null
            and url_status = 'valid'
            and url_verified_at is not null
            and cardinality(learning_outcomes) > 0
        )
    );

create table public.learning_resource_chunks (
    id bigint generated always as identity primary key,
    resource_id text not null
        references public.learning_resources(id) on delete cascade,
    chunk_key text not null check (chunk_key ~ '^[a-z0-9][a-z0-9:_-]{2,119}$'),
    context_prefix text not null,
    content text not null check (length(content) between 20 and 12000),
    content_sha256 text not null check (content_sha256 ~ '^[a-f0-9]{64}$'),
    embedding extensions.vector(384),
    embedding_model text,
    search_vector tsvector generated always as (
        to_tsvector(
            'english'::regconfig,
            coalesce(context_prefix, '') || ' ' || coalesce(content, '')
        )
    ) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (resource_id, chunk_key),
    check (
        (embedding is null and embedding_model is null)
        or (embedding is not null and embedding_model is not null)
    )
);

create trigger knowledge_sources_set_updated_at
before update on public.knowledge_sources
for each row execute function public.set_updated_at();
create trigger source_documents_set_updated_at
before update on public.source_documents
for each row execute function public.set_updated_at();
create trigger knowledge_chunks_set_updated_at
before update on public.knowledge_chunks
for each row execute function public.set_updated_at();
create trigger skill_concepts_set_updated_at
before update on public.skill_concepts
for each row execute function public.set_updated_at();
create trigger question_packages_set_updated_at
before update on public.question_packages
for each row execute function public.set_updated_at();
create trigger learning_resource_chunks_set_updated_at
before update on public.learning_resource_chunks
for each row execute function public.set_updated_at();

create index source_documents_source_idx
    on public.source_documents (source_id, review_status, ingest_status);
create index knowledge_chunks_document_idx
    on public.knowledge_chunks (document_id);
create index knowledge_chunks_filters_idx
    on public.knowledge_chunks (seniority, difficulty);
create index knowledge_chunks_competencies_gin
    on public.knowledge_chunks using gin (competency_ids);
create index knowledge_chunks_skills_gin
    on public.knowledge_chunks using gin (skill_terms);
create index knowledge_chunks_search_gin
    on public.knowledge_chunks using gin (search_vector);
create index knowledge_chunks_embedding_hnsw
    on public.knowledge_chunks using hnsw
    (embedding extensions.vector_cosine_ops)
    where embedding is not null;
create index skill_concepts_aliases_gin
    on public.skill_concepts using gin (aliases);
create index skill_concept_sources_source_idx
    on public.skill_concept_sources (source_id);
create index role_skill_links_concept_idx
    on public.role_skill_links (concept_id);
create index role_skill_links_source_document_idx
    on public.role_skill_links (source_document_id)
    where source_document_id is not null;
create index role_skill_links_lookup_idx
    on public.role_skill_links (role_id, competency_id, review_status);
create index question_packages_lookup_idx
    on public.question_packages (
        role_id, competency_id, seniority, difficulty, validation_status
    );
create index question_packages_skills_gin
    on public.question_packages using gin (skill_concept_ids);
create index question_packages_search_gin
    on public.question_packages using gin (search_vector);
create index question_packages_embedding_hnsw
    on public.question_packages using hnsw
    (embedding extensions.vector_cosine_ops)
    where embedding is not null;
create index question_package_sources_document_idx
    on public.question_package_sources (source_document_id);
create index learning_resources_competencies_gin
    on public.learning_resources using gin (competency_ids);
create index learning_resources_source_idx
    on public.learning_resources (source_id)
    where source_id is not null;
create index learning_resources_skills_gin
    on public.learning_resources using gin (skill_terms);
create index learning_resources_search_gin
    on public.learning_resources using gin (search_vector);
create index learning_resources_embedding_hnsw
    on public.learning_resources using hnsw
    (embedding extensions.vector_cosine_ops)
    where embedding is not null;
create index learning_resource_chunks_resource_idx
    on public.learning_resource_chunks (resource_id);
create index learning_resource_chunks_search_gin
    on public.learning_resource_chunks using gin (search_vector);
create index learning_resource_chunks_embedding_hnsw
    on public.learning_resource_chunks using hnsw
    (embedding extensions.vector_cosine_ops)
    where embedding is not null;

alter table public.knowledge_sources enable row level security;
alter table public.source_documents enable row level security;
alter table public.knowledge_chunks enable row level security;
alter table public.skill_concepts enable row level security;
alter table public.skill_concept_sources enable row level security;
alter table public.role_skill_links enable row level security;
alter table public.question_packages enable row level security;
alter table public.question_package_sources enable row level security;
alter table public.learning_resource_chunks enable row level security;

create policy knowledge_sources_approved_read on public.knowledge_sources
for select to authenticated
using (review_status = 'approved' and retrieval_enabled);
create policy source_documents_approved_read on public.source_documents
for select to authenticated
using (review_status = 'approved' and ingest_status = 'ready');
create policy knowledge_chunks_approved_read on public.knowledge_chunks
for select to authenticated
using (
    exists (
        select 1
        from public.source_documents d
        join public.knowledge_sources s on s.id = d.source_id
        where d.id = knowledge_chunks.document_id
          and d.review_status = 'approved'
          and d.ingest_status = 'ready'
          and s.review_status = 'approved'
          and s.retrieval_enabled
    )
);
create policy skill_concepts_approved_read on public.skill_concepts
for select to authenticated using (review_status = 'approved');
create policy skill_concept_sources_approved_read
on public.skill_concept_sources
for select to authenticated
using (
    exists (
        select 1 from public.skill_concepts c
        where c.id = skill_concept_sources.concept_id
          and c.review_status = 'approved'
    )
);
create policy role_skill_links_approved_read on public.role_skill_links
for select to authenticated using (review_status = 'approved');
create policy question_packages_validated_read on public.question_packages
for select to authenticated
using (
    validation_status in (
        'generated_validated_for_practice',
        'faculty_reviewed_research_set'
    )
);
create policy question_package_sources_validated_read
on public.question_package_sources
for select to authenticated
using (
    exists (
        select 1 from public.question_packages q
        where q.id = question_package_sources.question_package_id
          and q.validation_status in (
              'generated_validated_for_practice',
              'faculty_reviewed_research_set'
          )
    )
);
create policy learning_resource_chunks_approved_read
on public.learning_resource_chunks
for select to authenticated
using (
    exists (
        select 1 from public.learning_resources r
        where r.id = learning_resource_chunks.resource_id
          and r.reviewer_status = 'approved'
          and r.url_status = 'valid'
    )
);

revoke all privileges on table
    public.knowledge_sources,
    public.source_documents,
    public.knowledge_chunks,
    public.skill_concepts,
    public.skill_concept_sources,
    public.role_skill_links,
    public.question_packages,
    public.question_package_sources,
    public.learning_resource_chunks
from anon;

grant select on table
    public.knowledge_sources,
    public.source_documents,
    public.knowledge_chunks,
    public.skill_concepts,
    public.skill_concept_sources,
    public.role_skill_links,
    public.question_packages,
    public.question_package_sources,
    public.learning_resource_chunks
to authenticated;

grant select, insert, update, delete on table
    public.knowledge_sources,
    public.source_documents,
    public.knowledge_chunks,
    public.skill_concepts,
    public.skill_concept_sources,
    public.role_skill_links,
    public.question_packages,
    public.question_package_sources,
    public.learning_resource_chunks
to service_role;

grant usage, select on sequence
    public.knowledge_chunks_id_seq,
    public.learning_resource_chunks_id_seq
to service_role;

create or replace function public.match_question_packages(
    p_query text,
    p_role_id text default null,
    p_competency_id text default null,
    p_seniority text default 'junior',
    p_difficulty text default null,
    p_query_embedding extensions.vector(384) default null,
    p_match_count integer default 10
)
returns table (
    id text,
    package_key text,
    version text,
    role_id text,
    competency_id text,
    seniority text,
    difficulty text,
    question_type text,
    prompt text,
    expected_concepts jsonb,
    rubric jsonb,
    follow_ups jsonb,
    reference_explanation text,
    validation_status text,
    keyword_rank real,
    semantic_similarity double precision,
    hybrid_score double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
    with query_input as (
        select websearch_to_tsquery('english'::regconfig, p_query) as ts_query
    ),
    ranked as (
        select
            q.*,
            ts_rank_cd(q.search_vector, i.ts_query)::real as text_score,
            case
                when p_query_embedding is null or q.embedding is null then 0.0
                else 1.0 - (
                    q.embedding OPERATOR(extensions.<=>) p_query_embedding
                )
            end as vector_score
        from public.question_packages q
        cross join query_input i
        where q.validation_status in (
                'generated_validated_for_practice',
                'faculty_reviewed_research_set'
            )
          and (p_role_id is null or q.role_id is null or q.role_id = p_role_id)
          and (p_competency_id is null or q.competency_id = p_competency_id)
          and (p_seniority is null or q.seniority in (p_seniority, 'all'))
          and (p_difficulty is null or q.difficulty = p_difficulty)
          and (
              q.search_vector @@ i.ts_query
              or (
                  p_query_embedding is not null
                  and q.embedding is not null
              )
          )
    )
    select
        r.id, r.package_key, r.version, r.role_id, r.competency_id,
        r.seniority, r.difficulty, r.question_type, r.prompt,
        r.expected_concepts, r.rubric, r.follow_ups,
        r.reference_explanation, r.validation_status,
        r.text_score, r.vector_score,
        (0.55 * r.text_score + 0.45 * r.vector_score) as hybrid_score
    from ranked r
    order by hybrid_score desc, r.id
    limit least(greatest(p_match_count, 1), 50);
$$;

create or replace function public.match_learning_resources(
    p_query text,
    p_competency_id text default null,
    p_difficulty text default null,
    p_query_embedding extensions.vector(384) default null,
    p_match_count integer default 5
)
returns table (
    id text,
    title text,
    canonical_url text,
    source_organization text,
    competency_ids jsonb,
    difficulty text,
    estimated_minutes integer,
    description text,
    resource_type text,
    learning_outcomes text[],
    keyword_rank real,
    semantic_similarity double precision,
    hybrid_score double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
    with query_input as (
        select websearch_to_tsquery('english'::regconfig, p_query) as ts_query
    ),
    ranked as (
        select
            r.*,
            ts_rank_cd(r.search_vector, i.ts_query)::real as text_score,
            case
                when p_query_embedding is null or r.embedding is null then 0.0
                else 1.0 - (
                    r.embedding OPERATOR(extensions.<=>) p_query_embedding
                )
            end as vector_score
        from public.learning_resources r
        cross join query_input i
        where r.reviewer_status = 'approved'
          and r.url_status = 'valid'
          and (
              p_competency_id is null
              or r.competency_ids ? p_competency_id
          )
          and (p_difficulty is null or r.difficulty = p_difficulty)
          and (
              r.search_vector @@ i.ts_query
              or (
                  p_query_embedding is not null
                  and r.embedding is not null
              )
          )
    )
    select
        r.id, r.title, r.canonical_url, r.source_organization,
        r.competency_ids, r.difficulty, r.estimated_minutes,
        r.description, r.resource_type, r.learning_outcomes,
        r.text_score, r.vector_score,
        (0.55 * r.text_score + 0.45 * r.vector_score) as hybrid_score
    from ranked r
    order by hybrid_score desc, r.id
    limit least(greatest(p_match_count, 1), 20);
$$;

revoke all on function public.match_question_packages(
    text, text, text, text, text, extensions.vector, integer
) from public, anon;
grant execute on function public.match_question_packages(
    text, text, text, text, text, extensions.vector, integer
) to authenticated, service_role;

revoke all on function public.match_learning_resources(
    text, text, text, extensions.vector, integer
) from public, anon;
grant execute on function public.match_learning_resources(
    text, text, text, extensions.vector, integer
) to authenticated, service_role;
