
## 2026-11-13｜批准的 LocBench 两题真实试跑停止：终答额外字段

- 用户明确批准两题数据范围、最多16次DeepSeek请求/34元。当前登录账户CNY，“产品定价”跳官方中文页，deepseek-flash当前版本DeepSeek-V4.1-Flash-1017、峰值输入2/输出8元每百万符合预算。复用既有私有.env，仅运行器加载，不展示密钥。13份旧生产子账按各自冻结预留规则/receipt/hash核对，无未决调用；新生产授权目录此前不存在。
- 冻结hash `6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9` 未变；新一次性grant登记后仅启动一次，审核通过。真实入口退出1，12请求后 `finish_message_contract_error` 停整批，无重试、补跑、修改执行代码或放宽规则。
- Loguru基础4请求，正常finish，7调查调用，11.44s，费用上界0.034822元；检索可用组4请求正常finish，7调查调用，10.07s，费用上界0.035708元。两组都将参考文件放第5位，文件F1=1/3、MRR=.2；参考函数_format_list均未命中，实体F1=0。回答重点为增加测试，自动定位分不等于人工内容判定。
- SQLGlot检索可用组4请求、6调查调用、10.90s，费用上界0.035968元。末轮HTTP200完整JSON，563输出tokens，message多出 `entities_note:null`，违反实际schema的additionalProperties:false，触发字段集合校验；不是截断/字符长度/网络故障。外层summary为SDK合法可选字段。原始终答虽含参考函数，但无有效finish，不计成功；SQLGlot基础组not_run。
- 两个已运行检索组均未自主调用LocAgent（0），没有强制补跑。SQLGlot读取offset5960/5969返回约145行，符合字符游标语义；模型可能误当行号，尚未修复验证。保留原回包和结果；仅对副本做三字段结构诊断，未追认答案。
- 全部12原receipt已结算，输入41977、输出2818（缓存命中17408/未命中24569）；高峰全未命中费用上界0.106498元，账单实扣未对账。未知请求费用0；总账17元案例hold只是失败额度占用，不是新增费用。授权已领取，不可重复启动。
- 报告 `LOCBENCH_LIVE_RESULT.md`；验收 `verification/LOCBENCH_LIVE_ACCEPTANCE.json`；故障原响应/schema `verification/LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json`；生产run下stopped/measurements/账本/SDK轨迹保存。当前计划及13旧账本未变。新增模型曝光：Loguru两组、SQLGlot检索组；一题完整配对、实际检索0，不声明检索收益/退化或独立测试结果。

