# PostgreSQL/pgvector real integration acceptance — 2026-10-15

## Outcome

**17 real database test methods passed in 6.676s**, using separate psycopg
connections and fake vectors. **142 offline methods passed in 19.412s** afterward.
Total distinct final methods: **159**. Initial 16-method run had 15 pass / 1 fail;
those repeated methods and parametrized cases are not added to the final count.
No LLM/embedding API calls, credential loading, public exposure or original DB
migration occurred. No commit, push or merge. Baseline remains
`1eb1638d7b624c9e3b077d11f6ee49ac607196b9`.

## Image and isolated environment

Source verified against [pgvector project Docker instructions](https://github.com/pgvector/pgvector#docker).
Tag: `pgvector/pgvector:0.8.7-pg16-bookworm`.
Digest / image ID: `sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a`.
Actual `server_version`: `16.15 (Debian 16.15-1.pgdg12+2)`.
Actual extension version: `0.8.7`, installed in public only in the test database.

Container: `locagent-vector-acceptance-20261015`; dedicated volume with suffix
`-data`; database `vector_acceptance`; port `127.0.0.1:55441`; memory 768 MiB,
CPU limit 2. Trust authentication is used only for this loopback test container,
not proposed as public deployment configuration. Each test uses a fresh
`public_preview_vi_<random>` schema. No schemas/volumes were deleted afterward.

Actual commands and coordinator actions:

```text
docker pull pgvector/pgvector:0.8.7-pg16-bookworm
docker run --pull=never -d --name locagent-vector-acceptance-20261015
  --memory 768m --cpus 2 -p 127.0.0.1:55441:5432
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=vector_acceptance
  -v locagent-vector-acceptance-20261015-data:/var/lib/postgresql/data
  sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
```

Existing project Python ran `run_pgvector_acceptance.py`, then `--reuse` after
the local fix. Coordinator checks the exact owned resource identity and free
port, runs `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public` only against
the isolated DSN, and invokes:

```text
LOCAGENT_VECTOR_TEST_DSN=postgresql://postgres@127.0.0.1:55441/vector_acceptance
  <existing-python> -B -m unittest discover -s tests
  -p test_rag_postgres_integration.py -v
```

Every test explicitly calls optional initialization for its fresh schema. The
original TaskStore schema-v3 initializer is unchanged. Coordinator finally runs
`docker stop locagent-vector-acceptance-20261015` after both runs.

## Real defect found and minimal fix

Initial SQL table accepted an embedding whose dimensions differed from the build;
Python validation alone could not protect a direct SQL insert. The first real
test reproduced this, and its failure log remains preserved.

`004_vector_preview.sql` now binds row dimensions to build dimensions via a
composite foreign key, checks `vector_dims(embedding)=dimensions`, and rejects
zero norm. pgvector itself rejects NaN/Infinity. `rag_postgres.publish` includes
the expected dimensions in each bound insert. Added direct SQL regression covers
wrong embedding dimension, wrong build dimension and zero vector. This was a
local validation fix, not a change to query architecture.

Important migration boundary: this optional DDL is still an initial unpublished
schema definition, not an upgrade for the first experimental schema layout.
Old failed-run test schemas are preserved as evidence; corrected tests use fresh
schemas. Do not reuse an old experimental schema without an explicit upgrade plan.

## Fault injection and tested invariants

- Two independent connections synchronize at a threading Barrier: only one build
  claim succeeds, the other receives BuildConflict.
- Controlled expiry in the dedicated schema permits a fresh token; old token
  publication and cancellation both fail. Failed/cancelled builds can be explicitly
  rebuilt; ready builds and consumed publish tokens cannot overwrite ready data.
- Publication pauses after real executemany inserts, before commit. A second
  connection observes zero committed rows and IndexNotReady. After release it
  sees all three rows and ready state, never a partial published index.
- Raising an injected exception after real inserts rolls back all rows.
- `pg_sleep(5.1)` with a 5-second lease forces expiry during publication; the final
  fence rejects publication and all rows roll back.
- `pg_terminate_backend` targets only the owned publishing connection. Its
  transaction rolls back; zero rows remain, and an explicit expired-claim takeover
  publishes a complete replacement successfully.
- Real SQL checks entity dedup and distance ordering; version/repo/commit/model/
  membership changes do not read a different build. Hybrid graph adapter uses a
  fake provider; default BM25 and complete not-ready fallback retain lexical nodes.
- Initialization and extension lookup execute against the real server; same-layout
  initialization is repeatable. No ANN indexes are created or claimed.

## Protected resources and evidence

Original learning README SHA256 before/after:
`6858a33beaf68c0e4a9d561891e864dd1fc672afc0a5aa5b3ecd7a428755370a`.
Original demo container state and mount metadata are equal before/after; it was
not started or connected to. No physical checksum of all original DB pages is
claimed. Historical ledger file hashes under the inspected original/feature
outputs are equal before/after (36 files).
Only hashes were retained, not credential or ledger contents.

Both evidence folders preserve image/versions, test logs, result, protected
before/after hashes and cleanup:
`outputs/vector-acceptance-20261015/` and
`outputs/vector-acceptance-20261015-rerun/`.
Own container is stopped; own database volume and schemas remain for review.

## Remaining unverified boundaries

No real embedding provider/billing/unknown-outcome workflow, model quality study,
ANN, scale benchmark, OS power-loss recovery, whole-server crash during commit,
network partition, hostile DB-owner mutation, multi-tenant ACL or production
deployment was tested. Recovery here means real backend-session interruption,
rollback and lease takeover; do not broaden it to every crash class. The two
runs restarted the test container, but this is not a formal power-loss durability
test. Exact cosine scanning is still exact retrieval, not ANN.
