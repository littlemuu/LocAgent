# Persistent exact-vector preview — uncommitted next stage

> 本页保留原阶段的设计范围。2026-10-16 最新进展见[百炼 embedding 排错与验收边界](BAILIAN_TROUBLESHOOTING.md)：包含响应留存、索引适配、传输诊断及数值对照；后续已完成[32块/10题探索性检索与复核](BAILIAN_RETRIEVAL_ACCEPTANCE.md)，不代表通用质量或生产验收。

Baseline: `1eb1638d7b624c9e3b077d11f6ee49ac607196b9` (17 files; 126 offline tests).
This next stage is separate and uncommitted. No real SQL migration, extension
installation, provider call, model download or database start was performed.

## Decisions and dependency checklist

- Existing TaskStore uses schema version 3. Its initializer explicitly applies
  migrations 001–003 only. New 004 is an optional sidecar, not a task schema upgrade.
- All known local test containers are stopped. Installed server-side pgvector is
  **unknown**, not inferred from the PostgreSQL image name. This stage did not
  start a service or inspect the original DB. Python pgvector was previously
  found absent; this implementation needs only existing psycopg because vector
  values are validated, normalized and passed as bound text parameters cast to
  `public.vector`. A Python pgvector package is not currently necessary.
- A future operator must approve a pinned trusted extension/image and a separate
  database/volume/port. The supported extension location is explicitly `public`.
  initialize checks pg_extension and refuses to install/create the extension.
  The target schema must already exist and start with `public_preview_`.
- Provider remains injected `Embeddings`: explicit immutable model version,
  dimensions 1..2000, bounded finite nonzero vectors. Model/version and dimensions
  must match the spec before a query embedding is attempted. No new network
  embedding adapter or credentials are supplied. Real provider choice, retention,
  endpoint, tokenizer limits, input data and budget remain undecided.

## Implemented architecture

`rag_postgres.BuildSpec` binds repo/commit/model/chunker/max_chars, dimensions and
the sorted exact chunk-ID membership to one content-addressed build key. It rejects
duplicate/mixed memberships. Membership count is bounded to 20000; vectors remain
operator-owned trusted inputs, not a public upload API. All query chunks are
reconstructed from the caller's exact verified spec, not untrusted DB JSON.

Two sidecar tables: `rag_vector_builds` (building/ready/failed/cancelled, claim token,
lease and version metadata), and `rag_vector_rows` (chunk/entity IDs and vectors).
The composite rows primary key begins with build_key to scope candidate reads.

`begin` atomically inserts or replaces an explicitly failed/cancelled/expired
building claim. Active or ready builds cannot be overwritten. The caller receives
a unique token. `publish` validates a complete already-computed vector set outside
the transaction; inside one transaction it locks/fences the unexpired owner,
inserts every row and transitions to ready with a final lease fence. Any failure
rolls back. No external provider call occurs while holding a DB transaction.
`terminate` marks failed or cancelled only for the unexpired owner. A restart can
explicitly acquire an expired claim and republish a complete set; partial-batch
resume, heartbeat and automatically repeating embedding calls are not implemented.

`query` requires exact ready membership. Cosine distance is evaluated inside the
database, window-ranked by entity, then unique entities are limited by top-k with
stable chunk-ID ties. It does **not** fetch all vectors into Python. This is still
an exact scan/sort of the version's rows, not ANN. No HNSW/IVFFlat index is created.
Exact and approximate search have different recall/performance properties;
[pgvector's official documentation](https://github.com/pgvector/pgvector) documents
both. Approximate candidate expansion/refill is future work.

`module_retriever` is an explicit Python factory, not a new public API parameter.
BM25 returns the supplied lexical retriever immediately without store/provider
construction. Dense/hybrid require `enabled=True`, spec and storage. The adapter
uses existing entity RRF and complete BM25 fallback. Missing/not-ready storage and
safe storage failures become IndexNotReady; version/membership mismatch stays a
hard error. DB exception strings/DSNs are not exposed through retrieval fallback.
Provider failures retain existing sanitized ProviderError behavior.

Ready data is immutable via this adapter, so the ready check/query pair cannot race
an adapter-supported reset. Direct DBA mutations are outside the contract. This
stage has no shared content-vector payload cache, cache expiry/GC, authorization
ledger for new embedding requests, tenant ACLs, or production deployment claim.
Do not pass a real embedding provider until its separate grant/usage/retry/unknown
outcome protections have been implemented and approved. The prior 3-call chat
grant is consumed and cannot authorize any embedding calls.

## Verification and first real validation plan

16 fake-connection tests cover explicit gates/default, spec identity, missing
extension, SQL template rendering, duplicate build admission, bounded lease,
vector completeness/validation before transaction, final-fence rollback signaling,
cancel/stale owner, entity query structure, storage sanitization, mismatch before
embedding, exact fallback identity, and the injected fake query path.

These tests do not run a SQL parser/server or establish ACID/concurrency behavior.
Real pgvector integration is **not run / not accepted**. After isolated environment
approval, first use deterministic fake vectors to verify DDL, exact cosine/entity
top-k against a reference, duplicate writers, lease takeover, cancellation,
rollback, ready visibility and process crash. Do not test on the original DB.

Only after that, propose a separate tiny real embedding experiment: one fixed
public snapshot, two selected files, at most 100 chunks and one query. Provider,
exact model/revision/dimensions, recipients, explicit request/token/byte budgets,
prices and total spend must be approved first. A dedicated embedding ledger with
unknown-outcome non-replay is a prerequisite; this stage does not grant it.

No external installation/model decision is needed for the code and fake tests in
this stage. The blocked next step is real DB integration: minimally approve the
extension/image version and isolated DB resources. Real embeddings have a later,
separate provider/data/budget decision.

## Stage verification result

`rag_persistent_suites.py` used existing Python, disabled paid/live paths and blocked
socket connections: **142 distinct selected tests passed in 19.198s** (126 baseline
plus 16 new fake-connection tests). No errors/failures/skips. Repeated runs are not
added. Real PostgreSQL/pgvector integration remains unrun. `git diff --check` passes.
The four new stage files remain untracked/uncommitted on the accepted baseline.

## Subsequent approved real integration

The earlier not-run statements describe the engineering-preparation checkpoint.
A later explicitly approved isolated PostgreSQL16.15/pgvector0.8.7 run passed 17
real tests after a database dimension-constraint fix. See RAG_PGVECTOR_ACCEPTANCE.md
for preserved initial failure, exact commands, fault injection and limitations.
