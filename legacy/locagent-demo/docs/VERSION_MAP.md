# 版本地图与保留策略 · 2026-11-08

## 当前唯一演示入口

`locagent-demo-20261108/` 是本次独立整理副本，基于 `locagent-local-web-20261107` 的源码。保留 CLI、web 与既有定位引擎；只整理文档、启动/检查脚本和相关包装测试。无提交、推送或旧目录覆盖，也没有 `.git` 历史伪装成已发布版本。

底层历史来源为 `a006f58523b71110be08433b70c2e6cec4b7c21b` **加各阶段未提交改动**，因此不是纯净的 a006f58 checkout。`SOURCE_MANIFEST.json` 标识本次实际源码。

## 各副本用途

- `Projects/LocAgent`：`work/locagent-baseline`，HEAD `8ec986b`，本次起始已有 `tests/run_stage5_compose.py` 未提交修改。保留原状。
- `Projects/LocAgent-rag-preview`：`work/rag-offline-preview`，HEAD `a006f58`，已有 RAG/HTTP/UI 等未提交改动。保留原状。
- `locagent-local-install-20261107`：同 a006f58 历史基础，加 CLI、文档与其他未提交内容；原 `.venv-local` 不修改。
- `locagent-local-web-20261107`：非 Git 完整副本，加入本地网页和简化界面；保留原服务、历史任务和账本。本演示包不沿用它的运行目录、供应商配置或 key。
- `locagent-offline-retrieval-validation-20261107`、`locagent-controlled-retrieval-prep-20261107`：构造函数补读、后续阅读提示的隔离实验。**未合入**；离线机制测试不能替代真实模型收益评测。

起始保护快照保存在本机 verification；完成后会逐文件与 Git status 再核对。它不属于对外源码包。

## GitHub README 不同在哪里

2026-11-08 已通过 GitHub 连接器只读核对：

- [master README](https://github.com/littlemuu/LocAgent/blob/master/README.md)：上游论文/benchmark 流程；README blob SHA `c6d7ebeef4b6813d57820292c2904e4e883d788e`。
- [work/locagent-baseline README](https://github.com/littlemuu/LocAgent/blob/work/locagent-baseline/README.md)：旧异步服务、Docker/PostgreSQL、fake preview；README blob SHA `d4afe3c36bc98cce6703b06dda0d3a263e0cd054`。

这些是文件 blob SHA，不是分支 commit。它们目前都不是新 CLI/web 演示版的安装说明。本轮没有改动远端，也不提供会误导读者的旧分支 clone 即可安装承诺。

## 实验未合入的可核对点

演示基线的 `repo_ops.py` SHA256 为 `fa71542f83848bbddc40c678fa36dfb9d7efe6425d81ae80b45a1de1fb1a56fa`；`util/localizer.py` 为 `e1337f95d9ba3b9bddb54160841bfcac4298d0fd58561dc6bf9fa397a419f3c1`。不含 `constructor_source.py` 或 `skeleton_followup.py`。

对比 local-install 与 local-web 的核心 Python 树，唯一新增/不同文件为 `locagent_service/local_web.py`。原图/BM25、授权、预算、严格 finish 与源码证据机制不在这次整理中修改。

本次副本额外排除继承的生成式 benchmark 输出 `evaluation/loc_output/locagent/claude_3-5/loc_outputs.jsonl`，以免把旧评测结果当成可重跑源码。原四份目录中的文件保持原样。
