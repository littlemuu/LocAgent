ALTER TABLE {schema}.tasks ADD COLUMN IF NOT EXISTS progress jsonb;
UPDATE {schema}.schema_version SET version=3 WHERE version=2;
