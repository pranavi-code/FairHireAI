-- Defense in depth: the owner RLS policy already denies anonymous rows, but
-- the Data API role should not have a table-level privilege at all.

revoke all on table public.answer_analyses from public, anon;
grant select on table public.answer_analyses to authenticated;
grant all on table public.answer_analyses to service_role;
