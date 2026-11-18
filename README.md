# LocAgent × OpenHands

**最新状态（2026-11-18）**：冻结的 Verified holdout50 一次性 A/B/C 实验与审阅已完成。原始 resolved 为 A 21/50、B 20/50、C 20/50，三项预注册精确 McNemar / Holm p 均为 1；本轮未提供 C 更优的证据。供应商余额不足和 harness 日志/评分不一致均保留原结果，没有补跑或重新评分。

- [最终实验报告](holdout50-final-run-20261117/delivery/FINAL_REPORT_ZH.md)
- [150 组逐题结果](holdout50-final-run-20261117/delivery/ABC-per-task.csv)
- [预注册口径](holdout50-final-run-20261117/PREREGISTRATION_ZH.md)
- [GitHub 代码快照范围与复现边界](docs/GITHUB_SNAPSHOT_ZH.md)

本分支以原 LocAgent 的 `master` 为父提交，保留其源码、许可证和历史，并加入本地 OpenHands 项目的代码、测试、各版本冻结副本与实验脚本。原默认分支不变。历史实验授权已消费；仓库中保留授权记录不代表允许再次运行付费实验。

## 阶段 1 历史说明

以下段落保留阶段 1 当时的状态，不代表当前实验进度。

研究问题：**定位改进是否提升 Coding Agent 的端到端修复率？** 定位是手段，SWE-bench resolve 率是主要目标，当前尚未得出效果结论。

日常开发在本目录使用独立 `runtime/`、`data/dev37/` 和根目录 `.venv`：

```sh
./dev bootstrap   # 仅首次：本地锁定轮包，断网安装；已有环境拒绝覆盖
./dev test        # 离线单元与实际 SDK 测试
./dev regression  # 原 37 题离线回归
./dev verify      # 核验阶段 1 冻结哈希
```

验证输出要求新目录；如需重跑先归档相应 verification 子目录。统一路径配置在 `project_config.json`。旧 `workspace/` 与 `legacy/` 为保留的历史档案，原路径与原实验报告不改写；日常入口不依赖它们指向的旧环境。

阶段 1 报告见 `docs/STAGE1_REPORT_ZH.md`，协议与端到端设计见 `design/`，冻结清单见 `freezes/stage1-lock.json`。本轮未调用付费 API、未生成真实向量、未执行 holdout 或云端修复评测。交付阶段 1 后停止。

---

以下为迁移前项目介绍，保留历史上下文；其中状态与命令不作为当前日常入口。

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
