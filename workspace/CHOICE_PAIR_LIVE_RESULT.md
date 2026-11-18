# 工具说明真实配对：首请求返回后停止

2026-11-13（北京时间）。用户对DeepSeek目的地、SQLGlot题面/提示/工具定义/历史搜索源码证据和会话、两请求/5元上限明确确认后，启动一次。**实际仅发送1请求，HTTP 200且费用已结算；随后新入口校验失败，第二份没有运行。无重试、无工具执行。**

## 已观察到的选择

原说明（control）响应包含：

1. `read_file(path="sqlglot/parser.py", start_line=5960, end_line=6015)`。
2. `search_text(query="_parse_set_item_assignment")`。

两项都有SDK wire schema允许的简短 `summary`。模型没有选择LocAgent。候选说明未发请求，不能计为不选择，也不能比较两种说明的影响。

## 停止原因：新入口适配错误

新增的 `experiments/choice_pair/run.py` 为观察下一步选择，直接使用 `ReadAction.model_validate` / `QueryAction.model_validate` 校验返回参数，漏掉SDK对wire辅助字段的提取步骤。

- 已发schema在read_file和search_text中都声明了可选字符串summary。
- 原始模型参数遵守这一schema。
- 底层Action类禁止未声明字段，不直接包含summary，因此直接校验报告 `summary: extra_forbidden`。
- 已保存源码 `reference/openhands-1.62.0/openhands/sdk/agent/agent.py` 中 `_extract_summary` 会提取非工具实参的summary，再调用action校验。本地只读复现：保留原响应不变，在副本中去掉summary后，两项动作参数均通过。

这是新入口缺失SDK适配步骤，不是模型选错工具或供应商失败。此前12项离线测试的正常响应夹具没有包含summary，因此未覆盖这个真实路径。未删除或修改原始回包，没有把此次halted追认成完整成功；本轮未改冻结入口或续跑。

## 费用与保护

- 冻结hash：`64dee9be8533dd47b3543e0d17b7e20c87ed5faf57e1a5c15a197c1c3f4f18b9`，发送payload与原control文件hash逐字一致。
- 1次真实请求，1份完整HTTP 200回包；输入2,820、输出151 tokens，缓存命中1,920、未命中900。
- 全输入按峰值未命中价计算：2,820×2 + 151×8 = 6,848 micro-CNY，即 **¥0.006848成本上界**。无待结费用；未与账户逐笔实扣对账。
- 一次性授权已消费，账本已halted。候选组not_run，不自动重试、补跑或追加额度。
- 上次自动审批拒绝记录保留；这次依据用户新增明确确认获得执行许可，并非绕过拒绝。
- 复核2,667份历史材料哈希不变，旧18份账本无未决请求。Key仅由已批准的本机私有加载器使用，未显示或新增保存。

## 后续边界

应先离线修复配对入口的wire辅助字段处理，按SDK语义保留摘要与原始响应、继续严格校验实际工具参数，补充合法/错误summary及未知字段回归测试。修复后是否重新做完整配对，需要新的运行方案与授权；不能直接从已halted的授权继续。

本次只有原说明下一步选择可观察，没有新说明的对应响应；样本为已曝光的人工历史状态重放，不是完整自然Agent轨迹，不构成检索收益或说明因果证据。

证据：

- [明确用户确认](verification/choice-pair-live-v1/explicit-user-confirmation.json)
- [真实验收](verification/choice-pair-live-v1/live-acceptance.json)
- [离线失败复现](verification/choice-pair-live-v1/failure-diagnosis.json)
- 原始响应和SQLite账本：`authority-choice-pair/64dee9be8533dd47b3543e0d17b7e20c87ed5faf57e1a5c15a197c1c3f4f18b9/run/`。
