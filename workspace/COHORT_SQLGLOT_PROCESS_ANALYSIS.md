# SQLGlot 单题过程对照：原始轨迹只读分析

本次只读取已完成试跑的请求、响应、工具结果和执行器规则；没有读取密钥、调用模型、读取 gold 或修改历史。原始文件前后哈希一致，核验记录在 `verification/cohort-sqlglot-process-analysis-v1/read-only-receipt.json`。逐轮完整参数、模型可见证据、终答和 usage 导出到同目录 `round-evidence.json`。

## 最重要的区别

原生适配组是“两轮调查 + 一轮终答”；OpenHands 是“两轮搜索 + 一轮读取 + 一轮终答”。**原生组第三轮是证据字节预算耗尽后的强制收尾；OpenHands 第四轮是请求次数上限触发的强制收尾。** 两次末轮实际请求都只提供 finish，并设置指定 finish 的 tool_choice。因此，3 对 4 不能解释为原生模型自主判断更快或更有把握。

这也不是“纯基础工具对检索”的单变量实验：原生组有图探索、实体/正文混合搜索，OpenHands 有普通搜索/读取并额外开放实体 BM25 检索；提示和工具不同。

## 原生 LocAgent 适配组逐轮

表中“返回证据”指真正进入下一次模型请求的工具消息，不是后端生成的所有内容。一次模型响应可包含多个工具调用。

| 请求 | 模型调用及关键参数 | 实际返回证据 | 输入 / 输出 token |
|---|---|---|---:|
| 1 | `explore_tree_structure(start_entities=["/"], traversal_depth=2, dependency_type_filter=["contains"])`；`search_code_snippets(search_terms=["SET TAG","_parse_set_tag","SetItem","Command(this=TAG"])` | 目录图首屏 4,096 字节，含许多文件；搜索首屏 4,096 字节，先给 parser.py 6001–6080 的正文，包括 `_parse_set_item`、`_parse_set` 和 Command 回退，再到 snowflake.py 401–480 的前段。两页均有 next_offset，但未续页。 | 3,875 / 147 |
| 2 | `search_code_snippets(search_terms=["_parse_set_item_assignment","SET_PARSERS","SET_TRIE","TAG"], file_path_or_pattern="sqlglot/parser.py")`；另一次 `search_terms=["SET TAG","SET_PARSERS","TAG"]`、文件限定 `sqlglot/dialects/snowflake.py` | parser 页 4,096 字节：精确实体匹配给出 `_parse_set_item_assignment` 5969–5987 完整函数，随后正文片段；Snowflake 页仅剩 2,048 字节，包含 ALTER_PARSERS 的 SET/TAG 分派。两页均还有 next_offset，未续页。累计证据正好 14,336 字节。 | 6,193 / 163 |
| 3 | **只允许 `finish`** | 提交 3 个文件、4 个实体候选和原因说明，没有再调查。 | 6,151 / 587 |

实际调查工具共 4 次：图探索 1 次、search_code_snippets 3 次；正文后端另记录 10 个子查询，不能把它们算成 10 次模型请求。工具可返回完整函数正文，所以第二轮搜索已兼有“读取目标函数”的作用。目录首屏占了总证据预算的 4,096/14,336，约 28.6%；不能把这一页全部视作定位所需的有效信息。

第三次请求仍包含先前 4 条工具消息，长度分别为 4096、4096、4096、2048，未发现改写或删除旧工具消息。第三轮输入 token 略低于第二轮不能据此推断历史被截断；收尾工具定义缩减为 finish 是可观察的输入变化之一。

原生终答的文件为 parser.py、dialects/snowflake.py、expressions.py；实体为 `Parser._parse_set_item_assignment`、`Parser._parse_set`、`Parser._parse_set_item`，以及 `Snowflake.Parser.ALTER_PARSERS`（带各自文件前缀）。它认为 `_parse_primary` 只消费 `foo`，留下点号后部分，最终触发 `_parse_set` 的 Command 回退；建议完整解析点号标识符，并声明 `_parse_column` 未直接核实。类属性候选不应自动视为合格函数实体。

## OpenHands 适配组逐轮

| 请求 | 模型调用及关键参数 | 实际返回证据 | 输入 / 输出 token |
|---|---|---|---:|
| 1 | 两次 `search_text`，query 分别为 `SET TAG`、`SetItem` | 374 字节：dotless SET/UNSET TAG 测试及另一测试；833 字节：SetItem 的定义/引用，包括 parser.py:5987、expressions.py:1456、generator.py:1987。此时拿到行级线索，未拿到目标函数全文。 | 1,973 / 121 |
| 2 | 两次 `search_text`，query 为 `_parse_set_item`、`TAG` | 1,685 字节：函数定义在 parser.py:5969、6001 等位置；2,958 字节：Snowflake 426/429 行 TAG 分派，同时有 LISTAGG、STAGE 等字面匹配噪声。累计证据 5,850 字节。 | 2,481 / 110 |
| 3 | `read_file(path="sqlglot/parser.py", start_line=5960, end_line=6015)`；`read_file(path="sqlglot/dialects/snowflake.py", start_line=420, end_line=435)` | 2,621 + 838 字节，完整覆盖目标赋值函数、Set/Command 回退和 Snowflake 分派。两个 next_cursor 都为 null，未发生续页。累计证据 9,309 字节。 | 4,045 / 192 |
| 4 | **只允许 `finish`**；controller 的 closure reason 为 `request_limit` | 提交 4 个文件、5 个实体候选和原因说明。controller 显示可用证据为 0 是调查已关闭的状态，不表示实际上用满了 14,336 字节。 | 4,762 / 624 |

所有 search_text/read_file 参数还包含解释操作意图的 `summary` 字段，完整原文见 JSON。模型未显式提供搜索 offset，默认行为不等于它主动请求了分页。

OpenHands 的文件候选比原生多 generator.py；前三个函数候选相同，另有 `sqlglot/dialects/snowflake.py:Parser.ALTER_PARSERS` 和 `sqlglot/expressions.py:SetItem`。前者限定名与原生不同且是属性候选，后者是类。它把 `_parse_primary` 描述为已消费点号表达式为 Column，再触发回退，与原生说法不一致；它也声明没有检查 `_parse_primary` 的具体实现。这里仅复述模型结论，未将其当作已验证根因。

## 检索选择：哪些可以知道

原生组实际选择了其检索工具：正文 BM25 回退和精确实体命中都在模型可见消息中出现。OpenHands 第 1–3 轮每次都实际提供 `locagent_retrieve`，tool_choice 为 auto，但三轮均未选；第四轮收尾时该工具才被移除。

OpenHands 看到的检索说明明确写明：按文件路径/符号名查询实体 ID，词法 BM25，最多五个实体，返回片段；不搜索正文、不做语义检索或调用关系遍历；正文词串可用 search_text，已知文件可用 read_file。

**与证据相容的解释**：初始线索 `SET TAG` 是正文文字，用 search_text 合理；后续搜索已经给出文件与行号，read_file 能直接得到目标函数，形成了不依赖 LocAgent 的完整路径。到了第三轮，已无下一轮调查机会，按已知位置读取也是可行选择。

**不能由轨迹证明**：模型是否认为 LocAgent 无用、是否不理解工具说明、是否偏好熟悉工具、换题/换预算后是否会选择它。第二轮已有符号线索时仍有自主选择机会，所以不能说它“完全没有机会用检索”。本次不能判定检索无收益，也不能量化两工具在同一决策状态下的反事实差异。

## 请求、token 和费用

| 项目 | 原生适配组 | OpenHands 适配组 | 合计 |
|---|---:|---:|---:|
| 请求及 HTTP 200 有效回包 | 3 | 4 | 7 |
| 累计输入 token（包含重复会话历史） | 16,219 | 13,261 | 29,480 |
| 累计输出 token | 897 | 1,047 | 1,944 |
| 输入缓存命中 | 4,352 | 4,992 | 9,344 |
| 输入缓存未命中 | 11,867 | 8,269 | 20,136 |
| 保守账本上界／元 | 0.039614 | 0.034898 | 0.074512 |
| 按运行时已记录空闲价和缓存估算／元 | 0.01554204 | 0.01255684 | 0.02809888 |

保守账本把所有输入按未命中高峰 2 元/百万 token、输出按 8 元计算。运行时已核验的周末空闲价为未命中输入 1、缓存命中 0.02、输出 4 元/百万 token，估算式为 `(miss + 0.02 × hit + 4 × output) / 1,000,000`。这里复算已保存的价格依据，不作新的实时报价；没有访问账户最终账单，不能称“实际扣款已核验”。缓存命中来源不明，不能自行归因跨组或历史调用。

OpenHands 多一次请求，但输入总量和费用估算更少；轮数不等于 token 成本或有效信息量。两组失败/自动重试均为 0。

## “成功”的边界与可追溯性

流程成功的直接证据是：真实 live 账本中 7 次启动全部获得 HTTP 200 和有效 usage、原始响应包含正常 finish、两组结果 completed、待结算预留为 0。候选定位的直接证据是：两组上下文均含目标赋值函数正文，终答都列出该函数。**未读 gold、未正式计分，不能将候选重合当作准确率或全部解释正确。** 本题已曝光，固定物理行后端也不是上游原版；不构成独立评测或公平单变量因果结论。

原始证据根目录：`authority-cohort/8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585/run/`。`ledger.sqlite` 的 calls 表 id 1–3 对应原生第 1–3 轮，id 4–7 对应 OpenHands 第 1–4 轮；每条保存 request/response 原文和费用计数。`native.json`、`sdk/result.json` 保存组结果，`sdk/trace.jsonl` 保存 SDK 事件。可见性以账本下一次请求中的 tool 消息为准，不能把 native.json 里较大的后端 raw 输出全部算作模型看到的证据。

旧 comparison_contract.live_enabled=false 是遗留描述字段，本次依据 live 账本/授权/真实响应确认执行身份，未修改该历史字段。本报告及结构化导出为新增分析产物，历史结果与开发日志未修改。
