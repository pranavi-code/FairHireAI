-- Resolve actionable security and performance advisor findings.

alter function public.set_updated_at() set search_path = public;
alter function public.owns_attempt(uuid) security invoker;

alter policy profiles_owner_all on public.profiles
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

alter policy attempts_owner_select on public.attempts
using (user_id = (select auth.uid()));
alter policy attempts_owner_insert on public.attempts
with check (user_id = (select auth.uid()));
alter policy attempts_owner_update on public.attempts
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));
alter policy attempts_owner_delete on public.attempts
using (user_id = (select auth.uid()));

alter policy progress_owner_select on public.progress_metrics
using (user_id = (select auth.uid()));

alter policy consent_owner_select on public.consent_records
using (user_id = (select auth.uid()));
alter policy consent_owner_insert on public.consent_records
with check (
    user_id = (select auth.uid())
    and (attempt_id is null or public.owns_attempt(attempt_id))
);

alter policy deletion_owner_select on public.deletion_requests
using (user_id = (select auth.uid()));
alter policy deletion_owner_insert on public.deletion_requests
with check (
    user_id = (select auth.uid())
    and (attempt_id is null or public.owns_attempt(attempt_id))
);

alter policy documents_owner_select on storage.objects
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
);
alter policy documents_owner_insert on storage.objects
with check (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);
alter policy documents_owner_update on storage.objects
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
)
with check (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);
alter policy documents_owner_delete on storage.objects
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
);

alter policy interview_video_owner_select on storage.objects
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
);
alter policy interview_video_owner_insert on storage.objects
with check (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);
alter policy interview_video_owner_update on storage.objects
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
)
with check (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);
alter policy interview_video_owner_delete on storage.objects
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and owner_id = (select auth.uid())::text
);

create index attempts_parent_attempt_idx
    on public.attempts (parent_attempt_id);
create index consent_attempt_idx
    on public.consent_records (attempt_id);
create index deletion_attempt_idx
    on public.deletion_requests (attempt_id);
create index deletion_user_idx
    on public.deletion_requests (user_id);
create index evidence_edges_source_idx
    on public.evidence_edges (source_node_id);
create index evidence_edges_target_idx
    on public.evidence_edges (target_node_id);
create index processing_jobs_answer_idx
    on public.processing_jobs (answer_id);
create index processing_jobs_attempt_idx
    on public.processing_jobs (attempt_id);
create index progress_later_attempt_idx
    on public.progress_metrics (later_attempt_id);
create index progress_user_idx
    on public.progress_metrics (user_id);
create index resume_claims_document_idx
    on public.resume_claims (resume_document_id);
create index roadmap_resource_idx
    on public.roadmap_items (resource_id);
create index roadmap_skill_gap_idx
    on public.roadmap_items (skill_gap_node_id);
