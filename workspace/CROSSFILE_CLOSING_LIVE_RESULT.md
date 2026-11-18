# 收尾修复版真实试跑验收

2026-11-12 北京时间。用户本机执行已完成；本次检查没有启动新的模型请求。

方案：`487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35`。
同一 10 文件 webhook 样例，deepseek-flash，两组调查阶段均为 auto 工具选择。

| 检查 | 基础组 | 检索工具可用组 |
| --- | --- | --- |
| 真实请求 | 4 | 4 |
| SDK 状态 | finished | finished |
| 最终第 4 次响应 | 单次 finish | 单次 finish |
| 调查工具执行次数 | 10 | 9 |
| LocAgent 调用 | 未开放 | 0（已开放但未选） |
| 源码证据字节 | 3319 | 3094 |
| 保守费用上界 | ¥0.026384 | ¥0.025126 |

8 次请求均 HTTP 200、settled；总保守费用上界 **¥0.051510**，未结预留 0，没有停机或重试。该数字按固定高峰、缓存未命中价格计算，尚未与供应商实际扣款对账。结果字段 network_attempts=0 指 SDK 进程内网络保护计数；真实传输由隔离 helper 执行，以 live_calls 和持久账本的 8 次请求为准。

逐次核对原始请求和响应：前三次 tool_choice=auto；第四次只开放并指定 finish，末尾有显式关闭调查通知，模型均提交单个 finish。SDK ActionEvent、ObservationEvent 和正常终答链已核验。这说明本样例本次收尾成功，不能据一次成功推断稳定可靠或证明修改的因果效果。

检索组真实回包依次为 search_text/list_files、四次 read_file、三次 read_file、finish。没有 locagent_retrieve，因此本次未验证真实模型自主检索、检索证据进入真实上下文或检索收益；未强制补跑。

源码人工核对：两份答案都覆盖稳定 delivery_id、429/5xx 且 attempt<3 的重试条件、发送前 receipt 检查，以及内存存储和并发竞态限制。基础组额外读取并讨论 cleanup 清除回执；检索可用组明确未读 cleanup，没有该条证据。此为有限人工核对，不是质量评分或性能比较。

一次性授权已消费；三个历史账本 SHA256 未变，原失败结果保留。当前账本 SHA256：`3c8f1a736296e8a970b1f2f16a69047a68a93db9ecb4e769961a9f118366221a`。

[机器验收记录](verification/CROSSFILE_CLOSING_LIVE_ACCEPTANCE.json) · [收尾修复说明](CLOSING_REPAIR.md)

下一步可免费检查检索工具说明与样例的适配性，再提出独立的连通性或自主选择验证方案；任何新付费试跑需单独授权，本轮不追加请求。
