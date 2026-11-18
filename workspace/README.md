# LocAgent → OpenHands：只读代码理解 Agent

最新：[工具说明真实配对首请求后停止](CHOICE_PAIR_LIVE_RESULT.md)。用户明确确认后实际1请求返回，
原说明选read_file/search_text；新入口遗漏SDK summary提取而校验停止，新说明未运行。
费用上界¥0.006848、无未决/重试。已定位适配错误，不能据此比较说明效果。以下为历史记录。

最新：[检索工具说明配对离线试跑完成](RETRIEVAL_CHOICE_OFFLINE_RESULT.md)。两种说明各8场景，最终16/16按预期通过；
检索/读取完整正文进入下一模拟请求，故障停止。真实模型请求0、费用0；尚未测量自主选择偏好。
生产工具与授权未改，旧记录保留。以下为历史记录。

最新：[未选检索：状态对照与既有正例](RETRIEVAL_CHOICE_STATE_FINDINGS.md)。相同LocAgent定义曾有2次自主成功调用；
旧SQLGlot有2轮已知名缺正文机会，新试跑目标名出现时正文已到手。新增说明单变量离线草案，
未发模型请求、未改生产工具；不把任务路由假说当作已证因果。以下为历史记录。

最新：[LocAgent 原题与真实已见线索离线能力检查](LOCAGENT_CAPABILITY_CHECK.md)。复用12条查询，仅新增4次离线检索；
严格区分完整题面接口拒绝、标题、真实已见线索与oracle。SQLGlot已见符号可首屏完整取正文，
Loguru发现覆盖和大结果预算仍有限。2732份历史材料不变，本轮模型调用0、费用0。以下为历史记录。

最新：[SQLGlot 修复后单题真实验证完成](SQLGLOT_READ_LIVE_RESULT.md)。8请求、两组正常终答；
均正确按行读取并将目标函数完整正文送入上下文，无cursor续页、LocAgent调用0。
成本保守上界¥0.063666，无失败/重试/未决费用；已曝光流程验证，不作检索收益结论。以下为历史记录。

最新：[SQLGlot 读取修复后的单题验证准备完成](SQLGLOT_READ_VALIDATION_READY.md)。两组共享修复后的工具，
仅检索可用性不同；新方案冻结未授权，最多8请求/17元。52项相关测试最终通过、9种SDK模拟场景通过，
17份旧账本无未决请求、2,584份历史文件不变。本轮无付费请求，待新批准与账户核查。以下为历史记录。

最新：[未选检索的逐项假说与反证](RETRIEVAL_CHOICE_HYPOTHESES.md)。确认SQLGlot第2/3轮已有可查符号与充足证据预算；
原生工具可调用，新基础读取也可给出正文。8项假说逐条列支持/反例/区分实验，另发现查询长度约束未出现在wire说明。
本轮仅诊断，不改检索策略，无付费模型调用。以下为历史记录。

最新：[共用按行读取修复完成](READ_LINES_REPAIR.md)。read_file使用start_line/end_line和独立cursor，
153项测试、SQLGlot两组SDK离线复现及三条批量模拟通过。检索实现未改，未选检索的原因仅列可检验假说。
新方案已冻结未授权；本轮无付费调用，历史结果保留。以下为历史记录。

最新：[LocBench 离线诊断完成](LOCBENCH_OFFLINE_DIAGNOSIS.md)。四组轨迹、17组搜索/检索探测与参考补丁已核对；
SQLGlot发现共享读取游标误用，现有检索擅长已知实体读取、原问题发现能力不足。
建议先修两组共有的按行读取；本轮不改生产行为、无付费调用，2,263份历史文件不变。以下为历史记录。

最新：[LocBench 两题修复版补测完成](LOCBENCH_V2_LIVE_RESULT.md)。16次真实请求、4/4组正常终答、
0失败/重试，费用保守上界¥0.141562，无未决费用。两个检索组实际LocAgent调用均0；
兼容分支本次未触发，不作检索收益或独立评测结论。旧结果全部保留。以下为历史记录。

最新：[SQLGlot 空扩展字段离线修复完成](FINISH_NULL_COMPAT_REPAIR.md)。仅兼容 `entities_note:null`，
原始响应保留并记录审计事件；124项测试、9条离线路径通过，1,960个历史文件不变。
原真实失败不追认成功；新方案已冻结但未授权，本轮真实请求0、费用0。以下为历史记录。

最新：[LocBench 两题真实试跑已停止](LOCBENCH_LIVE_RESULT.md)。12请求、费用上界¥0.106498、无未决请求；
Loguru两组完成，SQLGlot检索组finish多出字段被拒，基础组未运行。实际LocAgent调用0，未重试。
原始回包/账本/历史保留，不作检索收益结论。以下是启动前准备记录。

最新：[LocBench 两题真实批量入口离线验收完成](LOCBENCH_BATCH_LIVE_READY.md)。60 项测试与8条模拟场景通过，
已验证一次性授权、16请求/34元预算、重复启动、超时及终答停机；历史材料保持不变。
生产授权尚未创建，无付费请求；真实入口已就绪，等待新批准及账户价格核查。

最新：[LocBench 两道真实仓库开发题离线接入](LOCBENCH_OPENHANDS_PREPARATION.md)。Loguru 与 SQLGlot
两题四组通过，65 项测试通过；修复 AST 末行注释导致的误拒，保留空检索及中止记录。
无新增付费调用；拟议最多16请求/34元，真实两题批量入口及新授权尚待完成，不是独立测试。

最新：[六题盲化 AI 内容评审完成](BLIND_REVIEW_V3_RESULT.md)。两位新上下文评审48项中47项一致，
第三位独立裁决1项后解盲：基础17/24、检索工具可用组19/24。无新增模型API调用；不是独立人类盲评，
共享环境和措辞推断风险已披露。唯一实际使用LocAgent的题两组同分，不能据此声称检索收益。

当前：[v3 六题真实配对试跑完成](DEV_BATCH_V3_LIVE_RESULT.md)。12/12 组正常终答、45 请求、0 失败/重试，
费用保守上界 ¥0.269208、无待结。检索组在文档权限题自主调用 LocAgent 一次，证据进入下一真实请求；
两组关键定位召回均为 100%，不据此宣称检索收益或回答完全正确。以下为历史阶段记录。

最新：[取消终答字符硬限制的离线修复](ANSWER_POLICY_REPAIR.md)。1200 字符改为风格目标，完整正文原样保留；
继续使用 2048 输出 tokens 与 64 KiB 原始回包限制。历史 1527 字符答案离线重放可正常完成；
超限回包仍停机并保留未知费用，报告明确标记证据缺口。v3 已冻结但未授权，无新增真实调用。

当前：[修复版六题真实重跑已停止](DEV_BATCH_V2_LIVE_RESULT.md)。首题基础组第 3 次返回完整 finish，
正文 1527 字符被新设 1200 字符硬校验拒绝；不是 token 截断。3 次请求费用上界 ¥0.017430，
无待结费用，其余 11 组未运行，没有重试或效果比较。v2 授权已消耗。以下为历史阶段记录。

最新：[终答截断离线修复](FINAL_LENGTH_REPAIR.md)。统一 1200 字符正文约束与 2048 输出 tokens；
97 项 SDK、23 项核心测试和五条批量模拟路径通过。v2 已另行冻结，未授权、无新增付费调用。
建议另获批准后从头复测六题，最多 48 次/102 元；旧结果保留，首题的真实模型暴露已记录。

当前：[六题批准试跑已异常停止](DEV_BATCH_LIVE_RESULT.md)。首题基础组第 4 次响应的 `finish` 输出达到
1024 tokens 上限而截断；4 次请求费用保守上界 ¥0.026422、无待结费用。检索组和其余题均未启动，
没有有效配对或检索收益结论；授权已领取，没有重试。以下保留各阶段历史记录。

最新：[六题真实批量适配已完成离线验收](DEV_BATCH_LIVE_READY.md)。89 项测试通过，正常/收尾越界/超时路径
均完成模拟核验；真实入口默认锁定，等待六题最多 48 次、102 元的新批准。本阶段付费调用 0。

最新离线准备：[六题配对开发集](DEV_SUITE_PREPARATION.md)。36 个源码文件，题目/评分/预算已冻结，
12 组离线回放完成；提案最多 48 次/102 元，未授权，真实批量入口仍锁定。

最新真实结果：[`.env` 复用后的工具说明版试跑](ENV_REBOUND_LIVE_RESULT.md)。两组各 4 次请求正常终答，
检索组首次自主调用 LocAgent，返回证据进入下一实际请求的链路已核验；仍不作检索收益结论。

当前本地密钥配置见 [`.env` 使用说明](LOCAL_ENV.md)：优先复用已有私有配置，
提供隐藏输入与 `--env-api-key` 入口，付费授权/预算仍独立。此次只配置、不启动试跑。
最新真实收尾结果见 [验收报告](CROSSFILE_CLOSING_LIVE_RESULT.md)，工具说明改进见
[离线分析](RETRIEVAL_CHOICE_ANALYSIS.md)。以下阶段记录保留历史时间点。

最新免费修复：[显式收尾控制与下一试跑方案](CLOSING_REPAIR.md)。逐轮预算提示、末轮明确关闭调查、
执行器硬关闭和精确错误报告已完成，92 项离线测试通过；未新增付费请求或授权。

**最新真实检查：跨文件试跑在基础组第 4 次收尾请求停止，检索组未启动。**
回包要求调用已关闭的 read_file，本地拒绝并停机；本轮费用上界 ¥0.018574，无未知预留。
见 [跨文件结果诊断](CROSSFILE_LIVE_RESULT.md)。以下保留历史阶段记录。

下一步的 [跨文件检索自主选择方案](RETRIEVAL_CHOICE_PREPARATION.md) 已完成离线准备：
10 文件样例、检索证据进入下一请求的审计、固定样例选择入口；尚未授权或付费运行。

**最新验收：修复版真实双组试跑完成。** 两组各 3 次请求，均正确终答；本轮费用上界 ¥0.019130、
无未知预留。检索组未实际调用 LocAgent，不能作检索收益结论。见 [真实试跑结果](LIVE_PILOT_RESULT.md)。
以下为历史阶段记录。

最新：首次真实试跑基础组 3 次回包成功、终答协议验证失败，检索组未启动。
接口已修复，72 项离线回归通过，没有自动重试。见 [诊断与修复](FIRST_LIVE_FAILURE.md)。
下文为分阶段记录。

2026-11-12：按最新决定，**OpenHands Software Agent SDK 1.62.0 是当前优先底座**。
已有 LocAgent 检索保留独立 Python 接口；不改旧 harness、旧评测和旧账本。
learn-claude-code 风格的最小循环保留作离线协议参考与回归夹具，不作为继续扩张的生产底座。

后续已完成 [DeepSeek 真实调用准备与预算仿真](REAL_CALL_PREPARATION.md)，以及
[现有前后端复用审查](FRONTEND_BACKEND_INTEGRATION.md)。
最新已接入默认锁定的真实传输与一次性授权，见 [启动说明](LIVE_PILOT.md)；尚未授权或发起真实调用。
以下保留第一阶段实现与验收记录；最新方案和测试数量以补充文档为准。

## 当前可运行内容

- OpenHands 的真实 `Agent` / `LocalConversation` 执行工具分派、事件记录和终答。
- 基础组：`list_files`、`search_text`、`read_file`、SDK 内置 `finish`。
- 检索组：上述工具 + `locagent_retrieve`。共享系统提示、源码快照、请求及工具输出预算。
- 检索是已有 LocAgent 的精确实体读取 + module BM25 + 图节点代码格式化。
  尚未开放 corpus BM25、邻接图探索、embedding 或旧 harness 的候选/补读控制策略。
- 至今验证用的模型响应全部来自确定性脚本。真实 SDK 循环与真实检索可验证，模型质量不可验证。
  付费 transport 默认锁定；需新的逐方案授权及本地隐藏密钥输入，不继承历史实验授权。

## 文件分工

| 文件 | 职责 |
|---|---|
| `readonly_agent/core.py` | 不依赖 SDK 的源码快照、基础工具、JSON 字节分页、终答验证；保留最小参考循环 |
| `readonly_agent/locagent.py` | 真实 LocAgent 图/实体检索接口，校验图与源码一致性，恢复旧全局状态 |
| `readonly_agent/bridge.py`、`locagent_worker.py` | 用原 LocAgent Python 环境运行检索；固定命令、JSON stdin/stdout、45 秒超时，不调用 shell |
| `readonly_agent/openhands_tools.py` | 原生 SDK Action/Observation/Executor/ToolDefinition；会话内共享输出预算 |
| `readonly_agent/openhands_replay.py` | SDK 离线完整循环；独立 case/arm 进程入口、脚本模型、请求门限、轨迹 |
| `readonly_agent/offline.py` | Python 网络调用拒绝；隔离用户配置与凭据环境 |
| `requirements-openhands.lock` | 官方 SDK 及 134 个已解析 wheel 的固定版本和 SHA256（包含 SDK） |

## 环境与复现

SDK 装在当前目录 `.venv-openhands`（Python 3.12.16，约 443 MB），未升级原 LocAgent venv。
安装仅用 PyPI 二进制 wheels，无源码构建；版本/下载哈希见 lock 与安装报告。
原 LocAgent 仍在 `/Users/xiaomu/Documents/Codex/locagent-demo-20261108`。
此目录与原项目均没有 Git 元数据；没有提交或推送。

在本目录运行基础组；每次使用新的输出目录，禁止覆盖旧结果：

```sh
.venv-openhands/bin/python -B -m readonly_agent.openhands_replay \
  --case examples/case.json --arm baseline --output verification/new-baseline
```

同题检索组：

```sh
.venv-openhands/bin/python -B -m readonly_agent.openhands_replay \
  --case examples/case.json --arm retrieval --output verification/new-retrieval \
  --locagent-python /Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python \
  --locagent-root /Users/xiaomu/Documents/Codex/locagent-demo-20261108
```

case JSON 必须仅含 `root`、`source_files`、`issue`、`scripts`。相对 root 以 case 文件为基准。
`source_files` 是显式源文件白名单；gold、patch、hints、历史答案不得放入其中或题面。
每个 case/arm 使用新进程、新快照、新 Conversation、新输出路径。不要复用旧 Conversation 续跑评测。
检索 worker 只把白名单源码写到临时副本供静态分析，不 import/执行待测源码，不读取 pickle。
worker 使用自己的原 LocAgent 依赖；SDK 与 LocAgent 的 pydantic / LiteLLM 版本无需混装。

测试：

```sh
python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/xiaomu/Documents/Codex/locagent-demo-20261108:. \
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
MPLCONFIGDIR=/tmp/locagent-readonly-mpl \
/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python \
  -m unittest discover -s tests -p '*.py' -v
.venv-openhands/bin/python -B -m unittest discover -s tests_sdk -v
```

第二条包含 23 项核心测试与 3 项真实 LocAgent 集成测试；SDK 套件另 7 项。

## 已验证证据

- [核心/LocAgent 最终日志](verification/final-tests.log)：26/26。
- [OpenHands 测试日志](verification/openhands-tests-v1.log)：7/7。
- [基础组结果](verification/openhands-baseline-v2/result.json) 与
  [检索组结果](verification/openhands-retrieval-v1/result.json)：均 completed/finished，各 2 次脚本请求。
- 两臂 contract 仅 `retrieval` 与 `script_hash` 不同；分别给出源码、系统提示、运行代码哈希。
- 基础组送达 77 字节工具正文，检索组 852 字节；**相同上限不要求相同实际用量**。
- 两臂父进程网络尝试均为 0；成功检索 worker 也通过旧 `offline_engine` 的零尝试断言。
  真模型调用和费用均为 0；`quality_measured=false`。
- [旧引擎哈希记录](verification/demo-pair/engine-provenance.json)：145 个行为文件运行前后不变。
- 初次 SDK 集成错误见 `verification/openhands-baseline-v1.log`：公开 Conversation factory
  不接受 `profile_store_dir`；改用该版本支持的 LocalConversation。失败记录保留。

## 边界与下一步

默认每臂最多 8 次脚本请求、16 次调查工具调用、14336 字节序列化工具正文、4096 字节单页，
请求 JSON 上限 65536 字节，响应 JSON 上限 8192 字节，输出 token 参数 1024。
这些字节值不是供应商 token 或人民币额度。控制错误信息不计入源码额度，但计入请求大小。
最后一轮或工具/源码额度耗尽后，离线模型调用门只提供 finish，禁止额外调查；违反协议记失败，
不自动补跑。请求上下文本身装不下时会明确失败，并不保证任意参数下都能终答。

只读来自工具实现与白名单，不来自 SDK `readOnlyHint` 注解。未启用 Bash、编辑器、插件、MCP、
记忆、自动压缩或子代理；会话 workspace 为独立空目录。Python 网络 guard 不是恶意代码 OS 沙箱。
IPC 超时为单次检索时限；暂未做多机、大仓库吞吐、OS 级沙箱或真实供应商兼容性验收。

后续已将 durable reservation/未知请求处理接到 SDK 调用边界，并提供默认锁定的传输入口；
离线仿真仍不等于供应商验收或用户授权。启动前需批准固定方案、账户价格与总上限。
SDK 自带费用统计不能替代预留账本；实际预算以外部 SQLite 账本为准。
再以同一 SDK、同题同预算只切换检索进行开发集对照，单列终答率、定位分数、请求数与费用。
旧第二阶段基础组有 15 题未提交终答，该结果继续只作诊断，不能据此宣称 harness 优势或退化。

## 上游参考

- [OpenHands 自定义工具官方文档](https://docs.openhands.dev/sdk/guides/custom-tools)：API 设计参考；
  实际安装版本 1.62.0 的 registry 只接受工具实例或子类，未照搬文档中的 factory function 示例。
- [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk)：
  `reference/openhands-1.62.0` 是从固定 wheel 解包的源码审阅副本，附上游 MIT LICENSE；运行来自隔离 venv。
- [learn-claude-code s01](https://github.com/shareAI-lab/learn-claude-code/blob/main/agents/s01_agent_loop.py)
  / [s02](https://github.com/shareAI-lab/learn-claude-code/blob/main/agents/s02_tool_use.py)：早期最小循环/分派模式参考，
  新代码独立实现，未执行或整体搬入该仓库。
