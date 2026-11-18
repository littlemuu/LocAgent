# 跨文件真实试跑：基础组收尾失败，检索组未启动

后续已完成 [显式收尾控制修复与离线验收](CLOSING_REPAIR.md)，尚未付费验证。
以下原始失败记录保持不变。

2026-11-12，北京时间。检查原始账本、出站请求、HTTP 回包、SDK 结果与工具审计后确认：
本轮未完成。基础组的第 4 次请求触及收尾阶段，供应商回包仍要求调用已关闭的调查工具，
被本地校验拒绝；按“异常停止、不补跑”的授权范围，检索组没有启动。

## 可核对的原因

- 前 3 次模型请求共执行 10 次调查工具，成功读取 api、retry、identity、worker、receipts、backoff、http、cleanup 等文件。
- 第 4 次出站 JSON 中 `tools` 只含 `finish`，`tool_choice` 指定 `finish`，`thinking.type=disabled`，并非 auto。
- 该次 HTTP 200 的原始回包却给出两个 `read_file` 调用，目标是 `dispatch/metrics.py` 与 `dispatch/reports.py`；没有 finish。
- 本地 `normalize(response, {'finish'})` 离线复现 `ValueError: unavailable_or_invalid_tool_call`。
  这两个被拒绝的工具**没有执行**，没有第 5 次请求；SDK 结果为 failed / ConversationRunError。

[官方接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)说明非思考模式允许指定工具选择。
本次发出的参数形式与文档一致，回包没有遵守该工具限制。单次证据不足以定位供应商内部原因，
也不能保证换一种提示就能解决；现阶段不能把 `tool_choice` 当作实际执行权限或可靠收尾的唯一保障。
本地拒绝越界工具的保护按预期生效。

这与第一次 greeting 试跑的“终答字符串/JSON schema 不一致”不同：本次根本没有返回 finish。
既有实现收尾时收窄工具表，但没有额外插入一条明确告知“调查已结束、现在提交现有证据”的消息；
这是后续可以离线改进的提示策略，尚未修改或验证其对真实模型的效果。

## 费用和检索结论

- 本轮 4 次请求全部 HTTP 200，usage 均落盘并 settled；费用上界 **¥0.018574**，未知预留 **¥0**。
- 账本 halted / needs_review 来自协议停止，**不是仍有费用未知请求**。
- 加上此前两轮，累计 13 次请求，账本费用上界 **¥0.045940**。均为保守核算上界，不是供应商余额实扣对账。
- 检索组状态应记为 **not_run**，不能记为“模型未选择检索”，也不能判断是否会自主调用 LocAgent。
- 本轮检查没有读取 Key、发起新模型请求、补跑、修改运行代码、放宽工具权限或重置授权。

[诊断摘要与账本哈希](verification/CROSSFILE_LIVE_INCIDENT.json) ·
[第 4 次精确请求/回包](verification/crossfile-closing-exchange.json) ·
[基础组原始结果](authority/7295139e58ac88d2d500f50e7b8c0fcafca1d9d9df5b4d114dc8d1a0b8b56a2a/run/baseline/result.json)。

原授权已消费，不要重新运行旧命令。后续应先离线审查收尾提示和更明确的错误分类，
再提出新的、有独立范围与预算的验证方案；不能继续本轮或自动把检索改成强制调用。
