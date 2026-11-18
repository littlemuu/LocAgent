# 跨文件样例：观察真实模型是否自主选择 LocAgent

**最新结果：真实试跑已停止，检索组未启动。** 基础组第 4 次指定 finish 的请求返回越界 read_file，
本地拒绝；4 次费用均结算、上界 ¥0.018574，没有补跑。原授权已消费，不要重跑命令。
见 [真实结果诊断](CROSSFILE_LIVE_RESULT.md)。以下为准备和批准过程记录。

**后续状态：用户已批准该方案，grant 已记录，尚未领取或启动。**
等待本机终端隐藏输入同一人民币账户 Key，保持自主选择、不强制或补跑。
见 [批准后启动检查](verification/CROSSFILE_APPROVED_PREFLIGHT.json)。下文为准备阶段记录。

2026-11-12，北京时间。只完成离线准备；未读取密钥、未创建新 grant、未发起付费请求。
旧失败轮和已完成真实试跑的账本哈希均核对未变。

## 具体题目和范围

自写 `examples/crossfile/source/dispatch/`，10 个 Python 文件，共 2710 字节。
入口、标识生成、worker、HTTP 请求、重试策略、回执存储、退避和报表/清理分散在不同文件；
不执行待理解源码，只做静态图构建与只读工具调用。

问题中文释义：一次 webhook 投递收到暂时性 HTTP 错误后被重试。解释原投递 ID 如何保留、
哪些响应状态和重试次数允许继续、已确认投递在哪里被拦截；跨文件追踪相关函数并说明防重机制的局限。

实际发送的英文题面：

> A queued webhook delivery receives a transient HTTP failure and is retried. Explain how the original delivery identifier is preserved, which responses and attempt counts permit another retry, and where a previously acknowledged delivery is prevented from being sent again. Trace the relevant functions across files, cite source evidence, and state limits of the duplicate protection. Do not modify or execute the source.

题面不指定 LocAgent、查询词、答案路径或“必须检索”；系统提示和工具描述不针对本题添加强制检索指令。
保留基础组作为同流程工具可用性对照，两组同题、同源、同提示和同额度；本轮不做效果排名。
样例很小，基础工具也能完成任务；不能保证模型会选检索，不通过削弱基础工具制造优势。

当前 LocAgent 索引的是文件/实体标识的 BM25，并支持精确实体读取，不是代码正文语义检索或完整图遍历。
本题的跨模块 retry/delivery/receipt 概念适合检验该工具是否被选择，但它只是开发样例，不代表真实仓库分布。

## 可复核的观察链

新审计器 `experiments/retrieval_choice/audit.py` 只读 SQLite 与 SDK 轨迹，逐次核对：

1. 该次出站请求确实提供 locagent_retrieve，记录原始 tool_choice。
2. 原始模型回包给出的 call ID、query/offset 与 SDK ActionEvent 一致。
3. ObservationEvent 对应同一 action/call ID，非错误且有带路径/行号的源码检索结果。
4. **紧接着的模型请求正文**含同 call ID 的 tool 消息，正文与 SDK observation 字节一致；记录内容哈希与大小。
5. 最终结果 completed/finished，并存在匹配的 SDK 原生 FinishAction / ObservationEvent。

审计器同时核对账本请求/响应哈希、方案哈希、SDK contract 的源码/提示/预算/代码绑定。
结果中的路径交集只说明答案提及检索返回的文件，不能证明模型依赖了证据或检索提高了效果。
分页未完会单独标出，不把一页当成完整结果。

## 三种结果严格分开

| 模式 | 选择方式 | 能说明什么 |
|---|---|---|
| 已完成的离线连通性验证 | 预先编排的模拟响应调用检索；HTTP 使用 MockTransport | 实际 LocAgent 执行、证据进入 SDK/下轮请求、正常终答链路可工作 |
| 拟申请的真实自主选择试跑 | 调查阶段 tool_choice=auto，基础工具保留，不要求使用检索 | 模型在该题、提示和工具集合下是否自行选择检索 |
| 强制调用诊断 | 如果将来使用指定 function 的 tool_choice 或提示中强制检索，须单列 | 只能说明真实模型/工具接口连通，不能算自主选择；本方案不包含该付费控制组 |

**即使离线请求中 tool_choice=auto，脚本安排的检索也不是自主行为。** 审计器将它标为 scripted_fixture。
真实请求若被强制工具策略控制，会标为 live_forced_tool_policy，不计入 live_auto_selection_observed。
调查预算关闭时只强制 finish，这不强制检索。
若真实自主组完全没调用检索，记录 not_selected；不自动改提示、换题、强制调用或补跑。

## 已完成的免费验收

- [检索观察链](verification/crossfile-choice-v2/retrieval-observability.json)：脚本请求 1 调用 `locagent_retrieve(query="retry")`，真实 LocAgent 返回 1642 字节正文、无需分页；同一 call ID 的正文完整进入请求 2，随后正常 finish。
- [双组回放](verification/crossfile-choice-v2.log)：两个隔离 SDK 进程，各 3 次模拟 HTTP；基础组与检索组均 completed，真实网络尝试/付费调用均为 0。
- [新增可观察性与样例选择测试](verification/retrieval-observability-tests-final.log)：10/10。
- [SDK/预算/授权回归](verification/crossfile-sdk-regression.log)：46/46。此前 26 项核心/LocAgent 回归记录保留，本轮未重复计为新执行测试。
- [上一轮真实结果的审计复核](verification/previous-live-retrieval-observability.json)：提供了检索工具、正常终答，但 retrieval_calls=0、outcome=not_selected，未将其误算为检索成功。
- 已增加固定 `--case crossfile` 入口；只允许 greeting/crossfile 两个具名样例。选错样例会在读取 Key 或消费 grant 前拒绝。
  case JSON 中的 scripts/预编排终答仅供离线回放，真实路径不会把它们放入模型上下文。

## 下一次真实试跑的精确提案（未授权）

方案 hash：`7295139e58ac88d2d500f50e7b8c0fcafca1d9d9df5b4d114dc8d1a0b8b56a2a`

| 项目 | 固定内容 |
|---|---|
| 源码与题目 | 本页的 10 文件 webhook 样例与英文题面；见冻结源码哈希 |
| 底座/模型 | OpenHands SDK 1.62.0；deepseek-flash，官方当前别名对应 DeepSeek-V4.1-Flash-1017 |
| 请求 | 官方 Chat Completions；非思考、非流式、temperature=0；每次 max_tokens=1024 |
| 分组 | baseline 基础组；retrieval 增加 LocAgent 工具的自主选择组；新进程、新会话、顺序执行 |
| 请求数 | 每组最多 4 次，总共最多 8 次；失败停机，不自动重试 |
| 工具/上下文 | 每组最多 16 次调查调用；源码结果累计 14336 字节、单页 4096 字节、单次出站 JSON 65536 字节 |
| 费用 | 每次保守预留 ¥2.105344，8 次 ¥16.842752；独立新授权上限 **¥17** |
| 发送内容 | 通用只读系统提示、题面、工具 schema、已有模型调用及工具返回的这 10 文件中的路径/源码证据 |
| 不发送 | 开发日志、审核说明、离线脚本/预编排答案、旧模型答案、gold/patch/hints、索引整体、账户配置 |

价格再次核对[官方价目表](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：
高峰输入缓存未命中 ¥2/百万 tokens，输出 ¥8/百万；以 1,048,576 输入 + 1024 输出预留，忽略折扣。
这是保守上界，不是预计实扣。获准启动时仍须确认同一人民币账户及适用价格，并在本地隐藏输入 Key。
旧授权已消费，不覆盖此题；本轮未创建新的授权。

[冻结 proposal](verification/crossfile-choice-v2/proposal.json) ·
[准备汇总](verification/crossfile-choice-v2/readiness.json) ·
[精确模拟出站内容](verification/crossfile-choice-v2/retrieval/wire-requests.json)。

只查看最新方案，无网络、无 Key 读取：

```sh
.venv-openhands/bin/python -B -m readonly_agent.live_run proposal --case crossfile
```

后续只有在用户批准上述 hash 和范围后，才记录一次性授权，并以 `run --case crossfile` 启动。
当前没有阻碍离线准备的权限问题；剩余步骤是用户批准、账户价格确认与本地 Key 输入。
本阶段没有修改前后端、SDK 工具表述或检索实现；没有性能收益结论。
