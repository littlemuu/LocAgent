-- Optional sidecar only. TaskStore.initialize never applies this migration.
-- Requires an operator-installed public.vector extension; no CREATE EXTENSION.
CREATE TABLE IF NOT EXISTS {schema}.rag_vector_builds (
    build_key text PRIMARY KEY CHECK (build_key ~ '^[0-9a-f]{{64}}$'),
    version jsonb NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 1 AND 2000),
    state text NOT NULL CHECK (state IN ('building','ready','failed','cancelled')),
    token uuid NOT NULL,
    lease_until timestamptz,
    UNIQUE (build_key,dimensions),
    CHECK ((state='building') = (lease_until IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS {schema}.rag_vector_rows (
    build_key text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 1 AND 2000),
    chunk_id text NOT NULL CHECK (chunk_id ~ '^[0-9a-f]{{64}}$'),
    entity_id text NOT NULL,
    embedding public.vector NOT NULL,
    CHECK (public.vector_dims(embedding)=dimensions),
    CHECK (public.vector_norm(embedding)>0),
    FOREIGN KEY (build_key,dimensions) REFERENCES {schema}.rag_vector_builds(build_key,dimensions),
    PRIMARY KEY (build_key,chunk_id)
);
