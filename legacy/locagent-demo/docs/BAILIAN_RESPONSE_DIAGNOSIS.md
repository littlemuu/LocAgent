# Offline response diagnosis — 2026-10-15

## Findings

No new model/embedding request was sent. The sole historical call remains
`unknown`, the run remains `halted`, and CNY **0.262144** stays reserved.
The original frozen manifest, authority JSON, SQLite ledger and external marker
all retain identical byte hashes before and after this diagnosis. No secret
configuration or headers were read. No database/container was started.

The actual failure cause remains **undetermined**: only HTTP 200,
`response_invalid`, a response SHA256 and elapsed duration survived. The only
call's `tokens` is NULL; the SQLite schema contains no request_id or field-path
column, and no response audit sidecar existed for that call. The available
stop/final summaries contain no additional field-level evidence. A response
hash cannot reconstruct the response or its request_id.

## Contract comparison and reproducible evidence

Official source checked:
https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api
(native DashScope response table and Flash success example).

| Field/shape | Old behavior | Evidence and conclusion |
| --- | --- | --- |
| Missing `model` | Accepted; checked only if present | Official native Flash example omits it. The preserved old validator passes this shape. Absence alone is not the failure cause. |
| `status_code: 200` | Accepted | Official success example uses integer 200. |
| `status_code: "200"` | Rejected | Field table calls it a string, while the example is integer. Reproducible compatibility gap; actual response type is unknown. |
| Missing `status_code` | Accepted with default 200 | HTTP status is separately checked in the live caller. |
| `usage.prompt_tokens` | Required integer equal to total | Flash documentation lists both prompt_tokens and total_tokens; older models list only total_tokens. Do not silently adapt a Flash request to another model's usage schema. |
| `usage.total_tokens` | Positive bounded integer required | Missing, string, boolean or excessive totals remain rejected. |
| `output.embeddings[].text_index` | Required, unique, in-range integer | Correct native shape. OpenAI-compatible `data[].index` is not accepted by the native parser. |
| Vector dimension/numeric values | Exactly 1024, finite, nonzero | Preserved. Present wrong model is also still rejected. |

Relevant pre-change code is preserved in this experiment's diagnostic output:
`outputs/bailian-diagnostic-audit/original-contract.py`, function `response`.
It used `data.get('status_code', 200) != 200`, a conditional model check, then
strict total/prompt usage checks. `original-live.py` shows all validation errors
collapsed into `response_invalid` and no raw response/field detail persisted.
That loss of diagnostics is an established implementation defect; it is not
evidence identifying the provider response mismatch that triggered it.

The official example contains an ellipsis rather than a full vector. Our fixture
preserves the documented envelope/usage and replaces the abbreviated vector
with explicitly synthetic 1024-dimensional numeric data. It is not labelled as
a captured real response. The old validator accepts that fixture without model,
but rejects its otherwise identical string-status variant.

## Minimal repair

`locagent_service/bailian_response.py` is the strict validator with a bounded,
allowlisted diagnostic result. `bailian_contract.response` delegates to it while
preserving the old return type. Only exact integer 200 or string "200" is accepted
when a body status is present; coercions such as "0200", "200 OK", 200.0 and
booleans are rejected. Actual HTTP success must still be integer 200.

Future call sidecars record response SHA256, HTTP status, fixed failure path,
expected type and actual type/reason; request_id presence, a canonical UUID ID
or hash for other formats; model presence/match; usage presence and fixed field
types; vector count and dimension distribution (bounded to the first 20 entries).
They omit arbitrary error messages, unknown field names, model values and all
headers. Successful validation additionally persists validated numeric vectors
and usage for local audit. Invalid usage never releases a reservation or becomes
a settled result merely because diagnostics were saved.

`Journal.step` now writes `response-NNN.audit.json` before settlement, and writes
failure metadata before globally halting. Persistence failure also leaves the
call uncertain. This only affects future explicitly admitted calls; no sidecar
was fabricated for the historical response.

The new module is included in `ENGINE_FILES`. The old frozen manifest now fails
admission with `Engine hash mismatch`, verified without loading credentials or
calling the transport. No manifest/authorization was replaced to bypass that
guard, and the halted state is not cleared.

## Tests and recovery boundary

49 offline tests passed in 0.668s with socket connections blocked. Nine new test
methods cover official-shaped native success, optional model/envelope fields,
exact string-status compatibility, missing usage, total-only usage rejection,
wrong model/dimension/index, boolean/nonfinite/zero values, redaction, duplicate
JSON keys, HTTP errors and bounded metadata. Existing fake Journal tests now
verify both success-vector/usage audit persistence and failure-sidecar redaction.
No live result is claimed by these fixtures. Existing unrelated regression suites
were not rerun this turn; their preceding 142-pass result remains historical.

Arithmetic under the unchanged CNY 1 cap:

- Unknown reservation retained: **0.262144**.
- Remaining conservative cap: **0.737856** (not permission to resume).
- Two never-sent original batches: 16 document blocks + 10 questions,
  conservative reservation **0.425984**.
- Headroom after those planned batches, if separately admitted later:
  **0.311872**. The missing first-batch vectors still prevent complete comparison.

Safe recovery starts with provider-side reconciliation of the existing request:
obtain its usage/request identifier and, if available, the response content
through an authorized audit source. No response retrieval capability is currently
implemented and no such retrieval or new embedding request was attempted.
If the exact raw body becomes available, its SHA256 must match the stored hash
before offline revalidation. Retain unknown cost unless evidence supports a
reviewed reconciliation. If the response cannot be recovered, do not pretend
the first 16 vectors exist or exclude them from the frozen comparison.

Any future resume needs an explicitly reviewed transition preserving the old
manifest/ledger and total budget; no retry, automatic regrant, ledger reset or
first-batch replay is authorized by this repair. Real calls remain paused.

## Deliverables

- New `locagent_service/bailian_response.py` and `tests/test_bailian_response.py`.
- Updated `locagent_service/bailian_contract.py`, `locagent_service/bailian_live.py`,
  `tests/test_bailian_live.py`.
- `outputs/bailian-diagnostic-audit/`: preserved original code, safe evidence
  inventory, before/after hashes, findings, offline test log.
- This report. No commit, push, merge, credential edit or original-workspace edit.
