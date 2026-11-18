# 默认锁定的 OpenHands + DeepSeek 首次调用

**最新状态：修复版真实双组试跑已完成，授权已消费。** 两组各 3 次请求、终答成功，
费用上界 ¥0.019130，无未知预留；模型未调用 LocAgent 检索。见 [验收结果](LIVE_PILOT_RESULT.md)。
下文为历史记录，请勿重复执行历史命令。

**最新状态：首次试跑已停止。** 基础组 3 次请求均结算，费用上界 ¥0.008236；
终答协议不匹配导致失败，检索组未启动。已修复并通过 72 项离线测试，未发起后续付费请求。
**不要再执行本文历史 authorize/run 命令**：原授权已消费，修复版本尚未授权。
详细原因、证据与修复方案见 [首次调用诊断](FIRST_LIVE_FAILURE.md)。

**用户批准后的进展（2026-11-12）：** 已收到对本方案的一次试跑批准，并从当前登录的 DeepSeek
账户确认 CNY 币种及其“产品定价”链接对应的 ¥2/¥8 高峰单价；已创建 24 小时一次性 grant，
尚未领取/启动。当前余额显示 ¥2.86，未充值。仍需本地终端隐藏输入属于该账户的 key。
本方案无需再次执行下方 authorize 命令，直接执行步骤 3；记录见
[批准后启动检查](verification/APPROVED_PREFLIGHT.json)。以下准备阶段结果保持原样。

2026-11-12 UTC。真实传输与一次性授权入口已实现并完成离线验收；**未创建本方案授权、未读取或保存真实密钥、付费请求 0 次**。
只在临时测试目录创建过使用假密钥的测试授权，已随夹具清理。

## 冻结范围

方案 SHA256：`7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f`

- SDK：OpenHands Software Agent SDK 1.62.0；源码、依赖 lock、LocAgent 行为文件、系统提示、题面和样例源码均绑定哈希。
- 模型：`deepseek-flash`；固定官方 `https://api.deepseek.com/chat/completions`；非思考、非流式、temperature=0、max_tokens=1024。
- 数据：自写 `examples/source/src/greeting.py`，题面 `Locate the function that constructs the greeting.`。
- 两个独立子进程依次运行基础组/检索组。每组最多 4 次模型请求，共最多 **8 次**；任一组失败立即停止整个配对，不补跑。
- 发送系统提示、题面、工具定义、模型工具调用与对应的源码工具结果；基础组 list/search/read/finish，检索组仅多 LocAgent 检索。
- 每组调查工具最多 16 次，序列化源码结果累计 ≤14336 字节、单页 ≤4096 字节；单个出站 JSON ≤65536 字节，原始响应 ≤65536 字节。
- 不发送评分标注、patch、hints、历史答案或整个图索引；不执行目标源码，不开放 shell、编辑、MCP、网页搜索、记忆或子代理。

[冻结 proposal](verification/deepseek-preparation-v2/proposal.json)；
[基础组模拟出站正文](verification/deepseek-preparation-v2/baseline/wire-requests.json)；
[检索组模拟出站正文](verification/deepseek-preparation-v2/retrieval/wire-requests.json)。
模型实际选择的工具和后续请求会变化，上述正文是序列化证据。

## 价格与预算

2026-11-12 再次核实[官方中文价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：
`deepseek-flash` 当前对应 DeepSeek-V4.1-Flash-1017；高峰输入缓存未命中 ¥2/百万 tokens，输出 ¥8/百万 tokens。
忽略缓存及空闲优惠，以 1,048,576 输入 + 1024 输出预留：

`单次 ¥2.105344 × 8 = ¥16.842752 < 批准上限 ¥17.00`

这是按公开价格计算的保守上界，不是预估费用或供应商账户级硬限额。
用户必须确认账户人民币计价、包含附加费用后的价格不超过 ¥2/¥8；否则不能使用此授权。
没有读取余额、账户信息或密钥，价格变化/账户差异无法在本地账本内自行核实。

## 入口与故障行为

- `authority.py`：完整方案 hash + 精确同意文字 + 账户价格声明；授权 24 小时有效。批准目录、领取票据均排他创建，不能重复消费。
- `journal.py`：固定绝对路径的私有 SQLite；FULL 事务先预留，随后单独提交传输票据，再允许启动网络 helper。每个票据只允许一次传输。
- `live_session.py`：实际 SDK 消息 → 预算 → HTTP → 原始回包落盘 → 原始 usage 验证 → SDK 消息；仿真会话不能使用真实账本。
- `live_transport.py` / `transport_worker.py`：固定官方 HTTPS POST；不继承代理、凭据环境，不重定向、不自动重试。单次 HTTP 等待 55 秒，helper 总时限 60 秒；每组进程总时限 360 秒。
- `live_run.py`：先验证授权、快照与本地终端，再隐藏输入密钥，或显式通过 `--env-api-key` 读取已有私有 `.env`（见 [最新配置说明](LOCAL_ENV.md)）。不接受环境变量或命令行中的 Key 值。密钥仅在内存和匿名管道传递给 HTTP helper，用于 Authorization 请求头，不进入 SDK 配置或账本。
- SDK 自身网络仍由 Python guard 拒绝，唯一出站通路为独立的已授权 HTTP helper。父进程保留管道，每次调用前检查其存活；取消/超时清理当前组及后代。
- HTTP 错误、超时、断流、使用量不可信或落盘失败均停机。可能已发送的请求保留完整预留；进程重启不能再次消费授权。已有效结算但终答格式错误，也停止后续请求，保留已知费用。
- 第四次请求只提供 finish，并强制工具选择；返回 model 不等于 `deepseek-flash` 或不符合协议，停止人工复核，不自动扩大模型白名单。

这些约束防止正常程序崩溃/重启造成重复计费，不防恶意本机账户所有者修改代码或删改授权。
Python guard 不是 OS 沙箱；网络端 exactly-once、供应商扣费和 SDK/模型真实兼容性尚未验收。
日志中的 SDK 原生费用不是结算依据；账本的 `spent_upper_micro_cny` / `reserved_micro_cny` 才是预算依据。

## 离线验收

- [SDK、预算和授权测试](verification/live-tests-final.log)：40/40；其中新增 15 项涵盖默认锁定、精确批准、授权过期/变更、重复领取、复制路径、单次传输、父进程退出、超时、落盘失败、敏感回包拦截、真实 SDK 四轮收尾及 helper 断流。
- [核心和真实 LocAgent 回归](verification/core-regression-live.log)：26/26。共 **66/66**。
- [双组完整回放](verification/deepseek-preparation-v2.log)：两个隔离 SDK 进程，各 2 次模拟 HTTP，4 条 settled；真实 LocAgent 检索成功；预留余额 0、网络尝试 0、付费请求 0。
- 新 live SDK 路径测试将 helper 替换为内存模拟响应；helper HTTP 测试仅使用 MockTransport。未创建真实 HTTP 连接。测试中的 `live_calls` 是被模拟的 live 分支调用计数，不能当作实际供应商请求。
- 仿真账本 ¥0.0112 是固定虚构 usage 的核算结果，**不是实扣或预估**。不提供模型效果结论。
- 初轮 6 项失败原因：授权开始/结束时间分别取值导致有效期略大于 24 小时；已改为一次取值，保留 `verification/live-tests-v1.log`，未放宽期限校验。

## 用户下一步操作

1. 审阅上述方案，确认人民币账户全包单价 ≤¥2/¥8，同意该 hash、8 次上限及 ¥17 总上限。旧实验授权不会继承。
2. 在项目目录的本地终端记录授权（**仅在明确批准后执行**）：

```sh
.venv-openhands/bin/python -B -m readonly_agent.live_run authorize \
  --plan-hash 7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f \
  --consent 'APPROVE 7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f CNY 17' \
  --currency CNY --input-ceiling 2 --output-ceiling 8 --all-charges-included
```

3. 同一终端运行，按隐藏提示输入 key；不要粘贴到聊天、命令行或文件：

```sh
.venv-openhands/bin/python -B -m readonly_agent.live_run run \
  --plan-hash 7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f \
  --live --prompt-api-key
```

4. 输出位于 `authority/<hash>/run/`，包括固定账本、分组轨迹/结果和日志。可用 `live_run status --plan-hash <hash>` 只读检查。
   若异常，保留目录并人工核对，不删票据、不重试。授权过期/代码或源数据改变时先重新审阅方案。

不需要再次改安全设置或代码来解锁此范围。若通过受限自动化环境启动，仍须遵守该环境的网络执行审批；本轮没有尝试此操作。
真实回包验收后再接页面；前后端复用建议见 [接入审查](FRONTEND_BACKEND_INTEGRATION.md)，本轮没有修改现有服务或页面。
