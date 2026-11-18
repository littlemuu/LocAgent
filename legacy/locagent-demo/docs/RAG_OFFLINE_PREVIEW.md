# RAG offline primitives — 2026-10-15

> 本页保留原阶段的设计范围。2026-10-16 最新进展见[百炼 embedding 排错与验收边界](BAILIAN_TROUBLESHOOTING.md)：包含响应留存、索引适配、传输诊断及数值对照；后续已完成[32块/10题探索性检索与复核](BAILIAN_RETRIEVAL_ACCEPTANCE.md)，不代表通用质量或生产验收。

This is a small preparatory implementation, not an enabled Agent feature or a
verified vector database. The existing BM25/graph tool code is unchanged.

## Implemented

`locagent_service/rag_offline.py` uses only the standard library:

- `chunk_snapshot`: trusted, already verified snapshot byte mapping → AST function,
  class and residual module regions, bounded line windows, long-line character
  slices. Includes nested entities and decorators; class/method overlap is
  intentional. Metadata includes repo, fixed commit, path, entity, kind, line span,
  part, content SHA, chunker and embedding model version.
- Hidden/environment/generated directories, configuration/secret filenames and
  non-Python/binary files are excluded. Invalid Python, file/AST/snapshot/chunk
  limits fail explicitly. This filter cannot prove arbitrary Python source has no
  embedded secrets. Do not provide private unreviewed snapshots to a real provider.
- Content/model/chunker/dimension cache identities are separate from repo/commit
  membership. Identical text can reuse a vector while shifted lines or renamed
  files get new member identities. Cache is trusted operator-owned in-memory data.
- `Embeddings` is dependency-injected; no network implementation, key lookup,
  environment switch or model download is provided.
- `ExactIndex` normalizes vectors and performs deterministic cosine search.
  Shape/nonfinite/zero vectors fail. Build failure publishes no index or cache
  update; successful immutable object creation is the in-memory publication point.
- `SearchConfig` defaults to BM25 and returns the supplied lexical result object
  unchanged. Dense/hybrid are explicit library options. Hybrid callers must adapt
  lexical candidates to the same `Hit(Chunk, score)` membership space. RRF uses
  rank rather than incomparable raw scores, deduplicates per list and breaks ties
  by stable chunk ID. Cross-version retrieval is always an error.
- Missing index/provider failure is an error by default; explicit BM25 fallback
  returns `degraded=True` and a safe reason. Lexical errors remain visible.

## Explicit Agent module-search wiring

`rag_graph_adapter.GraphModuleRetriever` can be injected through the existing
GraphLocalizer `module_retriever` argument. It maps candidates to existing graph
entities, deduplicates entities and exposes positive rank scores to the graph tool.
Its last_diagnostics records degradation; task repo/commit is checked before the
tool uses it. Default BM25 returns the original lexical nodes unchanged. A fake
model tool loop exercises hybrid module search then strict finish offline.

This wiring only covers graph module retrieval, not every content-search fallback.
Dense/hybrid are not HTTP options and require explicit caller construction, verified
snapshot membership and a provider. There is no real embedding provider or pgvector
storage. Existing behavior hashes include new modules: rebuild sources/plans rather
than weakening hash checks or reusing historical grants.

## Dependencies and next storage step

Existing Python environment contains psycopg and numpy, but not the pgvector Python
package. Database containers were stopped; no database was started or queried, so
server-side vector extension availability is **unknown**. No dependencies were
installed. Memory exact search is only a deterministic reference implementation.

Proposed PostgreSQL design (not installed/migrated): vector payload table keyed by
model version, chunker version, content hash and dimension; snapshot memberships
keyed by repo/commit/config plus chunk ID, including correct entity/line metadata.
Build generations are invisible until one transaction publishes the ready pointer.
Start with exact cosine distance on a fixed dimension/model, not ANN tuning. A
rebuild can reuse payloads but must rebuild version memberships. Scope all reads
to the ready generation; never silently search a different commit. Approve the
extension/dependency and isolated database first. Native pgvector concurrency,
crash recovery, disk quotas and throughput have not been tested.

## Evaluation design

After a successful separately approved single-question live smoke, freeze disjoint
development and holdout sets by repository/problem lineage; keep expected locations
outside prompts and indexes. Compare BM25, dense, RRF hybrid, then graph expansion
with identical question/tool/token budgets. Freeze chunker/model versions and
labels before holdout; no holdout tuning. Measure chunk/entity/file Recall@K,
final localization validity and Recall, p50/p95 retrieval/end-to-end latency,
input/output tokens, embedding index/query cost and cache reuse. Record failures,
fallbacks and zero improvements; fake vectors establish correctness only.

## Small adjacent fix

`demo.database_up()` already initialized schema v3 but printed v2. Only its message
is corrected here. Two mocked tests verify v3 is printed after successful
initialization and no ready message follows a failed migration. No database was
touched and no migration semantics changed.
