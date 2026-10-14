# 公开仓库：默认关闭的单题操作员授权

本阶段增加真实 provider 的受控执行入口，**本轮测试全部使用 stub，没有真实模型调用、真实凭据或真实费用**。
`github-v1` 不带 `authorization_id` 时，仍走原来的 fake 闭环；fake 的最终定位列表固定为空。
新入口提供执行机制，不代表已经验证任何模型供应商兼容性或定位质量。仍不适合公开部署。

## 执行与授权分开

1. 先通过原公开仓库 fake 流程固定 commit、构建索引，取得该问题的 `prepared-*` manifest。
2. 操作员在本机审核问题、仓库 commit、接收方 endpoint、模型、价格上限和预算。
3. `public_authorization plan` 从该 manifest 派生精确执行清单，写出可审阅计划；这一步不授予调用权限。
4. `authorize --expected-sha256` 校验完整计划哈希后，一次性创建独立授权目录和新账本。
5. API 与 worker 都必须有显式 `LOCAGENT_PUBLIC_LIVE=1`，并通过同一份授权验证；仅有环境开关也不足以发包。
6. HTTP 只引用 `authorization_id`，必须提供计划里的完整 40 位 commit、完全一致的问题、迭代选项及 `max_attempts=1`。
   API 返回普通任务 ID；执行复用已准备的不可变索引，不重新追踪 ref 或下载移动版本。

HTTP 不能提交 `allow_paid`、provider、model、endpoint、价格、账本路径或密钥。
这些额外字段仍返回 422。`LOCAGENT_ALLOW_PAID=1` 也不能开启这个新入口。
旧 prepared 入口继续使用原有固定授权策略；新代码不初始化、不重置、不复制旧预算。

## 可信计划与独立存储

代码：`locagent_service/public_authorization.py`。

`LOCAGENT_PUBLIC_AUTH_ROOT` 必须是显式绝对 canonical 路径、当前 UID 所有的 0700 私有目录，
与 source/cache 根不能相互嵌套。授权文件和账本要求当前 UID 所有、无组/其他用户权限。
计划包含并绑定：

- 完整 source manifest 哈希，因此绑定 repo、commit、原问题、索引文件和完整 engine 哈希闭包。
- 请求问题哈希、完整 commit、迭代次数、重复抑制选项。
- 精确 HTTPS endpoint、wire model、允许的响应模型名；不从 HTTP 或模型输出读取接收方。
- 凭据环境变量**名称**，不保存凭据内容；不会读取 `.env` 或 runtime 文件。
- 币种、all-in 输入/输出 peak price、完整供应商 context 上限、每次 output token 上限、总预算、总调用上限。
- 请求字节上限、socket timeout、操作员价格确认文字，以及绝对授权根目录。

操作员必须核实 context 上限和价格覆盖供应商实际全部收费；本实现不会自动查价、换汇或核验账单。
这些是可信配置假设，不是模型自报 usage 就能保证的外部账单上限。

同计划哈希目录通过排他创建消费授权；创建中断也留下墓碑，不允许重新 authorize 来重置。
计划绑定根目录，复制到另一目录不能取得同计划的新额度。首次执行在账本锁内永久绑定 task ID 和 claim token；
第二个 executor（包括同任务的重启）不能重新绑定。需要另一次实验时必须重新人工审核新计划，不能清空旧目录。
这些保证依赖可信本机操作员；不防拥有相同 UID 的恶意程序篡改或删除授权文件。

## 预算与结果不明

复用已有 `budget.ledger_lock`、原子 fsync 写入及 `response_store` 有界不可变原始响应文件。
不复用旧计划哈希、价格、model、授权 marker 或 ledger。

每次调用在同一个稳定文件锁下执行：

1. 重验授权、完整 manifest、当前账本、调用数和此前原始响应证据。
2. 检查可容纳一个最大 8 MiB 原始响应；总原始响应存储上限 32 MiB。
3. 计算 `完整 context × 输入 peak price + 输出上限 × 输出 peak price` 的满额预留。
   已结算上界 + 未结算满额预留 + 新预留不得超过本次预算。
4. 先持久化 reservation 和独立 inflight guard，再同步写受数据库 claim/lease/deadline fencing 保护的 progress。
5. 紧接着执行一次 POST；没有重试、重定向、代理、fallback 或并行 completion。
6. 先保存原始响应 bytes，再严格解析原始 JSON、整数 usage、usage 总和、模型和配置上限，最后规范化响应和结算。

输入 token 全部按批准的 peak price 计价，不使用缓存折扣来扩大额度；金额使用精确 Decimal 和固定小数格式。
只有成功且完整的 200 响应、有效原始证据和 usage 才会释放未使用预留。
断连、超时、非 200、响应超限、无效 usage、落盘失败均保留满额并停止该授权；已收到的响应片段也尽量保存。
任何恢复不自动退款、不自动认定“没有消费”、不自动重放。

`replay_safe` 统一控制 store recovery / interrupt / retry 和 worker 失败分支：

| 路径 | 运行中取消、失联、超时、崩溃 |
| --- | --- |
| demo-v1、未授权 github-v1 | 保留原来安全的 fake 重试策略 |
| 带授权 github-v1 | `needs_review` / `outcome_unknown`，不可自动或手动 retry |
| 旧 prepared | 保留原来的保守恢复策略；本轮不改变其取消语义 |

尚未开始执行的 queued 授权任务取消后为 `cancelled`，无模型调用。
运行中取消与 POST 间不可消除最后一小段竞态，因此即使本次可能未发出请求，也保守标记 `needs_review`。
若 provider 已结算而数据库最终结果尚未提交就崩溃，也不会重放；操作员应结合 attempt history、progress 和新账本审阅。

## 未来经确认后才使用的操作命令

本轮没有执行以下真实授权/真实执行操作。先由父对话明确确认单题、数据接收方、模型和预算；
用最终冻结代码重新生成 source，因为 engine 哈希不会豁免新模块。

```sh
# 沿用隔离 public_preview_ schema 和独立 source root；不指向学习 demo。
export LOCAGENT_PUBLIC_AUTH_ROOT=/absolute/private/separate/authorization-root
export LOCAGENT_PUBLIC_LIVE=0

"$PYTHON" -B -m locagent_service.public_authorization plan \
  --source prepared-<reviewed-source-hash> \
  --provider-config /absolute/operator-provider-config.json \
  --output /absolute/new-reviewed-plan.json

# 仅操作员确认后，以所审阅文件的精确哈希授权；命令本身不打开 LIVE。
"$PYTHON" -B -m locagent_service.public_authorization authorize \
  --plan /absolute/new-reviewed-plan.json --expected-sha256 <reviewed-plan-sha256>
```

provider config 的字段及严格上界见 `ProviderConfig`；离线示例见 `tests/test_public_authorization.py:CONFIG`，
其中 `provider.example`、价格、credential 环境变量名全是测试值，不能作为任何真实供应商的配置。
真实 transport 只在发包前读取操作员指定的凭据环境变量。不要把密钥写进 HTTP、计划或版本库。
该层目前只实现非流式 OpenAI-compatible chat completions；供应商特有协议/计费、真实连通性和模型效果未验收。

## 诊断与安全限制

查询原有任务 API 即可得到 `provider=operator-authorized`、authorization ID、source ID、commit、stage 和 diagnostic ID。
阶段包括 `authorizing`、`reserving`、`provider_inflight`、`settled`；以数据库 task status 为最终状态，不能只凭阶段判断成功。
日志不记录异常原文、请求内容、凭据或原始响应；原始响应留在私有授权目录供操作员审阅。

provider transport 只接受审核过的 public HTTPS endpoint，DNS 必须是 global unicast，连接固定已核验 IP，
TLS 验证原 hostname，不跟随重定向或继承代理。socket timeout 不是整体硬时限；worker deadline 负责整个 attempt。
离线导入 guard、Python 子进程和 RLIMIT 不是完整安全沙箱。解析器隔离、同 UID 文件访问、总缓存配额、
用户鉴权和公网 admission 控制仍是未实现项；详细限制沿用 `PUBLIC_REPOSITORY_PREVIEW.md`。

## 本阶段独立审查

独立 reviewer 只读检查了实现和调用链，发现并修复：

1. 极小合法金额被 Decimal 科学计数格式误拒绝：内部金额改为固定小数与足够精度，增加低价/高精度 provider stub 结算测试。
2. 断连导致已收 bytes 丢失：改为有界分段读取，保留 partial bytes，并检查 Content-Length；增加 mock HTTP 截断测试。

修复后的只读复核未发现本轮范围内的可复现阻塞。最终测试数字、命令及日志见验收记录；
没有执行真实付费 smoke，也没有宣称任何模型供应商已经验证可用。
