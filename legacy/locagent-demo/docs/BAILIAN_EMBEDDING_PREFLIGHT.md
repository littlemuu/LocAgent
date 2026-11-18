# Bailian embedding preflight — 2026-10-15

This is an offline contract checkpoint, not a completed paid experiment.
Base: `290c965a3321dd90d4e848dd924e3134ef10fc8c`, isolated worktree
`/home/lenovo/projects/LocAgent-rag-preview`, branch `work/rag-offline-preview`.

## Initial configuration check (before user supplied the endpoint)

A presence-only check in the WSL execution process returned false for
`DASHSCOPE_API_KEY`, `BAILIAN_API_KEY`, `DASHSCOPE_BASE_URL`,
`DASHSCOPE_API_HOST`, `DASHSCOPE_WORKSPACE_ID`, and
`ALIBABA_CLOUD_BAILIAN_API_KEY`. This proves only that these variables were
unavailable to that process; it does not prove no credentials exist elsewhere.
No credential files, complete .env, or runtime.json were read. No real request
was attempted and no database/container was started for this checkpoint.

The operator must privately make an existing Beijing credential available as
`DASHSCOPE_API_KEY` in the execution environment. Never paste its value into
chat or a command that will be logged. No new key is requested. In the same
environment, provide these nonsecret values from the actual workspace console:

- `DASHSCOPE_WORKSPACE_ID`: actual workspace ID.
- `DASHSCOPE_API_HOST`: exact HTTPS API origin copied from that workspace.

The documented Beijing pattern is
`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`. Do not substitute a guessed
workspace, legacy global hostname, or Singapore endpoint. If the console's
actual Host differs, stop and verify it before changing the allowlist. Setting
variables in an unrelated terminal may not propagate to a newly spawned WSL
process; repeat only a boolean presence check in the actual execution process.

## Verified contract and implementation

Primary sources consulted on 2026-10-15:

- [Model](https://help.aliyun.com/en/model-studio/qwen3-7-text-embedding-flash)
- [Synchronous API](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)
- [Embedding guide](https://help.aliyun.com/en/model-studio/embedding)

Chosen model: `qwen3.7-text-embedding-flash`, 1024 dimensions. DashScope native
POST path: `/api/v1/services/embeddings/text-embedding/text-embedding`.
Use `input.texts` and `parameters.dimension`, `parameters.text_type`,
`parameters.output_type=dense`; query requests additionally use a fixed English
`parameters.instruct`. Document requests omit instruct. Synchronous batches
contain at most 20 strings. Rate: CNY 0.125/million input tokens; do not apply
the asynchronous batch discount or free quota to reservations.

The synchronous table says 128000 tokens per input; the model page says 131072.
Reserve the larger 131072 per input. Local 16000-byte text validation is a
separate payload limit, not a tokenizer estimate. A planned total of 61 input
strings reserves CNY 0.999424; 62 would exceed the CNY 1 cap. This permits at
most 41 document inputs if using all 20 questions. If complete code coverage
needs more, revise the frozen chunking before running; never silently drop
documents after observing rankings. No additional retries fit outside the
frozen plan merely because actual token counts are smaller.

`locagent_service/bailian_contract.py` is stdlib-only and has no network or
credential access. It validates an explicit workspace origin, builds bounded
role-specific requests, separates query/document cache identities, calculates
conservative planned cost, and checks response indices/dimensions/finite
nonzero vectors/usage. It rejects duplicate JSON keys and sanitizes errors.
Response validation cannot establish HTTP success or release a reservation.

## Remaining implementation before real requests

1. Freeze and hash the public `pallets/itsdangerous` snapshot at commit
   `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`, document membership, preprocessing,
   chunker configuration, model, dimensions, instruction, endpoint and code.
2. Freeze at most 20 natural-language questions and entity-level labels before
   producing any retrieval output. Do not embed target symbol names in questions.
   This is a manually constructed development set on a previously inspected
   small repository, not blind evaluation. The earlier expiration question was
   already seen and cannot be claimed as held out.
3. Create one independent durable authorization ledger for this experiment,
   bound to that manifest and the CNY 1 authorization. No old paid ledger reuse,
   no new budget per output directory. Persist reservations before one-shot
   transport; unknown outcomes retain funds and cannot replay automatically.
   Test concurrent reservation, crash recovery, tampering and cache reuse.
4. Add pinned-public-IP TLS transport to the verified origin only; disallow
   redirects/proxies/retries, bound time and response size. Read the key only
   inside transport, never persist headers. Save request/response hashes, usage,
   cost and sanitized failure categories. Audit raw-response storage for secrets.
5. Reuse the isolated pgvector container/database under a fresh schema. Use the
   same fixed index membership and queries for BM25, dense and RRF hybrid;
   deduplicate graph entities before top-k. No generation-model calls.
6. Report Hit@k as questions with at least one labelled relevant entity in top-k
   divided by all frozen questions. Report macro Recall@k as the average over all
   frozen questions of retrieved relevant entities divided by that question's
   full relevant-entity label set. Never remove failed questions from the
   denominator; report failures separately and count their retrieval as empty.
   Labels must be nonempty and reference members of the frozen index.
7. Stop only this experiment's services, retain evidence, and report limitations.

No full experiment manifest or development labels have been frozen yet.
An offline-only SQLite ledger harness now exists; no live HTTP transport or live authorization binding exists at this stage.
The contract tests cannot demonstrate real retrieval quality, billing, or the
complete paid-call protection. Existing demo-v1/prepared paths are unmodified.


## Private file entrypoint and offline checkpoint

The loader follows `configure.py`'s opt-in, 0600, allowlist and no-interpolation
policy, using the already-installed python-dotenv parser. It returns a private
mapping without changing process environment. Duplicate/unknown names and
malformed lines are rejected; parsing diagnostics never print source lines.
O_NOFOLLOW and fstat reject symlinks, nonregular files, wrong owner and weak
permissions. This is Linux/WSL-only. No existing private file has been read.

Actual private path:
`/home/lenovo/projects/LocAgent-rag-preview/.env.bailian.local`.
Verified `git check-ignore -v -- .env.bailian.local` matches `.gitignore:191:.env.*`;
`git ls-files -- .env.bailian.local` is empty. The private file was not created.

User steps, performed privately in WSL (do not paste key into chat):

```sh
cd /home/lenovo/projects/LocAgent-rag-preview
# Create only if absent; noclobber protects any existing configuration.
(umask 077; set -C; cat docs/bailian.env.example > .env.bailian.local)
chmod 600 .env.bailian.local
```

If creation reports that the file already exists, do not overwrite it. Open
`.env.bailian.local` in a trusted local editor and fill the three blank fields:
`DASHSCOPE_API_KEY`, `DASHSCOPE_WORKSPACE_ID`, `DASHSCOPE_API_HOST`.
Use the actual Beijing workspace console's values, not example values.
Then run the presence-only checker (no API request):

```sh
/home/lenovo/projects/LocAgent/.venv/bin/python -m locagent_service.bailian_config --env-file .env.bailian.local
```

Output contains only three presence booleans and
`beijing_host_matches_workspace`. A true match validates syntax, not account
ownership or model availability. The explicit file will be loaded in the same
future execution process; no cross-terminal export inheritance is needed.
No real runner is enabled by this checker. Host verification remains pending.

`bailian_experiment.py` now freezes canonical manifest bytes containing model,
endpoint, instruction, preprocessing, chunker, engine SHA, input membership,
questions/labels and budget. It refuses foreign labels, target symbol substrings
in questions and a full reservation above CNY 1. The source provenance and actual
engine-file hashes still require external verification; fixture manifest data
is not evidence that input was obtained from the claimed public commit.

The offline SQLite harness binds one file to one manifest. Transactional
reservations commit before one injected fake transport invocation. Settled
vectors are cached across reopen; errors become unknown, and interrupted calls
remain reserved. Both block automatic replay. Query/document keys differ.
Every call retains its full reservation after settlement, so unused portions
cannot fund extra calls. The ledger records request/response hashes, token
usage and normalized vectors; accounting reports full retained reservations,
settled token cost and unresolved counts. It never stores credentials or raw
provider error messages. Hit@k and macro Recall@k count missing rankings as zero
over all frozen questions, deduplicating entities before top-k.

This remains a fake-only harness, not live paid-call protection: a caller can
choose a different SQLite file, and there is not yet a singleton live grant
binding outside that file. Do not attach real transport. A private trusted
filesystem is assumed; this does not defend against malicious local database
replacement. No actual itsdangerous question set, input membership or live
manifest has been frozen yet.


## User-provided endpoint update

The user supplied `https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` from their console.
This is the OpenAI-compatible **base URL**, whose embedding endpoint would be
`https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/embeddings`. Append `/embeddings` only; do not append
another `/compatible-mode/v1`. The official synchronous API documents the Flash
model and its compatible response (`prompt_tokens` and `total_tokens`).

This experiment instead selects the documented native DashScope HTTP API because
the official embedding guide restricts `text_type` and `instruct` to that API/SDK.
Do not inject native `parameters` fields into an OpenAI-compatible request.
The user-provided origin stays the same; native request URL is:

`https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding`

`DASHSCOPE_API_HOST` must contain only `https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com`. The loader deliberately rejects
the compatible base URL in that field, preventing accidental mixed paths.
`docs/bailian.env.example` now contains the supplied nonsecret workspace and
origin, leaving the key empty. No private file was read, created or modified.
The public URL pattern is verified against documentation; credentials, access,
model entitlement and actual HTTP responses have **not** been verified.

For a new private file use the noclobber creation steps above; the only blank
field to fill is now `DASHSCOPE_API_KEY`. For an existing private file, edit the
two nonsecret fields to match this example without replacing its key. The
presence-check command is unchanged and still makes zero network calls.
