# 32 代码块 / 10 查询：探索性内存检索验收

2026-10-16。批准 `Sentinel_8f31b18ee4c88191b87d0e23ea87a835`。独立工作区 `/home/lenovo/projects/LocAgent-rag-preview`，基线 HEAD `290c965a3321dd90d4e848dd924e3134ef10fc8c`。本轮已 completed，不继续下一实验；未启动数据库/服务、迁移、调用生成模型、commit 或 push。

## 结果与解释边界

固定原公开 itsdangerous 32 个代码块、10 个手工查询和标签，不删题、不截断、不修改查询、不调参。缓存复用最新 A/B 两个单输入 document 向量，其余 30 文档和 10 查询分 16+14+10 三次获取，全部 HTTP 200、原始 body 留存及严格校验通过，无重试。

每题一个金标，所以本次逐题 Hit@K=Recall@K，宏平均也相同：

| 方法 | @1 | @3 | @5 |
| --- | ---: | ---: | ---: |
| BM25 | 60% | 70% | 70% |
| dense | 80% | 100% | 100% |
| hybrid | 60% | 70% | 80% |

在这一个小型、非盲、已读源码后手工构造的开发集上，dense 表现最好；固定融合没有优于 dense。不能据此声称普遍检索提升或生产验收通过。未设质量通过分数线；没有根据结果调参或继续试验。

旧 A/B 近乎数值复现实验仍为 **inconclusive**，其阈值和结果未改。此次是独立探索性排名实验，不追认旧实验通过。未新增数值稳定性对照，模型后端固定版本/数值确定性仍无保证。

## 冻结输入、规则和缓存来源

新 manifest SHA256：`a6a0abb4f12cc6d45fce36a89a384ccd0d92175b94c0246abc9f9b3e14ebf39f`。绑定批准、当前代码哈希、包版本、原语料和标签、原 endpoint/model、角色参数、五个历史实验的文件哈希、缓存来源、3 个请求哈希、排名规则和累计预算。

- repo `pallets/itsdangerous`，commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。模型 `qwen3.7-text-embedding-flash`，1024 维，同一百炼北京 workspace host。
- document 参数保持 dimension=1024、text_type=document、output_type=dense；query 使用原 query 参数和冻结 instruct。两种角色以 `(role,id)` 隔离，不互用缓存。
- 只复用 `bailian-mapping-controls-20261015` 的两个 settled 单输入，source manifest `1ea1d3b244615e14395d07e5dfe09b2696d64dffddebf916cc289657b0e56511`。A 原始响应 SHA256 `9b7a959442ffcff6d30c5b755aa125f491f4226ed2fb797a1fab3ba4c1a2d4f9`；B 为 `44f3169f3a769e2949554daa9773e832624668950e6aa180369a50f97fd5e4cd`。
- 每份缓存重新验证输入、请求、参数、原 body、binding、manifest 和只读账本，并重新运行严格响应校验。不复用丢失 raw body 的旧批次，也不改其 unknown 状态。
- BM25：bm25s Lucene、k1=1.5、b=0.75、English stemmer/stopwords，保留所有正分候选；同实体多个块取最大分。dense：内存归一化点积、math.fsum，实体取最大块分。平分按实体字符串排序。
- hybrid：两臂完整候选序列的实体 RRF，k=60；BM25 正分候选与 dense 全候选。完整排名包含所有该臂候选；BM25 不伪造零分候选排名。
- 固定 K=1/3/5、分母 10。源清单和排名配置在请求前冻结。没有数据库缓存命中绕过新来源验证；本轮索引只在内存构建。

## 逐题结果

下表为金标实体在每臂的名次；名次 <= K 即该题 Hit/Recall@K=1，否则为0。逐题各 K 的显式指标和完整查询文本另见 CSV/JSON。

| 查询 | 金标函数 | BM25 | dense | hybrid |
| --- | --- | ---: | ---: | ---: |
| q01 | want_bytes | 1 | 1 | 1 |
| q02 | base64_encode | 2 | 1 | 2 |
| q03 | base64_decode | 1 | 1 | 1 |
| q04 | int_to_bytes | 21 | 2 | 8 |
| q05 | bytes_to_int | 20 | 1 | 8 |
| q06 | Signer.derive_key | 1 | 1 | 1 |
| q07 | Signer.verify_signature | 1 | 2 | 1 |
| q08 | Signer.unsign | 9 | 1 | 4 |
| q09 | URLSafeSerializerMixin.dump_payload | 1 | 1 | 1 |
| q10 | URLSafeSerializerMixin.load_payload | 1 | 1 | 1 |

q04/q05 的融合名次仍为8，q08 从 BM25 的9升到4；这是本次固定排名结果，不是因果分析或调参理由。

## 调用、usage 与预算

| 请求 | 输入项 | usage（prompt=total） | 调用与留存耗时 | 原始响应 SHA256 |
| --- | ---: | ---: | ---: | --- |
| 0 document | 16 | 1738 | 0.6844 秒 | `a6eaa7c95d7d96917a54b0d294cf4c7a764f238ee05223ab31f05954e6671b8e` |
| 1 document | 14 | 2525 | 0.5253 秒 | `62815059948bb167b7556683c670b9a8988cdbe6ce737807a171de0aed543e36` |
| 2 query | 10 | 622 | 0.4519 秒 | `144e095c702429d7f4987f0cb4208c502004e15eb8cd93c259ce53c7aee3493e` |

新3行全部 settled，新 usage **4885 tokens**，按冻结费率估计 **CNY 0.000610625**。这是标价估计，不是已查询的提供商扣费；实际费用未知。

旧占用 **0.622592 元**未动，新40项完整保留 **0.655360 元**，累计 **1.277952 元**；旧 unknown **0.557056 元**未释放。此上限由本轮明确批准，未改全局旧实验 CAP 或用事后 usage 放松限额；现有 Journal 仍对 settled 保留完整预留。

本轮新增传输入口/HTTP 响应均3次；累计 **10 次入口、9 次 HTTP 响应证据、7 份现存完整 raw body**。最早两份丢失 raw body 的 HTTP 响应仍不冒称完整留存。所有新 body 均先原子保存再解析；最终逐份重算 SHA256。

内存评估总耗时约0.4198秒，其中 BM25 构建0.3792秒；10题检索累计 BM25 0.0100秒、dense 0.0290秒、RRF单独融合0.0004秒，hybrid组合约0.0395秒。为本机单次测量，不是性能基准；不含模型调用、Python导入和证据读取时间。

## 实现、验证与产物

新增模块：`locagent_service/bailian_memory_evaluation.py`（原始证据汇集、角色隔离、内存排名/评分）、`locagent_service/bailian_retrieval_experiment.py`（固定来源、3步一次性授权、跨旧新预算、完成关闭）。新增 `tests/test_bailian_retrieval_experiment.py`；没有修改旧执行代码或历史账本。

请求前 **133 项离线测试通过，10.473秒**，其中9项新增测试；测试进程禁用 socket 网络，fake全流程只写临时目录。覆盖来源哈希/账本篡改、参数/输入/角色不一致、重复/缺失、累计预算、防重放、失败即停及 raw 留存、实体去重/平分/融合、漏题计零以及完整32/10组装和内存评估。此数不与历史轮次相加。未运行数据库集成测试，本次无数据库路径。

实际执行：原虚拟环境 `python -B -m locagent_service.bailian_retrieval_experiment prepare`，然后分别 `step 0`、`step 1`、`step 2`；最后在禁网进程调用 `finish()`。run 已标记 completed，写入 completed.json；本轮不再执行。

项目证据目录 `outputs/bailian-retrieval-20261016/`：manifest/authority/ledger、三个 intent/report、三份 raw body/binding/派生审计、results.json（全部来源、完整排名、逐题指标、耗时、账本）及 completed.json。外部计划 `outputs/bailian-retrieval-manifest.json` 和锁 `outputs/bailian-retrieval-20261016.lock`。

交付目录另有 `bailian-retrieval-results.json`、`bailian-retrieval-rankings.csv`、`bailian-retrieval-per-query.csv`、`bailian-retrieval-verification.json`、`bailian-retrieval-preflight-tests.log` 和新增代码 diff。不复制密钥、请求头或完整原始响应到报告。

最终核对：manifest 绑定的56个历史证据/原学习区 README 文件哈希全部一致；本轮冻结的全部引擎文件哈希一致。用户已有修改、旧阈值及旧实验判定均保留。此次完成只说明该开发集探索性流程和结果；更广泛质量、稳定性、供应商契约或生产适用性仍未验证，需要另行设计和批准，不自动继续。

## 2026-10-16 独立只读复核补充

本次不新增模型/网络请求，不运行原执行入口，不改代码、参数、账本或旧数值实验。只用标准库读取原始证据和保存排名，并在本报告及排错文档补充结论；未 commit/push。

### 输入与原始证据

五份来源逐份核验：最新 A/B 单输入各1项、当前16文档、14文档、10查询。所有请求由固定输入和角色参数独立重建 canonical body，SHA256 与 binding/账本一致；原始响应 body SHA256、source manifest SHA256、settled 状态、HTTP 200、usage 全部对应。显式 index 范围、唯一性、完整覆盖与1024维有限非零向量检查通过，独立归一化结果与账本保存向量逐项相同。

最终 `(role,id)` 集合恰为32 document +10 query，无重复、遗漏或角色混用。32代码块去重后有30个实体，三臂使用同一语料、相同10题与同一实体级金标评分。新增3请求均 settled；累计10入口、9次HTTP响应证据准确。

### 指标与融合解释

独立从保存排名重算10题的金标rank、逐题Hit/Recall@1/3/5和宏平均，全部与本报告/JSON一致。每题单金标，Hit与Recall相同；没有删除失败或未命中的题。另从已验证原始向量独立重算全部dense排序，再从保存的BM25/dense排序独立重算RRF，全部一致。

- @1：dense独有命中q02、q05、q08；BM25独有命中q07，所以净增2题。
- @3和@5：dense独有命中q04、q05、q08，无BM25独有命中。
- 固定RRF为 `1/(60+rank_BM25) + 1/(60+rank_dense)`，没有权重学习或强制保留dense前3。如下数值直接解释掉出前3，不推测模型或任务语义根因。

| 题 | 金标 BM25/dense rank | 金标 RRF 分数 | 融合第3名分数 | 金标融合 rank |
| --- | --- | ---: | ---: | ---: |
| q04 | 21 / 2 | 0.0284747113 | 0.0298773690 | 8 |
| q05 | 20 / 1 | 0.0288934426 | 0.0295716460 | 8 |
| q08 | 9 / 1 | 0.0308861962 | 0.0310544054 | 4 |

三题金标都在候选中，没有被过滤掉；两臂较均衡靠前的其他实体获得更高分。例如q04的base64_decode是BM25第4、dense第3，RRF为0.0314980159，超过金标。不能从这一次结果事后修改k、权重或候选策略。

### 冻结范围、泄漏检查与未检查项

BM25固定Lucene k1=1.5、b=0.75、English stemmer/stopwords、仅正分候选；q01–q10实体候选数依次为29、8、6、29、28、10、18、19、8、4。dense与hybrid每题均30实体；候选数差异来自事先冻结的策略，不是语料或评分分母变化。所有臂都以实体最大块分聚合、实体字符串破同分；RRF k=60，K=1/3/5。

query instruct原文为：`Given a code localization question, retrieve Python code that implements the described behavior.`；text_type=query、dimension=1024、output_type=dense。document不含instruct，text_type=document。

检查的请求重建字节只包含原问题文本、模型和参数，没有 `relevant_entities` 标签；文档输入为固定路径/符号/源码，未拼接查询或金标元数据。检查的执行代码在生成排名后才用标签计分，未见按金标调整排名或直接返回金标的捷径。公开源码中的函数名本身是合法检索文本，不等于把金标字段注入请求。

这不能证明“无任何泄漏”：数据是读源码后手工构造的非盲开发集，A/B亦在此前排错中被观察过；没有盲审标签正确性、排除提供商预训练污染或验证外部大语料泛化。本次没有独立重新运行BM25分词/打分实现，而是核对冻结配置/源码、使用保存BM25排序重算评分和融合；没有重新测速、重跑全量测试或调用供应商。不能把有限复核写成生产正确性证明。

### 费用与保护

有效新usage为1738+2525+622=4885 tokens；按冻结0.125元/百万token计算为0.000610625元，仅标价估计，非实际扣费。累计1.277952元是保守占用，包含settled完整预留；旧unknown 0.557056元未释放。冻结的旧证据和代码哈希再次核验一致；原学习区README未变。旧数值稳定性实验依旧不确定，没有追认通过。
