ALTER TABLE {schema}.schema_version DROP CONSTRAINT IF EXISTS schema_version_version_check;
UPDATE {schema}.schema_version SET version = 2 WHERE version = 1;
ALTER TABLE {schema}.tasks ADD COLUMN IF NOT EXISTS idempotency_key text;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_idempotency_idx ON {schema}.tasks(idempotency_key);
ALTER TABLE {schema}.tasks ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 0;
ALTER TABLE {schema}.tasks ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE {schema}.tasks ADD COLUMN IF NOT EXISTS deadline timestamptz;
ALTER TABLE {schema}.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE {schema}.tasks ADD CONSTRAINT tasks_status_check
 CHECK (status IN ('queued','running','completed','failed','cancelled','needs_review'));
ALTER TABLE {schema}.tasks DROP CONSTRAINT IF EXISTS task_state_payload;
ALTER TABLE {schema}.tasks ADD CONSTRAINT task_state_payload CHECK (
 (status='queued' AND started_at IS NULL AND finished_at IS NULL
  AND worker_id IS NULL AND claim_token IS NULL AND result IS NULL AND error IS NULL)
 OR (status='running' AND started_at IS NOT NULL AND finished_at IS NULL
  AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NULL AND error IS NULL)
 OR (status='completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL
  AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NOT NULL AND error IS NULL
  AND jsonb_typeof(result)='object')
 OR (status IN ('failed','needs_review') AND started_at IS NOT NULL AND finished_at IS NOT NULL
  AND worker_id IS NOT NULL AND claim_token IS NOT NULL AND result IS NULL AND error IS NOT NULL
  AND jsonb_typeof(error)='object' AND error ? 'code' AND error ? 'message'
  AND jsonb_typeof(error->'code')='string' AND jsonb_typeof(error->'message')='string')
 OR (status='cancelled' AND finished_at IS NOT NULL AND result IS NULL AND error IS NULL)
);
CREATE INDEX IF NOT EXISTS tasks_lease_idx ON {schema}.tasks(lease_until) WHERE status='running';
CREATE TABLE IF NOT EXISTS {schema}.attempts (
 task_id uuid NOT NULL REFERENCES {schema}.tasks(id),
 attempt integer NOT NULL, token uuid NOT NULL UNIQUE, worker_id text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 finished_at timestamptz, outcome text, error jsonb,
 PRIMARY KEY(task_id,attempt)
);
-- Existing v1 running rows have unknown outcomes. Do not replay historical work.
UPDATE {schema}.tasks SET status='needs_review', finished_at=clock_timestamp(),
 error='{{"code":"legacy_interrupted","message":"Historical execution requires operator review"}}'::jsonb
 WHERE status='running' AND lease_until IS NULL;
