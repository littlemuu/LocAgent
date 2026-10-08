# Offline regression tests

Run from the LocAgent repository root with the existing CPU virtual environment:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The combined suite currently has 132 unittest methods. The Stage 2 baseline
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
