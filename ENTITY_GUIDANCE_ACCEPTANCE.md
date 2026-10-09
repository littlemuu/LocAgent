# Entity submission guidance acceptance — 2026-10-09

## Result and boundary

Implemented in `/home/lenovo/projects/LocAgent` on `work/locagent-baseline`,
HEAD `54fcb660d4a886e7f0675ed419b3a4ed21aa3fb6`. The previous 20 uncommitted
files were backed up before this repair. No applicable repository/ancestor
AGENTS.md or .agents skill was found.

This task made **zero paid calls** and rebuilt **no existing repository/index**.
The graph builder, exact all-or-nothing finish validator, scoring and worker
isolation were not changed. No credential or .env edits, authorization reset,
historical rescoring, commit or push occurred. The complete current change set
is prepared for independent review; a local commit must wait for review approval.

## Minimal repair

- Bounded search/read/tree output now derives submission metadata from actual
  graph nodes: exact IDs, node types and valid files/entities payloads.
- Only existing function/class IDs belong in entities. Files, directories and
  variable/assignment aliases do not. Variables use their existing file ID only.
- A class with no separate `Class.__init__` node advertises its own class ID.
  Requesting that absent constructor explains the boundary and points to the
  class; constructor source remains available inside the class's full source.
- The finish schema, system guidance and forced final-round reminder state these
  same rules. One invalid item still rejects the whole payload; nothing is
  silently removed, normalized or salvaged.
- Metadata is opt-in for bounded-v1. Legacy output remains unchanged. Internal
  flags cannot be overridden by model arguments. Repeat detection includes the
  metadata; paginated/unread source remains unmarked as seen.
- The traversal formatter is included in future preparation engine hashes.
  Old manifests, plans, source registries and indexes were not edited or rebuilt.
  Temporary tiny test fixtures are not benchmark index regeneration.

## Portable regression provenance

`tests/fixtures/invalid_finish_cases.json` retains four original finish argument
strings, frozen commit IDs, original response SHA-256 values and the minimum
actual graph node/type facts needed for strict validation. It contains no raw
response bodies, usage/account data, credentials, authorization markers or indexes.

| Saved case | Invalid entity | Known-valid target also present |
| --- | --- | --- |
| 2317 off | `requests/compat.py:builtin_str` (assignment alias, absent node) | `Session.request` |
| 2317 on | `requests/compat.py` (file placed in entities) | `Session.request` |
| 863 off/on | `requests/models.py:Request.__init__` (absent node) | `Request.register_hook` |

All four original mixed submissions remain `invalid_finish`, with empty
locations and zero score. The tests do not delete the bad item or award the
valid item's score. The saved responses are not replayed against a provider.
The evaluator's live-shaped envelope in the test is synthetic input solely to
verify zero scoring; it is not a new live run or quality measurement.

The real source analyzer is also exercised on tiny temporary source: assignments
and constructors have no separate node, but class source retains the constructor.
Actual search/read/tree outputs are checked against the strict validator, along
with function/file differences, legacy display, final guidance, repeat folding,
pagination and forbidden model overrides.

## Verification

Evidence directory: `outputs/stage4/entity-guidance-repair-20261009/`.

| Check | Result | Evidence |
| --- | --- | --- |
| New focused regressions | **16 passed**, 4.711 s | `targeted-tests.log` |
| Full offline/unit/HTTP/budget suite | **196 passed**, 16.746 s | `full-offline.log` |
| Real PostgreSQL/process suite | **32 passed**, 75.179 s | `postgres-process.log` |
| Historical Day 4/5/6 scripts | **3 passed**, network/live calls blocked | `historical-smokes.log` |
| Protected existing artifacts and .env | **2042 hashes unchanged** | `before.json` / `verification.json` |
| Retained PostgreSQL history | Same 7 task rows and schema-version row, same content hashes | `postgres-results.json` |
| Formatting and candidate boundary | `git diff --check` and reverse-apply check pass | `candidate.json` / `verification.json` |

The first focused run found two incorrect source line ranges in the newly written
test fixture. Those fixture ranges were corrected; production validation was not
relaxed. The final focused and full runs above passed.

Only the existing labeled `locagent-stage2-pg` container was temporarily started.
Its initial stopped state was restored; test-created schemas/processes were cleaned
up and the database volume/history retained. Compose configuration was unchanged;
the Stage 5 clean-start acceptance remains prior evidence and was not rerun here.

## Historical real results remain unchanged

The previously authorized bounded experiment completed **30 real calls**, with
**zero provider length truncations**, no unknown/transport failures and no unrun
arms. Ten task envelopes completed, but only **six valid finishes** were accepted.
Both arms retain the fixed denominator of five: **3/5 valid finishes**, and both
file/function **Recall@1 = Recall@3 = 0.6**.

| Metric | Suppression off | Suppression on |
| --- | ---: | ---: |
| Calls | 15 | 15 |
| Input tokens | 76,624 | 77,225 |
| Output tokens | 2,213 | 2,297 |
| Total tokens | 78,837 | 79,522 |
| Conservative CNY estimate | 0.170952 | 0.172826 |
| Sum of task seconds | 49.589666014 | 46.918753695 |
| Actual folds reaching later context | 0 | 4 |

Total conservative cost estimate was **CNY 0.343778**, with zero pending reserve.
These are pricing-based estimates, not an invoice or confirmed account charge.
The enabled arm used **685 more total tokens** and **CNY 0.001874 more**
conservative estimated cost. **No total-token or cost savings were observed.**
Timing differences from this small single cohort are descriptive only.

See [BOUNDED5_ACCEPTANCE.md](BOUNDED5_ACCEPTANCE.md) for original results/evidence.
The offline guidance fix has **no newly measured real accuracy, token, cost or
latency result**. Additional live work would need independent review, newly frozen
source/plan identities and separately authorized budget/pricing. All old consumed
approvals remain consumed; do not rerun their evaluator commands.

## Reproduce offline checks

Run from the repository root, using the existing CPU environment:

~~~sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -B tests/run_historical_smokes.py

# Existing configured local PostgreSQL must be available; no new credentials.
.venv/bin/python -B tests/run_stage2_acceptance.py \
  --pattern stage3_postgres_acceptance.py
~~~

Do not run the preparation/index-building or paid evaluation commands to reproduce
this scoped repair. The four portable regressions need only the checked-in JSON
fixture and tiny in-memory graphs.

## Commit candidate and remaining review

The local evidence package includes:
`candidate-files.txt` (explicit allowlist), `candidate.json` (content hashes),
`candidate-worktree.patch` (all prior follow-up/bounded support plus this repair),
and `entity-guidance-only.patch` (this task's changes versus its backup).
The candidate intentionally excludes .env, raw HTTP responses, budgets,
authorization markers, outputs, prepared indexes, credentials and database data.
Only compact public invalid-argument/node-type regression fixtures are included.

Suggested eventual commit subject:
`Add bounded localization protocol and exact graph submission guidance`.
Nothing has been staged or committed. Independent review should check strict
mixed-payload rejection, displayed ID/type truth, constructor-source visibility,
legacy compatibility, bounded-context accounting, protected evidence and the
broader already-uncommitted follow-up/budget code. Do not infer review approval
from the passing author-run tests.

Accurate resume evidence: implemented bounded structured localization and
graph-backed submission guidance; verified **196 offline tests, 32 real
PostgreSQL/process tests and 3 historical smokes**; retained four real invalid
submissions as portable fail-closed regressions. The earlier five-sample comparison
had six valid finishes out of ten arm tasks, with no demonstrated token/cost gain.
