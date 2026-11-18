# Public repository single-question live smoke proposal

Status: **NOT AUTHORIZED, NOT RUN**. No grant, paid ledger or credential was created
or consumed during preparation. No embedding calls are part of this proposal.

## Exact candidate for operator approval

- Repository: https://github.com/pallets/itsdangerous
- Human release: 2.2.0; request ref must be the complete commit
  `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd` (previous static acceptance identity).
- Exact question: `Where does the library reject an expired signed value when a maximum age is supplied?`
- Proposed wire model: `deepseek-flash`; endpoint:
  `https://api.deepseek.com/chat/completions`; credential variable name only:
  `DEEPSEEK_API_KEY`. No credential value has been read. The current accepted
  response-model policy is exact allowlist `["deepseek-flash"]`, subject to operator
  confirmation before creating a plan; no wildcard or automatic fallback to old
  aliases. Unknown returned model halts with outcome_unknown and full reservation.
  Raw response id must be a nonempty string, persisted with the immutable body/hash;
  this id does not prove backend weights or justify retry.
- Recipient: official DeepSeek API. Data: the question, fixed public repository
  metadata, system/tool definitions, graph identifiers, retrieved public source
  snippets and tool/message history. No private repository, gold answer, local
  .env, runtime configuration or historical ledger is part of the request.
- One task/one attempt, max_calls=3, output_tokens=1024 each, temperature=0,
  `disable_thinking=true` bound into the new plan, serialized as
  `thinking={"type":"disabled"}` alongside tools; timeout=60 seconds/request,
  request_bytes=65536, task deadline=300 seconds, no redirects/SDK retries/fallback
  model. Unknown outcomes retain reserve and require manual review.
- The current full-context policy requires **CNY 2.105344 before even one call**:
  `(1048576 * 2 + 1024 * 8) / 1000000`. Three full reserves are CNY 6.316032;
  this explains the earlier suggested fresh CNY 7 cap. Successful settlement
  releases unused reserve, so it is not a forecast of actual spend.
- Updated pricing evidence supplied by the parent on 2026-10-15 from the official
  page: current `deepseek-flash` routes to DeepSeek-V4.1-Flash; old
  `deepseek-v4-flash` is accepted but also routes to that version. Context is 1M;
  peak CNY/M input miss 2, cache hit 0.04, output 8; off-peak half price. The plan
  uses peak uncached pricing, no discounts. 1,048,576 is retained as a conservative
  full-context accounting ceiling, pending exact account/context confirmation.
  Source: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
  Local retrieval of that page failed; the updated facts are attributed to the
  parent's successful official-page read, not a local live API probe.

## Requested <= CNY 1 cap: currently blocked, not advertised as safe

`request_payload` enforces serialized UTF-8 JSON bytes <=65536. It does not prove
provider prompt-token count, server-added chat/tool wrappers or reasoning billing.
`reserve` uses configured full context, and `usage` verifies returned usage only
after a request has already been billed. Setting context_tokens=65536 would hide
the missing proof. ProviderConfig currently rejects budget=1 because even one
full-context reserve exceeds it. No guard is bypassed or weakened here.

Conditional target for a later reviewed guard: with a proved per-request total
prompt cap of 65536 and output cap 1024, three peak-cost calls would be
`3 * (65536*2 + 1024*8) / 1000000 = CNY 0.417792`, leaving room below CNY 1.
This is **only arithmetic**, not an implemented safe bound. Required first: obtain
a provider-matched tokenizer/template or documented conservative bound including
all messages, tools and provider-added wrappers; bind its version and limit in
the exact plan; count the final serialized request before reserve/send; reject
over-limit requests and test Unicode/tool schemas/history/boundary cases. Unknown
usage, retries, pricing and output/reasoning charges must remain within the same
new ledger. No current-price reading alone establishes this tokenization proof.

Code evidence in public_authorization.py: `request_payload` handles byte cap and
explicit nonthinking; `reserve` and ProviderConfig enforce full-context reserve;
`AuthorizedProvider.__call__` locks, verifies, persists reserve/guard before
transport, enforces max_calls and saves raw response before `usage` settlement;
exceptions retain reserve and halt. `exchange` sends one POST without retries or
redirects. `usage` rejects models outside exact response_models and inconsistent
integer token counts. No automatic regrant/replay is permitted.

The new `disable_thinking` flag is explicit, defaults false for generic providers,
and is hashed with provider configuration. Earlier code discarded the inherited
disabled-thinking field; that offline blocker is fixed and tested in this branch.
Actual provider compatibility with tools remains untested. The operator must
choose a justified full-context cap or wait for the <=1 guard proof; no new paid
request is authorized by this document.

## Two linked tasks, not implicit authorization

The current API requires a prepared source before a precise live grant can be
created. Do not describe this as one HTTP request performing automatic approval.

1. In an isolated environment, submit the fixed GitHub URL/ref/question with no
   authorization to POST /tasks. Existing worker resolves/persists SHA, downloads
   static sources, builds graph/BM25, publishes manifest, runs fake and persists
   result. GET task and attempts; record source ID, commit, cache and diagnostics.
   This source must be rebuilt under this branch's complete engine hash closure.
2. Create a proposed provider-config file with the newly confirmed limits and
   exact response aliases. Use existing `public_authorization plan --source ...
   --provider-config ... --output ...`. Review canonical plan/hash and exact task
   binding. The plan itself is not authority. Only after explicit new approval,
   use the existing single-use authorize path and fresh private authority root.
3. Submit a second github-v1 request with the same exact question/commit,
   authorization_id, max_attempts=1, options.max_iterations=3 and the suppression
   setting bound in the plan. Independent worker uses verified prepared artifacts
   and actual provider tool calls; persist and query final task/result/attempts.
4. Verify immutable raw response hashes, returned models, token usage, settled
   costs, reservations, ledger task/claim binding and no replay. Save both task
   IDs and source association. Check final file/entity against the static code
   manually after the answer; do not add expected filenames/functions to prompt.
   Empty/iteration-limit/incorrect answers count as quality failure even if the
   HTTP/ledger transport works. Three calls may be insufficient; do not extend
   quota or repeat without a new decision.

## Isolation/dependency request

Use a fresh test container/database with loopback port 55440, API 18090 and schema
`public_preview_single_20261015` after checking ports/resource names are free.
Use feature-worktree `outputs/public-single-20261015/sources` and separate private
`outputs/public-single-20261015/authority`, never historical grants. These are
proposed names, not running resources. Existing PostgreSQL image/Python runtime
may be reused; verify availability first. Any image download or extra dependency
installation requires the normal permission process. No pgvector is needed for
this BM25 live smoke. Original demo/database remains stopped and untouched.

Admission gate: explicit approval of question, recipient, model and fresh budget;
fresh account/context and exact response-model confirmation; current immutable source/plan hashes;
isolated DB/API/worker and valid credential available locally. No permission is
inferred from historical experiment approvals. Full OS sandbox/public service
authentication/cache quota remain absent; this is local supervised validation.
