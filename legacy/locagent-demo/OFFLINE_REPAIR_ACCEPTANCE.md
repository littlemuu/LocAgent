# Offline repair acceptance — 2026-10-08

> Command examples run from the repository root. Shell examples require a configured environment; Examples using `$PYTHON` accept an existing compatible interpreter; direct `.venv/bin/python` commands require the project environment. Historical `outputs/` evidence and helper scripts are local artifacts, not included in a fresh clone.

## Outcome and scope

Implemented and verified in WSL the repository root on
`work/locagent-baseline`, HEAD `54fcb660d4a886e7f0675ed419b3a4ed21aa3fb6`.
No commit, push, paid call, authorization consumption/reset, credential creation or
.env edit occurred. The previous eight uncommitted follow-up files were backed up
before edits; their support and all historical failed-run evidence are retained.
No applicable repo/ancestor AGENTS.md or .agents skill was found during inspection.

This is an offline protocol repair, not a new quality experiment. The original
five-sample run remains stopped: 13 actual calls, four iteration-limit results,
one failed task and five unrun arms, with no valid final locations. Its metrics,
budget ledger and raw responses have not been rewritten or rescored.

## Changes and compatibility

1. **Exact root aliases.** Search, entity read and graph/tree exploration now resolve
   only `/` and `.` to the actual directory root present in the graph. Prepared
   graphs continue using `.`; legacy `/` graphs also work. Other path normalization
   behavior and repository path safety checks are unchanged.
2. **Explicit structured termination.** New protocol `bounded-v1` accepts only a
   single `finish` call with exactly `{"files":[...],"entities":[...]}`. Locations are
   matched exactly against graph nodes, ranked in supplied order, and entities must
   belong to the submitted files. No prose extraction or fuzzy repair awards success.
   The final round sends only the finish schema and forces its tool choice. It will
   never execute a further retrieval returned in that round.
3. **Bounded model-visible tool output.** One tool message is at most **8,192 bytes**
   and all tool messages in one run total at most **24,576 bytes**, measured using
   canonical UTF-8 JSON including message metadata, escaping, wrappers and newlines.
   Pages prefer complete entity boundaries, then whole output lines; an oversized
   single line can be split by character position without corrupting UTF-8.
   `read_tool_output(output_id, offset)` reads only the current run's stored result.
   The preview includes the next offset and output-line range. These ranges describe
   the tool output; source line numbers remain in the original formatted content.
4. **Context correctness and diagnostics.** Full original tool returns are kept in
   `diagnostics.tool_outputs`. Each delivered message records raw size, delivered
   size, offsets, tool identity and truncation reason. Only complete return content
   actually present in a delivered message is marked `in_context`. Withheld tails
   never qualify for suppression. An entity split across multiple messages may stay
   conservatively unmarked; that can cause redundant reads but cannot hide unseen code.
5. **Legacy contract.** Default `LocalizationOptions` and old CLI loop stay on
   `legacy`. Old result JSON/HTTP/database views omit absent diagnostics, preserving
   their original shape. Existing result statuses are unchanged: unsuccessful bounded
   submission uses `iteration_limit` with an explicit diagnostic reason. The
   isolation lock, worker child processes, leases, fencing and billing code are unchanged.

Bounded diagnostic reasons distinguish `output_truncated` (provider `length`),
`missing_finish` (final prose), `iteration_limit` (final retrieval),
`invalid_finish`, `context_limit`, `tool_budget_exhausted` and invalid tool input.
A truncated response is retained but never parsed or executed, even when its partial
arguments happen to look valid. Only `finished` can produce success or normal empty.

The existing **65,536-byte request estimate gate**, including the **4,096-byte reserve**,
is unchanged. The bounded loop checks the same messages/tools/tool-choice envelope
before calling the provider. It does not increase token limits, call count or budget.
A tool batch is capped at 16 calls; invalid batches fail closed.

## Configuration

```sh
# Builds new artifacts from the sample's exact local Git commit. No model calls.
.venv/bin/python -m locagent_service.prepare \
  --repo /path/to/local/repository --sample /path/to/fixed-sample.json \
  --search-protocol bounded-v1
```

For the isolated adapter:
`LocalizationOptions(max_iterations=3, suppress_repeats=True, search_protocol="bounded-v1")`.

The protocol is stored in the immutable source manifest and is not an HTTP request
override. Old manifests are not edited or migrated. Engine hash validation correctly
rejects pre-repair manifests as current experiments; new source IDs and plans are
required. Both paired arms must use the same protocol/configuration. No new live
plan has been approved or enabled by this repair.

A fresh local build at commit `091991be0da19de9108dbe5e3752917fea3d7fdc` produced:
`prepared-da465d40e97ecc50f33710d1e7f99877ce907c9c4824010a5147658df404c5e7`.
It lives in the separate acceptance registry under `prepared/sources` and passed a
two-response synthetic root-read/empty-finish loop. It is not quality evidence.

## Verification evidence

All paths below are under `outputs/stage4/offline-repair-20261008/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Full offline/unit/HTTP/budget suite | **174 passed**, 18.733 s; previous 153 + 21 new methods | `full-tests-final.log` |
| Real PostgreSQL/process suite | **32 passed**, 79.433 s | `postgres-tests-final.log` |
| Historical Day 4, 5 and 6 scripts | **3 passed**, network/live-model attempts blocked | `historical-smokes.log` |
| Settled raw-response forensic replay | 5 executed historical arms inspected; no new model calls | `forensic/summary.json` and individual result JSON |
| New fixed-commit source | Config/hash validation and synthetic tool loop passed | `prepared/summary.json`, `prepared/result.json` |
| Preservation / cleanup | 133 protected files unchanged; HEAD unchanged; no test processes or running containers | `verification.json`, `before.json` |
| Formatting | `git diff --check` passed | `verification.json` |

The first PostgreSQL pass exposed two legacy serialization equality failures from
an added `diagnostics:null` field. The serializer was corrected and the legacy-shape
assertion strengthened. The first failure log (`postgres-tests.log`) is retained;
the final complete 32-test rerun passed. No database-history assertion was weakened.

### Original failure reproduced without model execution

The forensic runner verifies the original manifest/artifact hashes and saved raw
HTTP body hashes. It deliberately reads these historical artifacts as evidence,
not through the current-experiment engine-hash gate. It then exercises the current
real graph tools under a socket/live-model guard.

| Original arm | Offline result |
| --- | --- |
| 1963 off | `output_truncated`; no final locations |
| 1963 on | `output_truncated`; no final locations |
| 2148 off | `output_truncated`; no final locations |
| 2148 on | `iteration_limit`; final retrieval not executed |
| 2317 off | Original overflow reproduced; bounded next-request path verified with a deliberately synthetic **empty** finish |

For 2317, restoring only the original root-alias behavior during the legacy
forensic run reproduced the previous **80,352-byte** next-request estimate exactly.
The repaired root/tool path produced **26,253 bytes** for the next request, within
the unchanged 65,536-byte gate. This is a request-byte comparison, not a token or
monetary measurement.

The raw multi-keyword search returned **61,379 UTF-8 bytes**. Its bounded message
was **6,397 JSON bytes**, cut at an entity boundary and offering continuation.
The root observation was **1,397 JSON bytes**, making **7,794 bytes** of actual tool
messages. Ten incomplete/withheld return records remained unmarked as seen.
All original raw output remains in the diagnostic result.

Saved responses were produced for the old conversation. Reusing them proves
mechanical behavior and failure classification only; it cannot predict how a
live model would react to the new context or establish accuracy/cost improvements.

## Reproduction

Run from the repository root. Forensic/preparation output directories must be new;
their runners refuse overwrite.

```sh
sh scripts/check_local.sh
.venv/bin/python -B tests/run_historical_smokes.py
.venv/bin/python -B tests/run_offline_repair_acceptance.py \
  --output outputs/stage4/repair-forensic-new
.venv/bin/python -B tests/run_prepared_protocol_smoke.py \
  --output outputs/stage4/repair-prepared-new

# Requires the existing configured local PostgreSQL (no new credentials).
.venv/bin/python -B tests/run_stage2_acceptance.py \
  --pattern stage3_postgres_acceptance.py
```

For this acceptance only, the existing labeled `locagent-stage2-pg` container was
temporarily started and stopped again. Tests own/drop only their fresh temporary
schemas; retained database volumes were not removed. No API/worker/test processes
remain. Docker Compose topology/build was unchanged and its clean-start suite was
not rerun in this scoped repair; prior Stage 5 evidence remains historical.

## Review focus and remaining conditions

Independent review should inspect final-round enforcement, malformed/truncated
argument handling, exact graph validation, UTF-8/JSON boundaries, cache isolation,
suppression visibility, old result serialization and manifest opt-in wiring.
The delivery includes a repair-only patch separating these edits from the earlier
five-sample support, plus the complete current worktree patch.

Remaining live validation requires independent review, new fixed sources/plan,
fresh pricing/budget authorization and a new ledger/approval marker. Old consumed
approvals must remain consumed. No live call was made to check provider support
for forced tool choice or its accuracy under the new prompt. A 512-token completion
may still truncate; the repair reports that honestly instead of inventing success.

Tradeoffs: pagination uses some model rounds, so a three-call cap leaves limited
continuation opportunities. Limits bound model input, not tool execution CPU/memory
or stored raw-diagnostic size. Native tool calling is required by the new protocol;
text-only legacy model paths remain available only in the legacy branch.

Accurate resume evidence: implemented exact-root resolution, structured final
submission and bounded/traceable tool context; validated with 174 offline tests,
32 real PostgreSQL/process tests and 3 historical smokes; reproduced and contained
an 80,352-byte historical input overflow. Do not claim improved benchmark quality,
production reliability, measured token savings or lower real cost from this repair.
