# 固定四配置 RRF 离线探索与基线重建

2026-10-16；基于提交 `657aca1258547d43abae73aee01812e19f13b711`。开始时工作区干净，`outputs/bailian-retrieval-20261016` 原证据完整。本轮零网络/embedding/LLM请求，无数据库、生产参数修改、commit或push；旧成绩、真实向量、账本和数值实验结论不变。

## 先冻结、后计算

计算前保存 `docs/BAILIAN_RRF_OFFLINE_PLAN.json`，SHA256 `4ee3a0115b078def75fcd4670d7fb10ecc21c4b1eb5551337c7c1451ded8dfa4`。仅比较以下四项，另保留BM25、纯dense对照，没有额外搜索：

1. 原等权RRF60。
2. RRF60：dense权重2、BM25权重1。
3. 等权RRF10。
4. 等权RRF60，两臂各截top10后融合。

公式为各入选臂的 `weight/(k+实体名次)` 求和，缺席臂贡献0。先按实体最大块分聚合，再排名、截断、融合；同分按实体字符串排序。所有配置使用原32块/30实体、10题、相同金标和K=1/3/5，不删题。每题单金标，Hit与Recall相同。

## 独立重建核对

五份来源（复用A/B各1、16文档、14文档、10查询）重新核对原始body/request/manifest哈希、角色参数、settled账本及索引。独立归一化向量与原账本一致，最终覆盖32 document和10 query，无重复或遗漏。

未调用生产评估函数：分析脚本独立组织原文本，使用同版本bm25s/PyStemmer重新分词、建BM25索引和打分；Lucene k1=1.5、b=0.75、English stemmer/stopwords、严格正分过滤不变。另从原始向量独立重算dense，并重新实现RRF。

**10题的BM25、dense、原等权RRF60排序均与原保存值完全一致**。这补上了此前复核未重新运行BM25打分的未检查项，但仍使用相同BM25库，不是对该库数学实现的独立证明。聚合、tie、候选过滤另有合成测试。

## 结果：已曝光开发集，不是优化验收

| 配置 | Hit/Recall@1 | @3 | @5 |
| --- | ---: | ---: | ---: |
| BM25 | 60% | 70% | 70% |
| dense | 80% | 100% | 100% |
| 原等权RRF60 | 60% | 70% | 80% |
| RRF60，dense×2 | 70% | 80% | 100% |
| 等权RRF10 | 60% | 80% | 90% |
| 等权RRF60，各臂top10 | 60% | 70% | 90% |

本开发集上三种变体没有比原等权RRF60丢失已有K内命中，但这不是独立优化成功。纯dense仍有最高@1/@3；所有变体在@3仍丢失dense已命中的q04/q05。原等权、RRF10及top10在@1还丢失dense的q02；融合各项均保住BM25在q07的第1名，而dense该题第2。

逐题金标排名（完整名次与逐题Hit/Recall均已保存）：

| 题 | BM25 | dense | 原RRF60 | dense×2 | RRF10 | top10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| q01 | 1 | 1 | 1 | 1 | 1 | 1 |
| q02 | 2 | 1 | 2 | 1 | 2 | 2 |
| q03 | 1 | 1 | 1 | 1 | 1 | 1 |
| q04 | 21 | 2 | 8 | 5 | 7 | 7 |
| q05 | 20 | 1 | 8 | 4 | 4 | 5 |
| q06 | 1 | 1 | 1 | 1 | 1 | 1 |
| q07 | 1 | 2 | 1 | 1 | 1 | 1 |
| q08 | 9 | 1 | 4 | 2 | 2 | 4 |
| q09 | 1 | 1 | 1 | 1 | 1 | 1 |
| q10 | 1 | 1 | 1 | 1 | 1 | 1 |

q04/q05在BM25较低排名，原RRF把它们排到8；提高dense权重后分别到5、4，但没有进入前3。q08从4到2（dense×2或RRF10）。这是固定公式在保存分数/名次上的变化，不推测模型或服务端原因。

## 截断改变了什么

BM25仍只保留正分实体，q01–q10原候选数为29、8、6、29、28、10、18、19、8、4；dense为30。前三种融合候选并集均30。

top10变体在实体去重后分别截两臂，而非截融合结果。其候选并集为 **15、15、13、16、16、12、14、14、14、10**；原语料和评分分母不变，但可返回候选减少。q04/q05的金标失去BM25贡献，仅由dense保留。此次10个金标都仍在并集中，不保证新题也如此；若被两臂同时截掉，必须计0，不能删除该题。

## 测试、证据与复现

**16项离线测试通过，1.259秒**：7项新公式/聚合/过滤/tie/权重/top10/漏金标计零测试，加9项已有证据汇集与一次性编排测试（fake传输、临时目录）。进程禁止socket连接；未进行模型请求。没有累加历史测试次数。

新文件：

- `scripts/offline_bailian_rrf.py`：独立重建、固定四配置比较及哈希保护。
- `tests/test_offline_bailian_rrf.py`：新增测试。
- `docs/BAILIAN_RRF_OFFLINE_PLAN.json`：计算前固定清单。
- 本报告。

结果目录 `outputs/bailian-rrf-offline-20261016/`：`comparison.json` 保存全部配置的完整排名、分数、逐题指标、来源绑定和保护哈希；`per-query.csv` 保存逐题名次、候选数及Hit/Recall；`plan.json` 保存原清单。

首次执行命令（已执行，目标目录禁止覆盖）：

```bash
cd /home/lenovo/projects/LocAgent-rag-preview
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/offline_bailian_rrf.py
```

复现到另一个尚不存在的目录，保留原结果；脚本仍强制禁网：

```bash
cd /home/lenovo/projects/LocAgent-rag-preview
PYTHONPATH=scripts /home/lenovo/projects/LocAgent/.venv/bin/python -B -c "import offline_bailian_rrf as a; a.OUT=a.ROOT/'outputs/bailian-rrf-offline-reproduce-001'; a.main()"
```

测试命令：

```bash
/home/lenovo/projects/LocAgent/.venv/bin/python -B -m unittest discover -s tests -p test_offline_bailian_rrf.py
```

分析前后134个保护文件哈希一致，包含历史实验、原执行引擎及学习区README；三个旧臂的保存成绩未改。累计仍10入口、9次HTTP响应证据，unknown 0.557056元、保守占用1.277952元；本轮不增加费用。

## 下一轮独立样本验收建议（未执行）

先保持生产默认不变。另建约20–30条独立单函数定位种子：来自未用于这轮选择的文件/仓库或真实问题，记录公开来源与commit；问题描述和金标由未看过候选排名的人先写/复核，保留相邻函数等难负例。不要重写问题迎合本轮失败项，也不把同函数近义改写当独立样本。

在看到新排名前锁定语料、标签、完整评分分母、tie/候选规则、允许失败范围及比较臂（至少BM25、dense、原融合；如选一个变体，明确其已由旧开发集启发）。先核查输入和已有可复用证据，再单独批准可能新增的模型请求/预算；一次报告全部题及损失，不边看留出集边调参。多函数/跨文件任务应另定标签与评分协议，不能沿用本页单金标Hit=Recall的假设。新样本仍不足以单独证明广泛泛化或生产适用性。
