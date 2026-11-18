# Public repository pipeline acceptance — 2026-10-13

> Command examples run from the repository root. Shell examples require a configured environment; Examples using `$PYTHON` accept an existing compatible interpreter; direct `.venv/bin/python` commands require the project environment. Historical `outputs/` evidence and helper scripts are local artifacts, not included in a fresh clone.

## Scope and isolation

- Base: `5869343`, original `work/locagent-baseline` checkout at
  the repository root, observed clean before and after development.
- Development branch: `work/public-repo-pipeline`; independent worktree:
  the isolated project checkout.
- No AGENTS.md found in the project/ancestor paths inspected; no project
  `.agents` or `.codex` skills directory was present. Current files, not historical
  memory or runtime configuration, were the implementation source of truth.
- Ordinary Windows sandbox calls to WSL returned access denied. Explicit
  escalated WSL commands were approved, so development was not blocked.
- Separate database: container `locagent-public-preview-pg`, existing local
  `postgres:16-bookworm` image, loopback port `55439`, database `public_preview`.
  Test schemas are `public_preview_*` or existing test runner's unique
  `acceptance_*` schemas on this separate database. The original
  `locagent-stage2-pg` on `55432` was not stopped, reconfigured or cleared.
- Cache/output: this worktree's `outputs/public-preview` and uniquely named
  temporary test directories. No old paid ledgers, runtime.json or .env were read,
  reset or replayed. No new software was installed. No commit, push, PR or deploy.

## Implementation files

| Files | Change |
| --- | --- |
| `locagent_service/public_repo.py` | Strict URL/ref validation, pinned public-IP HTTPS, no redirects/proxy/auth/git, bounded tree/archive validation, Python-only static extraction |
| `locagent_service/public_pipeline.py` | Fake-only preview, child resource limits, exclusive cache build and atomic ready pointer, per-question manifests, correlated sanitized errors |
| `locagent_service/models.py`, `api.py` | `github-v1`, repository URL/ref, opt-in isolated schema/root admission, queryable progress |
| `locagent_service/store.py`, `worker.py` | Fenced persistent checkpoints, preserved SHA across recovery, existing supervision/lease/timeout/cancel machinery |
| `locagent_service/migrations/003_public_pipeline.sql`, `db.py` | Additive schema version 3 with progress JSON |
| `locagent_service/prepare.py` | Reuse graph/BM25 build helper, original default top-k preserved; record the actual running interpreter's package environment |
| `tests/test_public_pipeline.py` | URL, ref, networking, archive/resource boundaries, isolation, submodules, cache concurrency and failed/incomplete builds |
| `tests/public_pipeline_postgres_acceptance.py` | Real database/API/worker/parser, fake source/provider; restart/fence/commit pinning, failure/retry, cancellation and timeout |
| `tests/run_public_static_smoke.py` | Opt-in genuine GitHub source download and real static index + fake model, two questions to prove cache reuse |
| `README.md`, `docs/PUBLIC_REPOSITORY_PREVIEW.md` | Entry point, architecture, operating instructions, exact limits and outstanding isolation/production work |

## Results

Commands use the existing compatible Python environment with `-B` from the test
checkout; set `PYTHON` when its environment is outside that checkout. Legacy engine tests removed proxy variables only in the command's
environment; global proxy settings were not changed.

| Check | Result |
| --- | --- |
| Original `test_stage2_service.py` | PASS, 13 tests |
| New `test_public_pipeline.py` | PASS, 11 tests |
| `run_stage2_acceptance.py --pattern stage3_postgres_acceptance.py` | PASS, 32 tests on separate PostgreSQL |
| `run_stage2_acceptance.py --pattern public_pipeline_postgres_acceptance.py` | PASS, 4 tests; final run 28.360 seconds |
| `run_stage2_acceptance.py --pattern stage4_compatibility_postgres_acceptance.py` | PASS, 3 tests |
| Complete offline `unittest discover -s tests -p 'test_*.py'` | PASS, 412 tests in 364.587 seconds; 2 added boundary tests also passed separately |
| Real GitHub static + fake smoke | PASS after anonymous quota reset; 2 completed tasks, miss then hit, same fixed commit and distinct question manifests |
| `git diff --check` | PASS, including final tracked code/docs |
| Real paid model smoke / quality evaluation / public deployment | NOT RUN; intentionally outside authorization |

The first complete offline test run executed 412 tests and reported one failing
test with one subtest error: the engine binding guard rejected a changed source
hash while I was still editing engine files in parallel. This was a test-process
mistake, not an exception to the manifest checks. After freezing implementation
files, the whole suite was rerun. Two later isolation/submodule tests were added
only under `tests/` and were separately included in the 11-test boundary pass.

The first new fixture integration exposed BM25 top-k greater than the tiny
fixture corpus. Preview index/module retrieval is now top-k 1; the original
prepared top-k 5 remains unchanged. The repeated database acceptance passed.

## Genuine GitHub attempt

Requested `https://github.com/pallets/itsdangerous`, ref `2.2.0`, through the actual
API submission and supervised worker. First attempt returned a persisted failure:

- Task: `b76a5d6d-c744-4133-8a78-2fd7bd0e0dc7`
- Stage: `resolving`; error: `github_http_403`
- Diagnostic: `2ddaa21c92db4ef38576e63dfea87ea9`
- Read-only header check confirmed `X-RateLimit-Remaining: 0` and reset at
  `2026-10-13T10:07:20Z`. No token was used or requested.

After the published quota reset, the unmodified pipeline succeeded twice:

- Pinned commit: `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`.
- Build/miss task: `1b5e90fe-7c52-4b5f-8930-b2a0d25d2da8`, completed.
- Reuse/hit task: `84340c30-7719-47ea-ab83-86b5d6ac096b`, completed.
- Shared cache key: `b80d8daa46475e1203a5234b45d43bb27c103d2081da59ec1b2ecf994b329d2c`.
- Question sources:
  `prepared-9a8c0c2e533ef74bf1d82c7f4ac93b5573da2fdc681f517029ec9370b4491293`
  and `prepared-5be97a3e3da0893a6c21e8066327fb31e7cd9baa133c9fd5b515d6d299f848c9`.
- The runner asserts real queryable results, zero paid calls, miss then hit,
  equal commit and different question source IDs.
- Original-run evidence: `outputs/public-preview/evidence/static-smoke.json` and
  `outputs/public-preview/evidence/static.log`. This is genuine public source
  acquisition with a fake model; final locations are deliberately empty, so it
  proves orchestration rather than semantic localization accuracy.

No remaining environment/approval blocker was observed. GitHub anonymous rate
limits remain an operational limit, handled as a persisted failure.

The task-owned PostgreSQL container was stopped after evidence collection; its
database is retained. Resume only that container with
`docker start locagent-public-preview-pg` to inspect the stored task IDs using
schema `public_preview_static`. No API or worker is left running. The original
demo container remains running on 55432.

## Remaining work and review split

The delivered endpoint is explicitly fake-only. It tests orchestration, not
localization quality. Real model enablement remains a separate step requiring
the operator's explicit single-question, recipient, model and budget
confirmation plus a recovery/ledger design for new public-repository jobs.

There is no complete OS sandbox, cgroup aggregate limit, total-cache quota,
multi-host locking, authentication, admission/body limits or cleanup/eviction
policy. Native parser vulnerabilities and inherited filesystem privileges remain
relevant. Do not expose this service publicly. Detailed implemented limits and
non-guarantees are in `PUBLIC_REPOSITORY_PREVIEW.md`.

Suggested review/commit split (nothing committed):

1. Acquisition validation + limits and unit tests.
2. Reusable index helper + immutable cache + fake localizer.
3. API/store/worker checkpoint integration + migration + database acceptance.
4. Runbook, real static smoke and acceptance record.

Final diff and test logs are retained under `outputs/public-preview/evidence`.
No model ledger is created by this preview.


## Delivery review follow-up

The independent review and main review reproduced and fixed two narrow issues:
multicast DNS answers that Python classified as global are now explicitly
rejected, and cache hits now bind the entire expected repo/config/engine/commit/
instance/bundle association instead of accepting a valid different-repository
manifest at the same commit. The reviewer read back both fixes and reported no
remaining reproducible blocker within this local trusted-registry scope.

The download timeout wording was corrected: socket inactivity and between-read
elapsed checks do not guarantee a strict 60+10-second bound under a slow stream;
the supervisor's persisted attempt deadline supplies the actual whole-attempt
wall-clock limit.

Added HTTP tests reject provider/model/api_key/api_base/allow_paid and nested
provider overrides before persistence. Another test proves fake fixed empty
finish behavior and that even a paid-enabled environment does not select the
BudgetProvider path. This remains fake-only orchestration, not localization
quality evidence. Real provider enablement needs separate new-job authorization,
durable budget reservation and unknown-outcome recovery design.

Review-run results:

- Public boundary suite: **14 passed**, 2.534 seconds.
- Public PostgreSQL suite: **4 passed**, 27.307 seconds.
- Real GitHub static source + fake: **both tasks completed** after rebuilding
  against the revised engine in separate `review-sources` and `public_preview_review`.
  Same commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`; miss task
  `c5c6becb-ea15-4915-9248-ef081dd34c6c`, hit task
  `f4b07b72-041c-4828-8788-4d7d60431a46`. No paid calls.
- Complete offline review-run: **417 passed**, 319.793 seconds. This total already includes all 14 current public unit tests and the original 13 HTTP/fixture tests.

Count reconciliation: historical 412 already included the HTTP/fixture 13 and
the then-public-unit 9; later 11 and current 14 overlap those 9. Current full
discovery includes the current public unit suite. PostgreSQL 32 is a separate
suite (13 inherited database tests + 19 lifecycle tests), and those inherited 13
are not the HTTP/fixture 13. Public PostgreSQL 4 and prepared PostgreSQL 3 are
separate from test_*.py discovery. Two real-source tasks are smoke cases, not
additional unittest methods. Do not add all numbers as independent tests.

Review evidence: `outputs/public-preview/evidence/review-*.log`,
`review-static-smoke.json`, and refreshed `final.diff`. See
`PUBLIC_REPOSITORY_REVIEW.md` for the user-facing Chinese design and review.


## 2026-10-13 授权层验收检查点

此节记录 2026-10-13 授权层验收检查点；后续完整验收见 `PUBLIC_REPOSITORY_RESUME.md`。
新增默认关闭的精确操作员授权、独立账本、发包前满额预留、原始响应后结算、未知结果不重放。
详见 `PUBLIC_REPOSITORY_AUTHORIZATION.md`。独立审查发现的内部 Decimal 格式和 partial body 留存问题已修复并复核。

最终冻结实现的结果：

| 验收 | 结果 | 证据文件（outputs/public-preview/evidence/） |
| --- | --- | --- |
| 授权边界/预算/并发/断连/写盘/审查回归 | 16 项通过，8.371s | authorization-unit.log |
| 授权 API/真实 parser/worker/DB/stub、恢复和取消 | 7 项通过，21.114s | authorization-postgres.log |
| 原公开仓库 fake 流水线 | 4 项通过，26.074s | authorization-fake-regression.log |
| 原 DB 生命周期 | 32 项通过，90.556s | authorization-lifecycle-regression.log |
| 原 prepared 兼容 | 3 项通过，10.049s | authorization-prepared-regression.log |
| 全量 test_*.py | 中止，未完成，不能记为通过 | authorization-full-suite.log |
| 最终版真实 GitHub 下载＋fake smoke | 失败：解析阶段 github_http_403，未继续下载 | authorization-static.log |
| git diff --check | 通过 | 收尾命令退出 0 |
| 真实模型/付费 smoke | 未运行；无凭据读取、无真实授权 | 不适用 |

历史 fake-only 阶段的 417 项全量通过和真实源码 miss/hit 成功保留为历史证据，不能当作新增授权实现的全量通过。
HTTP 403 的原因未确认，不将其直接归因于匿名额度或代理。请求失败后的诊断 ID 为
`ec96401c090945d6b4d276ef2e0950ad`。全量中的具体中断位置请保留原日志，不据部分点号推算通过总数。

所用命令（共同前缀移除代理仅作用于该命令；Python 是原有安装，不改学习目录）：

```sh
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
# 所有 unittest 命令均以以下 env 前缀运行：
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  LITELLM_LOCAL_MODEL_COST_MAP=True "$PYTHON" -B -m unittest discover -s tests -p test_public_authorization.py
# DB 命令另外使用 LOCAGENT_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/public_preview
"$PYTHON" -B tests/run_stage2_acceptance.py --pattern public_authorization_postgres_acceptance.py
"$PYTHON" -B tests/run_stage2_acceptance.py --pattern public_pipeline_postgres_acceptance.py
"$PYTHON" -B tests/run_stage2_acceptance.py --pattern stage3_postgres_acceptance.py
"$PYTHON" -B tests/run_stage2_acceptance.py --pattern stage4_compatibility_postgres_acceptance.py
```

真实静态 smoke 使用独立 schema `public_preview_auth_static`，缓存
`outputs/public-preview/auth-static-sources`，显式 `LOCAGENT_PUBLIC_LIVE=0`、`LOCAGENT_ALLOW_PAID=0`。
测试自己的临时授权都指向 provider.example 和 synthetic 价格，transport 由 stub 注入；没有建立真实供应商授权。

## 后续验证与隔离要求

该检查点的全量回归中止及静态下载 403 均保留为未通过证据；后续结果见 [2026-10-14 验收](PUBLIC_REPOSITORY_RESUME.md)。
复测数据库仅使用独立测试容器、55439 端口和 public_preview_ schema；静态 smoke 使用新 schema 和新缓存根。
真实模型 smoke 仍须操作员确认单题、接收方、模型和预算，不自动继续或重放旧付费账本。
历史实现快照保存在 `outputs/public-preview/evidence/authorization-checkpoint.diff`。
