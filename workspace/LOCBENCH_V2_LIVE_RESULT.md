# LocBench 两题修复版补测：四组完成

2026-11-13。按用户批准，仅运行一次固定两题四组补测。16 次真实 DeepSeek 请求全部 HTTP 200、回包完整、费用已在本地账本结算；4/4 组正常 SDK finish，失败 0、自动重试 0。
费用保守上界 **¥0.141562**，低于批准的 ¥34；未决请求/预留/案例 hold 均为 0。供应商账单实扣尚未逐请求对账，不能把该上界称为实扣。

## 范围与启动核查

- 固定 Loguru-1239 与 SQLGlot-3417，两题每组最多 4 请求；同一 OpenHands SDK 1.62.0、deepseek-flash、temperature=0、非思考、2048 输出 tokens。工具组区别只有是否开放 LocAgent。
- source v4：8e178f5756b7e7b16b66cf8ed571702e5a09b7a056cb6a0b0907355cc87751e4。
- live v2：eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83。运行后重算冻结内容仍一致。
- 用户批准向 DeepSeek 发送题面、提示、工具定义、相关源码证据和各组会话历史；执行器未加载评分标签或参考补丁。
- 刷新当前登录账户后显示 CNY，产品定价链接指向官方中文页。2026-11-13核对 [官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：deepseek-flash 对应 DeepSeek-V4.1-Flash-1017，高峰输入未命中2元/百万、输出8元/百万，符合冻结预算。运行前账户显示余额2.65元；没有充值或更改账户设置。
- 15份旧生产子账无未决请求；旧LocBench状态halted，12请求已结算；进程只读检查没有运行中的Python试跑。新授权目录此前不存在；.env路径、权限、大小和修改时间与此前相同，无本地覆盖，只有运行器安全加载，不输出Key。没有以API额外调用核验Key与浏览器账户的密码学绑定。
- [启动检查](verification/LOCBENCH_V2_APPROVED_PREFLIGHT.json)；新一次性授权已消耗，不可重复启动。

## 实际结果

调查工具计数不含最后一次 finish；每组均另有 1 次 finish。

| 题目/组 | 请求 | list/search/read | LocAgent | 耗时 | 费用上界（元） | 文件命中/预测；F1 | 实体命中/预测；F1 |
|---|---:|---|---:|---:|---:|---|---|
| Loguru 基础 | 4 | 1/3/2 | 0 | 12.11s | 0.033304 | 1/5；0.333 | 0/3；0 |
| Loguru 检索可用 | 4 | 1/3/3 | 0 | 11.34s | 0.036858 | 1/5；0.333 | 0/3；0 |
| SQLGlot 检索可用 | 4 | 0/4/2 | 0 | 12.11s | 0.036442 | 1/3；0.500 | 1/3；0.500 |
| SQLGlot 基础 | 4 | 0/4/2 | 0 | 12.84s | 0.034958 | 1/5；0.333 | 1/5；0.333 |

Loguru两组都将参考文件loguru/_better_exceptions.py排第5（MRR=.2），没有命中参考函数_format_list，回答主要讨论异常格式测试。
SQLGlot两组都将参考文件sqlglot/parser.py排第1，参考函数Parser._parse_set_item_assignment排第2（实体MRR=.5），实体召回均1。
SQLGlot检索可用组少报了两个非参考候选，因此严格precision/F1较高；它实际没有调用LocAgent，不能将这一差别归因于检索。
定位指标基于冻结参考补丁涉及函数，不是唯一根因证明，也不等于完整答案质量或独立盲评。

## 收尾、证据与费用

4个真实finish都只包含files/entities/answer；finish_normalization事件为0。
新schema在本次真实请求中正常被接受，但已知空字段兼容分支没有在本轮触发。它的直接证据仍是此前历史原字节离线重放；不能声称新规则必然导致这次成功。

累计输入55,357、输出3,856 tokens；输入缓存命中22,528、未命中32,829。按高峰所有输入均未命中计上界：
55,357×2 + 3,856×8 = 141,562 微元 = ¥0.141562。实际缓存/时段价格可能更低，未用粗粒度账户余额差代替逐请求实扣。
16份receipt及请求SHA256逐项验证，每组最多4请求；前三轮tool_choice=auto，末轮只有finish；没有补跑、扩大额度或强制检索。

- [验收报告与逐请求工具/usage/hash](verification/LOCBENCH_V2_LIVE_ACCEPTANCE.json)
- [测量、答案与检索可观察性](authority-locbench/eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83/run/measurements.json)
- [总账运行结果](authority-locbench/eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83/run/result.json)

1,960个旧历史文件、15份旧账本hash未变；上次失败保持失败。本轮新增结果独立保存。

## 局限与后续

这是已曝光的两道开发题，一次采样、每组4请求，不是独立评测，也不能证明收益/退化或稳定性。
两个检索可用组均未选择LocAgent，真实检索链路仍未在这些真实仓库题上验证。
SQLGlot检索组在终答中明确说明read_file返回了错误offset区域，因此其具体解析机制仍有推断成分；之前发现的字符游标/行号混淆没有在本次任务中修改。
下一步可先离线审查read_file行号与分页接口、检索工具描述及题目匹配，不追加真实请求。
