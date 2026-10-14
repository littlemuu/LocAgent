# Public GitHub repository preview

This is a local, opt-in backend preview that defaults to a **fake provider**. It proves acquisition,
index preparation, persistence, supervision and queryability. It does **not**
measure localization quality. Optional live execution requires a separate exact operator grant;
see `PUBLIC_REPOSITORY_AUTHORIZATION.md`. No real model call has been tested. It is not ready
for public deployment. Its scripted provider ends with fixed empty location lists;
it is not yet a semantic localization service. See the Chinese review in
`PUBLIC_REPOSITORY_REVIEW.md` for the exact behavior and test-count reconciliation.

## Request and query

Use the existing `POST /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`,
`POST /tasks/{id}/retry` and `GET /tasks/{id}/attempts` endpoints.

```json
{
  "source_id": "github-v1",
  "repository_url": "https://github.com/pallets/itsdangerous",
  "ref": "2.2.0",
  "problem_statement": "Find how URL safe timed serialization signs data.",
  "timeout_seconds": 300,
  "max_attempts": 3
}
```

`ref` is optional; omission resolves the default branch. The API validates the
request and commits a queued task, returning HTTP 202, its ID and Location. No
network download or graph work happens in the API. Existing Idempotency-Key
semantics apply. Extra paths, model/provider fields and arbitrary source IDs are
rejected. The user problem remains bounded to 8,000 characters for this source.

Run the existing worker. Stages in `progress.stage` are `resolving`, `resolved`,
`waiting_for_index`, `downloading`, `extracting`, `building_index`, `index_ready`,
`localizing`, and `completed`. The overall `status` is authoritative: progress
is the last checkpoint, and can still name an earlier stage after cancellation,
timeout or a queued retry. A completed stage alone is not a committed result.

`progress` also exposes the pinned `commit`, `cache_key`, `cache_hit`, per-question
`source_id`, `provider: fake-only` and `diagnostic_id` when available. A failure
contains a stable code and last stage/correlation ID, without raw exceptions.
The fake provider performs actual graph/BM25 tools and deliberately returns an
empty final location list. This tests the protocol, **not** relevance or quality.
`result.diagnostics` reports `paid_calls: 0` and `quality_evaluated: false`.

## Isolated local launch

Linux/WSL only for this preview. Reuse the installed LocAgent Python environment;
do not run anything from the downloaded repository. Use a separate PostgreSQL
instance or database and a schema starting with `public_preview_`.

The development worktree is `/home/lenovo/projects/LocAgent-public-pipeline`.
The original learning checkout is untouched. Example for the separate local
test database already created during development (do not point at the demo):

```sh
cd /home/lenovo/projects/LocAgent-public-pipeline
export LOCAGENT_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/public_preview
export LOCAGENT_SCHEMA=public_preview_local
export LOCAGENT_PUBLIC_PREVIEW=1
export LOCAGENT_PUBLIC_ROOT="$PWD/outputs/public-preview/sources"
export LOCAGENT_SOURCE_ROOT="$LOCAGENT_PUBLIC_ROOT"
export LOCAGENT_ALLOW_PAID=0
export LOCAGENT_PUBLIC_LIVE=0
PYTHON=/home/lenovo/projects/LocAgent/.venv/bin/python
"$PYTHON" -B -m locagent_service.db
"$PYTHON" -B -m locagent_service.api --host 127.0.0.1 --port 18089
# Another shell with the same environment:
"$PYTHON" -B -m locagent_service.worker
```

The database migration is additive schema version 3 (`progress jsonb`). HTTP
startup does not migrate. Do not run this migration against the learning demo.
Original demo-v1/prepared requests continue to work on a separately migrated
schema. Existing prepared manifests correctly reject changed engine files;
reprepare artifacts in this worktree rather than weakening their hash checks.

For fresh infrastructure, use an already available PostgreSQL image with a
distinct container name, loopback port and data directory/volume. The development
container used local trust authentication strictly on loopback for disposable
tests. That is not a production configuration. See the acceptance record for
whether the development container was left running or stopped.

## How the pipeline works

1. The existing store claims the task using row locks, lease, token, attempt and
   deadline. Each attempt runs in a fresh supervised child, as before.
2. Unauthenticated GitHub metadata confirms a public repository; commit lookup
   resolves the optional ref to a full 40-character SHA. A synchronous fenced
   progress transaction persists the SHA **before** download. Restarts reuse it.
   A crash before that transaction may resolve again; nothing was pinned yet.
3. A cache key binds normalized repository, commit, fixed index configuration,
   acquisition policy and complete engine behavior hashes. A per-key Linux
   `flock` prevents simultaneous builders. It is a local filesystem lock, not a
   distributed lock for multiple hosts/NFS.
4. GitHub's recursive tree rejects submodules and symlinks. The bounded archive
   is checked against the tree's blob hashes. Only `.py` files are written to the
   snapshot. The reused `prepare.build_indexes` creates graph and BM25 artifacts
   under an offline network/model guard. Preview retrieval top-k is 1 so tiny
   repositories are supported; the existing prepared default remains 5.
5. The complete index manifest passes existing `load_manifest` integrity checks
   before an fsync + atomic ready-pointer publication. Cache hits also verify the
   full expected repo/commit/config/engine and instance/bundle key association,
   so a valid manifest for another index cannot be substituted. Readers never consume a
   partial bundle. A crash releases the OS lock; the next owner removes the
   incomplete deterministic bundle and rebuilds. A damaged published cache fails
   closed rather than being silently repaired. Index file paths remain stable.
6. Each question receives a separate hash-addressed manifest over the same
   artifact bundle. The question and iteration options do not trigger a rebuild.
   The existing `localize_prepared` validates the manifest and runs a scripted
   fake provider inside `offline_engine`; no BudgetProvider or paid ledger is used.

Retries preserve the pinned commit and existing attempt history. Automatic
recovery after expired leases is permitted for github-v1 precisely because this
request has no operator authorization and therefore runs fake-only. An explicit known failure can use the existing
bounded retry endpoint. Cancellation and timeout retain fencing and kill the
attempt child. Prepared/paid tasks retain the existing needs-review/unknown-outcome
policy; no historical budget is reset or replayed. Authorized github-v1 requests use the separate single-task policy described in
`PUBLIC_REPOSITORY_AUTHORIZATION.md`; every interrupted authorized attempt requires review.

## Input and execution boundaries

Implemented:

- Only normalized `https://github.com/owner/repo` URLs (optional `.git` and trailing
  slash); no credentials, ports, query, fragment, escapes, local paths or SSH URLs.
- Acquisition only uses fixed `api.github.com` and `codeload.github.com` hosts on
  443. All DNS answers must be global unicast; multicast is explicitly rejected. The TCP connection uses the already checked
  IP and TLS validates the original hostname, preventing a second DNS lookup.
  No redirects, proxy inheritance, auth headers or Git subprocess/protocols.
- 8 MiB maximum response/download, 32 MiB expanded tar, 3,000 tree/archive entries,
  1 MiB per file, 512-character paths, 30 path components, 100,000 AST nodes/file.
  Downloads have 10-second socket inactivity timeouts and elapsed-time checks
  between completed reads against a 60-second target. A read may contain multiple
  receives, so a slow continuous stream can exceed that target. The actual hard
  wall-clock bound is the worker's persisted attempt deadline (default 90 seconds,
  configurable 1–900), including DNS, downloading, parsing and lock waits.
- Reject traversal, duplicate entries, hard/symbolic links, special members,
  submodules, `.gitmodules`, LFS pointers and `filter=lfs` declarations. Validate
  all ordinary file blob hashes against the pinned tree before parsing.
- Reject files Python's AST cannot parse. Use existing static AST/tree-sitter
  parsing; do not install dependencies, import repository modules, execute setup
  scripts, tests, hooks or arbitrary repository code. Only Python files enter the
  index; existing parser skip/exclusion rules remain in effect.
- Linux child limits: 6 GiB virtual address space, 180 CPU seconds, 128 MiB per
  output file, 256 file descriptors, core dumps disabled. Native numerical thread
  defaults are set to one. Routine parser/engine stdout/stderr is suppressed to
  avoid logging questions or source text; structured error logs include only ID,
  stage, exception class and code. Proxy variables are removed in the child only
  to avoid the observed LiteLLM import incompatibility; global settings stay intact.

Not implemented / limitations:

- No OS security sandbox, seccomp, dedicated UID, namespace filesystem isolation,
  or OS-level network isolation. A Python child plus monkeypatch-based offline
  guard is **not a complete sandbox**. Native parser vulnerabilities remain a risk;
  the child retains the user's filesystem access and inherited process privileges.
- No cgroup aggregate memory/process limits, per-user admission limits, total disk
  quota, cache eviction/retention policy, authentication, ingress body-size cap or
  multi-host lock. RLIMIT_FSIZE bounds individual files, not total cache growth.
- The registry is trusted operator-owned local storage, not a hostile multi-user
  shared directory. Orphan manifests/partial work from old engine keys need an
  operator-reviewed cleanup policy; do not clear historical demo outputs.
- GitHub anonymous rate limits fail closed. 403/429, unavailable repositories,
  archives using export exclusions, oversized trees and unsupported Python syntax
  may be rejected. No credentials are requested or read as a fallback.
- Crash recovery is checkpoint/rebuild, not byte-level resumable downloads. A
  moving ref resolved by a different new task can legitimately produce a new SHA.
- No real model evaluation or paid smoke has been run. Parent approval must first
  identify the single question, data recipient, model and budget.

## Verification commands

Use the isolated database environment above. For legacy tests, remove proxy
variables **for the command only**, because the existing fixture imports LiteLLM
before its older guard can mask the inherited socks5h proxy.

```sh
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PYTHON" -B -m unittest discover -s tests -p 'test_*.py'
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PYTHON" -B tests/run_stage2_acceptance.py --pattern public_pipeline_postgres_acceptance.py
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PYTHON" -B tests/run_stage2_acceptance.py --pattern stage3_postgres_acceptance.py
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PYTHON" -B tests/run_stage2_acceptance.py --pattern stage4_compatibility_postgres_acceptance.py
# Explicit real GitHub download, real parser, fake model. Use a fresh cache root
# and a fresh public_preview_ schema; the test expects miss then hit.
"$PYTHON" -B tests/run_public_static_smoke.py
git diff --check
```

See `PUBLIC_REPOSITORY_ACCEPTANCE.md` for actual results and unresolved blockers.
