# SQLGlot 单题真实流程验证结果（2026-11-15）

两组均正常终答。原生 LocAgent 适配组 3 次、OpenHands 适配组 4 次，共 7 次实际启动且取得 HTTP 200、有效 usage 的响应；失败 0，重试 0。未超过 8 次请求、17 元上限，剩余预留为 0。模型回包均为 `deepseek-flash`。一次性授权已使用，不能重启或补跑。

| 观察 | 原生 LocAgent 适配组 | OpenHands 适配组 |
|---|---|---|
| 请求数 | 3 | 4 |
| 调查工具 | 1 次目录图探索、3 次正文/实体搜索 | 4 次普通文本搜索、2 次按行读文件 |
| LocAgent 相关路径 | 正文后端记录 10 个子查询 | 未调用 `locagent_retrieve` |
| 工具证据字节 | 14,336 | 9,309 |
| 终答 | 正常 finish | 第四轮正常 finish |
| 共同定位 | `sqlglot/parser.py:Parser._parse_set_item_assignment`、`Parser._parse_set`、`Parser._parse_set_item` | 同左 |

两组均给出了更多候选文件/实体和原因解释，但本轮没有进行正式语义评分。OpenHands 的解释称 `_parse_primary` 消费点号表达式为 Column，原生组则称只消费前段、留下点号；两者解释不一致，不应因为协议完成或候选函数重合就认为分析全部正确。部分输出实体是类属性或不完整限定名，仍需按既定实体评分口径审查；没有修改终答或 gold。

原生组用满工具证据预算后第三次即收尾。OpenHands 正确发出了按行读取 parser.py 5960–6015、snowflake.py 420–435 的请求；本轮没有观察到自主 LocAgent 检索或续页选择。此结果不解释模型为何不选检索，更不能证明检索无效。

费用证据来自全部 7 条持久化原始回包：输入 29,480 token（缓存命中 9,344、未命中 20,136），输出 1,944 token。按全输入未命中及高峰单价保守核算，账本上界 **0.074512 元**。按执行日周末空闲时段公开价及回包缓存命中，估算 **0.02809888 元**，约 0.0281 元；未查看供应商最终账单，不能称实扣已核验。价格依据：<https://api-docs.deepseek.com/zh-cn/quick_start/pricing/>。

两组是“LocAgent 图工具 + physical-line80 正文 BM25（适配版）”与“OpenHands 基础工具 + 实体 BM25（适配版）”，提示和工具体系不同。SQLGlot3417 已用于开发，因此只是单题流程验证，不是正式评测或独立泛化结论。

本次使用原冻结计划 `8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585`。完整具体数据范围的用户确认后，审核通过；此前审核拒绝与超时记录全部保留。没有覆盖历史结果、执行目标仓库代码或发送 gold/参考补丁。密钥经既有安全加载器进入内存和匿名管道，没有显示或另行保存。

审计限制：旧 comparison_contract 中 `live_enabled=false` 描述性字段未随新接线更名；本次真实运行身份应依据一次性真实授权、ledger 的 live 模式和 7 条真实传输回执判定。未在运行后修改历史元数据来掩盖此差异。总结果中的 `real_model_requests=null` 是保守原始字段，本报告依据完整回执确认实际 7 次响应。

证据：`verification/cohort-live-explicit-confirmation-v1/run-summary.json`，原始结果和账本位于 `authority-cohort/<plan_hash>/run/`。没有后续请求或补跑。
