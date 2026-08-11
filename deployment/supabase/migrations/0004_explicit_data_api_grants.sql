-- New Supabase projects do not implicitly expose public-schema objects through
-- the Data API. Keep the browser-facing surface explicit and least-privileged.

grant usage on schema public to authenticated, service_role;

revoke all privileges on table
    public.profiles,
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
    public.consent_records,
    public.deletion_requests
from anon;

-- Students can read only rows admitted by RLS. Writes are limited to records
-- that genuinely originate from the student-facing product.
grant select, insert, update, delete on table public.profiles to authenticated;
grant select on table public.attempts to authenticated;
grant select on table public.job_descriptions to authenticated;
grant select, insert, update on table public.resume_documents to authenticated;
grant select on table public.resume_claims to authenticated;
grant select on table public.interview_questions to authenticated;
grant select, insert, update on table public.answers to authenticated;
grant select on table public.processing_jobs to authenticated;
grant select on table public.evidence_nodes to authenticated;
grant select on table public.evidence_edges to authenticated;
grant select on table public.scorecards to authenticated;
grant select on table public.learning_resources to authenticated;
grant select, update on table public.roadmap_items to authenticated;
grant select on table public.progress_metrics to authenticated;
grant select, insert on table public.consent_records to authenticated;
grant select, insert on table public.deletion_requests to authenticated;

-- Trusted backend workers use the service role for durable processing,
-- inference, evidence, report, retention, and deletion workflows.
grant select, insert, update, delete on table
    public.profiles,
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
    public.consent_records,
    public.deletion_requests
to service_role;

-- These validated lifecycle functions are the only authenticated write path
-- for attempts. SECURITY DEFINER is safe here because both functions validate
-- auth.uid(), constrain their inputs, and pin search_path to public.
alter function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) security definer;
alter function public.transition_attempt(uuid, text) security definer;

revoke all on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) from public, anon;
grant execute on function public.create_assessment_attempt(
    uuid, text, text, text, text, jsonb, text, text, text, jsonb
) to authenticated, service_role;

revoke all on function public.transition_attempt(uuid, text) from public, anon;
grant execute on function public.transition_attempt(uuid, text)
to authenticated, service_role;

revoke all on function public.owns_attempt(uuid) from public, anon;
grant execute on function public.owns_attempt(uuid)
to authenticated, service_role;

revoke all on function public.set_updated_at() from public, anon, authenticated;
grant execute on function public.set_updated_at() to service_role;

-- The required-JD RPC was superseded by the optional-JD assessment RPC.
drop function public.create_attempt_with_jd(
    uuid, text, text, text, jsonb, jsonb
);
