# 跨文件收尾控制修复与下一次试跑提案

最新结果：用户已完成真实试跑，两组均在第 4 次响应正常 finish；检索组未选择 LocAgent。授权已消费，无追加请求。见 [真实验收结果](CROSSFILE_CLOSING_LIVE_RESULT.md)。

更新：用户已批准下述修复方案，一次性授权已登记，等待本机终端隐藏输入 Key；尚未启动真实请求。
最新状态及有效期见 [启动检查记录](verification/CROSSFILE_CLOSING_APPROVED_PREFLIGHT.json)。下文“未授权”描述保留为离线修复完成时的历史状态。

2026-11-12，北京时间。已完成免费修复与离线验收：**新增付费请求 0 次，未读取密钥，未创建新授权**。
三个历史付费账本哈希均保持不变，原失败结果没有改判或覆盖。

## 为什么上一轮仍请求 read_file

可证实的事实：第 4 次请求已关闭 thinking，只提供 finish，并通过 tool_choice 指定 finish；
真实回包却继续要求读取 metrics.py 和 reports.py。本地允许列表拒绝，未执行这两个读取。
[官方接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)描述非思考模式支持指定工具选择，
因此不能将这次回包解释为请求本来允许 read_file，也不能仅凭一次回包判断供应商内部实现原因。

本地可以确认的提示缺口：系统提示只泛泛要求“调查结束时提交”，没有逐轮预算信息；
最终请求以一条源码工具结果结尾，没有明确告知“本轮必须结束、无需读完所有文件”。
模型表现出继续遍历剩余文件的行为。这个缺口可能助长了继续调查，但因果关系尚未通过真实调用验证。

执行边界原本正确拒绝了越界工具；本轮保留它，并补足执行器主动关闭及可读的错误分类。

## 已实现的行为

1. **每轮预算提示**：在请求末尾追加可信控制消息，标明第几次响应、调查工具与源码结果可用额度，明确最后一次响应留给 finish；鼓励证据充分时提前终答，不要求遍历整个仓库。
2. **显式收尾消息**：最后一轮或调查额度耗尽时，明确“INVESTIGATION IS CLOSED”，可用调查额度为 0；只能提交一次结构化 finish，以已有证据作答，证据不足可返回空列表并说明不确定性。
3. **不增加请求**：每组仍最多 4 次，至多 3 次调查响应加 1 次预留收尾；提前收尾可以少用。没有修复重试、额外模型整理或超额补答。
4. **三层限制同时生效**：出站仅提供 finish 并指定工具；入站校验拒绝其他工具或混合终答；会话工具执行器提前关闭，即便意外调用执行器也不能再读取源码或消耗调查额度。
5. **准确诊断**：分别记录 closing_tool_violation、closing_finish_missing、model_output_truncated、finish_message_contract_error 等固定错误码；SDK 包装后仍把原始停机原因写入结果，终端显示可读说明和预算状态。
6. **预算落盘机制保留**：原始请求先预留、原始回包先落盘、usage 校验后结算，再解析工具。已知费用即使协议失败也保持 settled；超时/未知结果保留预留，全部停止、不重试。

控制消息由 `readonly_agent/control.py` 生成，不来自仓库文本；以当前请求的 user-role 控制通知发送，
保留原始系统提示、题面、工具结果和 call ID，不累积旧通知到 SDK 会话历史。
控制消息自身计入请求字节限制；超长时在预留/联网前失败。工具结果未闭合时仍拒绝请求，通知不能掩盖协议错误。
控制策略以 controller_policy 字段和代码哈希绑定到新 proposal / grant / SDK contract。

## 离线验证

- [SDK、预算、授权与收尾测试](verification/closing-control-tests-final.log)：**56/56**，包括本轮新增 10 项测试及原测试的加强断言。
- [可观察性/样例选择回归](verification/closing-observability-regression.log)：**10/10**。
- [核心与真实 LocAgent 回归](verification/closing-core-regression.log)：**26/26**。合计 **92/92**。
- [提前终答双组回放](verification/crossfile-closing-v1.log)：各 3 次模拟请求，均 completed。
- [最终第 4 轮双组回放](verification/crossfile-closing-final-turn-v1.log)：各 4 次模拟请求，均 completed；最后请求明确关闭调查并指定 finish，之前仍是 auto。
- [检索证据审计](verification/crossfile-closing-final-turn-v1/retrieval-observability.json)：真实 LocAgent 返回的 1642 字节证据仍原样进入后续请求；脚本连通性不被误算为自主选择。
- 原始越界回包在真实 SDK + 模拟 HTTP 的第 4 轮仍失败，错误码明确，两个额外读取未执行、没有第 5 次调用、已知 usage 正常结算。这是正确的保护行为，不是把原回包“修成成功”。
- 其他异常覆盖缺少 finish、输出截断、坏结构化终答、关闭后的执行器直调、控制消息导致请求过长、孤立工具结果、超时与落盘失败。
- 第一轮有两项测试夹具重建历史 SDK 消息时缺少其内部必需 name 字段，补齐 call ID → name 后通过；未放宽生产协议，失败日志保留为 `verification/closing-control-tests-v1.log`。

这里验证的是控制内容、协议路径和预算边界；模拟模型按脚本返回 finish，**不能证明真实模型一定会遵守新提示**。
没有更换模型、扩大请求数、启用强制检索或改写原有检索实现。

## 下一次试跑提案（未授权）

新方案 hash：`487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35`

- 仍是同一 10 文件 webhook 样例、同一问题、同一源码快照；使用 `--case crossfile`。
- OpenHands SDK 1.62.0 + deepseek-flash，非思考、非流式、temperature=0、每次最多 1024 输出 tokens。
- 基础组与检索工具可用组各最多 4 次，总计最多 **8 次**；每组预留最后一轮用于终答。
- 调查时模型自主选工具，不要求调用 LocAgent；若没选就记录，若基础组先失败则检索组记未运行。异常停止，不补跑。
- 发送通用系统提示、原题面、工具定义、允许源码的工具证据，以及新增的逐轮预算/收尾控制消息。无 gold、离线脚本答案、旧模型答案或账户信息。
- 预算仍为每次最保守 ¥2.105344，8 次 ¥16.842752，拟新授权上限 **¥17**。
  [官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)再次核实：高峰输入 cache miss ¥2/百万 tokens、输出 ¥8/百万。不是预计实扣，启动前须核对账户适用价。

[冻结 proposal](verification/crossfile-closing-v1/proposal.json) ·
[精确第 4 轮出站示例](verification/crossfile-closing-final-turn-v1/baseline/wire-requests.json) ·
[准备汇总](verification/CLOSING_REPAIR_SUMMARY.json)。

没有沿用已消费的旧授权。若批准新方案，可记录对应 hash 的一次性授权，再由用户在本机终端隐藏输入 Key；
当前不存在执行此新方案的 grant。修改提示不是模型遵从保证，本次试跑也不作检索收益结论。
