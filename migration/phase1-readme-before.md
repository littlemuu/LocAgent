# LocAgent / OpenHands 项目

当前工作入口：`workspace/`。本目录将当前代码、历史实验、原版依赖与基准源码集中管理；原工作区保留。

**最新开发（2026-11-16）**：v8 完整混合检索已接入实际 OpenHands SDK，40项离线测试和端到端演示通过；真实向量与付费调用尚未启用。见 [v8 接入与复现](docs/V8_OFFLINE_INTEGRATION_ZH.md)。


**真实向量恢复（2026-11-16）**：已核验9,846个文档向量及60个查询向量，历史排名复现通过；与37题预统计输入匹配为0。编码前需处理重复限定名及固定题面查询长度，当前仍无新增付费调用。见 [恢复结果与37题覆盖](docs/V8_REAL_VECTOR_RECOVERY_RESULT_ZH.md)。

**最近真实验证（v7）**：六题自检提示 v7 已真实完成，12/12组、46请求，无技术中止。平均 Recall@5 从73.61%升至80.56%，首位命中均5/6；已曝光开发题各跑一次，不代表稳定泛化收益。新增响应计量费用上界0.517462元，累计472请求/5.490738元。

先读 [当前进度](docs/STATUS_ZH.md)、[目录与架构](docs/ARCHITECTURE_ZH.md)、[开发与复现](docs/DEVELOPMENT_ZH.md)。历史报告见 [报告索引](docs/REPORTS_INDEX.md)，开发记录见 [日志索引](docs/LOGS_INDEX.md)。最新完整结果：[六题自检报告](workspace/verification/sdk-finish-selfcheck-v7-live/REPORT_ZH.md)。

| 目录 | 内容 |
|---|---|
| `workspace/` | 当前完整代码、tests、experiments、engine_adaptation、verification 与原历史资料，保持原相对结构 |
| `legacy/locagent-demo/` | 原 LocAgent 代码、服务/界面及历史记录 |
| `legacy/locbench-adapter/` | 原基准适配器 |
| `benchmarks/` | batch134 基准资料，各适配版本引用的白名单 Python 源码快照及父清单 |
| `docs/` | 新的项目导航、当前结论、开发说明与分类索引 |
| `scripts/` | 仅做本地完整性检查和关键离线回归的入口 |
| `migration/` | 来源映射、复制文件哈希、排除清单与验证记录 |

原冻结计划包含旧绝对路径，完整保留，不能批量替换路径后声称仍是同一冻结计划。旧环境通过两个明确的本机符号链接复用，基准快照已另行收集；本次是本机项目整理，并非已经完成跨机器可移植化。**暂时保留旧目录**；以后迁移运行路径需要生成新计划并验证。已消费的真实授权不会因复制获得新的使用次数。

没有复制 `.env`、本地 provider 配置、虚拟环境实体或缓存；`.env.example`、依赖锁与本机环境位置保留。整理没有模型请求、费用或上传。旧 `workspace/README.md` 是历史时间线，当前状态以本首页及 docs 为准。
