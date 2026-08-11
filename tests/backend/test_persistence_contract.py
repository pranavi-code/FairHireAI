from pathlib import Path


def test_supabase_migration_contains_required_tables_and_rls() -> None:
    migration = Path("deployment/supabase/migrations/0001_product_foundation.sql").read_text(
        encoding="utf-8"
    )
    required_tables = {
        "attempts",
        "job_descriptions",
        "resume_documents",
        "resume_claims",
        "interview_questions",
        "answers",
        "processing_jobs",
        "evidence_nodes",
        "evidence_edges",
        "scorecards",
        "learning_resources",
        "roadmap_items",
        "progress_metrics",
    }
    for table in required_tables:
        assert f"create table public.{table}" in migration
        assert f"alter table public.{table} enable row level security" in migration
    assert "create or replace function public.owns_attempt" in migration
    assert "create or replace function public.create_attempt_with_jd" in migration
    assert "create or replace function public.transition_attempt" in migration
    assert "private_video_storage_key" in migration
    assert "public_video_url" not in migration


def test_private_storage_and_privacy_migration_fails_closed() -> None:
    migration = Path(
        "deployment/supabase/migrations/0002_private_storage_and_privacy.sql"
    ).read_text(encoding="utf-8")
    assert migration.count("false,") >= 3
    assert "roleready-documents" in migration
    assert "roleready-interview-video" in migration
    assert "roleready-derived-artifacts" in migration
    assert "create policy documents_owner_insert" in migration
    assert "create policy interview_video_owner_insert" in migration
    assert "(storage.foldername(name))[1] = auth.uid()::text" in migration
    assert "create table public.consent_records" in migration
    assert "create table public.deletion_requests" in migration
    assert "alter table public.consent_records enable row level security" in migration
    assert "alter table public.deletion_requests enable row level security" in migration
    assert "Consent history is append-only" in migration
    assert "derived_artifacts_owner" not in migration


def test_optional_jd_migration_supports_both_profile_sources() -> None:
    migration = Path(
        "deployment/supabase/migrations/0003_optional_job_description.sql"
    ).read_text(encoding="utf-8")
    assert "rename column jd_mapping_version to assessment_profile_version" in migration
    assert "assessment_profile_source" in migration
    assert "'approved_role', 'job_description'" in migration
    assert "create or replace function public.create_assessment_attempt" in migration
    assert "Approved-role attempts cannot contain JD fields" in migration
    assert "Approved-role attempts require base competency weights" in migration
    assert "JD-based attempts require all JD fields" in migration
    assert "Storage key is not scoped to the authenticated user" in migration
    assert "p_mapping_result -> 'competency_weights' <> p_competency_weights" in migration


def test_data_api_grants_are_explicit_and_anonymous_access_is_revoked() -> None:
    migration = Path(
        "deployment/supabase/migrations/0004_explicit_data_api_grants.sql"
    ).read_text(encoding="utf-8")
    assert "from anon;" in migration
    assert "grant select on table public.attempts to authenticated" in migration
    assert "grant select, insert on table public.consent_records to authenticated" in migration
    assert "grant select, insert on table public.deletion_requests to authenticated" in migration
    assert "alter function public.create_assessment_attempt" in migration
    assert "security definer" in migration
    assert "drop function public.create_attempt_with_jd" in migration


def test_database_advisor_hardening_is_preserved_in_source() -> None:
    migration = Path(
        "deployment/supabase/migrations/0005_database_advisor_hardening.sql"
    ).read_text(encoding="utf-8")
    assert "alter function public.set_updated_at() set search_path = public" in migration
    assert "alter function public.owns_attempt(uuid) security invoker" in migration
    assert "(select auth.uid())" in migration
    assert "create index processing_jobs_attempt_idx" in migration
    assert "create index evidence_edges_source_idx" in migration


def test_processing_queue_is_authenticated_idempotent_and_core_complete() -> None:
    migration = Path(
        "deployment/supabase/migrations/0008_processing_queue.sql"
    ).read_text(encoding="utf-8")
    assert "create or replace function public.enqueue_attempt_processing" in migration
    assert "where id = p_attempt_id and user_id = auth.uid()" in migration
    assert "jsonb_object_length(current_attempt.competency_weights)" in migration
    assert "on conflict (idempotency_key) do nothing" in migration
    assert "answer-preprocessing:" in migration
    assert "from public, anon" in migration
    assert "to authenticated, service_role" in migration


def test_worker_execution_migration_freezes_evidence_and_claims_jobs_atomically() -> None:
    migration = Path(
        "deployment/supabase/migrations/0012_worker_execution_and_frozen_evidence.sql"
    ).read_text(encoding="utf-8")
    assert "'external_ai_processing'" in migration
    assert "create table public.answer_analyses" in migration
    assert "alter table public.answer_analyses enable row level security" in migration
    assert "question_package_version" in migration
    assert "expected_concepts_snapshot" in migration
    assert "rubric_snapshot" in migration
    assert "source_mapping_snapshot" in migration
    assert "roleready-processing-artifacts" in migration
    assert "create or replace function public.claim_next_processing_job" in migration
    assert "for update skip locked" in migration
    assert "create or replace function public.claim_next_deletion_request" in migration
    assert "to service_role" in migration
    assert "to anon" not in migration.lower()


def test_answer_analysis_privilege_hardening_revokes_anonymous_access() -> None:
    migration = Path(
        "deployment/supabase/migrations/0013_answer_analyses_privilege_hardening.sql"
    ).read_text(encoding="utf-8")
    assert "revoke all on table public.answer_analyses from public, anon" in migration
    assert "grant select on table public.answer_analyses to authenticated" in migration
    assert "grant all on table public.answer_analyses to service_role" in migration


def test_supabase_secret_setter_rejects_arbitrary_clipboard_text() -> None:
    script = Path("scripts/set_supabase_secret.ps1").read_text(encoding="utf-8")
    assert "[switch]$FromClipboard" in script
    assert "^sb_secret_[A-Za-z0-9_-]{20,}$" in script
    assert "^eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$" in script
    assert "$isModernSecret -or $isLegacyServiceRole" in script


def test_local_frontend_uses_api_origin_without_duplicate_version_prefix() -> None:
    script = Path("scripts/configure_local_frontend.ps1").read_text(encoding="utf-8")
    assert "VITE_API_BASE_URL=http://127.0.0.1:8000" in script
    assert "VITE_API_BASE_URL=http://localhost:8000/api/v1" not in script


def test_local_cors_defaults_cover_localhost_and_loopback_hosts() -> None:
    config = Path("backend/app/config.py").read_text(encoding="utf-8")
    assert '"http://localhost:3000,http://127.0.0.1:3000,"' in config
    assert '"http://localhost:5173,http://127.0.0.1:5173,"' in config


def test_local_launcher_normalizes_duplicate_windows_path_keys() -> None:
    script = Path("scripts/start_local.ps1").read_text(encoding="utf-8")
    assert '[EnvironmentVariableTarget]::Process' in script
    assert '[Environment]::SetEnvironmentVariable(' in script
    assert '"PATH",' in script


def test_processing_rpc_qualifies_columns_that_collide_with_output_names() -> None:
    migration = Path(
        "deployment/supabase/migrations/0014_qualify_processing_rpc_columns.sql"
    ).read_text(encoding="utf-8")
    assert "from public.answers as a" in migration
    assert "where a.attempt_id = p_attempt_id" in migration
    assert "update public.attempts as a" in migration
    assert "where a.id = p_attempt_id" in migration
    assert "set search_path = ''" in migration
    assert "from public, anon" in migration
