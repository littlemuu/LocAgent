# 现有前后端复用建议（只读检查，未修改服务或页面）

当前有两套入口，适合先接本地网页，再评估异步服务：

| 层 | 现有实现 | 可复用部分 | 新增适配 |
|---|---|---|---|
| 本地页面 | `locagent_service/local_web_assets/app.js` | 输入、计划/费用确认、轮询、源码卡片、逐次费用、assistant/tool 轨迹 | 显示 SDK 引擎名；消费下表数据投影 |
| 本地 controller | `locagent_service/local_web.py` | `/api/prepare`、`/api/jobs/{id}/run`、job 状态、子进程监控、超时清理 | 固定白名单 engine 类型分派到 SDK venv；独立 plan/账本投影 |
| 本地 CLI | `locagent_service/local.py` | prepare/source 验证、保存终答后再构造 evidence 的顺序 | 新引擎执行器，勿把新 SDK 请求伪装成旧授权策略 |
| 异步 API | `locagent_service/api.py`、`store.py`、`worker.py` | `/tasks`、幂等、attempt、lease/fencing、cancel、needs_review | 新 schema/source/engine policy、SDK 子进程、租约与每次调用前授权校验 |

现有源码位置：
[本地 controller](/Users/xiaomu/Documents/Codex/locagent-demo-20261108/locagent_service/local_web.py:198)、
[CLI 执行](/Users/xiaomu/Documents/Codex/locagent-demo-20261108/locagent_service/local.py:198)、
[页面渲染](/Users/xiaomu/Documents/Codex/locagent-demo-20261108/locagent_service/local_web_assets/app.js:157)、
[异步 API](/Users/xiaomu/Documents/Codex/locagent-demo-20261108/locagent_service/api.py:60)。

## 数据投影，避免重写页面

| 新 Agent 输出 | 旧页面字段/语义 |
|---|---|
| SDK finished + 通过终答校验 | `result.status=success`；空 files/entities 为 `empty` |
| `answer.files` / `answer.entities` | `result.found_files` / `result.found_entities` |
| SDK ActionEvent/ObservationEvent、原始 wire message | 按 tool_call_id 转为 `result.messages` 中 assistant/tool 记录；只展示实际保存的内容 |
| ledger settled usage/cost | `accounting.calls[].status/usage/cost`；micro-CNY 转十进制字符串 |
| ledger `unknown` | 页面已有 `outcome_unknown`；job.state=`needs_review`，`can_run=false` |
| spent upper / outstanding reservations | `accounting.spent` / `accounting.reserved`，不得把预留显示为已扣费用 |
| 只读原源码 + 已验证位置 | `evidence.items` 的 path/start_line/end_line/snippet/hash；位置存在与相关性分开 |
| 当前模拟输出 | `demo=true`，页面明确真实调用 0、费用 0；不能把模拟 usage 当供应商 usage |

现有页面 fallback 已能在没有 evidence 时显示文件/实体名，因此可以先接结果与轨迹，再接完整源码卡片。
当前自写样例没有 GitHub commit，不能伪造源码 URL；后续真实公开仓库沿用已冻结 repo/commit manifest。
有模型预测却没有可验证的图节点时，应标记“位置未验证”，保留终答而不是重新付费运行来补证据。

本地页面目前只认旧 `authority/{identity}/ledger.json`；新账本是 SQLite，需要后端只读投影，
不要让浏览器读 SQLite、raw HTTP、授权记录或 key。现有费用组件 already 区分未知与 0、预留与结算，
应继续沿用这一口径。一次双臂实验可展示两个子结果及共同总预算；不要给每臂各复制一份 17 元授权。

## 建议接入顺序与验收

1. 先按真实调用准备文档完成 CLI 小样例协议验收，确认新授权一次性消费和第一条真实回包。
2. 在 controller 增加固定 `engine=openhands-readonly-v1` 执行器与结果适配；路径由服务器配置白名单决定，
   不接受浏览器传任意命令、解释器路径或环境变量。两个 Python 环境继续分离。
3. 免费 mock job 覆盖 prepare→preview→consent→run→completed/needs_review，确认重复提交、刷新与超时
   不会重跑；验证 usage/源码/轨迹投影，再做已有页面集成测试。
4. 最后才接异步 worker；每次模型调用前校验任务租约与批准记录，父进程退出/取消后不再发送新请求。
   macOS 不具备现有 Linux PDEATHSIG 保证，不能把 Linux 行为未经验证宣称适用于本机。

本次**没有修改** loopback/Host/Origin/session token/CSP、密钥输入、paid 开关或自动重试设置。
它们都应保留。没有启动网页服务、浏览器验收、PostgreSQL 或改数据库 schema；以上复用判断来自源码检查，
不是已接回页面的声明。
