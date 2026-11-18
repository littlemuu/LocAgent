# Bounded five-sample live acceptance — 2026-10-09

> Command examples run from the repository root. Shell examples require a configured environment; Examples using `$PYTHON` accept an existing compatible interpreter; direct `.venv/bin/python` commands require the project environment. Historical `outputs/` evidence and helper scripts are local artifacts, not included in a fresh clone.

## Actual outcome

The single authorized round completed **30 real requests**, all with verified raw
usage settled. The conservative all-input-cache-miss estimate is **CNY 0.343778**,
below the independent **CNY 5** cap. Pending reserve is **0**; unknown outcomes,
transport failures, provider length truncations and unrun groups are **0**.
There were no retries or extra rounds.

All **10 task envelopes completed**, and all ten final responses called the
structured finish tool. Only **6/10 were graph-valid finishes**. Four contained
invalid entity IDs/types and correctly remained unsuccessful. Task completion must
not be described as ten successful localizations.

Fixed canonical plan hash:
`1fb5b84b25ef43ef27f71b28a9e56f19321b8361f7a139aee69d0b5cd9e710e8`.

Started **2026-10-09 02:38:15.244963 UTC**, finished **02:40:05.407767 UTC**;
the sole evaluator process exited 0. Requested Flash alias and actual returned
`deepseek-flash` were retained; all 30 responses returned that model name.
The same five samples, commits, original labels, alternating arm order, bounded-v1
engine, 3 calls per group and 512 output-token cap were used without adjustment.

## Fixed-denominator comparison

| Measure | suppress_repeats off | suppress_repeats on |
| --- | ---: | ---: |
| Fixed denominator | 5 | 5 |
| Task execution completed | 5/5 | 5/5 |
| Effective graph-valid finish | 3/5 | 3/5 |
| Invalid finish | 2/5 | 2/5 |
| Normal empty result | 0 | 0 |
| Truncation / transport failure / unrun | 0 / 0 / 0 | 0 / 0 / 0 |
| File recall@1 and @3 | 3/5, 60% | 3/5, 60% |
| Entity recall@1 and @3 | 3/5, 60% | 3/5, 60% |
| Provider calls | 15 | 15 |
| Input tokens | 76,624 | 77,225 |
| Output tokens | 2,213 | 2,297 |
| Total tokens | 78,837 | 79,522 |
| Cache-hit input tokens | 34,816 | 44,160 |
| Cache-miss input tokens | 41,808 | 33,065 |
| Conservative CNY estimate | 0.170952 | 0.172826 |
| Sum of task elapsed seconds | 49.590 | 46.919 |
| Sum of provider elapsed seconds | 19.766 | 19.538 |
| Actually delivered folds | 0 | 4 |
| Folds confirmed before a later provider response | 0 | 4 |

Total usage: **153,849 input + 4,510 output = 158,359 tokens**.
The on arm used **685 more total tokens** and **CNY 0.001874 more** under the same
conservative ledger basis. Therefore this run provides **no observed token or
conservative-cost reduction**, and both arms have the same valid-result metrics.
Small timing differences from one run are descriptive, not a performance claim.
Retrieval trajectories and cache exposure differed; do not attribute all arm
differences to folding.

The total cache-aware **peak-rate** estimate is **CNY 0.18898504**
(off 0.10271264; on 0.08627240), using observed cache hit/miss fields and published
peak rates. It is a secondary estimate, not the ledger's release basis or an
account invoice. No balance/account invoice was queried.
[Official pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/).

## Per-sample results

| Sample | Off / on outcome | File/entity rank-1 hit | Actual folds off / on |
| --- | --- | --- | ---: |
| psf__requests-1963 | finished / finished | yes / yes in both arms | 0 / 1 |
| psf__requests-2148 | finished / finished | yes / yes in both arms | 0 / 0 |
| psf__requests-2317 | invalid_finish / invalid_finish | 0 / 0 under frozen rules | 0 / 3 |
| psf__requests-2674 | finished / finished | yes / yes in both arms | 0 / 0 |
| psf__requests-863 | invalid_finish / invalid_finish | 0 / 0 under frozen rules | 0 / 0 |

### Invalid finish diagnosis, with no rescoring

- **2317 off:** included `requests/compat.py:builtin_str`, which is not a graph entity.
- **2317 on:** included `requests/compat.py` in `entities`; it is a file node, whereas
  this field accepts function/class nodes.
- **863 off and on:** included `requests/models.py:Request.__init__`, absent from
  the fixed graph's entity IDs.

These submissions also contain relevant locations, but the predeclared strict
all-or-nothing finish validation rejects the whole payload. They retain public
localization status `iteration_limit` plus diagnostic `invalid_finish`, not
`success`. No invalid item was silently dropped, no prose was extracted, no label
was changed, and no additional call was made to repair an answer.

This exposes a remaining limitation: the model can submit visible code symbols
that are not valid nodes of the fixed graph, or confuse file nodes with entities.
Any protocol change or new experiment needs separate review and authorization.

## Fold and bounded-context evidence

Four replacement notices were present in actual tool messages and preceded a
subsequent successful provider response, proving that the same retained messages
were included in the next call:

- 1963 on: `SessionRedirectMixin.resolve_redirects`; message 6, next assistant 9.
- 2317 on: `PreparedRequest.prepare_method` and `Session.request`; message 6,
  next assistant 9.
- 2317 on: `requests/auth.py:_basic_auth_str`; message 7, next assistant 9.

Exact tool-call IDs, notices and message indices are saved in `verified-outcome.json`.
This count is based on model-visible replacements, not just repeat flags.
The original full tool returns and withheld page tails remain in diagnostic
artifacts. All observed next-request estimates were below the unchanged 65,536
gate; the maximum was **35,321 bytes**. No input gate failure occurred.

## Budget, preservation and cleanup

The full pre-call reserve remains CNY 2.101248. The largest reconstructed
spent-plus-next-reservation amount was **CNY 2.432056**, below the CNY 5 cap.
All raw bodies were persisted before settlement, independently revalidated, and
exported byte for byte. Their usage was not synthesized from SDK defaults.

The new marker is `outputs/stage4/authorizations/bounded5-20261009-cny5.json`;
all ten groups consumed their three-call quotas and the 30-call quota is exhausted.
The remaining monetary headroom does not authorize additional calls or another
round. The marker/ledger remain retained and must not be reset or replayed.

The exact plan was pinned only after independent preflight
PASS and verification of the original user authorization evidence. The one permitted
execution approval retry was accepted; one local evaluator launch occurred.
Authorization transcripts were supplied solely in approval metadata, never shell
code or model input.

All **321 protected historical evidence/.env files** retain their hashes.
HEAD remains `54fcb660d4a886e7f0675ed419b3a4ed21aa3fb6`. No commit, push, credentials
change, database operation or volume deletion occurred. The only execution-code
activation change was pinning this new plan hash. The evaluator and its children
have exited; no inflight guard remains.

## Artifacts and local re-audit

All live evidence lives under `outputs/stage4/bounded5-live-20261009/`:

- `budget.json`, `summary.json`: durable billing and original evaluation summary.
- `responses/*.json`: all 30 exact raw response bodies.
- Ten canonical task JSON files and ten preserved child JSON files.
- `verified-outcome.json`: raw verification, per-row outcomes, fixed denominators,
  token/cost/time aggregates, fold context evidence and preservation proof.
- `invalid-finish-diagnosis.json`: strict graph validation of the saved arguments.
- `LIVE_REPORT.md`: this report.

The plan, source registry, original-label mapping, fresh pricing provenance,
preflight package and activation log are retained in
`outputs/stage4/bounded5-20261009/`.

To audit saved results locally without provider calls:

```sh
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -B outputs/stage4/bounded5-20261009/audit_live.py
```

The audit writes audited-metrics.json from immutable local evidence and leaves
verified-outcome.json with its separately checked preservation/cleanup snapshot
intact. Do not re-run the live evaluator.

Accurate project evidence: completed a fixed five-sample, ten-arm, 30-call real
comparison with durable capped accounting; six valid localizations, four actual
folds reaching subsequent context, and fully retained unsuccessful results.
This small development cohort does not establish general accuracy or cost gains.

## Subsequent offline guidance repair

The four invalid finishes motivated an offline display/prompt repair documented
in [ENTITY_GUIDANCE_ACCEPTANCE.md](ENTITY_GUIDANCE_ACCEPTANCE.md). It advertises
existing function/class IDs, file-only variable targets and owning classes for
constructors without separate graph nodes. Strict validation and these historical
scores remain unchanged. Both arms still have 3/5 valid finishes and file/function
Recall@1/Recall@3 of 0.6. No new paid run has tested the repaired guidance; the
30-call experiment showed no total-token or conservative-cost savings.
