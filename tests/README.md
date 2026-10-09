# Offline regression tests

Run from the LocAgent repository root with the existing CPU virtual environment:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The combined suite currently has 196 unittest methods (the previous 180 plus
16 graph submission guidance and saved-invalid-finish regressions). The Stage 2 baseline
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
Add --postgres to run 32 distinct actual PostgreSQL/process tests, including
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
