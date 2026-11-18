# GitHub 代码快照（2026-11-18）

目标仓库：`littlemuu/LocAgent`。新分支：`locagent-openhands-holdout50-20261118`，基于原 `master` 的 `4935b557326c154bad8e8dcf3747cc8d32d1f387`，保留原 LocAgent 源码和 Apache-2.0 许可证。原默认分支不变。

本次提交覆盖当前项目源代码和测试、`workspace/` 的历史开发代码、`legacy/` 保留实现、`runtime/`、版本 v8/v8.1/v8.2 校准代码、各轮冻结副本，以及 dev24/holdout 的数据适配、调度、离线核验、统计和收尾脚本。实验的原始冻结源码不为发布而修改；本次仅整理 Git 忽略规则、项目首页和发布说明。

同时保留预注册协议、依赖锁、选择清单、冻结哈希、结果表和报告。源码中的小型测试夹具与已有 dev37 源码快照随代码提交；大型 benchmark 镜像/索引、向量、数据集二进制、封存证据压缩包、完整模型轨迹、控制台截图、虚拟环境、安装轮包、本地密钥和环境变量文件留在本地。忽略规则不会删除本地文件。

## 当前实现与入口

| 内容 | 入口 |
| --- | --- |
| 当前检索实现 | `runtime/` |
| 历史 OpenHands 集成与测试 | `workspace/readonly_agent/`、`workspace/experiments/`、`workspace/tests_sdk/` |
| 最终校准版本 | `locator-diagnostic-calibration-v8.2/` |
| 最终冻结运行实现 | `holdout50-final-run-20261117/frozen/` |
| holdout 适配、核验与调度 | `holdout50-final-run-20261117/control/` |
| 揭盲后的审阅与报告脚本 | `holdout50-final-run-20261117/monitor/` |
| 主要结果表 | `holdout50-final-run-20261117/delivery/ABC-per-task.csv`、`summary.json` |
| 原始 LocAgent 入口 | `auto_search_main.py`、`dependency_graph/`、`repo_index/` |

这是代码和研究记录快照，不是完整离线数据包，也不是新一轮运行授权。依赖轮包、封存 parquet、向量/索引和证据原包没有上传；需要这些文件的校验、报告或运行入口不能仅靠一次 clone 完整复现。历史文件保留原相对/绝对路径及既有哈希，未批量改写成可移植路径；原报告内的本机绝对链接在 GitHub 上不可直接访问。

发布验证只检查提交内容、凭证候选、文件大小、冻结哈希和 Git 差异，不执行模型、harness 或付费实验。最终实验只运行一次，报告 A=21/50、B=20/50、C=20/50；不得因仓库复制而重置授权或重跑。
