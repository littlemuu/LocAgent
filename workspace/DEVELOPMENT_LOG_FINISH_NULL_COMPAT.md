
## 2026-11-13｜SQLGlot 已知空扩展字段最小兼容：仅离线

- 原回包完整、563输出tokens，旧schema拒绝finish.message.entities_note:null；不是截断、缺失必填字段或类型错误。为什么生成该字段无证据，不作模型归因。
- 新wire schema仅显式允许可选entities_note:null；canonical只保留原样files/entities/answer。原回包字节/arguments和账本不变，新增finish_normalization审计事件及报告字段。其余未知字段、非空说明、错误/缺失字段、外层异常参数继续拒绝，不截断或丢弃内容。
- 124项测试与9条完整MockTransport路径通过。原SQLGlot四份回包逐字节重放，SDK正常finish，核心答案一致且仅1条兼容事件；错误字段/路径、截断、收尾越界、超时、超大回包仍停止，未知结果保留预留，不重试、不重复启动。初次测试误把实体语义正确性当协议校验，已修正测试，生产格式验证规则不变，失败日志保留。
- 1,960个历史文件hash不变；312个源码/评分文件不变。原真实运行仍失败，没有追认成功。旧授权不能重启或加载Key；新生产授权未创建。本轮不加载.env，真实模型调用0、费用0。
- source v4 hash 8e178f5756b7e7b16b66cf8ed571702e5a09b7a056cb6a0b0907355cc87751e4；live v2 hash eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83。拟议仍两道曝光开发题/两组最多16请求、34元，需新批准及实际账户价格核查。官方价格再次核实deepseek-flash输入未命中2/输出8元每百万，34元不是预计费用。无检索收益结论；游标混淆未改。
- 报告 FINISH_NULL_COMPAT_REPAIR.md，验收 verification/FINISH_NULL_COMPAT_ACCEPTANCE.json，测试 verification/finish-compat-tests-v2.log，历史夹具 tests_sdk/fixtures/locbench_extra_field_incident.json。
