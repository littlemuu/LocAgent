
## 2026-11-12 北京时间｜.env 换绑授权与首次真实自主 LocAgent 检索

- 根据用户对同一样例、最多 8 次请求/17 元的既有批准，先检查旧工具说明版试跑未领取、无运行目录/账本，全部历史账本无未结预留。当前官方高峰输入/输出价格仍为 2/8 元每百万 tokens。
- 在内存反向还原 .env 相关改动后，整体 runtime hash 精确匹配旧批准版本；新旧 plan 除 runtime_hash 外完全一致。冻结新方案 `5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2`。
- 旧 `fb1fca68…` grant 原字节归档为 grant.superseded.json 后，移除 grant.json 可执行入口、fsync，并复核无 claim/run；保留 supersession.json。之后才将同一用户批准绑定至新方案，无两份同时可用的授权。
- 通过受控 CLI --live --env-api-key 执行一次。程序在授权/范围/TTY 检查后复用原私有 .env；Key 不显示、不复制，不放入模型、日志或子进程环境。没有自动化 Terminal 应用、改系统安全设置或要求用户再输入 Key。
- 两组均 4 次真实请求、SDK finished；8 次 HTTP 200 全部 settled，总保守费用上界 ¥0.052532（基础组 ¥0.025462、检索组 ¥0.027070），未结预留 0，无重试/补跑。新授权已消费，旧授权已失效且仍无运行；四个历史账本哈希不变。
- **首次观察到真实自主检索**：第一轮 tool_choice=auto，模型自行调用 locagent_retrieve，query 为 webhook delivery retry；工具成功返回 retry.py 相关源码。call ID/参数、SDK action/observation、完整 1642 字节观察结果进入第 2 次真实请求、正常 finish 的链路全部核验通过，分类 live_auto_selection，chain_verified=true。
- 两组第一轮出站与 .env 改动前冻结的工具说明版第一轮出站完全一致。单次结果不证明描述调整的因果效果或检索收益；检索组未读 http.py，缺少 Idempotency-Key 的证据，其超时重试表述未由已读代码确立，不做质量评分。
- 当前账本 SHA256：d5da0c98137ec3b637a578733813ee18faf8f88309dbf5e3189cfbc5778cdc94。交付 `ENV_REBOUND_LIVE_RESULT.md`、`verification/env-rebound-v1/live-acceptance.json`、`retrieval-observability.json` 及冻结 proposal/preflight。无剩余用户操作或未结请求；后续新试跑不自动执行。
