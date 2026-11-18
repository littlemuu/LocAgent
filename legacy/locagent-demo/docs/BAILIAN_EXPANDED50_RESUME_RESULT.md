# expanded50 r01授权续跑完成与冻结三臂结果

2026-10-16。用户明确续跑授权：`Sentinel_f70cd891666081918372e2e6c932a09f`，2026-10-16 08:58 UTC。该ID引用用户消息，不是凭据。用户已自行关闭用完即停；本轮没有修改任何账户设置。

**续跑128请求全部成功；累计物理请求619，618个唯一批次都有成功向量。三组冻结指标均已完成。** 原403失败attempt及其0.262144元unknown仍保留，没有退款、重置或覆盖证据。

## 固定实验与原始证据

run仍为 `bailian-expanded50-78e24794-cap2-20261016-r01`，唯一真实账本仍为：

`outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01/`

没有新建r02或第二个真实预算目录。新增 `continuation-authorization.json`、`continuation-event-*.json`、`continuation-body-*.bin`均在同一目录，继续使用同一flock。原run.json、原事件和原响应的全部hash与首次停止审计一致。

固定manifest SHA256：`78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`。数据仍为9个公开仓库、9814文档片段、50个issue标题；模型 `qwen3.7-text-embedding-flash`、1024维，host `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com`。冻结分块、候选、角色、instruct、费用率及三臂参数不变。

原失败：第491次物理请求（原批次零基490），HTTP403，`AllocationQuota.FreeTierOnly`，无usage。诊断已确认其说明免费额度耗尽且仅用免费额度保护触发；原失败记录本轮仍是unknown，新增成功attempt不会覆盖它。

## 最小恢复流程与检查

新增 `locagent_service/bailian_expanded_resume.py` 和显式续跑CLI。默认dry-run，真实执行必须匹配此次续跑授权ID；不能输入另一run、目录、cap、计划或transport。内部核验原停止审计SHA、全部原文件hash和原引擎，然后从固定manifest只选原批次490–617。

新授权记录绑定唯一目录、原审计hash、完整续跑计划hash、原spent/unknown、固定2元累计cap、最多128新请求/619累计物理请求及续跑代码hash。新增attempt分别记录原batch_index和物理attempt_index：原失败490的重试是零基物理491，最后原批次617对应零基物理618。

预留检查使用 `原spent + 原unknown + 续跑spent + 续跑unknown + inflight + next <= 2元`。原0.262144元不释放。每个新attempt仍先持久预留、dispatch，再持久raw与hash，严格验证usage后结算；遇新异常/未知即停，无再次自动重试。原成功0–489批不再发送。代码只追加新文件，不修改原实现及证据。

续跑前 **50项禁网测试通过**，包括12项新恢复测试、原预算/响应/指标回归；7个真实进程强制退出窗口验证无重复发送。全部128冻结请求体经mock逐一验证，完成后重启零调用。累计cap包含原spent及unknown、二次403停止、timeout占用、auth/raw篡改、无授权拒绝、写盘失败和索引映射均有覆盖。临时fake账本只用于离线测试，不是第二个真实预算域。

## 精确请求与向量覆盖

| 项目 | 数量 |
|---|---:|
| 原成功批次 / 复用向量 | 490 / **7840** |
| 原失败attempt保留 | 1 |
| 本次新增请求 / 成功 | **128 / 128** |
| 本次文档输入 | **1974**（失败16 + 未发1958） |
| 本次查询输入 | **50** |
| 累计物理请求 | **619** |
| 有成功结果的唯一批次 | **618** |
| 完整唯一文档向量 / 查询向量 | **9814 / 50** |
| 本次新失败 / 自动重试 | **0 / 0** |

原失败批次只按此次明确授权重试一次。原成功向量仅从已保存响应读取并校验/归一化，未重新生成。向量来源映射按原批次0–489读旧body，490–617读continuation-body；全部请求/响应hash及usage逐条验证，9864个角色+输入ID无重复或缺失。

## 费用、上界和仍保留的unknown

| 项目 | 数值 |
|---|---:|
| 续跑usage | 349,691 tokens |
| 续跑usage按固定费率核算 | **0.043711375元** |
| 累计成功usage | 1,819,872 tokens |
| 累计成功usage核算额 | **0.227484000元** |
| 原失败unknown保留 | **0.262144000元** |
| 新unknown / inflight | **0 / 0元** |
| remaining reserved | **0.262144000元** |
| 本run累计核算+未知保守上界 | **0.489628000元** |
| 原累计cap | **2元** |
| 更早历史占用（不变） | **1.277952000元** |
| 包含历史占用的合计上界 | **1.767580000元** |

固定费率0.125元/百万输入tokens。上述是已验证usage的标价核算，不是账户账单核销；此前免费额度抵扣、实际现金扣费与原403计费情况仍应以控制台账单为准。本轮没有据此释放任何unknown或减少历史占用。即使向量已完整，原失败attempt的资金占用也继续保留。

## 冻结指标

函数主评30题；另20题partial/NA不进入函数主分母。文件评估50题。指标是macro Hit与macro Recall，二者在多gold时不同。候选是各固定commit的完整受支持Python函数区域，包含tests/docs；gold为静态修复补丁重叠代理，非已证明因果定位。公开历史issue也不是严格无污染盲测。

参数保持：BM25 Lucene k1=1.5/b=.75、English stemming、正分候选；dense精确余弦，实体取最大块分；RRF k=60、dense权重2/BM25权重1，无截断；词法平分；文件按最佳函数排名投影。

### 函数主评（n=30）

| 方法 | Hit@1 | Recall@1 | Hit@3 | Recall@3 | Hit@5 | Recall@5 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 26.67% | 21.11% | 56.67% | 46.11% | 66.67% | 52.22% |
| dense | **56.67%** | **45.56%** | **66.67%** | **55.56%** | 66.67% | 55.56% |
| RRF60 dense2/BM251 | 50.00% | 41.11% | 63.33% | 50.56% | **73.33%** | **64.44%** |

### 文件评估（n=50）

| 方法 | Hit@1 | Recall@1 | Hit@3 | Recall@3 | Hit@5 | Recall@5 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 50.00% | 46.40% | 82.00% | 76.73% | 90.00% | 83.73% |
| dense | **66.00%** | **59.73%** | **90.00%** | 83.73% | 94.00% | 88.13% |
| RRF60 dense2/BM251 | 64.00% | 59.33% | **90.00%** | **84.47%** | **96.00%** | **90.47%** |

本样本中，dense的@1较好，加权RRF的@5较好；不能概括成混合在所有K上优于纯向量。函数Hit@5分别20/30、20/30、22/30；文件Hit@5分别45/50、47/50、48/50。没有用本轮结果调参，也未做显著性检验；样本及代理gold限制应随结论保留。

BM25的全部函数/文件排名和指标与首次停止后的离线基线**逐项完全一致**。评分期间网络被禁用，原ledger以及263份历史/冻结保护文件hash不变。

## 交付与复核路径

结果目录：`outputs/bailian-expanded50-resumed-evaluation-20261016-r01/`。

- `ledger-audit.json`：累计physical attempts、usage/费用/保留额及完整账本hash。
- `results.json`：三臂指标、按仓库分层、全部50题排名、候选数及618批向量来源绑定。
- `outputs/bailian-expanded-resume-preflight-20261016/`：50项测试日志和128批mock验收。
- 同一原run目录的continuation授权、事件和原始响应：私有本地证据，不在报告中展示凭据或完整headers。

实际已执行命令（Python为原项目venv，cwd为独立预览工作区）：

```sh
python -B scripts/verify_expanded_resume.py
python -B scripts/resume_expanded_live.py --execute-approved-continuation --approval-id Sentinel_f70cd891666081918372e2e6c932a09f
python -B scripts/evaluate_expanded_resumed.py
```

续跑命令已完成，不要另建run或追加重试；离线报告拒绝覆盖已有证据。当前没有需要继续发送的实验请求。原403unknown和实际账单核销是剩余审计事项，不影响本次完整向量与指标。无commit/push、无数据库操作、无原学习工作区修改。
