-- Authenticated, idempotent handoff from the student API to durable workers.
-- The worker remains the only component allowed to claim or mutate jobs.

create or replace function public.enqueue_attempt_processing(p_attempt_id uuid)
returns table (
    attempt_id uuid,
    started boolean,
    queued_job_count integer,
    message text
)
language plpgsql
security definer
set search_path = public
as $$
declare
    current_attempt public.attempts;
    answer_row public.answers;
    inserted_count integer := 0;
begin
    select * into current_attempt
    from public.attempts
    where id = p_attempt_id and user_id = auth.uid()
    for update;

    if not found then
        raise exception 'Attempt was not found';
    end if;
    if current_attempt.status not in ('interviewing', 'processing', 'failed') then
        raise exception 'Attempt is not ready for processing';
    end if;
    if not exists (
        select 1 from public.answers where attempt_id = p_attempt_id
    ) then
        raise exception 'At least one submitted answer is required';
    end if;
    if (
        select count(distinct q.competency_id)
        from public.interview_questions q
        join public.answers a on a.question_id = q.id
        where q.attempt_id = p_attempt_id
          and not q.is_follow_up
    ) < jsonb_object_length(current_attempt.competency_weights) then
        raise exception 'Every approved core competency requires an answer before processing';
    end if;

    for answer_row in
        select *
        from public.answers
        where attempt_id = p_attempt_id
          and processing_status in ('pending', 'failed')
        order by submitted_at
        for update
    loop
        insert into public.processing_jobs (
            attempt_id,
            answer_id,
            job_type,
            status,
            stage,
            idempotency_key
        )
        values (
            p_attempt_id,
            answer_row.id,
            'answer_preprocessing',
            'queued',
            'waiting_for_worker',
            'answer-preprocessing:' || answer_row.id::text || ':v1'
        )
        on conflict (idempotency_key) do nothing;

        if found then
            inserted_count := inserted_count + 1;
        end if;

        update public.answers
        set processing_status = 'queued'
        where id = answer_row.id
          and processing_status in ('pending', 'failed');
    end loop;

    if current_attempt.status in ('interviewing', 'failed') then
        update public.attempts
        set status = 'processing'
        where id = p_attempt_id;
    end if;

    return query
    select
        p_attempt_id,
        true,
        inserted_count,
        case
            when inserted_count > 0
                then format('%s answer-processing job(s) queued.', inserted_count)
            else 'Processing was already queued for every submitted answer.'
        end;
end;
$$;

revoke all on function public.enqueue_attempt_processing(uuid)
from public, anon;
grant execute on function public.enqueue_attempt_processing(uuid)
to authenticated, service_role;
