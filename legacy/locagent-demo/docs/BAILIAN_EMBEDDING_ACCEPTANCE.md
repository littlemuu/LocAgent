# Bailian first embedding experiment — stopped, 2026-10-15

## Outcome

Exactly **one** authorized embedding HTTP request was attempted. It contained
the first 16 frozen public Python function blocks and no generation request.
HTTP status was **200**, but strict response validation failed. The journal is
**halted**, the call is **unknown**, and all later calls/replays are blocked.
No claim of authenticated usable embedding success is made from HTTP 200 alone.

The full reservation **CNY 0.262144 remains held**. Settled usage is unavailable.
The accounting field `settled_usage_cost_cny=0` means no charge has been settled
locally; **it does not establish a zero provider charge**. Do not reset this
ledger, remove its authority marker, or send the same request again.

Response SHA256:
`56031aa97ee99715dc57f0e1092b829843b14fab5223f7faf2b23288e3becd2e`.
The raw response was not persisted. Only its hash, HTTP status, bounded failure
category and elapsed time are available, so the specific rejected field cannot
be diagnosed retrospectively. Missing usage, shape mismatch and other schema
errors must not be asserted as the established cause. This diagnostic gap needs
safe field-presence/type/count diagnostics in a future reviewed implementation.
No raw error text or credential was printed or stored in experiment evidence.

## Frozen scope

- Worktree `/home/lenovo/projects/LocAgent-rag-preview`, branch
  `work/rag-offline-preview`; unchanged HEAD
  `290c965a3321dd90d4e848dd924e3134ef10fc8c`.
- Manifest SHA256
  `0f7a528612306d2fa6d3047520b6c279ebdcca0e1edb6f615530dbf3c5fdd36b`.
- `pallets/itsdangerous`, commit
  `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`.
- Four files: `src/itsdangerous/{encoding,signer,timed,url_safe}.py`.
  All 32 function regions (including overloads), 10 manually authored questions
  and direct implementation entity labels, frozen before any retrieval output.
  Classes/module residuals and other files are outside this experiment.
- Fixed model `qwen3.7-text-embedding-flash`, dense 1024 dimensions, native
  `text_type` query/document, query-only English instruction. Full ordered
  request bodies, chunking/preprocessing, engine and dependency versions are
  bound by the manifest. The configured key is never part of it.
- Approved origin `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com`; path
  `/api/v1/services/embeddings/text-embedding/text-embedding`.
- Three planned batches: 16 documents, 16 documents, 10 questions. At CNY
  0.125/million and 131072 tokens reserved per input, total conservative plan
  ceiling is **CNY 0.688128**, within CNY 1. No free-quota/batch discount applied.
  Only the first batch ran; no questions were sent.

GitHub's tree API returned 403 during provenance admission; cause was not
determined. An alternate bounded HTTPS archive download from codeload at the
exact commit succeeded. All four cached source files matched that archive
byte-for-byte, with archive SHA256 recorded in the manifest. This is explicit
fixed-commit HTTPS archive provenance, **not independent Git tree verification**.
Existing manifest/engine checks were not bypassed and old paid ledgers were not
loaded for execution, replayed, reset or reused.

## Validation and evidence

- 40 new offline tests passed (0.655s final pre-call run), sockets blocked.
  Includes fixed origin/native request shape, redirects not followed, no retries,
  bounded payload/response, dimensions/nonfinite/zero vectors, usage/model
  mismatches, private config mode/symlink/interpolation restrictions, manifest
  rebinding/inode changes, pre-send reservations, unknown/global halt, restart
  non-replay, budget cap, role cache separation and metric denominators.
- 142 existing offline regression tests passed, zero failures/errors/skips.
- Full fake-vector -> isolated pgvector -> BM25/dense/hybrid pipeline passed with
  the same frozen membership and 10 questions. Fake vectors do not measure the
  model's retrieval quality. Actual embedding comparisons **not run** because
  the first response was invalid; no quality improvement is claimed.
- Original learning README hash and historical JSON ledger hashes were checked;
  original demo container state/mount metadata unchanged. No original DB
  connection or migration was performed. Only the previously owned pgvector
  container on loopback 55441 was started for fake evaluation, then stopped.
- No new commit, push, PR, merge or deployment.

Commands (Windows workspace helper scripts executed with WSL Python):
`stage_bailian_live.py`, `prepare_bailian_run.py` (first failed on GitHub 403;
second passed using documented codeload provenance), `evaluate_bailian_run.py`
(fake only), `invoke_bailian_live.py --first` (stopped),
`rag_persistent_suites.py`. Do not rerun the live command to probe the error.

Files: `locagent_service/bailian_{config,contract,experiment,live,dataset,evaluate}.py`,
`tests/test_bailian_{contract,experiment,live}.py`,
`docs/bailian.env.example`, this report and `BAILIAN_EMBEDDING_PREFLIGHT.md`.
The older preflight sections describe earlier checkpoints; this report is the
current outcome. `.env.bailian.local` stays ignored and private.

Evidence under worktree outputs:

- `bailian-frozen-manifest.json`: complete frozen public content and labels.
- `bailian-live-20261015/{manifest.json,authority.json,ledger.sqlite}` plus sibling
  `bailian-live-20261015.lock`: one approved live authority, no directory override.
- `bailian-live-stop-report.json`, `bailian-final-status.json`: safe summaries.
- `bailian-evaluation-fake/{results.json,accounting.json,cleanup.json,protected-before.json,protected-after.json}`.

Metric definition: entity deduplication precedes top-k. Hit@k divides questions
with any relevant entity found by all 10 questions. Macro Recall@k averages each
question's retrieved-label fraction across all 10; missing/failed rankings count
as zero. Each question currently has one direct-implementation label, hence these
two metrics coincide. Narrow labels may exclude reasonable alternative caller
locations. This small development set was authored after reading the source and
is not a blind/generalization benchmark. BM25 indexes the same path/symbol/code
text as dense, rather than the original demo's symbol-only graph retriever; this
isolates retrieval comparison and does not change the demo default.

## Blocker and next step

Reconcile the first request's provider-side usage and response contract before
any new real request. The present evidence cannot recover the lost raw response
or establish why it failed. Keep the full unknown reservation. Any subsequent
change must preserve this authority and be explicitly reviewed against the
remaining total budget; no automatic retry or regrant is implemented.

The live entrypoint fixes authority path and origin, verifies frozen engine and
dependency hashes, commits SQLite reservations before transport, and has an
external single-use marker to detect a missing/replaced authority folder. It
assumes a trusted local filesystem; it cannot prevent a malicious local user
from rewriting both code and state. Pinned TLS/DNS and process timeouts are not
a general sandbox or evidence this service is safe for public deployment.
