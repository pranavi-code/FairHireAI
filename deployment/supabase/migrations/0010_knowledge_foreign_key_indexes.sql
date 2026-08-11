-- Cover the two optional foreign keys identified after the knowledge-layer
-- migration by the Supabase database advisor.

create index role_skill_links_source_document_idx
    on public.role_skill_links (source_document_id)
    where source_document_id is not null;

create index learning_resources_source_idx
    on public.learning_resources (source_id)
    where source_id is not null;
