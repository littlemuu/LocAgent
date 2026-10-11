# Opt-in candidate guidance: offline acceptance

Scope: reduce avoidable invalid finish arguments by showing recent graph-verified
IDs from model-visible retrieval evidence. This is an engineering acceptance,
not a new model-quality experiment. No paid calls, benchmark execution, Git
commit, push, credentials or historical evaluation changes are part of this work.

## Enable explicitly

Use the core GraphLocalizer with:

~~~python
LocalizationOptions(
    max_iterations=3,
    suppress_repeats=False,
    search_protocol="bounded-v1",
    candidate_guidance=True,
)
~~~

The new boolean defaults to False and requires bounded-v1. Legacy and HTTP
TaskOptions defaults are unchanged. The existing HTTP schema and phased paid
runner do not expose this new switch. A future evaluation needs a separately
reviewed, hash-bound plan that explicitly propagates it; this change does not
authorize or enable an old paid ledger to run under modified source.

## Evidence and strict acceptance

- The trusted tool renderer marks only generated finish-target metadata, using
  opaque per-call markers carried through its string assembly. Markers are stripped
  before tool paging, return tracing and provider dispatch. Context state resets
  on success and exception; the existing GraphLocalizer isolation lock remains.
- Pages retain structured spans with ID payload, type and character offsets.
  A candidate is admitted only when its entire rendered span lies within a
  delivered page's [offset, end_offset). Raw tails, model arguments, source
  comments that imitate finish hints, labels and the candidate note itself are
  not evidence sources. Supplemental diagnostics may retain withheld raw output,
  as before; only the admitted candidate list is included in the note.
- IDs are revalidated against the graph, including file ownership and entity
  type. A file ID is never an entity. Full qualified names distinguish collisions.
  A graph-valid ID is not evidence of relevance or a fully read implementation.
- Candidate state belongs to one run. Most recent observations replace older
  entries, up to 20 IDs (including file IDs), and every serialized note is at most
  4096 UTF-8 JSON bytes. IDs are never shortened. Long entries may be omitted.
  Overflow can evict an earlier target; another query can bring it back. A trusted
  suppressed-repeat notice can refresh an evicted target only by pointing to a
  previously delivered, complete original metadata span. The notice cannot seed
  evidence by itself, chain through another notice or certify a hidden raw tail.
- Exactly one current candidate note is present in each request. Its 4096-byte
  maximum is reserved inside the existing 24576-byte total tool-context allowance;
  individual tool pages remain at most 8192 bytes. The note also participates in
  the existing 65536-byte request estimate gate and normal provider usage/cost.
  There is no new completion, retry, iteration, quota or higher budget.
- Retrieval remains available before the existing final round. The list is not
  a whitelist: valid unlisted graph targets still pass the unchanged
  validate_locations contract. Invalid entries still reject the entire finish,
  leave all locations empty and retain invalid_finish/iteration_limit. No gold
  repair, silent filtering or success reclassification is performed.
- Existing return_records are unchanged by provenance marking. Partial source
  remains unread even when its complete ID/type hint is visible.

## Reproduce offline

Verified on 2026-10-10: 85 related tests passed in 7.945 seconds; the complete
381-test suite passed in 349.635 seconds from a clean source export without
operational cohorts, saved outputs, raw-response fixtures or credentials.


From the repository root and existing dependency environment:

~~~sh
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 PYTHONPATH=tests .venv/bin/python -B -m unittest -v test_candidate_guidance test_bounded_protocol test_submission_guidance test_finish_compatibility test_empty_query_boundary
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
~~~

The 24 new tests use synthetic graphs, deterministic mock providers, temporary
metadata and local pagination only. HTML paths absent from the graph, partial
aliases and absent builders paths are structural regressions for the three
observed failure categories, not replays of private provider bodies or new
efficacy results. A hidden graph target named gold_sentinel tests that the
candidate cache cannot manufacture unseen or comment-forged evidence.

Test results and source hashes are recorded in the accompanying offline
acceptance evidence directory. The disabled-function probe compares both
suppression settings against the protected pre-change index: complete provider
requests/schema, result serialization, usage, return_records and diagnostics.
The two snapshots are byte-identical (103837 bytes; SHA-256
6dd8bf5fee673bf908e4a50af0225ed7d2f13d5cad5513a27cb6da1fc3d717ca).
PostgreSQL and Docker Compose were not rerun: this change has no schema,
transport, worker scheduling or deployment changes.

## Limits and a fair next evaluation

These tests show boundary correctness, not fewer invalid answers or higher
localization recall. The note consumes context and can bias rankings; reserving
4096 bytes also reduces available raw-tool preview space. Recency eviction can
omit useful old targets, and a hint split across pages is intentionally ignored
until a complete copy is displayed. Renderer paths not instrumented with trusted
metadata produce no candidates. The core option is not yet wired into the
reviewed phased evaluation plan.

Keep the previous 20-task results immutable and use their failures only as
development regressions. For a new separately authorized experiment, freeze a
new versioned source/index/label/model configuration and a held-out sample list
before execution. Compare candidate_guidance off/on with suppress_repeats fixed,
identical call/output/context limits, predeclared order counterbalancing and
the same strict scorer. Report valid-finish rate, all-task file/entity recall,
applicability denominators, tokens, actual/conservative costs, time, context
stops, candidate omissions and failure categories. Count failed/invalid arms in
their original denominators. If testing both features, predeclare a 2x2 design
and separate budget rather than mixing factors. Repeated trials and uncertainty
analysis need their own budget; no new trial was run here.
