# 可恢复检查点

> 此检查点保留昨夜暂停状态；2026-10-14 的完整回归与静态验证状态见 `PUBLIC_REPOSITORY_RESUME.md`。



用户要求立即收尾、不再启动长测试。本阶段实现已保存到独立 worktree，无 commit。
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
| 全量 test_*.py | 按休息指令中止，未完成，不能记为通过 | authorization-full-suite.log |
| 最终版真实 GitHub 下载＋fake smoke | 失败：解析阶段 github_http_403，未继续下载 | authorization-static.log |
| git diff --check | 通过 | 收尾命令退出 0 |
| 真实模型/付费 smoke | 未运行；无凭据读取、无真实授权 | 不适用 |

历史 fake-only 阶段的 417 项全量通过和真实源码 miss/hit 成功保留为历史证据，不能当作新增授权实现的全量通过。
HTTP 403 的原因未确认，不将其直接归因于匿名额度或代理。请求失败后的诊断 ID 为
`ec96401c090945d6b4d276ef2e0950ad`。全量中的具体中断位置请保留原日志，不据部分点号推算通过总数。

所用命令（共同前缀移除代理仅作用于该命令；Python 是原有安装，不改学习目录）：

```sh
PYTHON=/home/lenovo/projects/LocAgent/.venv/bin/python
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

停止状态：本任务 `locagent-public-preview-pg` 已停止，数据保留；原 `locagent-stage2-pg`
仍运行在 127.0.0.1:55432。学习 checkout `git status --short` 为空。
已中止本任务剩余全量测试；进程检查未发现对应 unittest/acceptance/static-smoke 进程。
没有 commit、push、PR、部署，没有改全局代理，没有访问旧 paid ledger。

恢复步骤：

1. 进入 `/home/lenovo/projects/LocAgent-public-pipeline`（分支 `work/public-repo-pipeline`），先读本记录及授权设计。
2. 在用户愿意继续时重新跑 `unittest discover -s tests -p 'test_*.py'`；预计约 5–10 分钟，依主机负载，当前尚未完成。
3. 如需重跑数据库项，仅 `docker start locagent-public-preview-pg`，使用 55439 和 public_preview_ 独立 schema。
4. 查明/等待 GitHub HTTP 403 可用后，用新 schema 和新缓存根重跑真实静态 fake smoke；所需时间取决于外部访问，无法保证。
5. 更新验收记录后再决定是否需要真实模型 smoke。真实 smoke 仍须父对话确认单题、接收方、模型和预算，不自动继续。

建议后续人工拆分提交：①安全 acquisition；②后台任务/缓存/兼容；③默认关闭授权与预算；④测试和文档。
当前只保存 diff，未执行任何提交。完整 tracked+untracked patch 位于 evidence/authorization-checkpoint.diff。
