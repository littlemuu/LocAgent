# SQLGlot 单题一次性授权接线：离线准备结果

2026-11-14。当前环境已恢复。本轮真实模型请求、真实传输及实际费用均为 0；没有读取实际密钥或 `.env`、对外发送数据或执行目标仓库代码。

## 完成状态

新增 `experiments/cohort_admission/`，保留此前 cohort_preflight、eval_preflight、v4 引擎、harness、索引、gold 和历史结果。最新冻结材料在 `verification/cohort-admission-v2/`；较早 v1 冻结与模拟也保留，因后续父进程存活保护和请求统计修复，v1 代码绑定已过期，不应启动。

最新方案 digest：
`8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585`

- 冻结 41 个适配器 Python 文件，并沿用既有 runtime、SDK 依赖锁和 v4 引擎校验；绑定唯一 case、题面哈希、源码快照、实体索引、正文索引与证明文件。
- 真实路径要求新的 `CohortAuthority` 和精确方案授权；旧通用或旧比较授权不能接入。继承 24 小时有效期、精确账户价格上限确认、一次领取、固定账本路径、每次请求前校验与持久化预留。方案文件本身不是授权；其 capability 字段不代表用户已批准。
- 演练使用独立票据类型与 `rehearsal.json`，不生成生产 `grant.json`，真实传输函数直接拒绝演练票据；演练仅接受 MockTransport，不接受密钥。模拟账本保留 simulation 标记。
- 原生与 SDK 入口已接到同一费用账本和共有请求契约。正常 finish、未知/截断响应、超时、待结算请求、重复领取和重复启动均有离线验证；异常停止，不补跑。子进程每次请求前核对父进程仍存在。
- 实际启动传输数与持久化预留请求数分列。启动传输也不证明供应商一定收到请求；真实账单和是否收到响应仍须运行时核验，不能用预留条数冒充实际调用数。
- 不提供会自动找密钥、读取环境或批准运行的 CLI。CLI 仅能 `--rehearse`；真实接线为 `run_pair(plan_path, admission, key=...)`，需在用户批准并完成账户核价后，由已验证的本地启动步骤传入凭据。此轮没有读取或集成现有 `.env`。

## 测试与模拟

新增 14 项回归通过；另复验 3 项既有授权回归（价格/明确同意、24 小时过期及代码/路径变化、一次传输票据），共 17 项通过。生产桥接的单元测试在临时目录使用明确的合成字符串与替换后的传输子进程；临时测试授权随目录清理，不是项目真实授权，未发网络请求。

初次新增回归有两处测试响应遗漏 `model/id`，被现有 usage 校验正确拒绝；补全合成响应后通过，未放宽生产协议。

最新冻结版本在 SQLGlot3417 上完成原生、SDK 两组，4+4 共 8 次模拟响应、0 次真实传输。原生正文回退实际触发，两组第四次请求只提供 finish，均成功收尾。第一轮 v1 的 8 次模拟也保留，因此本轮成对端到端模拟共 16 次；单位测试的合成响应另计。脚本响应不代表模型自主选择或定位质量。

复现回归：

```sh
.venv-openhands/bin/python -B -m unittest discover -s tests -p test_cohort_admission.py
.venv-openhands/bin/python -B -m unittest tests_sdk.test_live.LiveTests.test_expiry_changed_runtime_engine_and_copied_grant_block tests_sdk.test_live.LiveTests.test_exact_consent_hash_and_account_prices_required tests_sdk.test_live.LiveTests.test_specific_ticket_consumed_once_before_helper
```

已经存在的冻结目录、演练票据和结果不能覆盖或重复启动；后续开发须另建隔离版本。证据见 `verification/cohort-admission-v2/final-verification.json` 及 `rehearsal-authority/run/`。

## 语义、曝光及公平性边界

复核本工作区 21 个历史账本哈希，全部未变；未增加真实模型曝光。已知仓库曝光仍为 96 题，未确认 34 题；更早外部工作区运行清单仍未穷尽，未查数量未知。

本轮没有新增人工语义审查，已有暂缓与带提示题状态继续保留；当前版本人工初查 6/130、未查 124、独立第二评审 0。正式计分准入仍为 0；历史排除 1、开发控制 1、人工暂缓 2、待最终审查 126。未审样本没有自动转为通过，gold 未改。

两组准确名称仍为“LocAgent 图工具 + physical-line80 正文 BM25（适配版）”和“OpenHands 基础文件工具 + 实体 ID BM25（适配版）”。固定物理行后端不是原版 EpicSplitter；提示、工具和检索行为不同，因此这是适配系统比较，不能直接归因检索增益。SQLGlot3417 已曝光，本次仅验证接入，不是独立评测。

## 待用户批准的具体范围

建议仅运行已曝光开发题 **tobymao__sqlglot-3417** 的两组对照：

- API：`https://api.deepseek.com/chat/completions`；锁定请求模型字符串 `deepseek-flash`，温度 0、thinking disabled、每次最多 2,048 输出 token。历史 family 名称只是旧记录，本轮未联网确认当前底层版本。
- 每组最多 4 次、总计最多 **8 次请求**；总上限 **17 元人民币**，不自动重试或追加额度。每组累计最多 16 次调查工具、14,336 字节工具证据，每页 4,096 字节，完整序列化请求最多 65,536 字节。最后请求只允许 finish。
- 发给 DeepSeek：题面、系统/任务提示、工具定义、该题工具选取的源码证据及本组会话。不发送 gold、参考补丁、审查结论、其他题或环境文件。审查产物不进入运行器。
- 现有账本采用输入 2、输出 8 元/百万 token 的历史保守价格上限；每次预留 2.113536 元，8 次总预留 16.908288 元。这是最坏预留，不是预计费用或当前报价。本轮未联网核价，也未访问账户。
- 启动前仍需核验账户当前适用价格与附加费用在该假设内，并取得对数据范围、模型、次数和预算的明确批准。随后才记录一次性授权，核对旧版本没有在运行，安全提供本机凭据；价格或冻结材料不符则停止。

目前代码的真实接线已离线验收；尚无项目真实授权，也没有可直接执行的现成带凭据命令。不应复用旧试跑命令或旧批准来启动。若后续增加本地 `.env` 启动包装器，必须将其纳入新的代码冻结和离线校验。

## 开发日志状态

环境恢复后及工作结束前均检查了原项目日志：此前完整日志条目出现次数为 0，成功回执不存在。本轮只尝试追加一次，自动权限审核再次超时；没有再试，也没有宣称已写入。

上一轮日志条目保留在 `verification/cohort-preflight-v1/development-log-entry.md`，本轮条目保留在 `verification/cohort-admission-v2/development-log-entry.md`。后续恢复权限时应先再查条目是否存在，仅追加缺失内容，防止重复。

Python 网络阻断不是 OS 级沙箱；此次仅静态读取/解析目标源码。现有日志写入阻碍属于自动审核超时，不是对操作风险的否定判定。
