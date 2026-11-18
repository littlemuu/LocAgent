# .env 复用与工具说明版真实试跑结果

2026-11-12 北京时间。已按用户既有批准完成一次试跑，无需再次输入 Key。新增真实请求共 8 次，未重试、未补跑，未扩大 17 元上限。

## 安全换绑与凭据使用

- 旧方案 `fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f` 原先未领取、无运行目录/账本。将旧 `grant.json` 原字节归档为 `grant.superseded.json`，移除其可执行入口并落盘，保留 `supersession.json`；旧目录仍存在，不能重复创建同 hash 授权。
- 当前代码方案为 `5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2`。在内存反向还原全部 `.env` 改动后，整体代码 hash 与旧批准版本完全一致；其余计划字段、引擎、源码、题面、预算和模型没有变化。
- 重新冻结后，依据用户同一批准登记一次新授权。旧授权先失效，新授权后创建，最终新授权已消费；旧方案仍无 claim/运行。四个历史真实账本 SHA256 未变。
- 启动前再次核对 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：高峰缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens，八次完整保守预留 16.842752 元，低于 17 元限额。
- 执行现有受控 CLI `--live --env-api-key`，经过授权、源码、代码及 TTY 检查后由运行程序读取原项目私有 `.env`。没有通过聊天/命令行明文输入或输出 Key，没有复制/修改原 `.env`，不导入旧付费开关，不把 Key 送入模型或环境变量。不是自动化 Terminal 应用，也没有改变系统安全设置。

## 结果

| 项目 | 基础组 | 检索可用组 |
| --- | --- | --- |
| 模型请求 | 4 | 4 |
| SDK 终态 | finished | finished |
| 调查工具调用 | 9 | 8 |
| LocAgent 自主调用 | 未开放 | 1 |
| 源码结果总字节 | 3094 | 3841 |
| 保守费用上界 | ¥0.025462 | ¥0.027070 |

总费用上界 **¥0.052532**；8 次 HTTP 200 均 settled，未结预留 0、halted=false。这是固定高峰缓存未命中单价的保守核算，未与供应商实际账单对账。

两组第一轮真实出站请求分别与 `.env` 改动前冻结的工具说明版首轮请求完全一致，因此密钥加载方式没有改变模型看到的首轮内容。前三轮 tool_choice=auto；第四轮均只提供并调用一次 finish，没有第五次请求。

## 本次真实自主检索证据

检索组第一轮模型同时选择 search_text("webhook") 和 locagent_retrieve("webhook delivery retry")。LocAgent 不是 forced tool，也不是脚本回放。

已对照原始供应商回包的 call ID/参数、SDK ActionEvent、对应 ObservationEvent 与下一次实际出站请求：

1. 模型自行请求 locagent_retrieve，出站 tool_choice=auto。
2. 工具执行成功，返回 retry.py 文件及相关函数源码。
3. **1642 字节的完整观察结果 JSON** 原样进入第 2 次模型请求，call ID 一致，未分页遗漏。
4. 最终正常 finish，终答引用 dispatch/retry.py。

审计分类为 `live_auto_selection`，`chain_verified=true`。这是首次完成本项目这条真实自主检索链的验证。

不能据此证明工具说明修改导致了选择变化，也不能宣称检索收益：只有一个样例和一次观察；两组都用了 4 次请求，检索组源码结果字节反而更多。基础组读取 http.py 并讨论 Idempotency-Key；检索组未读该文件、明确保留不确定性，也没有给出该头部证据。其关于超时后的重试表述并未由已读代码建立；本轮没有做质量评分或改写原始终答。

## 证据与状态

- [冻结方案](verification/env-rebound-v1/proposal.json) / [范围与历史状态核对](verification/env-rebound-v1/preflight.json)
- [真实验收记录](verification/env-rebound-v1/live-acceptance.json) / [检索链审计](verification/env-rebound-v1/retrieval-observability.json)
- 原始账本位于 `authority/5cb8a59a…/run/ledger.sqlite`，SHA256：`d5da0c98137ec3b637a578733813ee18faf8f88309dbf5e3189cfbc5778cdc94`。

当前没有待用户输入或未结请求。此授权已用完，后续新样例或新试跑不在本次批准范围内。
