# Single-task runbook — approval required, nothing executed

This is a command review document, not an authorization. Use only after the operator
approves the exact question, DeepSeek recipient/model and new CNY 7 budget, and
after independent review passes. The current branch and source manifests must then
be frozen. No command below was executed during this review.

## Approval fields

| Field | Proposed value |
| --- | --- |
| repo/ref | https://github.com/pallets/itsdangerous / 096c8d42545d3b68ea21a4f890fb2b2d8979c0bd |
| question | Where does the library reject an expired signed value when a maximum age is supplied? |
| endpoint / request model | https://api.deepseek.com/chat/completions / deepseek-flash |
| expected response model | exact deepseek-flash only; mismatch halts, no auto-expanded alias list |
| generation | disable_thinking=true; max output 1024; temperature 0; stream false |
| admission | one task, max_attempts=1, max_iterations/max_calls=3, suppress_repeats=true |
| limits | request bytes 65536, HTTP timeout 60s, task deadline 300s |
| new ledger cap | CNY 7, peak uncached input 2/M, output 8/M; no reused historical grant |
| full-context reservation | context_tokens=1048576; (1048576×2 + 1024×8)/1000000 = 2.105344 per call |
| three-call maximum reservations | 6.316032; unused reserve released only after durable validated settlement |
| data | public question/repository identifiers, system/tools, retrieved public source and tool history |

The parent reported current official documentation for DeepSeek-V4.1-Flash and
these prices on 2026-10-15. The old deepseek-v4-flash request name routes to the new
version; it is not used here. Exact returned model is an acceptance policy, not a
claim that a live response has been observed. Request id is required nonempty and
stored with the immutable raw response; it is not a version or billing proof.
Account/all-in pricing confirmation and exact context allowance must be recorded
in the plan before authorization. The byte cap is not a token cap. CNY <=1 cannot
currently satisfy full-context reservation; no such guarantee is made.

## Isolated setup (after approval)

Run from the feature checkout root. Verify port 55440/API 18090 and resource names
are unused; do not remove an existing resource to make this work. Use an already
installed postgres:16-bookworm image; if absent, request the required download
permission. Do not operate on the original demo container or volume.

```sh
PYTHON="${PYTHON:-$PWD/.venv/bin/python}" # set to existing compatible Python if needed
export LOCAGENT_DATABASE_URL=postgresql://postgres@127.0.0.1:55440/public_single
export LOCAGENT_SCHEMA=public_preview_single_20261015
export LOCAGENT_PUBLIC_PREVIEW=1 LOCAGENT_PUBLIC_LIVE=0 LOCAGENT_ALLOW_PAID=0
export LOCAGENT_PUBLIC_ROOT="$PWD/outputs/public-single-20261015/sources"
export LOCAGENT_SOURCE_ROOT="$LOCAGENT_PUBLIC_ROOT"
export LOCAGENT_PUBLIC_AUTH_ROOT="$PWD/outputs/public-single-20261015/authority"
export LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
docker run --pull=never -d --name locagent-public-single-20261015 \
  -p 127.0.0.1:55440:5432 -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=public_single \
  -v locagent-public-single-20261015-data:/var/lib/postgresql/data postgres:16-bookworm
# Wait for pg_isready to succeed; do not blindly retry a failed container creation.
docker exec locagent-public-single-20261015 pg_isready -U postgres -d public_single
"$PYTHON" -B -m locagent_service.db
"$PYTHON" -B -m locagent_service.api --host 127.0.0.1 --port 18090
# In another shell with the same environment:
"$PYTHON" -B -m locagent_service.worker
```

Trust authentication here is loopback-only isolated testing, not public deployment.
API and worker commands are foreground processes; record PIDs/session ownership
and stop only these processes on completion. Set model credentials only in the
live worker environment using the operator's normal local secret mechanism; never
print, copy into commands/files, or use repository .env loading as a shortcut.

## Static first task and proposal

```sh
api=http://127.0.0.1:18090
curl --noproxy '*' -fsS "$api/tasks" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: public-single-20261015-prepare' \
  -d '{"source_id":"github-v1","repository_url":"https://github.com/pallets/itsdangerous","ref":"096c8d42545d3b68ea21a4f890fb2b2d8979c0bd","problem_statement":"Where does the library reject an expired signed value when a maximum age is supplied?","timeout_seconds":600,"max_attempts":1,"options":{"max_iterations":3,"suppress_repeats":true}}'
# Set PREPARE_TASK_ID to the actual returned ID, then query until terminal:
: "${PREPARE_TASK_ID:?Use the actual API response ID}"
curl --noproxy '*' -fsS "$api/tasks/$PREPARE_TASK_ID"
curl --noproxy '*' -fsS "$api/tasks/$PREPARE_TASK_ID/attempts"
```

Proceed only after completed, pinned SHA/source/config verified and the static
source rebuilt under the current full engine hashes. Save source ID from progress.
Create provider-config.json privately in the new output directory with all table
fields, credential_env=DEEPSEEK_API_KEY, response_models=["deepseek-flash"], and the
actual fresh pricing_confirmation. This is an operator-prepared file, not shipped
with active approval in this repository. Then review a proposed plan:

```sh
: "${SOURCE_ID:?Use verified prepared source ID}"
"$PYTHON" -B -m locagent_service.public_authorization plan \
  --source "$SOURCE_ID" \
  --provider-config outputs/public-single-20261015/provider-config.json \
  --output outputs/public-single-20261015/plan.json
```

Review exact plan hash and grant fields. Only after explicit approval and that
review, run the following separately; never regenerate/reset a consumed grant:

```sh
: "${APPROVED_PLAN_SHA256:?Use the reviewed exact plan hash}"
"$PYTHON" -B -m locagent_service.public_authorization authorize \
  --plan outputs/public-single-20261015/plan.json \
  --expected-sha256 "$APPROVED_PLAN_SHA256"
```

Restart only the owned isolated API/worker with LOCAGENT_PUBLIC_LIVE=1 and the
approved worker credential available. Public LIVE is the gate; legacy ALLOW_PAID
does not grant this path. Set AUTHORIZATION_ID from actual authorize output.
Generate live-request.json with the exact static request fields, plus this ID,
timeout_seconds=300, max_attempts=1 and options.max_iterations=3. No model/endpoint
override is accepted in the API request. Review it before submission:

```sh
curl --noproxy '*' -fsS "$api/tasks" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: public-single-20261015-live' \
  --data-binary @outputs/public-single-20261015/live-request.json
: "${LIVE_TASK_ID:?Use the actual API response ID}"
curl --noproxy '*' -fsS "$api/tasks/$LIVE_TASK_ID"
curl --noproxy '*' -fsS "$api/tasks/$LIVE_TASK_ID/attempts"
```

Inspect raw-response hashes, model/usage, settled cost, remaining reservations,
ledger task and attempt identity, and final graph-grounded locations. Empty or
wrong locations fail semantic acceptance even if transport completes. A timeout,
cancel or unknown response stops the experiment; do not retry/regrant. Shut down
only the test API/worker/container; preserve its data, grant and evidence. No
container removal, volume deletion, original DB migration or public endpoint.
