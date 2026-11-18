# 修复版真实试跑结果

2026-11-12，北京时间。OpenHands SDK 1.62.0 + DeepSeek `deepseek-flash` 的基础组、检索工具可用组均正常终答。
两组采用同一自写样例和同一只读循环；均正确返回 `src/greeting.py:greeting`。

| 项目 | 基础组 | 检索工具可用组 |
|---|---:|---:|
| 完成状态 | completed / finished | completed / finished |
| 模型请求 | 3 | 3 |
| 调查工具调用 | 2 | 3 |
| 输入 tokens（累计） | 3066 | 3567 |
| 输出 tokens（累计） | 393 | 340 |
| 序列化源码工具正文 | 195 字节 | 263 字节 |
| 账本费用上界 | ¥0.009276 | ¥0.009854 |

基础组调用 `list_files → read_file → finish`。
检索工具可用组第一轮同时调用 `search_text` 与 `list_files`，随后 `read_file → finish`。
**模型没有调用 `locagent_retrieve`。** 因此本轮不能当作真实 LocAgent 检索执行验收，也不能得出检索收益结论。
真实 LocAgent 的独立工具执行仍仅有前面的离线集成证据。

## 预算与保留记录

- 6 次付费请求全部 HTTP 200、原始 usage 已持久化并 settled；两组执行 token 都标记 finished。
- 本轮费用上界 **¥0.019130**，未知预留 **¥0**，账本未 halt、无需未知请求复核。
- 加上之前失败轮的 3 次请求，合计 9 次，费用上界 **¥0.027366**。
- 金额按高峰、输入全缓存未命中计算；不是供应商账户余额实扣对账结果。
- 原方案 hash：`6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd`，运行绑定一致。
- 验收期间没有读取密钥、发起额外模型请求、改写结果或重置授权。此次授权已消费，不覆盖后续调用。

[验收汇总与账本哈希](verification/LIVE_PILOT_ACCEPTANCE.json)；
[基础组结果](authority/6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd/run/baseline/result.json)；
[检索工具可用组结果](authority/6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd/run/retrieval/result.json)。

本轮证明固定官方接口、原始 usage 结算、并行工具调用配对、结构化 finish 到 SDK 原生终答的转换在此样例上工作正常。
它不是性能评测：样例很小，没有评测集，也没有实际调用新增检索工具。
前后端尚未接入新 Agent；相关复用建议仍见 [前后端审查](FRONTEND_BACKEND_INTEGRATION.md)。
