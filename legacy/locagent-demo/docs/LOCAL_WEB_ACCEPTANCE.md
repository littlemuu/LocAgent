> 历史验收快照，结论仅覆盖当时范围。后续真实案例见 [REAL_CASES](REAL_CASES.md)，当前整理验证见 [DEMO_VALIDATION](DEMO_VALIDATION.md)。

# 本地前端验收 · 2026-11-07

## 交付与边界

交付目录：`/Users/xiaomu/Documents/Codex/locagent-local-web-20261107`。
基于当时 `locagent-local-install-20261107` 的工作区内容复制，保留其未提交改动；未复制 `.git`、虚拟环境、outputs、runs、密钥或历史授权。
原安装目录和 `Projects/LocAgent-rag-preview` 未改写、未提交、未推送。

新增：`locagent_service/local_web.py`、`local_web_assets/`、`start-local-web.command`、`tests/test_local_web.py`、测试专用 `tests/local_web_offline_job.py`、`README_LOCAL_WEB.md`。
仅在副本中修改 README 和 .gitignore。原有 engine、预算、授权、来源校验与 CLI 文件不改动。

UI 复用原工作台的视觉布局，改为当前 CLI 支持的 BM25/prepare/明确确认/run，不调用旧数据库 API。保留旧 `locagent_service/web/index.html` 供历史服务使用。

## 实际验证结果

1. **最终新增前端测试：11 项全通过**，`verification/local-web.log`。
   - 真实 loopback HTTP、服务与 CLI 子进程、真实图/BM25和 3 步工具循环，供应商 HTTP 为手写合成响应。
   - 正确的文件/函数、原始源码片段、行号、固定 commit 链接、工具返回轨迹与账本摘要。
   - 默认付费关闭、准确计划 SHA、逐题明确同意、提交标记先于启动、同题重复点击拒绝。
   - 未知 HTTP 结果保留完整预留并停止，只发生一次合成发送；拒绝重放。
   - Host、Origin、Fetch-Site、session header、JSON/大小限制、路径穿越、无 CORS/CSP/不回传 key。
   - 允许跨站顶层导航打开不含秘密的 HTML，但同样的导航头不能读取 session 或任务 API。
   - 8000 字中文输入、重复任务编号、单活动任务、相同目录双服务锁、异常重启持久只读封锁。
   - 配置/预览篡改不能改变用户看到的真实预算、endpoint 和问题。
2. **原 CLI 16 项全通过**，`verification/local-cli.log`。
3. **浏览器实际操作通过**：
   - Chrome 打开本机页面，合成 demo 完成，明确标为合成与零付费。
   - 页面真实下载并准备 `pallets/itsdangerous@2.2.0`，commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。
   - 免费准备任务编号 `7225d92d38dc48f798a1c50850cb885f`；问题为 `Where are signed timestamped values verified and checked for expiration?`。
   - 计划展示 endpoint/model/budget/commit/question/SHA；付费确认复选框与按钮确实禁用。
   - 刷新保留任务，切换 demo/真实准备历史正确，没有自动重发或 JS 控制台错误。
   - 默认桌面视口截图目视检查通过；未声称移动端实机验收。
4. 独立安全复核后，修复异常退出遗留进程可能与重启新任务重叠的问题；现在有持久只读封锁。最终复核未发现高优先级阻碍，不是完整安全审计。
5. Python AST、shell 语法和新增文件空白检查通过。

## 全仓库旧聚合测试并非全绿

按 `PYTHON=... LOCAGENT_ALLOW_PAID=0 sh scripts/check_local.sh` 实际运行，脚本设置了 macOS 需要的 canonical TMPDIR 和 PYTHONPATH。
该次 discovery 共运行 **741 tests，1 failure，13 errors，19 skipped**。输出保存在 `verification/full-offline.log`。该次包含最初 10 项 web 测试；新增的第 11 项导航回归后来在最终 focused run 通过。

- 11 个 error 来自缺失历史冻结实验/账本输入，其中 3 个硬编码 Linux 历史路径，另有 expanded50 冻结清单与旧账本审计；本交付刻意未复制历史 outputs 或授权。
- 2 个 error 来自旧 queue wrapper 导入评估模块依赖 `torch`，当前本地最小运行环境未安装。
- 1 个 failure 来自旧 phased 进程死亡测试调用 Linux `prctl`，macOS 无此符号。
- 19 个 skip 属于现有条件化测试。未补装大型历史依赖、未迁移旧实验、未执行 PostgreSQL/Docker 扩展验收。

因此不能称全仓库全通过。原聚合检查在 unittest 返回非零后停止，末尾 git diff 未执行；此副本没有 .git，新/改文件另做独立空白检查。
最初一次直接 discovery 未设置 canonical TMPDIR，已中止；保留 `verification/full-offline-first-attempt.log`，不作为最终结论。

## 真实调用与授权

本次前端任务 **0 次真实模型付费请求**。实际 web-runs 没有 `paid-request.json` 或 `run-started.json`。测试中的 3 次、1 次请求数字仅指合成响应，不是计费流量。
当前服务在 127.0.0.1:8765，付费禁用。复用的无密钥供应商参数于 2026-11-07 重新核实官方价格；旧单题授权文字已移除，未复制旧 grant/ledger。

新前端的真实付费端到端尚未执行。需要用户另行批准具体公开仓库版本、问题、DeepSeek 接收方、要发送的问题/源码/轨迹、最多 3 次请求及 CNY 2.20 总上限，或由用户在本机按 README 自行明确确认。此前 CLI 的真实单题成功不替代这一点，也不是普遍定位准确率结论。
