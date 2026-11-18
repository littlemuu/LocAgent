# SQLGlot：修复 read_file 后的单题开发验证（准备完成，未授权运行）

2026-11-13。已冻结单题入口并完成免费离线验收；本轮真实模型请求 **0**、费用 **0**，没有加载凭据或创建生产授权，没有执行 SQLGlot 仓库代码。

## 固定范围

- 题目：`tobymao__sqlglot-3417`，SET TAG 含点号的标识符被解析为 Command；原题 1,386 字符，内容不改。
- 源码提交：`e1b6483d5e26d556f6a3dd82c6d35f475c189c2b`。沿用已验证的完整提交树（325 文件）及只读工具可见的 147 个 Python 文件（2,791,727 bytes），不扩大来源。
- 框架：OpenHands Software Agent SDK **1.62.0**；模型请求名 **`deepseek-flash`**，直连 `https://api.deepseek.com/chat/completions`。温度 0，显式关闭思考，每次输出最多 2,048 tokens。
- 两组使用相同源码、题面、SDK 循环、共享提示和修复后的 `search_text` / `read_file` / `finish`。仅检索组额外开放 `locagent_retrieve`，工具选择仍为 auto，不强制检索或续页。保持原 SQLGlot 顺序：检索可用组 → 基础组；会话、工具状态、证据预算独立。
- 每组最多 4 次请求（最多 3 次调查，保留 1 次仅 finish 的收尾机会）、16 次工具调用、14,336 bytes 累计源码证据；每页完整 JSON 最多 4,096 bytes，请求/原始回包各最多 65,536 bytes。提前 finish 则不会补足次数。
- 两组共最多 **8 次请求、17 元人民币**。没有重试、自动补跑或恢复执行。任一组失败即停止，后续组保留 not_run。

只将执行范围从两题缩为 SQLGlot 一题，单题子计划逐项等于共用读取修复后的 v5 SQLGlot 计划；工具说明、检索策略及其他配置均未改。

## 冻结与隔离

新方案：`sqlglot_read_validation/v1/manifest.json`。

```
df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277
```

来源清单 v5：`6d742955688ac21b2405cfea1f0cc1807560333e61aa72053ee6ab87c1cc9b79`。
旧两题准备版 hash 仍为 `1286c563b5825f3ff56ee1b992f0502f4152311eb1430e5e465941b5d3202bd6`，未被覆盖。
新入口 `experiments.sqlglot_validation.live`、未来独立账本目录 `authority-sqlglot-validation`；该目录当前不存在，旧授权不能转用。冻结绑定来源、子计划、执行器、驱动与评分代码；改动后须重新冻结，不能继续使用旧 hash。

## 发送内容与验收

发给 DeepSeek：原始题面、系统/预算/收尾提示、当组工具定义、模型所选工具返回的固定源码片段与元数据，以及该组本题会话历史。不会预先把所有源码一次性发送；多轮请求可能重复携带已有证据。评分标签、参考补丁、参考函数及行号、离线测试脚本和其他组历史不进入模型上下文。Key 只用于授权后的 HTTPS 身份验证，不进入模型提示、日志或聊天。

观察标准在运行前固定：

1. **按行读取**：逐次保存模型 read_file 参数、SDK Action/Observation 链接、成功或拒绝、真实来源行号与正文比对，以及工具结果是否原样进入紧接的下一次模型请求。记录旧 offset 参数尝试，不默默转换。
2. **续页**：若模型选择 cursor，核对是否来自同路径前次响应，并由原生执行器验证会话/文件/范围绑定。没有使用续页记录为“未观察”，不判为失败，也不追加请求诱导使用。
3. **目标正文**：运行后用本地评分标签检查 `Parser._parse_set_item_assignment`（5969–5987 行）的完整正文是否经 read_file 进入模型请求。此项是读取链路观察；模型完全不用 read_file 时记为未覆盖，不能据此判接口故障。检索工具调用及证据另由既有审计器记录。
4. **终答**：记录原生 finish 是否完成、异常原因、函数/文件定位、实际回答及成本/时间。定位命中与正文已送达不等于语义回答正确，人工内容评分保持单独字段。

该题已多轮曝光且开发者看过参考标签。最近两批 LocBench 中 SQLGlot 已有 12 次真实请求，此外有离线探测与定向脚本；更早曝光未穷尽核实。此次只验证修复接入与真实使用行为，不作为独立泛化、盲测或检索收益证据。SDK 模拟脚本直接指定已知行号，只验证技术链路，不能冒充自主发现。

## 离线验收证据

- 52 项相关测试最终通过：单题授权/预算 17 项，观测审计 3 项，以及共享读取、收尾和传输 32 项。首次组合测试中的 1 个测试断言把 wrapper 新增 plan_hash 与来源清单直接比较而失败；修正为比较原字段及独立校验 plan_hash，17 项重检通过。未改运行逻辑，保留首次失败日志。
- 原生 SDK + MockTransport 的 9 种场景全部通过：正常续页、无需续页、第一组首请求超时、第二组首请求超时、收尾违规、finish 缺字段、输出截断、回包超限、第二组 worker 超时。网络封锁与凭据加载拒绝保护全程开启。
- 正常两场景各完成 8 个模拟请求；目标 19 行完整正文进入下一模拟请求。正常续页通过；无需续页得到 `paging_protocol_valid: null`。模拟结果不计真实质量分或自主工具选择。
- 故障均停机且重复启动被拒；已开始但结果未知的请求保留每次 2,113,536 micro-CNY 预留，不假定费用为零。worker 未开始网络请求的超时不产生该请求的预留。
- 单题边界测试含错误价格/范围/同意文本、24 小时过期、并发 claim 仅一个成功、错误组顺序、跨题账本、已消费授权、缺少交互终端、8 次最坏用量及第 9 次拒绝、超时杀进程组、Key 仅走私有管道。
- 复查 17 份历史调用账本：未决请求 0。2,584 份旧授权、账本、结果及冻结材料 SHA-256 不变。

证据目录：`verification/sqlglot-validation-v1/`；其中各场景 `verification.json`、`ledger-review.json`、测试日志及 `acceptance.json` 可直接复核。

## 价格与启动条件

2026-11-13 读取 [DeepSeek 官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：`deepseek-flash` 当前标示为 **DeepSeek-V4.1-Flash-1017**；高峰缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens，符合已有预算假设。请求使用可变别名，不能将网页版本名当作不可变模型快照；启动时须再次核对，不一致即停。

每次预留 = 1,048,576 × 2 + 2,048 × 8 = 2,113,536 micro-CNY，即 2.113536 元；8 次最多预留 **16.908288 元**。**17 元是保护上限，不是预计消费**。最终报告按响应 usage 和保守单价计算成本上界，账户实际账单需另行对账。

尚未核查账户本次实际适用价格/币种/附加收费，也没有读取 Key。真正启动前必须：

1. 获得针对本单题、两组、发送范围、8 次请求和 17 元的新批准。
2. 核对账户为人民币计费，全部收费不超过上述峰值单价；再检查官方别名版本、冻结 hash、历史未决账本、正在运行的任务及新方案无 grant/claim，避免重复。价格、版本或运行状态不明则停止。
3. 只在批准后创建绑定上述 hash 的一次性授权，有效期 24 小时；复用既有私有 `.env`，交互终端校验通过后才加载 Key。不要在聊天发送 Key。
4. 执行一次。HTTP/helper/worker 超时、协议错误或预算异常都停止；不自动重试、不转用旧授权。原始结果与未知费用状态保留。

预检（无需 Key、不发模型请求）：

```sh
.venv-openhands/bin/python -B -m experiments.sqlglot_validation.live proposal
```

获批且账户核查通过后的操作接口（本轮未执行）：

```sh
.venv-openhands/bin/python -B -m experiments.sqlglot_validation.live authorize --suite-hash df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277 --consent 'APPROVE SQLGLOT df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277 CNY 17' --currency CNY --input-ceiling 2 --output-ceiling 8 --all-charges-included
.venv-openhands/bin/python -B -m experiments.sqlglot_validation.live run --suite-hash df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277 --live --env-api-key
```
