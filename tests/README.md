# Offline regression tests

Run from the LocAgent repository root with the existing CPU virtual environment:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The combined suite contains 403 unittest methods (357 baseline, 24 candidate-guidance,
10 experiment-axis and 12 bounded-finish regressions). The full 403-test run passed
after the bounded-finish implementation; the later fixture precision correction reran
only its 12 affected tests. The independently reviewed 57 related tests overlap this
suite, so these counts must not be added together. The Stage 2 baseline
had 61: the original 48 (10 return-trace, 4 request-contract and 34 Stage 1 tests)
plus 13 Stage 2 contract, fixture and HTTP boundary tests. Install `requirements-service.txt` for Stage 2.
The pure suite needs no PostgreSQL, pytest or credentials.

The original return-trace tests use a small in-memory graph and the real entity
search, formatting and ledger functions. They do not run the main loop or load
saved fixtures. Tool observations include the newline added by `print()` in
`execute_ipython`.

The return-trace and Stage 1 modules enable socket guards before tool imports
and through their tests. DNS, TCP/UDP attempts fail, including attempts that an
imported library catches internally. Offline Hugging Face flags prevent dataset
downloads, and LiteLLM uses its bundled price metadata. Stage 2 fixture execution
also blocks Python network calls and real completions. Pure HTTP tests use a
FakeStore; they cannot prove PostgreSQL or independent worker execution.

The 10 return-trace tests cover source-independent repeat detection, changed
content and entity isolation, legacy histories, JSON round trips, current
observation messages, the suppression switch, unseen repeats, removed context,
short responses and folded entity hints. Original code stays in the ledger even
when the tool output is shortened.

The Stage 1 tests exercise the shared main loop, real graph tools, result
parsing, provider failures, state cleanup, path safety and the legacy queue
wrapper with fake providers. They prepare a small BM25 index and pickle fixture
in temporary directories and remove them on exit. They do not depend on saved
`outputs/day1` fixtures or call a real model.

Additional regression cases cover root-level files, unsafe root paths, legacy
nested-path parsing, and strict finish arguments with a matching isolated schema.

See [Stage 1 acceptance](../STAGE1_ACCEPTANCE.md) for the contract, resource and
concurrency boundaries. When the historical fixtures exist, run:

```sh
.venv/bin/python -B tests/run_historical_smokes.py
```

This runner checks `day4_return_trace_smoke.py`, `day5_main_trace_smoke.py` and
`day6_repeat_output_smoke.py`, including the legacy IPython path and trajectory
persistence. It requires saved files under `outputs/day1`, blocks TCP/UDP/DNS
and live completions, and allows local AF_UNIX IPC for multiprocessing.Manager.
Day5 creates a new output run directory without overwriting older artifacts.

Stage 2 real database/process acceptance is separate and fails when PostgreSQL
is unavailable (no SQLite or mock fallback):

```sh
.venv/bin/python -B -m locagent_service.demo db
.venv/bin/python -B tests/run_stage2_acceptance.py
```

The 13 real PostgreSQL tests cover short committed claims, concurrent claimers,
SKIP LOCKED, owner/token and terminal constraints, separate API/worker processes,
HTTP results, process restart persistence and the explicit running residue after
a worker is killed. Each test cleans up only its own generated schema/processes.
See [Stage 2 acceptance](../STAGE2_ACCEPTANCE.md) for demonstration and limits.

## Stages 3–5

sh scripts/check_local.sh runs all offline unit/HTTP/config/budget regressions.
Add --postgres to run 35 distinct actual PostgreSQL/process tests (32 existing plus
3 exact prepared-input HTTP/worker/admission regressions), including
the inherited Stage 2 regressions. Start the existing local demo PostgreSQL
container first or set LOCAGENT_DATABASE_URL.
Every database test owns and cleans only its unique temporary schema.

Add --compose to build the portable runtime and verify a brand-new Compose
volume: empty schema, API health, task closure, key replay/conflict, provider
failure, worker SIGKILL recovery and PostgreSQL restart. The runner stops its
containers but deliberately retains all volumes and logs.

See STAGE3_ACCEPTANCE.md, STAGE4_ACCEPTANCE.md and STAGE5_ACCEPTANCE.md for
fixed-source preparation, live-pilot results, precise evidence and limitations.
Offline fixture reports deliberately contain no model quality/token/cost claims.

The v2 budget adds 22 regressions, including actual child death after reservation,
concurrent durable arm quotas, atomic-save faults, account pricing gates and env-file
preservation. One test exercises the installed LiteLLM/OpenAI adapter with httpx.send
intercepted before network I/O: a timeout makes exactly one request attempt with
max_tokens=512, thinking disabled and SDK max_retries=0. No real key or call is used.

Ten further authorization regressions cover competing processes/directories, a
second run after six calls, unknown outcomes, copied ledgers, partial initialization,
and full pricing validation before any env-file loader. All use temporary markers;
these tests do not consume or reset real authorization. The approved real pilot has
separately completed six calls; its authorization and full reservations remain retained.

Six ledger-path regressions cover file/directory symlinks, relative paths, changes
to working directory or input alias, environment aliases and ten-process contention.
All aliases share one canonical ledger and lock; atomic replacement preserves links.

Fourteen exact-zero recovery/gate regressions cover consumed/unknown rejection,
eight-process competition, interrupted audit persistence, worker-lock contention,
aliases, the 64KiB boundary and integration with the paired evaluator. Real authority
is not migrated by these tests; all budgets and providers are temporary/offline.

The five-sample follow-up uses separate temporary authorization in all tests.
Missing original HTTP usage, settlement persistence failures and process death keep
full reservations and prohibit replay. See [follow-up acceptance](../FOLLOWUP5_ACCEPTANCE.md).

## Offline repair of five-sample failures

`test_bounded_protocol.py` covers actual graph root aliases, strict final-only
submission, length/missing-finish/iteration-limit diagnostics, exact graph IDs,
per-run continuation, UTF-8/JSON byte bounds, original-output retention,
unseen-tail suppression safety and legacy result serialization.

With the retained local benchmark artifacts, these additional runners make no
model/network calls and require a **new** output directory on each execution:

```sh
.venv/bin/python -B tests/run_offline_repair_acceptance.py --output outputs/stage4/repair-forensic-new
.venv/bin/python -B tests/run_prepared_protocol_smoke.py --output outputs/stage4/repair-prepared-new
```

The forensic runner verifies historical artifact hashes and reuses already-settled
HTTP responses. Its synthetic final response is deliberately empty; it does not
rescore old results. The preparation runner builds a new manifest/index in its own
registry from the exact local Git commit and uses only a synthetic provider.
See [offline repair acceptance](../OFFLINE_REPAIR_ACCEPTANCE.md).

The independently reviewed bounded five-sample round completed 30 real calls; its one-time authorization and every group quota are consumed. Temporary-ledger tests never consume real authorization. See BOUNDED5_ACCEPTANCE.md for actual results and retained evidence.

## Entity submission guidance repair

`test_submission_guidance.py` constructs a tiny graph using the real source
analyzer, exercises actual search/read/tree tools and the bounded loop, and
verifies displayed exact IDs/types against the unchanged strict finish validator.
Variable/file/directory entities remain invalid. Constructor source stays in its
class even though there is no separate `__init__` node. Legacy display, repeat
suppression and unread-tail safety are covered.

`fixtures/invalid_finish_cases.json` contains only the original finish argument
strings, commit IDs, source response hashes and minimal graph node/type facts
from four historical failures. Each portable regression mixes a known-valid
target with an invalid entity and verifies rejection, empty locations and zero
score. It needs no saved indexes, raw responses, credentials or model calls.
These are mechanical regression fixtures, not new quality measurements.

See [entity guidance acceptance](../ENTITY_GUIDANCE_ACCEPTANCE.md) for the 196
offline tests, separate real PostgreSQL/process tests, preserved historical
results and the candidate commit boundary.

## Frozen 20 compatibility repair

`test_expanded_compatibility.py` rejects escaping/chained/cyclic/code/special links,
submodules, missing or changed Git Python blobs, forged source IDs, changed manifests,
artifacts and problem text. It checks 8,000/32,768 character boundaries, full 22,778
character text, multi-target recall, explicit empty function truth, failed/missing
rows, constructor truth preservation and gold sentinels outside model/index inputs.

`stage4_compatibility_postgres_acceptance.py` runs real HTTP, PostgreSQL and a spawned
worker. Its test-only `prepared_offline_worker.py` uses the actual prepared-source
engine with scripted provider responses. It verifies input hashes and exact full
problem text, and confirms historical reads/idempotent replay after source removal.
Production worker behavior and paid authorization are not replaced by this helper.

Historical 25-source / 50-arm compatibility results are summarized in
[the acceptance report](../EXPANDED20_COMPATIBILITY_ACCEPTANCE.md).
Scripted empty finishes establish compatibility only; their quality metrics are null.


test_label_mapping.py fixes pure insertion attribution using the patched AST and
exact base qualified names. Class properties inserted before a method do not mark
the unchanged method; an indented insertion after a body's trailing blank still
belongs to that function. Deleted functions remain truth and genuinely new
functions are disclosed separately. The reviewed frozen cohort has 18 applicable
tasks and 27 function targets; the unrepresentable constructor remains in truth.


test_finish_compatibility.py runs the real offline GraphLocalizer loop for legacy
success, valid empty, iteration exhaustion and bounded invalid/missing/truncated
finish outcomes. A validated legacy success/empty status is terminal evidence;
bounded diagnostics take precedence. Ambiguous completed records make the
aggregate finish count/rate unavailable and expose an unknown count, while
failed/missing tasks keep their fixed-denominator zero. Location validation and
recall scoring are unchanged. These are scripted arithmetic tests, not live scores.


## Phased offline runner

test_phased.py uses temporary ledgers/owner markers and scripted original response
bytes. It includes four-process initialization contention, competing phase starts,
actual process exits at reservation/send/raw/settlement/result/checkpoint boundaries,
owner-head torn writes, explicit blocked audits, rollback/corruption, wrong plans,
per-arm quota, exhaustion before the next full reservation, replay request divergence,
fixed first-five denominators and actual isolated-arm parent death.
No test consumes an existing paid authorization. The separate retained full25
acceptance runs all 50 arms through real fixed-source GraphLocalizer child processes;
fake transport validates mechanics, not accuracy or token/cost improvements.


test_engine_binding.py mutates isolated source copies across 19 behavior categories
(execution, schemas/parsing, tool output, retrieval/index, prompt/query resources,
package initializers, offline guard, scoring, source validation and accounting).
It rejects content changes, new/deleted files, links and incomplete legacy source
maps. A static import closure check catches newly introduced project dependencies
outside the declared packages. Credentials, caches, tests and generated outputs
are excluded and covered by a negative control.


test_phased_http.py uses HTTPX MockTransport with the Python offline network guard.
Synthetic approved records exist only in TemporaryDirectory fixtures; the paid switch
stays 0 and the test replaces its gate locally, never creating a production approval.
Cases include HTTP success/redirect/4xx/5xx, timeout/post-send disconnect, partial or
invalid response/usage, request gating, reserve/raw/settlement disk failures, actual
process exits after send/raw/settlement/checkpoints, concurrent one-time admission,
duplicates, revoked/expired/wrong-scope approvals, and a complete 120-call shared
two-stage ledger. Historical raw-adapter tests remain part of the full suite.


test_response_storage.py reproduces a 6 MiB HTTP error and multiple valid 3 MiB
responses. It checks single-body and cumulative overflow (including a valid JSON
prefix that must not settle), full-store preflight, missing/hash-changed references,
publication disk failure, actual death after body publication but before reference
commit, ready-ledger evidence loss, path/link/overwrite rejection, and bounded JSON
writes. All tests use temporary stores and synthetic HTTP responses.

See [offline failure terminal acceptance](../OFFLINE_FAILURE_TERMINAL_ACCEPTANCE.md) for terminal failure, unverified-executor audit, historical response replay and explicit timing semantics. These tests use temporary owners and never resume historical paid ledgers.


The phased v3 safe-failure suite is test_settled_arm_isolation.py. It uses handwritten synthetic response bodies, temporary approvals and owners, MockTransport, real local subprocess exits/crashes, and the independent 256-condition oracle. See SETTLED_ARM_ISOLATION_ACCEPTANCE.md; no paid calls or old-ledger recovery are part of these tests.


## Portable phased fixtures

phased_test_support.py constructs synthetic cohorts and malformed JSON bodies, never saved provider responses. Phase/HTTP/storage tests use those cohorts; binding tests write synthetic configuration into isolated source copies. The operational phased_cohorts.json, original response fixture directory and outputs are not required for unittest discovery. The 256-condition oracle is enumerated independently in the helper. Optional historical smoke runners require retained local data and are outside portable discovery. No test activates real authority or executes a benchmark repository. See [real-run summary](../NEW20_REAL_EVALUATION.md); synthetic metrics do not measure model efficacy.

## Optional candidate guidance

See [candidate guidance acceptance](../CANDIDATE_GUIDANCE_ACCEPTANCE.md) for the default-off core option, trusted visible evidence, repeated-query recovery, budget tradeoffs and standalone offline commands. These regressions are synthetic boundary checks, not measured localization improvement.

The ten test_guidance_experiment.py methods cover explicit plan/approval axis
binding, suppression fixed off, balanced order, 2+8 scoring and function NA
denominators, subprocess flag propagation, raw returned-model consistency,
full-reservation budget stops, and unknown outcomes with no replay. They use
synthetic data and no provider traffic.


## Bounded budget closing

See [bounded finish offline acceptance](../BOUNDED_FINISH_ACCEPTANCE.md). The twelve
new test_budget_finish.py tests cover exhausted tool delivery, paired skipped calls,
one finish-only remaining iteration, unchanged provider cost/quota gates, UTF-8 and
request bounds, visibility isolation and strict terminal failures. They use scripted
responses and temporary ledgers; they do not measure model efficacy.
