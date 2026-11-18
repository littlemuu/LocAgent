
## 2026-11-14｜SQLGlot 自然检查点工具选择方案准备（未授权启动）

按小目仅准备的要求，冻结读取修复后 SQLGlot 检索组真实第3请求，原请求 hash b203e951bb9f3fc57f3ab47dfb9013db5d4d57bb031accf429e2a92b2cc48172；当前核心代码与SDK系统提示 hash 均一致。历史4次普通工具已消耗5346字节，复算剩余12次/8990字节/1个调查响应；无历史LocAgent调用、无悬空tool结果。有检索组与原请求逐字节一致，基线仅从工具列表删除locagent_retrieve，没有改提示或追加辅助函数名/离线证据。

拟各组仅取一次自主响应，共最多2次DeepSeek请求、5元总上限；不执行返回工具、不补发终答、不重试。deepseek-flash非思考、temperature0、max_tokens2048，固定基线先行。反例仅保留离线参照，不加本轮付费样本。方案明确小样本、固定顺序、自然前缀条件重放而非完整自然基线、不能把基础组必然不能检索当作调用率因果证据，也不测最终答案或检索收益。

公开价格页2026-11-14核对仍为Flash高峰输入未命中2元/百万、输出8元/百万，版本参考V4.1-Flash-1017；账户实际价格待获准启动前核对。每次最大上下文预留2.113536元，两次4.227072元低于5元；预留不是预计费用。新隔离入口绑定精确payload及代码、一次性授权/claim、持久化账本、最多两次和异常整轮停止，保留summary兼容且拒绝错误参数。18项offline mock测试通过；生产authority-natural-choice目录不存在，Key未读取，真实模型请求为0。

冻结plan hash：664680ac971ed7520b7d84de8ce38c9635608107219f340d869d73ed89a4e895。基础/检索payload分别13732/14704字节，将来只发送SQLGlot题面、提示、工具定义与已收到的源码证据/历史到https://api.deepseek.com/chat/completions，不上传标签、补丁、新离线结果、其他题目或.env内容。此轮只有公开价格页查询，没有发送项目数据。2757个历史文件哈希未变。

完整方案与明确确认语句：/Users/xiaomu/Documents/Codex/2026-11-12/task/NATURAL_CHOICE_EXPERIMENT_PLAN.md。冻结/验收：natural_choice/v1/manifest.json、verification/natural-choice-prep-v1/acceptance.json。当前未创建生产授权，不沿用此前试跑批准；需用户另确认范围并完成启动前检查后才可运行。
