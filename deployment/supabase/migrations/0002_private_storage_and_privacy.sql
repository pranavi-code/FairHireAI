-- Private user uploads and explicit privacy/retention records.
-- Worker-only derived artifacts deliberately receive no authenticated-user
-- storage policy and must be served through an authorized API.

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values
    (
        'roleready-documents',
        'roleready-documents',
        false,
        5242880,
        array[
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain',
            'text/markdown'
        ]
    ),
    (
        'roleready-interview-video',
        'roleready-interview-video',
        false,
        262144000,
        array['video/mp4', 'video/webm', 'video/quicktime']
    ),
    (
        'roleready-derived-artifacts',
        'roleready-derived-artifacts',
        false,
        52428800,
        array[
            'application/json',
            'application/octet-stream',
            'application/vnd.apache.parquet'
        ]
    )
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create policy documents_owner_select on storage.objects
for select to authenticated
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
);
create policy documents_owner_insert on storage.objects
for insert to authenticated
with check (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
);
create policy documents_owner_update on storage.objects
for update to authenticated
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
)
with check (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
);
create policy documents_owner_delete on storage.objects
for delete to authenticated
using (
    bucket_id = 'roleready-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
);

create policy interview_video_owner_select on storage.objects
for select to authenticated
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
);
create policy interview_video_owner_insert on storage.objects
for insert to authenticated
with check (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = auth.uid()::text
);
create policy interview_video_owner_update on storage.objects
for update to authenticated
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
)
with check (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = auth.uid()::text
);
create policy interview_video_owner_delete on storage.objects
for delete to authenticated
using (
    bucket_id = 'roleready-interview-video'
    and (storage.foldername(name))[1] = auth.uid()::text
    and owner_id = auth.uid()::text
);

create table public.consent_records (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    attempt_id uuid references public.attempts(id) on delete cascade,
    consent_type text not null
        check (consent_type in (
            'privacy_notice',
            'resume_processing',
            'interview_recording',
            'research_evaluation'
        )),
    policy_version text not null,
    granted boolean not null,
    occurred_at timestamptz not null default now(),
    source text not null check (source in ('web', 'mobile', 'admin_import')),
    metadata jsonb not null default '{}'::jsonb
);

create table public.deletion_requests (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    attempt_id uuid references public.attempts(id) on delete cascade,
    scope text not null check (scope in ('attempt', 'account')),
    status text not null default 'requested'
        check (status in ('requested', 'processing', 'completed', 'failed')),
    requested_at timestamptz not null default now(),
    completed_at timestamptz,
    error_code text,
    constraint attempt_scope_requires_attempt check (
        scope <> 'attempt' or attempt_id is not null
    ),
    constraint completed_deletion_has_timestamp check (
        status <> 'completed' or completed_at is not null
    )
);

create index consent_user_occurred_idx
    on public.consent_records (user_id, occurred_at desc);
create index deletion_status_requested_idx
    on public.deletion_requests (status, requested_at);

alter table public.consent_records enable row level security;
alter table public.deletion_requests enable row level security;

create policy consent_owner_select on public.consent_records
for select to authenticated using (user_id = auth.uid());
create policy consent_owner_insert on public.consent_records
for insert to authenticated
with check (
    user_id = auth.uid()
    and (attempt_id is null or public.owns_attempt(attempt_id))
);
-- Consent history is append-only for authenticated users.

create policy deletion_owner_select on public.deletion_requests
for select to authenticated using (user_id = auth.uid());
create policy deletion_owner_insert on public.deletion_requests
for insert to authenticated
with check (
    user_id = auth.uid()
    and (attempt_id is null or public.owns_attempt(attempt_id))
);
-- Only the trusted deletion worker may update request status.
