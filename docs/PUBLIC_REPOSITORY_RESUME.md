# 2026-10-14 恢复验收

从昨夜检查点继续。恢复时完整 tracked+untracked diff 与检查点逐字相同，SHA-256 为
`a5f5f59c77222ee58b5d28df2ddf686e1e1b410213615cb52003345b0105751a`。
未发现后续用户改动；本轮没有修改实现代码，没有重复开发已完成功能。

## 当前完整测试结果

| 套件 | 结果 | 用时 | evidence 下日志 |
| --- | --- | --- | --- |
| 全量离线回归 | 433 项通过 | 390.476s | `resume-full-suite.log` |
| 授权 API/worker/PostgreSQL stub | 7 项通过 | 27.122s | `resume-authorized-postgres.log` |
| 公开仓库 fake 流水线 | 4 项通过 | 31.609s | `resume-fake-postgres.log` |
| 原生命周期 | 32 项通过 | 99.744s | `resume-lifecycle-postgres.log` |
| 原 prepared 兼容 | 3 项通过 | 10.877s | `resume-prepared-postgres.log` |

本轮共 479 项 unittest 执行通过。433 项全量已包含公开仓库单元 14 项、授权单元 16 项和原 HTTP/demo fixture 13 项；
不要再把这些子集加一次。数据库套件另有 7+4+32+3=46 项，未包含在 test_*.py 模式内。
其中生命周期 32 项包含它继承的 stage2 PostgreSQL 13 项和新增 19 项；没有另跑/另加该继承套件。
历史 417、412 以及昨日16/7等记录只作历史证据，不与本轮总数相加。真实静态 smoke 的两个任务不算 unittest 个数。

## 403 的证据与处理

在 02:41:16 UTC 对同一 `https://api.github.com/repos/pallets/itsdangerous` 发出一次无凭据请求，
返回403：core limit=60、used=60、remaining=0、reset=1791948112，响应明确为 API rate limit exceeded。
request ID=`FFC6:21F548:7C0577:BE7F4B:6ACEEBCB`。完整允许列出的响应头见 `resume-github-diagnostic.json`。
这证明**本次**失败为匿名 API 额度耗尽，不是 TLS/解析器失败；昨天只有403状态，未保留响应头，不能追溯断言同因。
没有证据说明额度由本程序消耗；GitHub 匿名额度关联出口 IP。

依据 [GitHub 官方说明](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit)，
remaining=0 时应等 reset 后再请求。本轮等待至 03:22:02 UTC 才允许单次同接口复查，不更换出口、不加 token、
不关闭 TLS、不换下载协议或镜像绕过限制。未为环境限流改动业务代码。

已按 GitHub 响应要求等待至重置时间之后，原 HTTPS 接口恢复，真实静态 smoke 的两个任务均 completed。

- 任务 `3e7d583e-514b-46d0-ad3c-871ec5210ae4`：cache_hit=False，commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。
- 任务 `9b6225ce-cbdb-4915-ade2-7f990b76094e`：cache_hit=True，commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。

静态来源固定为公开仓库 `https://github.com/pallets/itsdangerous`，请求 ref `2.2.0`。
历史成功静态验收的 commit 为 `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`；本轮若成功，以以上任务实际固定 SHA 为准。
本轮静态任务使用独立 schema `public_preview_resume_20261014`，source/cache 根
`/home/lenovo/projects/LocAgent-public-pipeline/outputs/public-preview/resume-sources`。

## 能力边界与未运行项

- fake-only 默认路径运行真实图/BM25和工具循环，但最终固定空文件/实体列表，不代表任意问题的语义定位质量。
- 新真实 provider 入口默认关闭；本轮只用 stub 测试授权、预算、原始响应、并发、恢复、取消与未知结果不重放。
- **未运行真实模型请求、供应商连通性 smoke、真实计费核对或模型定位质量验证。** 这些仍需父对话确认单题、接收方、模型和预算。
- Python 子进程/RLIMIT/offline guard 不是完整沙箱；尚无OS/UID/namespace网络文件隔离、cgroup总资源限制、总缓存配额/淘汰、鉴权、入口admission或多机锁。
  native parser 漏洞和同UID文件访问风险仍存在，不适合安全公开部署。
- 本轮未读取密钥、.env、完整runtime配置或旧paid账本，未真实授权、commit、push、PR或部署。

## 可复现命令

只在独立 worktree 内运行；`$PYTHON` 指向既有 `/home/lenovo/projects/LocAgent/.venv/bin/python`，不修改它。

```sh
cd /home/lenovo/projects/LocAgent-public-pipeline
PYTHON=/home/lenovo/projects/LocAgent/.venv/bin/python
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  LITELLM_LOCAL_MODEL_COST_MAP=True LOCAGENT_PUBLIC_LIVE=0 LOCAGENT_ALLOW_PAID=0 \
  "$PYTHON" -B -m unittest discover -s tests -p 'test_*.py'

# 仅启动本任务数据库：docker start locagent-public-preview-pg
# 每个 integration pattern 均配合相同代理移除前缀，并显式使用以下DSN：
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  LOCAGENT_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/public_preview \
  LITELLM_LOCAL_MODEL_COST_MAP=True LOCAGENT_PUBLIC_LIVE=0 LOCAGENT_ALLOW_PAID=0 \
  "$PYTHON" -B tests/run_stage2_acceptance.py --pattern public_authorization_postgres_acceptance.py
# 其余pattern: public_pipeline_postgres_acceptance.py,
# stage3_postgres_acceptance.py, stage4_compatibility_postgres_acceptance.py

# 仅限流解除后；每次验收使用新的public_preview_ schema和新cache root：
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  LOCAGENT_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/public_preview \
  LOCAGENT_SCHEMA=public_preview_resume_20261014 LOCAGENT_PUBLIC_PREVIEW=1 \
  LOCAGENT_PUBLIC_ROOT="$PWD/outputs/public-preview/resume-sources" \
  LOCAGENT_SOURCE_ROOT="$PWD/outputs/public-preview/resume-sources" \
  LITELLM_LOCAL_MODEL_COST_MAP=True LOCAGENT_PUBLIC_LIVE=0 LOCAGENT_ALLOW_PAID=0 \
  "$PYTHON" -B tests/run_public_static_smoke.py
```

原学习 checkout 恢复时干净，原 demo 容器恢复时已经停止，未启动/重配它。
仅本任务55439测试容器为验收启动；最终停止状态以收尾报告为准，数据保留。
进展、限流等待与最终结果均应连同本文件保留，避免把环境失败记为代码缺陷或把历史通过当作本轮通过。


## 最终隔离检查

收尾再次比较：实现和测试文件与昨夜检查点一致；本轮仅补充文档/证据。
学习 checkout 仍干净。本任务55439容器已停止并保留数据，原学习demo仍保持恢复时的停止状态。
没有留下本轮等待、unittest、acceptance 或 static-smoke 进程。
期间发生一次工具输出连接中断；先核对旧等待进程及未请求状态，再恢复为持久日志输出，未因此重复请求GitHub。
最终完整 tracked+untracked diff 已保存在 `outputs/public-preview/evidence/resume-final.diff`。
