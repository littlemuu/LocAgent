# expanded50 r01真实实验：按失败停止，未完成三臂比较

日期：2026-10-16。用户授权凭据ID：`Sentinel_fbb9c43d04ac819197437d5bf7cf38f3`（用户消息引用，不是API key）。唯一run：`bailian-expanded50-78e24794-cap2-20261016-r01`。

**真实实验在第491次请求收到HTTP403后立即停止，无重试。490次成功、1次unknown。完整dense/RRF评估未完成；BM25全量离线基线已完成。** 失败不是额度不足；403原因和该失败请求实际是否计费尚未确认，不推测是代理、限流、内容或账号问题。

## 固定范围与真实入口复核

冻结manifest SHA256：`78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`。计划9个公开仓库、9814份唯一代码文本、50个公开issue标题；最多618请求，每批≤16，串行；北京host `ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com`，原生路径 `/api/v1/services/embeddings/text-embedding/text-embedding`；`qwen3.7-text-embedding-flash`，1024维。候选、分块、参数、instruct及固定评分方案未变。

本轮按新明确授权受控接通：正式execute仍不接受plan、binding、transport或账本根覆盖，仅内部加载固定manifest、固定r01/目录/cap；实际transport由代码固定为stdlib HTTPSConnection，不使用mock工厂。TLS主机/证书校验、固定host/path、原始body哈希、不跟随redirect、不自动重试、有限正文读取均经mock复核。没有把测试模式变成生产开关。

沿用已有 `.env.bailian.local` 安全加载器。仅核对必需键存在与工作空间/host一致，无新增持久凭据配置、无全局环境修改、无key展示。真实调用将key仅放在认证头，不作为模型输入。CLI默认仍dry-run，实际调用须显式匹配批准ID。

唯一正式账本目录：
`outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01/`。

未创建第二个真实预算目录、未清账或另起r02。真实入口接通前90项禁网/mock检查通过；另4项离线指标测试通过。既有旧账本与冻结证据保持原字节。无commit/push、无数据库服务、未修改原学习工作区。

## 精确请求数与数据覆盖

| 项目 | 结果 |
|---|---:|
| 计划最大请求 | 618 |
| 实际派发 / 收到HTTP响应 | **491 / 491** |
| 成功校验并结算 | **490** |
| unknown失败请求 | **1**（第491次，零基index490） |
| 未派发 | **127** |
| 成功文档输入 | **7840** |
| 失败批次文档输入 | **16** |
| 未派发文档输入 | **1958** |
| 已发送查询标题 | **0/50**（文档批次先执行，尚未进入查询批次） |
| 自动重试 / 额外探测请求 | **0 / 0** |

失败响应HTTP403，没有usage、没有向量。脱敏request ID：`c0288629-ba01-928b-84a3-f426d3bf767c`；原始响应SHA256：`bc1e31c6ddb24f5d3e3258a75cf911db8fc76892ec0f18d82f8c2b081a8c1aec`。原文保留在私有账本文件 `body-000490.bin`，未在报告中展示服务错误正文或未知字符串。`failure-audit.json`提供安全诊断；失败费用不能当0。

## 费用与占用

| 项目 | 人民币 |
|---|---:|
| 本run批准cap | **2.000000000** |
| 已验证usage | **1,470,181 tokens** |
| usage×固定0.125元/百万tokens的已结算额 | **0.183772625** |
| unknown保留预留 | **0.262144000** |
| inflight | **0** |
| remaining reserved（unknown+inflight） | **0.262144000** |
| 本run已结算+未知保守上界 | **0.445916625** |
| 旧账占用，完全不变 | **1.277952000** |
| 其中旧unknown，完全不变 | **0.557056000** |
| 旧占用+本run上界 | **1.723868625** |

这是提供方响应usage按固定费率核算，不是控制台发票/账单核销。unknown请求无usage，按16×131072 tokens保守占用，不推断免费、不退款。账本仍有预算空间也不能继续，因为unknown是独立停止条件。禁止重启后重发该批、换目录或新run绕过。

## 离线指标

函数主评仅30题；20题partial/NA不混入函数主分母。文件主评50题。Gold是静态补丁重叠代理，不等于因果真值。BM25使用全部支持Python函数候选，含tests/docs，不按gold筛文件；Lucene k1=1.5、b=.75、English stem、只保留正分、实体取最大块分、词法平分。文件排名按最佳函数投影。

| BM25范围 | Hit@1 | Recall@1 | Hit@3 | Recall@3 | Hit@5 | Recall@5 |
|---|---:|---:|---:|---:|---:|---:|
| 函数主评 n=30 | 26.67% | 21.11% | 56.67% | 46.11% | **66.67%** | **52.22%** |
| 文件 n=50 | 50.00% | 46.40% | 82.00% | 76.73% | **90.00%** | **83.73%** |

**dense与RRF60 dense2/BM251：未运行、无指标。** 文档向量不全且50个查询向量均未生成，不使用部分候选冒充完整实验、不用fake向量补齐、不缩减样本或调参。此结果不能得出向量或混合优于/劣于BM25的结论。冻结问题全集的BM25基线可独立计算，故予以保留。

## 审计与交付

离线报告目录：`outputs/bailian-expanded50-live-evaluation-20261016-r01/`。

- `ledger-audit.json`：逐事件重新构建状态，逐成功响应校验原始hash/索引/向量/usage及费用；含全部账本文件hash。
- `failure-audit.json`：403与缺usage的安全诊断。
- `bm25-only-results.json`：全部50题的函数/文件排名、候选数和BM25指标；dense/RRF显式null。
- 真实原始响应只保留私有账本；无需再次调用API即可复核。

原258份历史保护文件和5份冻结文件在启动前通过哈希核对；结束后再次核对历史与冻结、实际账本及引擎hash。分析期间禁止socket连接，账本仅读取，不调用recover、不改变unknown。

入口及分析命令记录：

```sh
# 已执行一次，因403停止；不要再次用于重试
python -B scripts/run_expanded_live.py --execute-approved-run --approval-id Sentinel_fbb9c43d04ac819197437d5bf7cf38f3
# 已执行的只读审计与离线评分；输出拒绝覆盖，复查应保留已有证据
python -B scripts/evaluate_expanded_live.py
python -B scripts/score_expanded_bm25.py
```

实际Python为 `/home/lenovo/projects/LocAgent/.venv/bin/python`，cwd为独立预览工作区。最终源文件包括真实入口、预算/transport、门禁测试、只读审计和评分脚本，另导出完整diff；本轮未提交。

## 剩余阻塞

完整dense/RRF比较被第491次403与unknown占用阻塞。当前授权明确要求失败即停，因此本轮到此结束。后续若调查，应先查看已有脱敏证据/服务方账单，不能自动补发、丢弃16个输入、改变冻结计划、重置预算或另起run。任何恢复发送需另行明确决策；本轮不实施。

一次跨线程即时状态发送被自动审批拒绝，理由是缺少用户明确的跨线程发送授权；该消息未发送，也未绕过。最终结果通过本任务正常返回，不影响真实实验自身的既有授权。
