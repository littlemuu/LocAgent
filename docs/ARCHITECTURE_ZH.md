# 目录与架构

主要链路：题面与冻结源码 → OpenHands SDK 会话 → 基础工具 / LocAgent 检索 → 原始 finish → 独立评分与审计。

| 位置（相对 workspace） | 职责 |
|---|---|
| `readonly_agent/` | 源码快照、基础工具、SDK桥接、预算账本、传输与一次性授权 |
| `experiments/sdk_finish_selfcheck_v7/` | 最近自检提示对照实验：冻结、守卫、SDK适配、批次、受保护启动器 |
| `experiments/retrieval_evidence_v6/` | 当前证据检索后端 |
| `experiments/cohort_preflight/` | 题目/源码/索引绑定及运行入口边界 |
| `experiments/eval_preflight/scoring.py` | 严格排名指标；gold仅用于运行后本地评分 |
| `experiments/finish_evidence_audit_v1/` | 终答与实际送达源码证据检查 |
| `engine_adaptation/v4/` | 固定引擎、源码计划、实体索引及验证证明 |
| `verification/` | 冻结准备、模拟记录、真实请求账本、响应、结果与审计 |
| `authority*/` | 既有一次性授权与消费记录；作为历史保留 |
| `tests/`、`tests_sdk/`、`tests_observability/` | 核心、SDK及观测回归 |
| `diagnostics/` | 历史离线诊断与适配构建工具 |
| `reference/`、`vendor-wheels/` | SDK参考源码与已有安装材料 |

没有移动 workspace 内部文件：冻结哈希、脚本相对路径和原报告引用因此保持原貌。新导航放在上层 docs，避免重写受保护的历史材料。旧版实现和实验是可追溯记录，后续开发请先确定版本入口再修改。
