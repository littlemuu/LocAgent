# 37 题开发集真实试跑 v4b

本批实际启动传输 148 次，保留响应 148 份；账本请求占位 148 次。整批停止标志：True；原因：RuntimeError。没有自动重试。

已完成 19 对；第 20 题 Sisyphus #191 的 B 组完成、A 组终答格式失败；后 17 题未启动。因此这不是完整 37 题成绩。

失败证据：A 组第 4 轮返回 HTTP 200，finish_reason=tool_calls，输出 566 token（上限 2048）。finish.entities 中混入四个没有冒号/限定名的纯文件路径；用冻结校验器离线重放得到 invalid_entity_format。没有改写或剔除这些值来冒充成功，没有新模型请求。

共同完成的 19 对（仅前缀开发样本）中：A 的 Hit@1/3/5 为 7/19、11/19、11/19；B 为 8/19、10/19、10/19。不能将这个提前停止的样本外推为全量结论。

A：LocAgent 图工具 + 正分正文 BM25 + 路径证据索引（适配 v3）。B：OpenHands 基础工具 + 实体 BM25 + 有界路径候选（适配 v4）。这是完整系统比较，不能归因于检索。

|系统|完成|技术失败|未启动|Hit@1|Hit@3|Hit@5|
|---|---:|---:|---:|---:|---:|---:|
|A 原生适配|19|1|17|7/37|11/37|11/37|
|B OpenHands|20|0|17|8/37|10/37|10/37|

上表分母固定每组 37 题；未启动和技术失败在计划口径计零，不叫定位错误。下列 Acc/Recall/Hit 为冻结原标签下的暂定开发诊断，标签风险见后文。

|系统|k|Acc 均值（完成组）|Recall 均值（完成组）|Hit 均值（完成组）|完成分母|
|---|---:|---:|---:|---:|---:|
|A 原生适配|1|0.3684|0.2795|0.3684|19|
|A 原生适配|3|0.3684|0.4392|0.5789|19|
|A 原生适配|5|0.4211|0.4713|0.5789|19|
|B OpenHands|1|0.4000|0.2739|0.4000|20|
|B OpenHands|3|0.4000|0.3906|0.5000|20|
|B OpenHands|5|0.3500|0.3906|0.5000|20|

## 调用与费用

已记录输入 681,744 token，输出 35,309 token；缓存命中 352,128，未命中 329,616。有 0 次请求缺少可用缓存明细，其未知部分不作零费用解释。

新批已结算的保守费用上界为 **1.645960 元**；未结算预留 **0.000000 元**。这是回包用量与上限单价计算，不是账户账单实扣。

在有缓存明细的请求上，按官方空闲/高峰价分别计算为 0.477895—0.955789 元；仅作价格区间估算，缺明细请求不包含在该区间。

此前两次五题 53 请求、保守费用上界 0.620428 元；计入本批后请求占位合计 201，保守已结算费用上界 2.266388 元。旧结果不混入本批质量得分。新批批准上限 296 请求/629 元，关联累计保护 349 请求/630 元。

官方价格核验：[DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。账户界面和实扣未独立读取；采用先前确认的人民币有效价格上限，启动时重新检查公开价。

|系统|实际传输|输入 token|输出 token|保守上界（元）|
|---|---:|---:|---:|---:|
|A 原生适配|69|397987|16769|0.930126|
|B OpenHands|79|283757|18540|0.715834|

## 工具选择

SDK 在已启动的 20 题中，有 6 题进入 locagent_retrieve 执行器（计划分母 37），共 8 次调用，8 次非错误返回；模型响应中提出该调用 8 次。调用次数包含分页或被预算门禁挡下的尝试，不能自动等同于有效检索证据。

返回中可见新路径候选头的页面数为 1。SDK 工具返回错误分布：{'tool_error': 5, 'investigation_closed': 3}；investigation_closed 表示调查预算关闭，与模型调用技术失败分开。

模型自主选择工具，没有强制 LocAgent 调用或未选后的补跑。使用或未使用工具不能单独解释最终成绩。

## 逐题结果

|题目|A 状态 / 请求 / 首次命中排名|B 状态 / 请求 / 首次命中排名|B 检索调用|标签风险|
|---|---|---|---:|---|
|AzureAD__microsoft-authentication-library-for-python-407|completed / 4 / 未命中|completed / 4 / 未命中|0|无上述结构告警，非语义通过|
|AzureAD__microsoft-authentication-library-for-python-454|completed / 3 / 未命中|completed / 4 / 未命中|0|潜在遗漏/粒度; manual_hold|
|CWorthy-ocean__roms-tools-227|completed / 4 / 2|completed / 4 / 1|0|潜在遗漏/粒度; 快照外补丁; gold>5|
|Delgan__loguru-1239|completed / 4 / 未命中|completed / 4 / 未命中|0|development_control_only|
|JoinMarket-Org__joinmarket-clientserver-1180|completed / 3 / 1|completed / 4 / 1|0|gold>5|
|TransformerLensOrg__TransformerLens-333|completed / 3 / 未命中|completed / 4 / 未命中|0|gold>5|
|duncanscanga__VDRS-Solutions-73|completed / 4 / 1|completed / 4 / 1|0|快照外补丁|
|gaogaotiantian__viztracer-528|completed / 4 / 未命中|completed / 4 / 未命中|0|无上述结构告警，非语义通过|
|huggingface__accelerate-3261|completed / 3 / 1|completed / 4 / 1|1|无上述结构告警，非语义通过|
|huggingface__trl-2332|completed / 3 / 1|completed / 4 / 1|0|无上述结构告警，非语义通过|
|huggingface__trl-2398|completed / 4 / 2|completed / 4 / 未命中|1|无上述结构告警，非语义通过|
|huggingface__trl-2433|completed / 3 / 未命中|completed / 4 / 未命中|1|无上述结构告警，非语义通过|
|huggingface__trl-2450|completed / 4 / 未命中|completed / 4 / 未命中|0|无上述结构告警，非语义通过|
|jazzband__django-two-factor-auth-390|completed / 3 / 3|completed / 4 / 未命中|1|快照外补丁|
|jobatabs__textec-53|completed / 3 / 未命中|completed / 3 / 2|0|无上述结构告警，非语义通过|
|matchms__matchms-backup-187|completed / 3 / 1|completed / 4 / 1|0|快照外补丁; manual_hold|
|phidatahq__phidata-1563|completed / 3 / 2|completed / 4 / 2|1|无上述结构告警，非语义通过|
|roboflow__supervision-1698|completed / 4 / 1|completed / 4 / 1|0|无上述结构告警，非语义通过|
|roboflow__supervision-1739|completed / 3 / 1|completed / 4 / 1|3|无上述结构告警，非语义通过|
|rwth-i6__sisyphus-191|failed / 4 / 未评分|completed / 4 / 未命中|0|无上述结构告警，非语义通过|
|sgkit-dev__sgkit-447|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|spotify__luigi-3308|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|spotify__luigi-3324|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-3167|not_started / 0 / 未评分|not_started / 0 / 未评分|0|潜在遗漏/粒度|
|tobymao__sqlglot-3417|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-3436|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-3901|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4366|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4369|not_started / 0 / 未评分|not_started / 0 / 未评分|0|潜在遗漏/粒度|
|tobymao__sqlglot-4415|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4480|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4515|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4519|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4523|not_started / 0 / 未评分|not_started / 0 / 未评分|0|潜在遗漏/粒度|
|tobymao__sqlglot-4524|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|tobymao__sqlglot-4526|not_started / 0 / 未评分|not_started / 0 / 未评分|0|无上述结构告警，非语义通过|
|xCDAT__xcdat-689|not_started / 0 / 未评分|not_started / 0 / 未评分|0|快照外补丁; gold>5|

## 局限与证据

- 37 题均为开发题，17 题有详细初查记录，20 题未归集到详细初查；没有独立语义复审。历史曝光已记录，不能称独立测试。
- 11 题有结构风险；MSAL #454、SQLGlot #4369 存在标签覆盖疑点，嵌套函数存在粒度差异。原 gold 未修改，不把所有非 gold 预测都解释成真实错误。
- 4 题 gold 超过 5 个，Recall@5 有先天上限。Acc@k 采用冻结的 coverage 定义：命中数达到 min(k,gold数)，并非单纯任意命中。
- 新路径层改善了特定文件名查询的证据可见性，不代表整体语义检索已完善，也无法从完整系统差异推断其因果收益。
- 严格预算下的 finish-only 请求、证据截断及无匹配都是运行条件，应结合逐轮轨迹解释。
- analysis.json 保存逐轮请求/响应哈希、工具参数、token、预算和评分；authority/run 下原始账本与终答不覆盖。评分在批次结束后离线执行。
- 已核对请求字节与证据预算，未发现其他题完整题面或完整参考补丁进入请求。评分模块及原标签哈希均匹配。
