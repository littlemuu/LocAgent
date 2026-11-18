# Single approved smoke — completed 2026-10-15

## Final outcome and evidence chain

The same approved experiment completed after one static-only retry. The original
failed task and zero-call/no-grant evidence remain intact below and in
`outputs/public-single-20261015/`. No actual model call counter was reset.

- Successful static task: `3bc0bce4-ccd4-4a2f-854a-169e5a3b25c4`, attempt 1, completed.
- Live task: `40b536f0-15e6-4bae-80a8-4bc305c47339`, attempt 1, completed/result success.
- Exact repo/commit/question/model/endpoint and CNY 7 / 3-call approval are unchanged.
- New source: `prepared-287672318b943a8b8220861db037c9cf03c655e48b56b06dd9683b940230cdbe`.
- Plan/authorization SHA256: `8145cc80a73ff96ce8cd4085d79429eeab5730269743ee1f44e5f76e50345226`.
- Source and plan were generated after diagnostics code/test review froze the engine.
- Durable continuity, plan, submission, task, attempts, cleanup and audit evidence:
  `outputs/public-single-20261015-resume1/`. Private authorization, ledger and immutable
  raw responses remain there; only the whitelist audit summary is copied for delivery.

## Actual model requests and budget

Exactly **3** calls, each HTTP 200 and `settled`; no retries, unknown outcomes or
further model requests. Each response returned exact model `deepseek-flash` and a
nonempty raw request ID. Plan bound `disable_thinking=true`, output cap 1024 each.
All three immutable response sizes/hashes verified using `response_store.read`.

| Call | Input tokens | Output tokens | Conservative CNY |
| --- | ---: | ---: | ---: |
| 0 | 3460 | 150 | 0.008120 |
| 1 | 5742 | 106 | 0.012332 |
| 2 | 4953 | 172 | 0.011282 |
| Total | 14155 | 428 | **0.031734** |

Ledger `finished=true`, `halted=false`, `reserved=0`; task ID matches. The amount is
the local conservative settlement at approved peak uncached CNY2/M input and CNY8/M
output, **not a claim about the provider account's final bill**. It is below CNY7.
The three-call allowance is exhausted; do not reuse this grant for another question.

## Manual correctness check

Returned entities include `src/itsdangerous/timed.py:TimestampSigner.unsign` and
`TimestampSigner.validate`. At the fixed commit, lines 138–146 check supplied
`max_age`, calculate age, and raise `SignatureExpired` when `age > max_age`.
`validate` at lines 160–167 delegates to `unsign` and returns false on `BadSignature`.
Thus the result contains the actual rejection site and a relevant wrapper.
It also returns five files and extra exception modules: correct central localization,
but broader than minimal. This is one manual smoke check, not a retrieval-quality
benchmark or proof dense/hybrid is better. This live path used default BM25.

No downloaded repository tests, installs or project code were executed. Only static
preparation and the existing LocAgent runtime were used.

## Download diagnosis and regression

First failure root cause remains unknown because the old implementation suppressed
transport details. A later DNS/TCP/TLS probe and one metadata GET succeeded, and the
new static attempt then completed. No observed 403/429 supports a rate-limit claim;
no proxy, DNS-pinning or TIME_WAIT root cause is asserted.

`public_repo.py` now records fixed transport stages and bounded exception categories
with numeric errno; HTTP status and numeric Retry-After/rate-limit fields are retained.
`public_pipeline.py` attaches this to claim-fenced progress and correlated logs.
No exception strings, URLs/paths, body, Authorization headers or credentials are logged.
No automatic retry added; public-IP validation, pinned connection, TLS verification,
no redirects, and size/time limits remain. Four new tests cover timeout cause chain,
403/429 numeric backoff, header filtering and TLS cleanup.

Commands used existing Python with command-local proxy removal and offline flags:
`python -m unittest discover -s tests -p test_download_diagnostics.py` — **4 passed (0.136s)**;
`test_public_pipeline.py` — **14 passed (5.180s)**;
`test_public_authorization.py` — **16 passed (8.670s)**;
`git diff --check` — passed. Independent read-only review passed and independently
ran the four diagnostic tests. Earlier adapter 8-method pass remains valid.
No full-suite rerun, pgvector, real embedding or broad quality benchmark was run.

## Isolation and cleanup

`single_smoke_resume1.py` restarted only the previously created owned PostgreSQL
container and reused its isolated schema without migrations/resets. Old failed task
remains in the database. Outputs/source/authority for the continuation are separate.
The script stopped its API, worker and container in finally; database volume remains.
Original demo remained stopped, learning README hash unchanged. No old ledger read,
reset or replay, no dependency installation, commit, push, PR or deployment.

Reviewable split suggestion (not committed): (1) offline RAG/versioned adapter and
tests, (2) bound non-thinking setting plus schema message fix, (3) safe download
diagnostics and tests, (4) design/runbook/acceptance documentation.

Remaining work: first-download root cause cannot be reconstructed; observe future
failures with the new diagnostics. Dense/hybrid HTTP configuration, persistent vector
storage, real embeddings, broader accuracy evaluation and stronger runtime isolation
remain future work. Do not claim this prototype is safe for unrestricted public hosting.

---

# First static attempt — preserved history (2026-10-15)

## Outcome

Blocked before live authorization. Static API task `797c21a2-1230-4d2a-ae92-53c1e2d7e485`
failed on its first and only attempt at `resolving`, code `download_failed`, diagnostic
`27b3534371324516a5617e009ef5971d`. No final localization result is available.
This does not establish a model or retrieval quality result.

Model HTTP requests: **0**. New grant/ledger: **not created**. Settled model cost: **CNY 0**;
unknown-outcome reserves: **none**. No model retry or repeated static submission occurred.

## Approval and exact intended scope

Human approval `Sentinel_57f25fc6b9088191984766b98e49ba23` allowed one task for
https://github.com/pallets/itsdangerous at `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`:
“Where does the library reject an expired signed value when a maximum age is supplied?”
Official DeepSeek endpoint, `deepseek-flash`, thinking disabled, max 3 actual HTTP requests,
1024 output tokens per call, new CNY 7 budget. The failure occurred before generating
the fresh engine-bound plan. These approval values were never used to bypass a guard.

## Offline review and verification

Independent review found no added live authorization/budget blocker. Its P2 finding
was fixed: hybrid-to-BM25 fallback now returns the original lexical result object,
preserving all nodes, order and scores. Missing-index and provider-error regressions
were added. `test_rag_graph_adapter.py`: **8 passed, 9.535s**; independent re-review passed.
This supersedes the earlier 6-method adapter result. Other earlier suite results remain
in RAG_OFFLINE_ACCEPTANCE.md; no full-suite rerun is claimed. `git diff --check` passed.

## Isolation and commands

Executed one-shot `single_smoke_runner.py` using existing project virtualenv Python.
Started existing trusted `postgres:16-bookworm` image with `docker run --pull=never`:
container `locagent-public-single-20261015`, separate preserved volume of the same name
plus `-data`, loopback PostgreSQL 55440, database `public_single`, schema
`public_preview_single_20261015`. Ran `python -B -m locagent_service.db` only against
that database; own API on loopback 18090 and own worker. Submitted the fixed public
request using idempotency key `public-single-20261015-prepare` and polled task/attempts.

Runner finally stopped its API/worker and container, preserving output and volume.
Original `locagent-stage2-pg` remained stopped. Original learning README SHA256 before
and after is `6858a33beaf68c0e4a9d561891e864dd1fc672afc0a5aa5b3ecd7a428755370a`. No original database migration, dependency installation,
embedding request, historical ledger read/replay/reset, commit, push or deployment.
Credential presence was checked through the existing strict local loader; no value
was printed or persisted. No live worker was started, so it received no credential.

## Evidence and remaining work

`outputs/public-single-20261015/` preserves submission, terminal task, attempt history,
worker/API logs, cleanup and optional separate network diagnostic. The latter is a
bounded TCP/TLS probe of public api.github.com; it does not resubmit the task.
A later probe passed public DNS, TCP and verified TLS. This does not prove the earlier
HTTP GET succeeded or identify its root cause. `fetch` currently normalizes transport
exceptions to `download_failed`; no unsupported proxy/TIME_WAIT cause is asserted.
Investigate the earlier HTTP acquisition failure before a new static attempt. Do not silently
enable inherited proxies or weaken pinned public-IP/TLS checks. Fresh source/plan and
one-shot grant are still required; real-model correctness and actual usage remain unrun.
Dense/hybrid HTTP exposure, real embeddings and pgvector persistence remain out of scope.
This prototype is not claimed safe for public deployment or a complete sandbox.
