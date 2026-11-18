# OpenHands + DeepSeek：真实调用准备，尚未授权启动

2026-11-12 UTC。已完成持久化预算与模型/工具协议的离线验证，真实调用默认锁定。
此次没有读取 API key、调用模型、改旧授权或修改现有前后端和安全设置。
后续真实传输、一次性授权与额外 15 项验收已完成，见 [最新启动说明](LIVE_PILOT.md)。
下方 25 项测试和 v1 回放为上一阶段留存记录；当前累计 66 项通过。

## 可审阅的首个验证方案

| 项目 | 固定内容 |
|---|---|
| 底座 | OpenHands Software Agent SDK 1.62.0；依赖 lock 和实现哈希绑定到 proposal |
| 模型 | `deepseek-flash`，官方文档当前版本标识 DeepSeek-V4.1-Flash-1017 |
| 接口 | `POST https://api.deepseek.com/chat/completions`；非流式；非思考；temperature=0 |
| 数据 | 自写 `examples/source/src/greeting.py`，一个题面；不使用 LocBench gold/patch/hints |
| 题面 | `Locate the function that constructs the greeting.` |
| 对照 | 基础工具组 vs 基础工具 + LocAgent 检索组；同 SDK、同源码、同提示、同预算 |
| 请求上限 | 每组 4 次，总共 8 次；源码/工具预算耗尽时可提前收尾 |
| 每次输出 | max_tokens=1024；请求 JSON ≤65536 字节，原始响应存储 ≤65536 字节 |
| 工具额度 | 每臂 16 次调查调用、14336 字节序列化工具正文、4096 字节单页 |
| 费用停止线 | **CNY 17.00**，需用户批准后才可形成新的真实执行授权 |

官方中文价目表目前列出的 Flash 高峰价为每百万输入 cache miss **2 元**、输出 **8 元**。
采用高峰、输入全 miss，忽略缓存和空闲折扣，完整上下文按 1,048,576 token 保守预留：

`单次预留 = (1,048,576 × 2 + 1024 × 8) / 1,000,000 = 2.105344 元`

`8 次完整预留 = 16.842752 元 < 17 元停止线`

这是上限核算，**不是预估实扣**。当前只核对了公开价目；未读取账户余额或实际账户币种。
启动前需确认账户人民币计价及全包价格不超过这两个单价；USD 账户须另行计算并冻结汇率上限。
来源：[DeepSeek 官方中文定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

此验证只验 SDK/供应商/工具/终答协议，不产生定位效果结论。通过后另行冻结真实开发题做对照。
旧第二阶段基础组 15 题收尾缺陷的结果保持原样，不用于声称新方案效果更好。

## 会发送什么

1. 只读代码定位系统提示、上述题面、模型参数和工具 JSON Schema。
2. 后续请求包含模型先前的工具调用和对应结果（按 call ID 串联），以及已经读取/检索到的源码片段。
3. 当前样例源码只有 greeting/farewell 两个函数，返回 `hello ` / `bye ` 与参数拼接。
4. 基础组可用 list_files/search_text/read_file/finish；检索组仅多 locagent_retrieve。
   `finish` 的 message 保存 files/entities/answer JSON。

不会发送评分标注、patch、hints、旧答案、整个图索引或账户配置。API key 将来仅用于 Authorization
请求头，不能放入模型消息、账本正文、轨迹或浏览器。当前离线 transport 只使用字面假 key。
精确模拟出站正文已保存，可逐条检查：

- [基础组 wire 请求](verification/deepseek-preparation-v1/baseline/wire-requests.json)
- [检索组 wire 请求](verification/deepseek-preparation-v1/retrieval/wire-requests.json)
- [冻结 proposal](verification/deepseek-preparation-v1/proposal.json)

请求序列会随真实模型选择变化；上述正文证明序列化形式，不是预先知道真实模型将选哪些工具。
每条出站正文的原始 bytes/hash 都在账本中，供真实阶段继续沿用审计模式。

## 已实现的预算与协议边界

`journal.py` 使用私有 SQLite 文件与 FULL 同步事务：

- plan hash、绝对账本路径、case/source/code/dependency 哈希绑定。复制/移动账本不能当作新账本继续使用。
- 每个 arm 只能领取一次执行 token；同臂启动第二个执行器被拒绝。
- 每次调用先提交 `reserved` 与原始出站正文，再允许 transport。原始响应先提交为 `raw_received`，
  然后验证原始整数 usage/model/总 token 一致性，再结算到 `settled`。
- 费用用整数 micro-CNY，避免浮点累计；已结算按输入全 miss 高峰价计算保守上界。
- 超时、HTTP 302/429/500、断流、无有效 usage、未知 model、进程退出、落盘失败均停止后续调用；
  未知调用保留完整预留，不作退款或自动重试。重启仍能检查状态，但不能自动接着发请求。
- 已知 usage 结算后若工具协议解析失败，保留已知结算费用并 halt，不伪装成零费用。
- SDK 侧最后一次请求/源码额度耗尽时仅提供并强制选择 finish；门限外工具调用被拒绝。
  请求正文自身超过上限时明确失败，不冒充已终答。

旧 `public_authorization.py` 同样具有成熟的先预留、原始回包留存与未知结果停止机制，但它与
GraphLocalizer source manifest/授权策略强绑定。本次实现独立 SDK 策略，没有复用旧 grant/金额/模型别名。
SQLite 是本机预算持久层，不是供应商账户级消费限额，也不能实现网络端 exactly-once。

`deepseek_wire.py` 使用 OpenHands 官方 Message 序列化再收敛到文字 Chat Completions 字段：
禁用 thinking、stream、重试和重定向；不发送图片、推理内容、任意 endpoint/model 或 SDK 私有字段。
工具调用与结果必须一一配对，拒绝孤立/重复结果；JSON 重复 key、非有限数、非整数 usage 拒绝。
不启用 DeepSeek strict beta，因为当前 SDK Schema 含非 beta 专用约束；本地依然严格校验参数。
依据：[官方 Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、
[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 实际离线验证

- [最终 SDK/预算套件](verification/preparation-tests-final.log)：**25/25**，含原 SDK 7 项和新增 18 项。
  包括并发预留、真实子进程在提交后退出、落盘失败、断流保留前缀、HTTP 错误、损坏/复制账本、
  错误 model/usage/cache 分项、坏 JSON 工具参数、8 次最大 usage 的金额上界和真实调用入口拒绝。
- [双组完整预算仿真](verification/deepseek-preparation-v1/budget-summary.json)：两个独立 SDK 进程，
  真 LocAgent 检索在独立旧环境运行；各 2 次模拟 HTTP 回包，共 4 条 settled，未结算预留为 0。
- 模拟 usage 固定为每次输入 1000/输出 100；账本 0.0112 元是**模拟核算量**，不是真实费用或预计费用。
  真实模型调用、真实费用和父进程网络尝试均为 0；成功的检索子进程也通过离线网络断言。
- 初轮 15 个新增测试因 macOS `/var`→`/private/var` 临时路径别名被 canonical 校验拒绝；只把
  测试夹具路径 resolve，未放宽生产路径校验。失败日志 `verification/preparation-tests-v1.log` 保留。

复现一套新的预算仿真（输出目录必须不存在）：

```sh
.venv-openhands/bin/python -B -m readonly_agent.prepare_run \
  --case examples/case.json --output verification/new-deepseek-preparation \
  --locagent-python /Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python \
  --locagent-root /Users/xiaomu/Documents/Codex/locagent-demo-20261108
.venv-openhands/bin/python -B -m unittest discover -s tests_sdk -v
```

## 后续完成的真实调用入口

旧 `deepseek_wire.exchange_live()` 兼容入口仍无条件拒绝；新的 `live_transport.exchange_live()`
只接受明确启用标记、有效 Admission 与已落盘的一次性请求票据。`BudgetedWire` 仅接受仿真账本。
proposal 继续保留 `authorization=not_granted`、`account_pricing_confirmed=false`，批准记录独立存放；
本轮没有创建可启动此方案的真实 grant。

新的批准记录已实现 plan hash、消费一次标记、24 小时有效期、固定账本路径绑定；
真实 transport 已实现固定官方 endpoint、禁重试/禁代理继承/禁重定向。
仍须用户批准和账户价格确认，再由用户在本地终端隐藏输入密钥；当前只接受返回 model 为 deepseek-flash，如果供应商
实际返回另一个标识，应停止并人工核实，不能悄悄放宽 allowlist 或再次请求。

真实供应商响应尚未验证。不能把仿真账本当作已经获准的真实付费预算。
先做此小样例协议验收，再考虑接回现有页面。
