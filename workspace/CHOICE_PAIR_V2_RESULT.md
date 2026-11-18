# SQLGlot 工具说明配对：入口修复与真实复跑

2026-11-13。用户授权：“修复入口适配，再试跑一次”。沿用上一轮明确批准的数据与范围：向 DeepSeek 发送 SQLGlot 题面、提示、工具定义、历史搜索源码证据与会话；两种说明各一次响应，共最多 2 次请求、5 元上限。只观察选择，不执行返回的工具、不跟进终答，异常停止、不自动重试。

## 修复与边界

旧入口直接把含 `summary` 的 wire 参数交给严格 Action，误拒绝了合法的 SDK 辅助字段。SDK 1.62.0 在 Action 校验前提取 summary（reference/openhands-1.62.0/openhands/sdk/agent/agent.py）。新入口 experiments/choice_pair_v2/run.py 仅提取冻结 schema 声明的字符串 summary；保存原始 wire_arguments、sdk_metadata、适配后的 arguments 以及原始响应。未知字段、未声明的 security_risk、错误类型及超过业务约束的参数仍拒绝。与 SDK 对非法 summary 的回退行为不同，本入口继续严格拒绝非字符串。finish 沿用现有结构及已知 null 标记兼容策略。

新模块与新冻结版本独立保留，旧入口、方案、授权、响应、失败记录均未改动。请求内容未因适配修复变化；两种请求仅 LocAgent description 不同。

离线共执行 32 次测试（20 个不同用例，12 个预算/授权用例在基类与重放类重复执行），全部通过。覆盖旧真实回包双调用重放、所有工具有/无 summary、未知字段、错误类型、必填字段、过长查询、截断、重复 JSON key、第二调用错误、超时、无授权/TTY、价格/过期/代码变化、并发与重复启动、最大预留。离线传输均为 mock，不执行目标仓库代码。

## 真实结果

冻结方案：327f2b94b2394808f75ef609f9a01aa2d855f8673b602d32664e0c0716daf3a2。
模型 deepseek-flash（官方当前版本 DeepSeek-V4.1-Flash-1017），temperature 0，非思考模式，输出最多 2048 tokens。

| 说明 | 模型返回的自主工具选择 | LocAgent | 输入 / 输出 tokens | 全未命中高峰价费用上界 |
|---|---|---|---|---|
| 原说明 control | read_file(parser.py, 5960–6015)；search_text(_parse_alter_table_set) | 未选 | 2820 / 151 | ¥0.006848 |
| 新说明 candidate | read_file(parser.py, 5960–6015)；search_text(_parse_set_item_assignment) | 未选 | 2849 / 151 | ¥0.006906 |

两次 HTTP 200，响应与参数验证通过，无异常、无重试、无未结预留。此次共 2 次请求，费用保守上界 ¥0.013754，低于 ¥5。账本每次预留 ¥2.113536 是覆盖最大上下文的保护值，不是实际费用。按照[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)以高峰输入未命中 ¥2/百万 tokens、输出 ¥8/百万 tokens 估算；未扣除缓存或空闲时段优惠，尚未和账户扣费逐笔核对。启动前账户显示人民币余额 ¥2.53、当日 37 次请求；用量页提示可延迟 5 分钟。

## 可解释范围

本次说明调整未在这个检查点引出检索选择。两次都优先请求同一文件范围，再搜索一个符号。只能观察到动作，不能据此断言模型动机、检索能力不足或新说明普遍无效。原说明此次搜索符号还与上轮不同，temperature 0 也未带来逐字一致动作；不要把组间符号差异全部归因于说明。

这是历史搜索之后人为构造的 SQLGlot 开发检查点、每种说明一个响应、固定原说明先行，并非自然完整轨迹、独立测试或因果效应估计。没有执行返回工具，所以未验证读取正文、检索结果、终答或定位质量。两种请求都开放 LocAgent，并非有/无检索对照。

若继续研究，应先离线划分“文件/行号已知”与“只有符号名”的真实历史状态，核实是否确有不同的信息需求；任何新增真实模型请求另列范围。本次不追加试跑。

## 证据

- 原始响应、请求与账本：authority-choice-pair/327f2b94b2394808f75ef609f9a01aa2d855f8673b602d32664e0c0716daf3a2/run/ledger.sqlite
- 结果：同目录 result.json
- 离线验收：verification/choice-pair-live-v2/offline-tests.log
- 启动与最终审计：verification/choice-pair-live-v2/preflight.json、live-acceptance.json
- 审计确认此前 2667 个文件及旧配对运行 5 个文件 hash 保持一致。
