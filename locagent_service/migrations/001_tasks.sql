CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.schema_version (
    version integer PRIMARY KEY CHECK (version = 1)
);
CREATE TABLE IF NOT EXISTS {schema}.tasks (
    id uuid PRIMARY KEY,
    request jsonb NOT NULL CHECK (jsonb_typeof(request) = 'object'),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    worker_id text,
    claim_token uuid,
    result jsonb,
    error jsonb,
    CONSTRAINT task_state_payload CHECK (
        (status = 'queued' AND started_at IS NULL AND finished_at IS NULL
            AND worker_id IS NULL AND claim_token IS NULL AND result IS NULL AND error IS NULL)
        OR
        (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL
            AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NULL AND error IS NULL)
        OR
        (status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL
            AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NOT NULL AND error IS NULL
            AND jsonb_typeof(result) = 'object'
            AND result ? 'status'
            AND result->>'status' IN ('success', 'empty', 'iteration_limit'))
        OR
        (status = 'failed' AND started_at IS NOT NULL AND finished_at IS NOT NULL
            AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NULL AND error IS NOT NULL
            AND jsonb_typeof(error) = 'object'
            AND error ? 'code' AND error ? 'message'
            AND jsonb_typeof(error->'code') = 'string'
            AND jsonb_typeof(error->'message') = 'string')
    )
);
CREATE INDEX IF NOT EXISTS tasks_queued_order_idx
    ON {schema}.tasks (created_at, id) WHERE status = 'queued';
-- CHECK accepts SQL NULL; explicitly reject absent/null/unknown result status.
-- Additive and repeatable for a previously initialized local demo schema too.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = '{schema}.tasks'::regclass AND conname = 'task_result_status_present'
    ) THEN
        ALTER TABLE {schema}.tasks ADD CONSTRAINT task_result_status_present CHECK (
            result IS NULL OR COALESCE(
                jsonb_typeof(result->'status') = 'string'
                AND result->>'status' IN ('success', 'empty', 'iteration_limit'), FALSE
            )
        );
    END IF;
END $$;
INSERT INTO {schema}.schema_version(version) VALUES (1) ON CONFLICT DO NOTHING;
