# expanded50最终独立离线复核

日期：2026-10-16。结论：**通过，未发现需要更正原排名、指标或费用结论的问题。** 原结果文件、账本和冻结物保持不动，复核另存。本次无网络请求、无commit/push。

## 独立性与证据范围

使用新增 `scripts/independent_expanded50_review.py`，没有导入原生产ledger、响应验证、实体聚合、RRF或指标辅助函数；从原始JSON响应独立解析向量和usage，独立回放事件链与资金状态，另写max-entity聚合、RRF、文件投影，并以Fraction精确分数计算宏平均。

为了忠实复现冻结方案，仍使用冻结版本的bm25s/PyStemmer分词与底层BM25实现，但改走直接 `get_scores` 接口，不使用原脚本的retrieve结果回填流程。这是独立实现的复核，不是另一家BM25库、外部人工审计或对供应商账单的独立认证。

复核输入是已授权固定manifest SHA256 `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`、已保存原始响应/事件/续跑授权、快照文档清单及已发布results。输出：`outputs/bailian-expanded50-independent-review-20261016/review.json`，记录输入hash与脚本hash；原输入不改写。

## 检索与指标

- **150份函数完整排名、150份文件完整排名逐项完全相同**（50题×3臂），不仅是Top K或最终百分比相同。
- 独立以Fraction重算所有K=1/3/5的macro Hit、macro Recall，并核对各仓库分层。与原结果最大数值差为 **1.1102230246251565×10⁻¹⁶**，属于浮点求和舍入，不影响任何报告百分比。
- 分母确认：函数主评 **30**、partial/NA **20**、文件 **50**。partial/NA不混入函数主评；多gold Recall按每题命中gold数/该题gold数，再逐题宏平均。
- 向量确认：**9814个文档角色ID＋50个query角色ID**，无重复/缺失；响应显式index/text_index逐一映射，1024维、有限非零范数，query和document角色分开。请求文本与manifest对应ID原文一致，model/parameters含instruct一致。
- 候选确认：**9仓库、49个(repo, commit)快照**；每份快照缓存的完整document_ids顺序与manifest相同，逐文档文本/实体一致。每题只取其repo+commit对应清单。文本完全相同的向量可跨快照复用，但候选成员不混合。
- 无gold参与检索：独立排序函数仅接收含id/text/repo/commit四字段的查询对象，gold字段在进入排序函数前移除；候选按快照清单构造，不按gold筛选。gold只在排序完成后的指标阶段访问。
- 冻结方案确认：manifest与调用前批准SHA一致，策略明确BM25 k1=1.5/b=.75/English/正分、max entity、dense精确余弦、RRF60 dense2/BM251、词法平分、K1/3/5。独立重算按这些固定值复现全部排名，没有发现根据结果改权或改分母的情况。

这些检查不将静态patch-overlap gold提升为因果真值，也不证明公开历史issue没有训练污染；它们验证的是冻结评估流程的正确执行。

## attempt、重发和费用

原事件链和续跑事件链均按序号/previous hash从各自授权绑定独立回放。原批次0–489各有一次成功attempt；原批次490为一次unknown失败加一次明确授权成功attempt；491–617各一次成功。**619物理attempt＝618成功＋1unknown**，除490外没有批次重复，成功批次没有重发。

| 项目 | 独立复核结果 |
|---|---:|
| 已验证成功usage | 1,819,872 tokens |
| usage×固定费率核算 | **0.227484000元** |
| 原unknown继续占用 | **0.262144000元** |
| inflight | **0** |
| 当前本run上界 | **0.489628000元** |
| 全过程中最大预留时点占用 | **0.751641000元** |
| 固定累计cap | **2元** |

对每一次reserve独立检查：此前spent＋已有unknown＋inflight＋新预留≤2元；全部通过。续跑时原403预留未释放，旧成功金额纳入累计。没有把unknown请求无usage当0元。原403响应仍保留且无usage，原失败状态没有改为settled。

这是usage标价核算，不证明控制台实际扣费；免费额度抵扣和旧unknown核销仍未知。更早历史占用1.277952元未参与可用额度，保持既有记录；报告的含历史合计上界1.767580元正确。

## 复现与范围限制

已执行：

```sh
cd /home/lenovo/projects/LocAgent-rag-preview
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/independent_expanded50_review.py
```

脚本禁止socket连接，输出目录拒绝覆盖。复查不要删除原证据后重跑；另存新的复核目录。脚本SHA256：`9d5fc2cfe492406f1649c7e90f1ae0e4cac717072df300b2670c9ba88f631673`。

独立复核共享固定BM25底层库，未独立证明其数学实现；未再次下载仓库或向供应商核验账单；不评估未知/对抗性账本整体回滚。这些限制不影响本次保存结果的一致性结论。原三臂结果无需更正，原报告和JSON痕迹全部保留。
