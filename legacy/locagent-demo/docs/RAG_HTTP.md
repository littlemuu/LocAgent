# RAG HTTP integration

The asynchronous task API now persists an explicit retrieval configuration and
passes it through the worker to the existing graph retriever. Omitted settings
retain the original BM25 behavior. Task schema stays at version 3: request,
progress and result are already JSONB. No task/lease/fencing semantics change.

## Run the no-cost integration demo

From the repository root, with Docker Desktop running:

```sh
docker compose --env-file /dev/null -p locagent-rag-http up -d --build --wait
curl -sS http://127.0.0.1:18080/tasks \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: rag-demo-1' \
  -d '{"source_id":"demo-v1","problem_statement":"Locate rendering behavior","retrieval":{"mode":"hybrid"}}'
curl -sS http://127.0.0.1:18080/tasks/REPLACE_WITH_RETURNED_UUID
```

Use `dense`, `hybrid`, or the default `bm25`. The demo uses real graph tools,
BM25, exact cosine search and RRF, but **synthetic two-dimensional embeddings and
a scripted LLM**. It is an integration fixture, not semantic retrieval quality
evidence. There are no model downloads, live embeddings, API keys or paid calls.
The RAG Compose image is named `locagent-rag-service:local`, separate from the
original service checkout. Linux ARM builds compile the pinned PyStemmer using
container-only Debian build tools; pip versions remain constrained by the existing
requirements files and downloaded wheels are cached by BuildKit.

The existing Compose file binds only the API to loopback and keeps PostgreSQL
on its internal network. It does not need pgvector for this ExactIndex path.

`docker compose --env-file /dev/null -p locagent-rag-http down` stops the services
and retains the database volume. Reusing that project restores the task history.
Do not add `--volumes` when retaining history.

## HTTP contract

The new top-level `retrieval` object accepts:

| Field | Meaning |
| --- | --- |
| `mode` | `bm25` (default), `dense`, or `hybrid` |
| `fallback` | `error` (default), or explicit `bm25` on unavailable query embeddings |
| `top_k` | Strict integer 1–50, default 10; bounds dense/hybrid module results |
| `index_id` | SHA256 of an operator-provided immutable cache JSON; required for non-demo dense/hybrid |

The HTTP request never accepts a filesystem path, credential, endpoint, provider
or model selector. `demo-v1` always uses its fixed fixture and rejects `index_id`.
Existing prepared/live authorizations remain BM25-only; changing the retrieval
path cannot reuse an old model-call grant. A public `github-v1` task without
authorization retains its existing scripted model and fixed empty final answer.

The configuration participates in idempotency comparison and survives request
deserialization, worker retries, GET polling, and service/database restarts.
The resolved public commit remains fenced in `progress` by the existing worker.
Changing a retrieval mode under an existing idempotency key returns 409.

`result.diagnostics.retrieval` reports requested mode, actually executed modes,
search count, degradation/reasons, pinned index identity, embedding kind and
repository/commit/model/chunker version. Exact entity lookup can finish without
using vector search: then executed modes is empty, not a false RAG claim.
The mode controls **module retrieval**. Exact entity lookup and the separate
existing BM25 content search remain available. No accuracy claim is added.

Missing/tampered caches, mismatched repository/commit/content, malformed vectors,
or a missing query vector fail with a sanitized `rag_unavailable` task error.
Explicit query fallback reports BM25 and `degraded: true`. A later successful
search cannot erase an earlier degradation. An error swallowed by tool feedback
still fails the task. Foreign/malformed cache identities never silently fall back.

## Existing vectors for a public repository

This phase adds a **cache-only** boundary. It does not enable an embedding API.
An operator may configure the same canonical absolute `LOCAGENT_RAG_CACHE_ROOT`
for the worker and mount that directory read-only. A cache is named
`<sha256-of-exact-file-bytes>.json`; its hash is the task's `retrieval.index_id`.
The cache is checked again on each execution. The normal public-preview isolated
schema/root requirements still apply; see [public preview](PUBLIC_REPOSITORY_PREVIEW.md).

The JSON format is:

```json
{
  "format": "locagent-rag-cache-v1",
  "version": {
    "repo": "owner/repository",
    "commit": "40-character-commit-sha",
    "model": "explicit-existing-embedding-model-version",
    "chunker": "python-ast-lines-v2",
    "max_chars": 2000
  },
  "dimensions": 2,
  "vectors": {"chunk-id": [1, 0]},
  "queries": {"sha256-of-exact-UTF8-query-text": [1, 0]}
}
```

Use the existing `Version` and `chunk_snapshot` primitives to derive chunk IDs
from the verified snapshot, retaining chunks whose entity IDs are in its graph.
Document membership must match exactly; query vectors must use the same embedding
model and dimensions. The format example is illustrative, not an actual cache.
Production vectors/query caches have **not** been migrated. Uncached new questions
cannot run dense/hybrid until an explicitly authorized embedding boundary is
implemented or their original cached query vectors are supplied. No historical
experiment authorization, result, vector or ledger is fabricated or regenerated.

## Verification

`tests/test_rag_http.py` covers request compatibility, actual dense/hybrid engine
calls, cache identity and content checks, explicit fallback, failure propagation,
and HTTP serialization/reloading. Its HTTP storage is a labeled test double.
`tests/run_stage5_compose.py` separately exercises real HTTP, PostgreSQL, Linux
worker, hybrid completion, retrieval idempotency conflicts, dense worker SIGKILL
recovery and database restart persistence. It creates a unique isolated project
and retains its volume/logs. Build the service image first, then run:

```sh
PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH" \
  .venv/bin/python -B tests/run_stage5_compose.py
```

Migration logs remain under `outputs/migration-20261030/`. Historical frozen
experiment files and the real pgvector test database remain separate requirements;
they are not supplied by this integration.


## Local acceptance — 2026-10-31

- Relevant offline regression: 93 / 93 passed; final affected integration check:
  11 / 11 passed; after adding the page: 24 / 24 passed. No network attempts.
- Full Mac regression: 705 discovered, 697 run, 667 passed, 1 failure,
  11 error records, 19 skips. The failure/error/skip identities are unchanged
  from migration: Linux prctl, missing historical frozen artifacts, and the
  unconfigured real pgvector database. Eight tests did not run after a class
  setup failed on missing historical files.
- Real Compose acceptance passed in `locagent-acceptance-5f7cc02da8`:
  hybrid completion, retrieval idempotency conflict, dense worker SIGKILL
  recovery to attempt 2, PostgreSQL restart persistence and subsequent task.
  See `outputs/stage5/locagent-acceptance-5f7cc02da8/evidence.json`.
  Containers stopped; the isolated acceptance volume is retained.
- Docker Desktop 4.97.0 / Engine 29.9.2, Linux ARM Python 3.10.22.
  Container behavior-hash inputs were checked successfully (139 files).
- The minimal same-origin page was added only after that RAG acceptance passed.
  A real Chrome submission completed and displayed `demo.py:render` plus code
  evidence. Reload restored task `92b96b5e-a5ac-4fdc-a64f-c58b776ba7b1`;
  the development database count stayed at 1, with no duplicate submission.

Current local page: <http://127.0.0.1:18080/>. Its running Compose project is
`locagent-rag-http-20261031`, volume `locagent-rag-http-20261031_pgdata`.
The page supports task submission, polling, cancellation, task-ID restoration,
result/evidence display and explicit fixture/degradation labels. Existing
public-preview configuration requirements still apply; default Compose enables
only the no-cost demo. No history playback or real semantic accuracy is claimed.
