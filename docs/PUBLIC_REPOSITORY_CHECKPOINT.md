# 2026-10-13 授权层验收检查点

> Command examples run from the repository root. Shell examples require a configured environment; Examples using `$PYTHON` accept an existing compatible interpreter; direct `.venv/bin/python` commands require the project environment. Historical `outputs/` evidence and helper scripts are local artifacts, not included in a fresh clone.

> 此检查点保留 2026-10-13 的历史验证状态；2026-10-14 的完整回归与静态验证状态见 `PUBLIC_REPOSITORY_RESUME.md`。


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
