
## 2026-11-12 北京时间｜修复版首次真实双组试跑完成

- 用户在本机终端完成隐藏 Key 输入并报告“好了”。只读检查真实账本、两组结果、工具审计和原始回包，修复版 hash `6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd` 绑定一致。
- 两组均 completed/finished，均定位 `src/greeting.py:greeting`，各 3 次模型请求；6 次均 HTTP 200、settled，源码工具调用均无错误，两个 arm token 均 finished。
- 基础组实际调用 list_files/read_file，检索工具可用组实际调用 search_text/list_files/read_file，**没有调用 locagent_retrieve**。不声称真实模型检索执行验收或检索收益；样例非 benchmark。
- 本轮账本费用上界 ¥0.019130，未知预留 ¥0，未 halt；加上失败轮共 9 次请求，上界 ¥0.027366。不是供应商实扣金额。
- 验收期间未读取密钥、未追加模型调用、未修改原账本/结果或重置授权；无需改代码和重复运行离线测试。前后端尚未接新 Agent。
- 交付 `LIVE_PILOT_RESULT.md` 与 `verification/LIVE_PILOT_ACCEPTANCE.json`；保留前一轮失败诊断及全部历史证据。
