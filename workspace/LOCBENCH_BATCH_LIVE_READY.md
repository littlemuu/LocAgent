# 两题 LocBench 真实批量入口：离线验收完成

2026-11-13：两题专用真实入口、一次性授权、持久化总账/子账、异常停机及结果审计已接通。**当前未授权、未启动真实运行、未读取 `.env` 或密钥，真实费用 0。** 旧六题和前次 LocBench 离线结果保持不变。

入口为 `experiments.locbench_batch.live`。冻结计划 [locbench_live/v1/manifest.json](locbench_live/v1/manifest.json)，摘要：

`6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9`

原两题源码/题面/评分计划摘要仍为 `45688f8a1c3a705b542d39573fcca9176d1e514edc81114de72f636fc0ddbf1c`。新增入口引用这一计划，未重写旧冻结文件。验收证据：[LOCBENCH_BATCH_READY_ACCEPTANCE.json](verification/LOCBENCH_BATCH_READY_ACCEPTANCE.json)。

## 固定范围

| 项目 | 本次方案 |
|---|---|
| 框架 | OpenHands Software Agent SDK 1.62.0，依赖锁和运行代码摘要绑定 |
| 模型 | 请求名 `deepseek-flash`；当前公开版本 DeepSeek-V4.1-Flash-1017；非思考、temperature 0、非流式 |
| 题目 1 | `Delgan__loguru-1239`，递归重复栈帧格式化；提交 `65fe4a8db9a8f297ae3648f51b5e3050b30945a9` |
| 题目 2 | `tobymao__sqlglot-3417`，带点号 SET TAG 解析；提交 `e1b6483d5e26d556f6a3dd82c6d35f475c189c2b` |
| 工具源码 | 同一题两组共用相同 Python 文件投影：Loguru 163 文件、SQLGlot 147 文件，均含测试/文档 Python；整仓完整性已在上一阶段校验 |
| 对照 | 基础文件列表/搜索/读取 vs 额外开放 LocAgent；第一题先基础，第二题先检索 |
| 请求 | 每组最多 4 次，两题四组总计最多 **16 次**；调查时 `tool_choice=auto`，末轮仅允许 finish |
| 工具与证据 | 每组最多 16 次调查工具调用，14,336 bytes 源码证据，每页 4,096 bytes；请求/回包各最多 65,536 bytes，输出最多 2,048 tokens |
| 截止时间 | 单次 HTTP helper 60 秒；单次 LocAgent IPC 45 秒；每组进程 360 秒，超时终止进程组并停止批次 |
| 预算 | 每题 17 元，总上限 **34 元**；不重试、不恢复、不补跑、不追加额度 |

模型别名由供应商维护；冻结的是请求名、当时的公开版本参考和参数，并不能强制供应商永远不更新别名。正式启动前需复核映射未变。

发往固定地址 `https://api.deepseek.com/chat/completions` 的内容：系统与预算/收尾提示、当前题的原始题面、工具定义、模型自行调用工具得到的文件列表/搜索结果/源码片段，以及**本题本组**会话历史。不会整库预塞；评分标签、参考补丁、另一组答案、开发日志及审计数据不进入提示。密钥只供 HTTP 鉴权使用，不进入模型消息或日志。

## 预算与价格核查

2026-11-13 再次核对 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：Flash 高峰输入未命中 2 元/百万 tokens、输出 8 元/百万 tokens，当前公开版本仍为 DeepSeek-V4.1-Flash-1017。预算使用高峰未命中上界，不依赖缓存优惠。

每请求在传输前持久化预留 **2.113536 元**：`1,048,576 × 2 / 1,000,000 + 2,048 × 8 / 1,000,000`。16 请求最保守预留合计 **33.816576 元**，低于 34 元。它不是预计花费或实际账单。收到完整响应后先存原始回包，再依据 usage 结算费用保守上界；账户实际扣费仍需账单核对。

**没有核查账户实际价格**：本轮不加载密钥、不访问账户。真实授权要求确认账户以 CNY 计价、包含附加费用后的输入/输出价格不超过 2/8 元每百万。若账户条件不符或不能确认，不能启动当前计划。

案例总账的 17 元 hold 是该题的额度占用；请求子账的未知预留是同一额度内的未决费用，不能将两者相加当成实际消费。超时/不完整回包保留预留并停机，已收到但终答无效的回包照实结算其 usage，不把失败当免费。

## 入口保护

- 独立 `authority-locbench/`，已加入忽略规则；新授权绑定整个计划 hash、两题顺序/分组、源码、题面、评分与驱动代码。旧六题或单题批准无法复用。
- 授权有效期 24 小时，原子领取一次；重复批准、并发领取和重复启动被拒绝。子授权每次请求重新检查当前题/组、总账停机状态和代码/源码摘要。
- 总账先占用每题 17 元；子账在每次传输前用 SQLite FULL 事务持久化一次性 ticket。每组 4 次、每题 8 次、整批两题上限同时约束；额外第三题不可启动。
- 正常终答必须 SDK finished 且子账已完成，无未知预留；任一组异常立即停整批，剩余组明确记为 not_run。父进程/授权失效、终答错误与传输异常都不会触发补跑。
- 默认禁止真实运行；需要有效新授权、`--live --env-api-key`、本机交互终端后才加载已有私有 `.env`。子进程通过匿名 stdin 管道接收密钥，不放进命令行或环境变量，清理进程组后不恢复。
- 报告分别记录状态、定位原文及 strict/参考指标、工具自主选择、证据进入下一请求、终答、耗时、usage、费用上界与未决预留。模拟运行禁止质量打分，并将调用明确标为脚本指定。

## 离线验收

**60 项测试通过**：新两题批量控制 16、真实传输/授权回归 16、终答长度与截断 10、持久化预算/协议 18。覆盖无授权不读 key、无 TTY 不启动、错误价格/范围、过期、代码变化、并发重复领取、组序、不恢复、子授权不可独立运行、外题账本替换、篡改负费用/组序、超时杀进程组和密钥仅进管道。最坏 usage 测试验证 16 张 ticket 合计 33.816576 元，且第 5 次组请求和第 3 题都被阻止。

另通过真实 SDK + LiveSession + 持久化账本运行 **8 条模拟场景**，仅将传输替换成 MockTransport，使用合成假密钥并令真实 `.env` 加载器直接报错；网络防护观察到 0 次网络尝试。

| 场景 | 模拟请求数 | 结果 | 请求未决预留 |
|---|---:|---|---:|
| 两题四组正常完成 | 16 | completed，4 个正常 finish，总账 hold 清零 | 0 |
| 第一题第二组超时 | 5 | TimeoutError，后两组未启动 | 2.113536 元 |
| 收尾轮仍请求 read_file | 8 | closing_tool_violation，调查工具未执行 | 0 |
| 第一题完成后第二题超时 | 9 | 第一题结果/结算保留，最后一组未启动 | 2.113536 元 |
| 输出 token 截断 | 4 | model_output_truncated | 0 |
| finish 提交快照外位置 | 4 | finish_source_validation_error | 0 |
| 没有结构化 finish | 4 | closing_finish_missing | 0 |
| 超大回包 | 3 | RuntimeError，保留不完整响应与未知费用 | 2.113536 元 |

八个场景共 53 次**模拟**传输；真实供应商请求 0、实际费用 0。模拟内部账本使用 live schema 以验证真实路径，但外层 execution 和报告明确标为 `mocked_live_transport`，不是实际账单或模型效果。全部场景均验证重复领取被拒，未自动重试。正常场景再次核对两组首轮消息与共享工具 schema 相同、第四轮只提供 finish、检索观测进入后续请求。1958 份既有源码/结果/账本/盲评材料的摘要保持不变。

## 正式运行条件与步骤

目前生产授权目录不存在，只有 `verification/` 下的离线模拟授权。真实入口已完成，不再缺两题批量代码；启动仍需这次范围的新批准和账户价格确认。

1. 批准将上述两题题面、工具/系统提示、相关源码证据和本题本组历史发送给 DeepSeek，最多 16 请求、总上限 34 元；明确仍为已曝光开发接入试跑。
2. 复核账户价格、公开模型版本与冻结摘要；未发现旧生产启动或未结调用。若代码或材料变化，停止并重新冻结审查，不能套用旧批准。
3. 获批准后记录一次性授权，再在本机交互终端运行。无需将 key 发到对话，已有 `.env` 可按既有方式加载。以下仅为操作说明，本轮没有执行：

```sh
cd /Users/xiaomu/Documents/Codex/2026-11-12/task
locbench_suite_hash=6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9
.venv-openhands/bin/python -B -m experiments.locbench_batch.live authorize \
  --suite-hash "$locbench_suite_hash" \
  --consent "APPROVE LOCBENCH $locbench_suite_hash CNY 34" \
  --currency CNY --input-ceiling 2 --output-ceiling 8 --all-charges-included
.venv-openhands/bin/python -B -m experiments.locbench_batch.live run \
  --suite-hash "$locbench_suite_hash" --live --env-api-key
```

停止后只查看 `status --suite-hash ...` 和保存的证据，不重跑同一命令。旧批次、旧批准和旧失败均保留。

两题属于已曝光开发集，不能支持独立测试结论；目前 LocAgent 工具只有实体 ID BM25/精确取回，并非全文语义检索或图关系扩展。Python 文件投影、4 请求/组、小样本及逐查询重建图的开销限制结论。离线脚本只证明协议与状态处理，没有证明模型会自主选择检索，更没有检索收益结论。目标仓库代码始终只作静态数据读取/解析，未执行其测试或代码。
