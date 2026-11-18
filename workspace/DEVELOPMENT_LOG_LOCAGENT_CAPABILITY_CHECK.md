
## 2026-11-13｜原题与真实已见线索的 LocAgent 免费能力检查

- 核对旧诊断后复用12条主查询，新增4次离线检索（Loguru raising_recursion/tail_recursion，SQLGlot _parse_set/_parse_primary）；另复用2条oracle结果单列。检索适配器、引擎、源码、分页函数及标签一致，旧输出hash校验通过；没有重复跑已知查询。
- 两题完整原文999/1386字符超过256接口上限，均在执行前被拒，标记未评估而非未命中；原标题57/55字符逐字等于第一行，不混用全文。16条主查询在新增检索前保存，但仍为已曝光开发集的分析者选择。
- 来源仅从原题和实际请求的tool消息取证，逐条记录run/arm/turn/message/hash及摘录。Loguru已见文件/测试basename来自A批第2轮list_files；SQLGlot新符号在B检索组第3轮已见、基础组第4轮才见，关闭调查后的信息不冒充可用机会。
- Loguru标题只返回Logger.add（49465原始bytes/4096首JSON页）；题目短词和新增两条basename均空（19/49）。已见_better_exceptions.py可精确读全文件24272bytes，原始含完整目标9行，但4096首屏和14336总预算均未交付目标。_format_list从未进入所查真实请求；oracle第1且761bytes完整返回，仅证明已知名读取。
- SQLGlot标题及SET TAG/SetItem未命中参考；已见_parse_set_item返回分派函数并含后续线索；已见_parse_set_item_assignment第1，原始1178/首JSON1244bytes，完整19行与源码匹配。新增_parse_set与_parse_primary分别返回对应非目标函数684/730、2559/2647bytes。
- 2732份历史/生产/冻结/诊断材料哈希不变；真实调用0、费用0、未读凭据、未执行目标代码、未改策略或授权。建议下一步免费研究发现覆盖与大结果预算、查询长度契约；不以oracle查询或反事实检查宣称模型自主调用、因果或检索收益。
- 报告LOCAGENT_CAPABILITY_CHECK.md；证据verification/locagent-capability-v1/results.json与acceptance.json。
