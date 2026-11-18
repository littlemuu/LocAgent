# SQLGlot finish 空扩展字段兼容：离线修复完成

2026-11-13。124 项测试、9 条完整离线路径通过，新增真实模型请求 0、费用 0。
旧试跑仍记为失败；没有改写为成功、重跑、补跑或创建生产授权。

## 原因与证据

原 SQLGlot 检索可用组第 4 次响应为 HTTP 200、完整 JSON，finish_reason=tool_calls，输出 563 tokens。
finish.message 同时包含必填 files、entities、answer 和额外的 entities_note:null；实际发送的旧 schema 禁止额外字段。
因此旧 structured_finish 的精确字段集合检查触发 finish_message_contract_error。
这不是输出截断、网络故障、必填字段缺失或 answer 类型错误；外层 summary 是 SDK 合法字段。

- 原回包和旧 schema：[故障证据](verification/LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json)。
- 原 SQLGlot 账本 SHA256：881d6f839d2a73f2bc81e448411bd08001b25a9b7e9368485262a8d7e422921e。
- 离线夹具保留原 4 份 HTTP 响应的 Base64 原字节、请求/响应 hash：[重放夹具](tests_sdk/fixtures/locbench_extra_field_incident.json)。
- 为什么模型生成该字段，现有证据无法证明。仅能确认该空值没有正文内容、也不承担任何必填字段的含义。

## 最小兼容规则

wire schema 显式允许可选 entities_note，且类型只能是 null；additionalProperties 继续为 false。
协议适配层只将这个已知空字段从 SDK-facing 副本中移除，files/entities/answer 完整复制，不截断、补默认值、转换类型或删除正文。
原始回包在账本中逐字节保留；raw_response 保留原始 arguments。成功规范化会写入 finish_normalization 事件，附策略名、工具调用 ID 和账本调用 ID，并出现在测量报告中。

其他未知字段（即便为 null）、非 null entities_note、错误/缺失必填字段、重复 JSON 键、NaN、重复或超过 5 项的预测均继续拒绝。
额外外层参数和非字符串 summary 也拒绝。混合 finish/调查调用、截断响应和收尾 read_file 不会被兼容规则变成成功。
路径必须属于本题快照，实体名称必须符合既有格式；实体语义正确性仍交给独立评分，不以参考标签或检索图决定是否接受回答。
规范化事件表示协议处理，不代表内容正确或任务成功，后续源码路径验证仍可拒绝。

改动：readonly_agent/deepseek_wire.py、live_session.py、openhands_replay.py；批量报告增加规范化事件。
题面、源码、评分标签、系统提示、检索算法、read_file 游标语义、请求/token/费用预算均未调整。
发送给模型的 finish schema 有变化，所以这是新冻结方案，不能沿用旧的一次性授权。

## 离线验收

[汇总验收 JSON](verification/FINISH_NULL_COMPAT_ACCEPTANCE.json)；[124 项测试日志](verification/finish-compat-tests-v2.log)。
初次测试有一项错误地期待执行器拒绝不存在的实体；已按既有格式验证规则修正测试，未改生产验证器，初次失败日志保留。

| 路径 | 模拟请求 | 结果 |
|---|---:|---|
| 完整两题四组，SQLGlot 检索组采用原始 4 回包 | 16 | 完成；四份回包原字节一致、三项核心终答完全相同、1 条兼容事件 |
| entities_note 非空 | 4 | finish_message_contract_error |
| 未知字段 instructions:null | 4 | finish_message_contract_error |
| 缺少必填 entities | 4 | finish_message_contract_error |
| 快照外文件 | 4 | finish_source_validation_error |
| 末轮调用 read_file | 8 | closing_tool_violation |
| 输出截断 | 4 | model_output_truncated |
| 第二组超时 | 5 | TimeoutError，保留单请求预留 |
| 回包超过 64 KiB | 3 | 停机，保留单请求预留 |

所有路径均启用 no_network、MockTransport、合成凭据，真实 .env 加载器被替换为抛错桩。
未知结果保留模拟预留 2.113536 元；这些是测试账本数字，没有真实费用。
每条路径验证不重复领取授权、唯一请求编号、16 请求和 34 元总限制；没有自动重试。
124 项测试还覆盖错误类型、恶意字段、收尾限制、请求前持久化预留、收到无效终答后先保存结算再停机、旧授权无法加载 Key 或重启。
1,960 个原历史文件逐项 hash 不变；312 个冻结源码/评分文件不变，生产授权目录仍只有旧批次。

## 可补测，但本轮未执行

已冻结 source v4：8e178f5756b7e7b16b66cf8ed571702e5a09b7a056cb6a0b0907355cc87751e4。
新 live v2：eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83；authorization=not_granted。

若要验证真实模型，可另获批准后从头运行相同 Loguru/SQLGlot 两题、两组各最多 4 请求，共最多 16 请求、34 元总上限。
保留 OpenHands SDK 1.62.0，模型 deepseek-flash，非思考、temperature=0，单次最多 2048 输出 tokens。
发送题面、提示、工具定义、该题源码证据和该组会话历史；不发送评分标签/参考补丁。让模型自主选择检索，不强制补跑。

2026-11-13 重新读取 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：deepseek-flash 对应 DeepSeek-V4.1-Flash-1017，高峰输入未命中 2 元/百万 tokens、输出 8 元/百万 tokens，与冻结预算假设一致。
34 元是最保守预留上限，不是预计花费或账单实扣。正式启动前仍须确认实际账户适用价格、币种/附加费用、冻结 hash、旧批次已停止以及新一次性授权；本轮未登录账户或加载 Key。
旧授权已消耗且绑定旧代码，不能恢复。新 schema 的供应商实际接受情况只能由新批准试跑验证，异常仍停机且不重试。

重放只证明这份历史响应现在能沿完整执行路径结束，不证明下一轮模型会遵循 schema、不证明回答正确或检索有收益。
两题已曝光，后续只能作为开发验证。此前真实检索调用为 0；离线重放不能改称自主检索。
先前观察到的字符 offset/行号混淆仍未处理，本修复不覆盖它。
