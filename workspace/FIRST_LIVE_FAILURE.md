# 首次真实调用的终答协议问题与修复

**后续已完成：修复版两组真实终答成功。** 详见 [真实试跑结果](LIVE_PILOT_RESULT.md)。
以下保留首次失败及批准过程，不代表当前待执行状态。

**后续状态：用户已批准修复版试跑，新 grant 已记录，尚未领取或启动。**
电脑操作工具禁止控制 Terminal，需用户在本机终端手动启动并隐藏输入 Key。
见 [修复版批准与交接记录](verification/REPAIRED_PILOT_APPROVAL.json)。下文保留原诊断记录。

2026-11-12，北京时间。基础组成功调用 DeepSeek 3 次，全部 HTTP 200 且 usage 已落盘结算。
模型通过 list_files、read_file 找到了 `src/greeting.py:greeting`，但在终答协议验证处停止。
检索组未启动，没有自动重试或额外付费请求。

## 原因

OpenHands 原生 FinishTool 把 `message` 声明为自由文本字符串，描述为发送给用户的最终说明；
我们的 SDK 适配器却在收到它后调用 JSON 解析，并要求 `files/entities/answer`。
系统提示有 JSON 要求，但工具 schema 与描述没有表达同一合同。
第三次真实回包遵循原生工具声明，在 message 中返回正确的自然语言定位说明；
本地 JSON 解析失败，经 SDK 包装为 ConversationRunError，再被父进程压成了用户看到的 RuntimeError。
原先正向测试直接构造了 JSON 字符串，所以没有发现这个接口缺口。

这是本地终答协议接入缺陷，不是密钥、网络或余额不足；三次成功回包也不能证明完整两组试跑成功。
不把自然语言结果自动抽取为结构化评测答案，也不改写这次原始 failed 结果。

## 费用与状态

- 原方案：`7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f`。
- 3 次基础组请求，逐次结算上界为 ¥0.002108、¥0.002372、¥0.003756，合计 **¥0.008236**。
- 上述是账本按高峰、输入全缓存未命中计算的保守上界，不是供应商余额实扣核对结果。
- 未结算预留 **¥0**；账本 halted、needs_review；原授权已消费，不能重跑。
- 原账本/轨迹/结果保留；修复期间未读取密钥、未调用真实供应商、未创建新授权。

[原始诊断摘要](verification/FIRST_LIVE_INCIDENT.json)；
[原始运行结果](authority/7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f/run/baseline/result.json)。

## 已完成修复

1. 模型端 finish.message schema 明确为 object，必需 files/entities/answer，包含数组长度、唯一性、文本长度和禁止多余字段约束。
2. 出站描述与系统提示对齐；本地拒绝自由文本、JSON 字符串、缺字段或错误类型，不做静默转换或结果猜测。
3. 入站对象通过验证后转换成 SDK 原生 FinishAction 所需的 JSON 字符串；原始 HTTP 回包保持原样，源码路径继续按相同快照校验。
4. 保留第一个停机原因，避免 SDK/父进程后续错误将它覆盖；终端报告给出可读原因、请求数、费用上界和未知预留，不打印原始异常文本。

## 免费验证与后续边界

- [SDK/预算/授权/终答回归](verification/finish-contract-tests-v1.log)：**46/46**；新增 6 项使用本次真实回包复现原矛盾、检验新 schema、转换不修改原回包、无效格式拒绝、先结算后停机及安全错误报告。
- [核心/LocAgent 回归](verification/core-regression-finish.log)：**26/26**；总计 **72/72**。
- [新版本双组离线回放](verification/deepseek-preparation-v3-finish.log)：两组各 2 次模拟 HTTP，均完成；真实 LocAgent 检索成功；无真实网络调用。
- 修复版本冻结 hash：`6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd`，
  [proposal](verification/deepseek-preparation-v3-finish/proposal.json) 保持未授权。

本次授权明确要求出错停止、不自动重试，且代码及终答协议已变更，因此没有继续消费原次数余额或自动生成新 grant。
如需再次付费验证，应单独批准修复后的具体运行范围；原命令不能继续使用。
离线通过不保证模型一定遵守新 schema，首次真实结构化终答和检索组兼容性仍待验证。
