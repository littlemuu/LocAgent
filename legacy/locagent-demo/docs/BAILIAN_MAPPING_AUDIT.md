# Read-only mapping audit — 2026-10-15

Conclusion: the existing saved response cannot safely establish input-to-vector
mapping. No compatibility fallback was added. Zero new model requests, no budget
release/reset, no service start and no commit/push occurred. Both experiments'
evidence files, manifests, markers and ledgers retain identical before/after
SHA256 values. Total unknown reservations remain CNY 0.524288.

## Actual saved structure

The following describes the **safe projection**, not reconstructed original JSON:

```text
{
  audit_projection: string,                 # local projection marker
  request_id: string (UUID),
  usage: {
    prompt_tokens: integer (1954),
    total_tokens: integer (1954)
  },
  output: {
    embeddings: array[16] of {
      embedding: array[1024] of finite numbers
    }
  }
}
```

All 16 saved row objects have only `embedding`. No `text_index`, `index` or other
mapping field is present in this projection. Original response metadata confirms
the first row's `text_index` was missing, independently of the projection.
It does not record the original row's complete key set or alternative indices.

Request ID: `f3b9a7e0-054c-97b3-a8a0-fd07a5cd6a5e`.

## Why absence of index in this file is inconclusive

`locagent_service/bailian_response.py::safe_response_json` copies only two known
row fields: a bounded integer `text_index`, and bounded finite numeric `embedding`.
It discards `index` and every unknown row field. Consequently, we cannot tell
whether the original response used `index`, another mapping field, or no mapping
field at all. It also drops unknown top-level/output/usage fields and arbitrary
strings, does not preserve original key order, whitespace, number spelling or
duplicate JSON keys, and may omit malformed values. Error messages and headers
are intentionally absent. It is not a lossless raw-response capture.

An offline synthetic check constructed two different raw responses, differing
only in `index: 0` versus `index: 1`. Their byte hashes differ, but the current
safe projection is identical. This proves the transformation loses precisely
the information needed to check that proposed alternate field. These fixtures
are a projection test, not evidence of what the provider actually returned.

## Official contract checked

Primary references (checked 2026-10-15):

- https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api
- https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api
- https://www.alibabacloud.com/help/en/model-studio/text-embedding-synchronous-api

The native response contract and Flash example use
`output.embeddings[].text_index` for the position in the input text array. The
native batching example also adjusts this field when concatenating batches.
The OpenAI-compatible response instead documents `data[].index`; that is a
different envelope/API, not documented permission to treat `index` in the native
envelope as an alias. `sparse_embedding[].index` is a vocabulary token index and
must never be used as the input-text index.

The examined official pages do not explicitly guarantee that missing-index
native responses retain input order. An example iterating an array, examples
whose displayed indices ascend, or equal input/output counts do not establish
such a guarantee. This finding is limited to the sources examined; it does not
claim that no provider-side guarantee could exist elsewhere.

No strict alias branch can be justified and applied to the existing evidence:
there is neither a retained alternate index nor a verified fallback-order
contract. The saved 16-vector projection was passed to the strict validator
offline and still failed at `output.embeddings[0].text_index`. Numerical shape
and finite-value checks succeeded independently; those facts do not identify
which input belongs to which vector.

## Integrity boundary

The ledger and diagnostic sidecar agree on received-response SHA256:
`b51a86bf1ddf5534e60b6e7a4d2067e6a5738a81ca3ef575af484928de0aa608`.
The saved projection has its own different SHA256, recorded in findings.json.
No exact original response bytes are available, so an independent auditor cannot
recompute the received-response hash or reproduce the full projection from it.
The files are associated by the same local request record and capture code;
that procedural association is not a cryptographic proof that the surviving
projection is the exact projection of bytes with the recorded original hash.
The new before/after file hashes establish that this audit did not alter the
existing evidence; they do not repair the earlier information loss.

## Smallest safe next step

Use the existing request_id through an authorized provider audit/support route
to obtain the original response or a request-specific mapping confirmation, plus
an explicit native Flash index/order contract. This task did not contact support
or make an API request. If exact original bytes become available, first match
the recorded SHA256, then test the mapping offline under the clarified contract.
If only a provider confirmation is available, identify its distinct evidence
strength rather than claiming byte-hash verification. Do not use the current
array positions as labels or mark the request settled.

For a future separately approved capture, preserve a bounded original response
securely when it is verified to contain only approved public-content outputs, or
retain a complete schema inventory and every documented mapping field before
redaction. Hash both raw bytes and the projection and record projection policy
version, but recognize that hashes alone cannot recover fields deliberately
discarded. No new request/capture was authorized or performed here.

The first experiment's failure cause remains unknown; this second-response
mapping diagnosis must not be retroactively asserted as the first failure cause.

Evidence: outputs/bailian-mapping-readonly-audit/{findings.json,
evidence-hashes-before.json,evidence-hashes-after.json}. Existing source code,
response evidence and all old ledger state were left unchanged.
