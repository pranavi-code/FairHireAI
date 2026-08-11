alter table public.question_packages
    drop constraint if exists question_packages_author_type_check;

alter table public.question_packages
    add constraint question_packages_author_type_check
    check (
        author_type in (
            'team_authored',
            'local_llm_generated',
            'gemini_generated'
        )
    );
