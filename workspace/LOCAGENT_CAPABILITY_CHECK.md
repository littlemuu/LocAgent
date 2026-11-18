# LocAgent 免费离线能力检查：原题与真实已见线索

2026-11-13。结论：**当前接入的实体ID检索能用SQLGlot已见的精确符号取得完整目标正文；从两题原标题或Loguru已见线索发现参考函数的能力有限。** 这不解释模型为何不选检索，也不意味着所有查询或完整LocAgent框架均无效。

本轮复用12条旧查询结果，仅新增4次离线检索；另复用2条参考答案查询作为单列校验。新增模型请求0、费用0，没有读取凭据、执行目标仓库代码、改检索策略或创建授权。2,732份历史/运行/冻结/诊断材料哈希不变，开发日志追加记录。

## 查询来源与复用依据

先核验已有 `LOCBENCH_OFFLINE_DIAGNOSIS.md`、`RETRIEVAL_CHOICE_HYPOTHESES.md` 及原始结果，再补查新增真实轨迹。

- **A批**：两题修复版真实补测 `eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83`，两题各两组。
- **B批**：读取修复后SQLGlot真实单题 `df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277`，两组。
- “已见”只从实际发送请求中的 user 原题或 tool 正文取证，不从终答、分析者读到的评分标签或模型自己的猜测反推。每条保存批次、组别、请求轮次、message序号、tool_call_id、请求hash和短摘录。符号匹配有词边界，`_parse_set` 不会被 `_parse_set_item` 的子串冒充。
- “第N轮已见”指发送第N次模型请求时，相关内容已在该请求的历史中。第4轮只能finish；若线索此时才出现，不能算还有调查机会。
- 原始快照、LocAgent引擎记录、bridge/worker/检索适配器、分页函数以及v4/v5评分标签均核对一致，旧原始输出hash匹配，故不重复跑同查询。
- 16条主查询在新增检索前保存于 `queries-before-execution.json`，但仍由已知开发结果的分析者选取；不是独立预注册测试，也不是模型自主选择成绩。

## 完整描述与标题严格分开

| 输入 | 实际长度 | 检查结果 |
|---|---:|---|
| Loguru完整原题（标题+正文） | 999字符 | 当前1～256字符接口拒绝；未执行检索，排名/命中未评估 |
| SQLGlot完整原题（标题+正文） | 1,386字符 | 同上 |
| Loguru原标题 | 57字符 | 逐字等于原题第一行，查询见下表 |
| SQLGlot原标题 | 55字符 | 逐字等于原题第一行，查询见下表 |

没有将全文截断成标题，也没有把全文接口拒绝记为检索失败或召回0。此前报告的标题分类经原始case逐字复核正确。完整问题的语义检索能力仍不能从本接口测试得出。

## Loguru结果

参考目标为 `loguru/_better_exceptions.py:ExceptionFormatter._format_list`，固定源码536–544行，共9行。排名只指目标实体本身在工具实际候选顺序中的位置，不把父文件算作函数命中。

字节列为“原始UTF-8检索文本 / 首个完整JSON页”；每条查询单独按4,096 bytes/页、14,336 bytes累计预算计算，不偷用真实轨迹之外的额外预算。

| 查询 | 可追溯来源 | 目标排名/返回内容 | 字节（原始/首JSON页） | 目标正文完整性 |
|---|---|---|---:|---|
| `Add unit tests for traceback formatting of RecursionError` | A两组第1轮原题的准确标题 | 无；仅Logger.add | 49,465 / 4,096 | 原始、首屏和预算内均无目标 |
| `traceback`、`RecursionError`、`Previous line repeated`、`recursion`、`repeated`（各一条） | A两组第1轮原题中的原词/短语 | 各无候选 | 各19 / 49 | 均无目标正文 |
| `loguru/_better_exceptions.py` | A两组第2轮已收到的list_files | 无目标实体排名；精确返回该文件 | 24,272 / 4,096 | 原始全文含完整9行；首屏和14,336预算内均未交付 |
| `raising_recursion` | A两组第2轮list_files内路径的basename线索，非函数名 | 无候选 | 19 / 49 | 无；本轮新增 |
| `tail_recursion` | 同上 | 无候选 | 19 / 49 | 无；本轮新增 |

路径证据原文包含 `tests/exceptions/source/backtrace/raising_recursion.py` 和 `.../tail_recursion.py`。这两条查询来自当时已收到的路径，未冒称看见了同名函数。当前BM25候选排除测试文件，与这些测试线索没有候选的现象相容；不单凭这一结果断言唯一原因。

**单列参考校验，不计已见线索成绩：** `_format_list` 来自参考标签，在本轮核对的A批两组实际请求中从未出现。旧检索确实把目标排第1，原始709 bytes、首JSON页761 bytes，完整9行与固定源码逐行一致。这证明“已知参考名可以读取”，不能证明从题目能找到它。

补充旧普通搜索对照：`traceback` 字面搜索有65条命中，其中11条来自目标文件，第一页已显示该文件；这说明发现文件存在其他免费路线。未重新运行，也未把普通搜索结果算作LocAgent能力。

## SQLGlot结果

参考目标为 `sqlglot/parser.py:Parser._parse_set_item_assignment`，5969–5987行，共19行。

| 查询 | 来源/可用时间 | 目标排名/返回内容 | 字节（原始/首JSON页） | 目标正文完整性 |
|---|---|---|---:|---|
| `SET TAG identifier containing dots is parsed as Command` | A/B两组第1轮原题的准确标题 | 无；Tag、Command、Set、Expression.set、Identifier | 3,257 / 3,421 | 无 |
| `SET TAG` | 原题第1轮 | 无；Tag、Set、Expression.set | 2,265 / 2,383 | 无 |
| `SetItem` | 原题第1轮 | 无；expressions.SetItem | 470 / 523 | 无 |
| `_parse_set_item` | A检索组第2轮、A基础组第3轮；B两组第3轮工具证据 | 无；Parser._parse_set_item | 472 / 510 | 无目标正文；分派函数含assignment调用名，可供进一步查询 |
| `_parse_set_item_assignment` | A检索组第2轮、A基础组第3轮搜索证据；B两组第3轮工具证据 | **第1名，正确参考实体** | **1,178 / 1,244** | **原始/首屏/预算内均完整19行，逐行匹配固定源码** |
| `_parse_set` | B检索组第3轮读取证据；B基础组到第4轮才见 | 无；Parser._parse_set | 684 / 730 | 无目标正文；本轮新增 |
| `_parse_primary` | B检索组第3轮5977行读取证据；B基础组到第4轮才见 | 无；Parser._parse_primary | 2,559 / 2,647 | 无目标正文；本轮新增 |

B检索组第3轮收到的证据确实包括 `6005: def _parse_set(...)` 及 `5977: left = self._parse_primary() or self._parse_id_var()`。B基础组则在第3轮才执行读取，内容到第4轮请求才进入上下文，此时已关闭调查。因此这两条新查询只证明B检索组当时存在可用线索，不能声称基础组也有同样机会。

**单列参考校验：** 完整参考实体ID `sqlglot/parser.py:Parser._parse_set_item_assignment` 为旧oracle查询，返回也为1,178/1,244 bytes和完整19行；不因此把完整ID追认成当时已见。短符号已见的结论另有上述实际请求证据，两者不能混用。

## 能说明什么、下一步建议

1. **发现与读取要分开。** 当前生产接入是实体ID BM25与精确实体/文件读取，没有开启正文语义检索或调用图扩展。两题原标题没找到参考函数；SQLGlot已有短符号后能高效读取，Loguru只有oracle符号才取得小而完整的目标正文。不能把这概括成“LocAgent完全没用”或“多调用就一定有效”。
2. **优先免费检查Loguru发现能力。** 若继续开发，可在隔离分支对比现有ID索引与明确命名的正文/文档字段索引，沿用已冻结的自然查询与来源，记录候选排名、首次完整正文所需字节、大结果比例和失败。oracle只做校验，不用于调整查询；这些已曝光题仍只算开发集。
3. **处理大结果与协议说明。** Logger.add和整文件返回会耗预算，可以另做短候选/按实体取正文的离线设计。256字符限制在执行器存在、实际wire说明缺失是此前已确认的问题，可单独修正并测试一致性；本轮未改代码或schema。
4. **SQLGlot先保持“已知符号取正文”的定位。** 既有真实新read_file也已经能正确送达正文，离线1244字节的检索结果并不能证明其胜过基础工具；是否减少调用或改善回答，需要另行设计，不能强制调用后称为自主收益。

本轮只是分析者对真实已见线索进行离线反事实查询。所有查询都有来源，但模型并未实际提出这些LocAgent调用。没有为“为何没选”确定因果；没有穷举全部可用查询，也未做新的付费模型实验。

## 文件

- 结果及逐条来源：[results.json](verification/locagent-capability-v1/results.json)
- 执行前查询清单：[queries-before-execution.json](verification/locagent-capability-v1/queries-before-execution.json)
- 验收与保护：[acceptance.json](verification/locagent-capability-v1/acceptance.json)
- 可复查脚本：[check_locagent_capability.py](diagnostics/check_locagent_capability.py)

来源快照、评分hash、原输出hash、原始与分页正文完整性、字节数、对照oracle与真实可用时间均保存在JSON。源码只按allowlist读取并静态AST检查；新检索使用既有隔离子进程和offline_engine网络/模型拒绝保护，不导入或执行目标仓库代码。
