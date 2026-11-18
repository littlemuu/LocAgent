
## 2026-11-13｜工具说明入口 summary 适配修复及授权复跑

用户要求“修复入口适配，再试跑一次”。新增隔离的 experiments/choice_pair_v2/run.py；只提取 wire schema 明确声明的字符串 summary，再执行原有严格 Action 校验。原始回包、原参数、辅助 metadata 与适配后参数分别保留；不接受其他未知字段，不执行模型返回工具。旧冻结入口和失败结果不改写。

离线 32 次检查全部通过（20 个不同用例，含 12 个重复预算/授权回归）；真实旧回包的两个带 summary 调用可通过，错误类型、未知字段、截断、超时、预算与重复启动仍拒绝。冻结 hash 327f2b94b2394808f75ef609f9a01aa2d855f8673b602d32664e0c0716daf3a2。

核对官方当前价格、已登录账户 CNY 状态、无旧运行或未结请求、.env 非秘密元数据后，用新的一次性授权运行同一 SQLGlot 历史构造检查点。原说明与新说明各 1 次 deepseek-flash 请求，共 2 次 HTTP 200 正常结算，无重试、无追加、无残留预留；费用按高峰全 cache miss 上界合计 ¥0.013754（用户上限 ¥5），尚未逐笔核对账户扣费。

两种说明都选 read_file(parser.py, 5960–6015) + search_text；原说明搜索 _parse_alter_table_set，新说明搜索 _parse_set_item_assignment，均未选 LocAgent。说明调整在本次单检查点未引出检索；不能断言模型动机、普遍无效或检索收益。没有执行工具或测量终答。2667 个历史文件与旧配对运行 5 个文件 hash 不变。完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/CHOICE_PAIR_V2_RESULT.md；审计：verification/choice-pair-live-v2/live-acceptance.json。
