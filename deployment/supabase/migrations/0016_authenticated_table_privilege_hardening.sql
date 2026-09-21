-- Restore least-privilege Data API grants for signed-in students.
--
-- Supabase may grant broad privileges on newly created public tables. RLS still
-- limits rows, but owner policies must not make worker-owned evidence and scores
-- writable by the browser. Student writes go through validated RPCs, except for
-- append-only consent/deletion requests and the user's own profile.

begin;

revoke all privileges on all tables in schema public from anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all on tables from anon, authenticated;

grant select, insert, update, delete on table public.profiles to authenticated;

grant select on table
    public.attempts,
    public.job_descriptions,
    public.resume_documents,
    public.resume_claims,
    public.interview_questions,
    public.answers,
    public.processing_jobs,
    public.evidence_nodes,
    public.evidence_edges,
    public.scorecards,
    public.learning_resources,
    public.roadmap_items,
    public.progress_metrics,
    public.role_templates,
    public.knowledge_sources,
    public.source_documents,
    public.knowledge_chunks,
    public.skill_concepts,
    public.skill_concept_sources,
    public.role_skill_links,
    public.question_packages,
    public.question_package_sources,
    public.learning_resource_chunks,
    public.answer_analyses,
    public.consent_records,
    public.deletion_requests
to authenticated;

grant insert on table public.consent_records, public.deletion_requests to authenticated;

-- The trusted worker and backend maintenance paths retain full table access.
grant all privileges on all tables in schema public to service_role;
alter default privileges for role postgres in schema public
    grant all on tables to service_role;

commit;
