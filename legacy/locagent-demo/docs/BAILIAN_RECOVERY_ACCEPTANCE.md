# One explicitly approved recovery — stopped, 2026-10-15

## Result and exact blocker

The one approved recovery sent exactly **one new HTTP request**: the same first
16 public function blocks as the original call. It returned HTTP 200, 16 vectors
of 1024 dimensions, and numeric `prompt_tokens=1954`, `total_tokens=1954`.
Strict validation stopped at **`output.embeddings[0].text_index`: missing**.
The recovery journal is halted and the request remains unknown. No second code
batch or query batch was sent. No automatic retries or extra rounds occurred.

Request ID: `f3b9a7e0-054c-97b3-a8a0-fd07a5cd6a5e`.
Response byte SHA256:
`b51a86bf1ddf5534e60b6e7a4d2067e6a5738a81ca3ef575af484928de0aa608`.
Model name was **not echoed**; this is explicitly recorded, not fabricated.
Absent model is allowed by the documented native shape and did not cause this
failure. The response passed the usage checks before failing the index check.

The frozen native API contract uses `text_index` to associate response vectors
with input texts. We did not guess association from array order or silently
accept an alternate field. The first entry's missing field is directly recorded
by the validator. The safe JSON stores no validated indices for the other rows;
that projection alone cannot establish whether another unretained field existed
in the original response. No claim is made that the original failed call had
the same cause, because its raw response was not retained.

## Authorization, unchanged data and total budget

Recovery approval: `Sentinel_f333a77eb8808191b7258386500ac2d3`.
Recovery manifest SHA256:
`34c3c005ea86d08aaff7bb8e4c48218fea062c86c2704ad63bc83e7edcea902c`.
Parent manifest:
`0f7a528612306d2fa6d3047520b6c279ebdcca0e1edb6f615530dbf3c5fdd36b`.

The new manifest preserves all 32 function blocks, 10 questions, relevance labels,
source commit/membership, preprocessing, model, 1024 dimensions, origin and
request parameters from the parent. Only engine hashes and the explicit recovery
binding differ. The actual first request-body hash equals the old first request's
hash. Both requests together sent 32 code-block instances representing the same
16 distinct blocks. Queries sent: zero. Generation requests: zero.

| Budget item | CNY |
| --- | ---: |
| Original unknown reservation, unchanged | 0.262144 |
| New unknown reservation, retained | 0.262144 |
| Combined retained reservation now | 0.524288 |
| Remaining conservative portion of original cap | 0.475712 |
| Complete recovery worst-case reservation | 0.688128 |
| Old unknown + complete recovery ceiling | 0.950272 |

At the frozen rate, the new observed 1954 tokens correspond to **CNY 0.00024425**
before platform discounts. This is an audit estimate, **not a provider invoice
or a settlement of this unknown request**. The entire new reservation stays
held. The user's screenshot of remaining free quota is not request-level usage
evidence and was not used to settle the original call or infer its failure cause.
Free quota never reduced reservations. Old and new ledger states remain separate;
the recovery code checks the combined original CNY 1 cap before admission and
each request, and verifies parent evidence hashes each time.

## Local evidence

Under `/home/lenovo/projects/LocAgent-rag-preview/outputs/`:

- `bailian-recovery-once-manifest.json`: old evidence hashes, recovery approval,
  complete identical dataset, current engine hashes and combined budget binding.
- `bailian-recovery-once-20261015/{manifest.json,authority.json,ledger.sqlite}`
  plus sibling `.lock`: one recovery authority with no new-round CLI override.
- `bailian-recovery-once-20261015/response-000.audit.json`: raw-byte hash,
  request_id, HTTP status, failure path/type, usage-field presence/types, model
  absence, vector count and dimension distribution.
- `bailian-recovery-once-20261015/response-000.safe.json`: allowlisted provider
  JSON, original numeric vectors before normalization, usage and safe request ID.
  It intentionally excludes headers, credentials and arbitrary string fields.
  It is a **filtered projection, not the byte-identical response**; the separate
  SHA256 describes the received raw bytes. Do not claim the projection can be
  reserialized to reproduce that original hash or reveal omitted field names.
- `bailian-recovery-stop-report.json`, `bailian-recovery-final-status.json`.

The original manifest, authority marker, SQLite ledger and external lock all
retain their pre-recovery hashes. No old budget was reset, released or settled.
The original learning README hash is unchanged. No database container was started
in this recovery, and the owned pgvector acceptance container remains stopped.
No original database migration/connection, commit, push or merge occurred.

## Offline validation and remaining work

53 offline tests passed in 1.012s before the new external call, with sockets
blocked. New tests verify original unknown + recovery cumulative cost, rejection
above the original cap, prohibition on reducing the unknown parent reservation,
unchanged dataset copying, preservation of original numeric vectors/usage and
removal of arbitrary strings from the safe JSON. Existing tests cover strict
usage/model/dimension/index checks, no retries, halted unknown state and recovery
non-replay. One local execution-channel failure occurred before starting the
manifest preparation process; only that no-network preparation command was
retried. It was not a model request or model retry.

BM25/dense/hybrid real-vector comparison **not run**: the required vector-to-input
association failed validation and no question embeddings were requested. The
earlier fake-vector pipeline remains a software-flow test, not a model-quality
result. No quality improvement or metric score is claimed for this real run.
The frozen development set is small, manually labelled after reading the code,
and not blind evaluation. Existing metric definitions/denominators remain fixed.

The one recovery authorization has been exercised. Stop here. Preserve both
unknown reservations and use this request_id with an authorized audit source to
investigate the actual output-index contract. Any future parser change must be
justified by evidence and tested offline; do not infer vector order or send a
third first-batch request under this exhausted one-recovery authorization.
