-- Permit image job descriptions in the existing private documents bucket.
-- Ownership policies and the 5 MiB limit remain unchanged.

update storage.buckets
set allowed_mime_types = array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/markdown',
    'image/jpeg',
    'image/png',
    'image/webp'
]
where id = 'roleready-documents';
