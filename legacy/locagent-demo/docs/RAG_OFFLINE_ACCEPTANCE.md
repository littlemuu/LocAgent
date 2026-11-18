# RAG offline stage acceptance — 2026-10-15

Feature worktree: LocAgent-rag-preview; branch work/rag-offline-preview; base 9b12e7b5567324e23f09c7306920becd33f1e7b7. No commit/push.

## Results

| Suite | Passed | Seconds |
| --- | ---: | ---: |
| test_rag_offline.py (final, versioned chunk size) | 21 | 0.030 |
| test_demo_schema_notice.py | 2 | 0.007 |
| test_public_authorization.py | 16 | 10.253 |
| test_public_pipeline.py | 14 | 2.187 |
| test_empty_query_boundary.py | 18 | 8.592 |

Total: 71 distinct selected test methods, not added to historical 479. Earlier 20-method RAG run is superseded by the final 21-method run. Existing dependency deprecation warnings were emitted; no test failure. Commands: existing project Python with `-B -m unittest discover -s tests -p NAME`; legacy suites used command-local proxy removal, offline metadata flags and paid/live defaults disabled. Authorization tests use stubs and synthetic grants in temporary directories, not actual authority.

No full suite, PostgreSQL integration, live provider, embedding network, vector database or semantic quality evaluation was run. No original database/service was started, migrated or reset. No dependency installed. Python pgvector is absent; server extension availability remains unknown. Local pricing retrieval failed; a subsequent parent-provided official-page check is attributed in the updated proposal. The <=CNY 1 input-token proof remains unavailable and blocks that lower-budget admission.

## Changed files and learning order

1. docs/PUBLIC_SINGLE_SMOKE_PROPOSAL.md: exact question/model/budget proposal and two linked API tasks; no authorization implied.
2. docs/RAG_OFFLINE_PREVIEW.md: scope, interfaces, storage design and evaluation plan.
3. locagent_service/rag_offline.py: Version → Chunk → chunk_snapshot → ExactIndex → rrf → search. All standalone and standard-library only.
4. tests/test_rag_offline.py: deterministic fake embedding tests.
5. locagent_service/demo.py: v3 success text only.
6. tests/test_demo_schema_notice.py: mocked successful/failed migration notice regressions.
7. This acceptance record.

Default BM25 implementation is untouched. The new optional library adapter preserves lexical object identity; existing BM25 boundary suite passed. At this first checkpoint dense/hybrid were not wired to Agent tools. The later explicit module adapter is recorded below; HTTP exposure and pgvector persistence remain absent. Fake vectors are correctness fixtures, not evidence of improved retrieval. Cache is trusted in-memory storage; no disk publication/concurrency or complete sandbox claim.

Original learning tree retains its uncommitted README; no automatic commit, stash or overwrite. Existing public-pipeline worktree remains clean. A complete tracked+untracked patch is supplied separately as LocAgent-RAG-Offline.diff. Behavior hashes necessarily change with new modules: new live smoke needs a fresh prepared source/plan, never reset historical grants.


## Subsequent module wiring and budget correction

- Added locagent_service/rag_graph_adapter.py, injected via the existing GraphLocalizer module_retriever argument. util/localizer.py validates adapter repo/commit before retrieval. BM25 default identity is unchanged; graph IDs are constrained to the supplied membership. HTTP remains unchanged.
- Added explicit plan-bound ProviderConfig.disable_thinking (default false) and request serialization when true. This fixes the discovered mismatch where the prior public authorization payload removed the shared disabled-thinking parameter. No old grant is changed or replayed.
- Updated proposal uses deepseek-flash / DeepSeek-V4.1-Flash and attributes current official prices to the parent-provided check. Exact response model allowlist, raw ID/usage checks and unknown-outcome handling are documented.
- CNY 7 originated from three full-context reserves (6.316032 total). <=CNY 1 is blocked by missing provider/tokenizer/template token upper-bound proof. A conditional 65536-input-token arithmetic estimate is NOT a valid implemented hard cap; no context/budget guard was weakened.

Additional verification: test_rag_graph_adapter.py 6 passed (9.834s); affected test_public_authorization.py 16 passed (8.284s, repeat of earlier suite); original test_stage1_localizer.py 34 passed (7.960s). The original 71 comprises 21 RAG + 2 schema notice + 16 authorization + 14 public pipeline + 18 BM25 boundary. Do not add repeated authorization or failed attempts as new coverage.

Integration test limitations: fake model and fake embeddings exercise module retrieval and strict finish through real GraphLocalizer/graph tools. Unchanged content fallback is explicitly stubbed empty. Earlier new test runs failed due to a wrong test option name, synthetic graph line-span mismatch, and missing content fallback fixture; final corrected test passes. These failed attempts are not reported as live pipeline bugs or hidden passes. No real provider, embedding, DB migration, pgvector or broad quality evaluation occurred.

Final diff includes tracked modifications and all untracked feature files. Learning README remains untouched by this branch. No commit/push.

## Later review and approved smoke attempt

Fallback P2 fixed and independently re-reviewed; adapter suite now 8 passed (9.535s).
The earlier no-DB statement describes that offline checkpoint. A later explicitly approved
isolated database/API/worker attempt failed during GitHub resolving, before grant or model calls.
See PUBLIC_SINGLE_SMOKE_ACCEPTANCE.md for evidence, cleanup and remaining blockers.

## Approved continuation completed

The same approved smoke subsequently completed: 3 settled HTTP requests, 14155 input/428 output tokens, conservative CNY0.031734, reserve0. The original static failure evidence remains. Download diagnostics: 4 tests pass, pipeline14 and authorization16 regressions pass; independent review passed. See PUBLIC_SINGLE_SMOKE_ACCEPTANCE.md for full accounting and limits.
