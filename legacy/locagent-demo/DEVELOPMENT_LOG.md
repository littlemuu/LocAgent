# 项目开发日志：排错、修复与验证

本日志从 2026-11-10 建立，汇总当前本地演示版及相关独立实验的可核验证据。日期使用事件报告日期；精确时间注明时区。历史报告按原快照保留，不把后续修复倒写成旧测试成功，不把合成测试当成真实模型效果。

入口：[项目 README](README.md) · [网页手册](README_LOCAL_WEB.md)。日志不包含密钥、授权正文、原始私密问题或完整运行记录；外部实验链接仅在保留同级目录的本机可用，不随源码包自动分发。

## 当前状态速览

- **已修复并做针对性验证**：公开仓库中一个特定大型评测产物导致的 `file_limit`；隐藏输入 key 的本机入口；逐次调用用量和易读工具轨迹；自主补读的逐签名可见性机制。
- **尚未证实**：自主补读能提高真实定位。三题六臂先导中两臂均覆盖 2/3 个标注方法，开启臂没有调用 `reread_visible_entity`。
- **待解决**：7220 的自然检索未送达目标方法；11143 的工具正文预算和收束时机限制了阅读机会。修复协议与提高质量是两回事。
- **验证边界**：下文各条测试是各自时间点的范围，不相加、不代表当前全项目全绿。本日志整理本身不重跑模型、不重启服务、不改账本。

## 2026-11-10｜大型评测文件触发 `file_limit`

**现象与原因**：公开仓库准备流程被生成的评测 JSONL 超过单文件限制阻断，它不是需要进入 Python 源码索引的文件。

**修复**：`locagent_service/public_repo.py` 使用 policy v2，仅对 `evaluation/loc_output/locagent/claude_3-5/loc_outputs.jsonl` 作精确路径例外：仍验证 Git blob 内容，但不落盘、不索引，并留下遗漏审计。没有提高源码文件上限，没有放行整个 evaluation 目录或所有 JSONL。保留压缩/解压/文件数/路径/链接/LFS 防护，并增加 TAR 逻辑总字节与 sparse member 检查。旧缓存和旧付费计划不能因修改而复用。

**验证**：固定 `littlemuu/LocAgent` commit `4935b557326c154bad8e8dcf3747cc8d32d1f387`，验证 90 个 blob，74/74 个 Python 文件提取且成为图文件节点；图 658 节点、1697 边，BM25 建立、二次缓存命中；唯一省略项为 2,452,770 字节的上述产物，缺失 Python 文件为 0。最终相关联合回归 70 项通过（包含 37 项公开仓库相关测试，不能相加），未调用付费模型。

**限制与使用**：较早全量 761 项有 1 failure、13 errors、19 skipped，不能称全绿；原因包括历史夹具缺失、torch 缺失及 macOS 不支持的 Linux 进程测试。最终 sparse guard 后只重跑相关测试及真实仓库准备。网页每次准备创建新子进程，新建准备即可读取修复，不覆盖旧失败任务；长期加载代码的 API/worker 需正常重启。

证据：[修复报告](verification/large-eval-output-20261110T133343/REPORT.md)、[最终 70 项日志](verification/large-eval-output-20261110T133343/final-regression.log)、[真实准备结果](verification/large-eval-output-20261110T133343/real-preparation-result.json)、[准备边界](docs/PUBLIC_REPOSITORY_PREVIEW.md)。

## 2026-11-10｜本机 key 配置与调用过程展示

**问题**：新终端环境变量不会进入已启动服务；用户需要能看懂配置方式、每次调用用量与查找过程。

**现有实现**：页面「配置 API Key」提供无密钥命令与说明，`--prompt-api-key` 在本机交互终端隐藏输入，非交互/无法禁用回显则拒绝。网页不收 key、不提供远程 shell。key 只进入当前服务及获准子进程环境；服务结束后需重新输入。DeepSeek 无密钥参考配置带拒绝启动标记，须先核实定价，不能把旧价当授权。

逐次调用卡片从账本展示状态、输入/输出 token、估算费用；未知不是 0，未结算预留不是实扣。缓存折扣未单列的旧账本不反推。查找过程按保存的 assistant/tool 消息及 ID 关联，分页范围可展开；不展示或声称模型内部思维链，缺记录不猜补。

**已记录验证**：用量展示报告记录 `check_demo.sh` 通过 70 项 Python、12 项 JS 及相关语法/CLI/合成演示；最后兼容修改后重跑全部 12 项 JS。只读历史页面实见 3 次调用、输入 16,758、输出 390 token、估算 CNY 0.036636。它不是本次新增调用或实扣账单。key 安全边界另有 `tests/test_key_setup.py`，本次整理不把测试存在当成重新执行成功。

**限制与使用**：静态展示变更刷新即可；更换供应商或 key 需要重启服务并重新准备计划。未做手机实机或完整历史实验测试。自动脱敏不能保证所有私人信息均被过滤，不应整体公开 web-runs。

证据：[网页手册](README_LOCAL_WEB.md)、[调用用量验收](docs/LOCAL_WEB_CALL_USAGE.md)、[key 测试源码](tests/test_key_setup.py)。

## 2026-11-10｜自主补读 v2：修复可见签名资格

**原因**：v1 把压缩后的整段类预览交给 AST；末尾缺失函数体或省略号结构会令已完整可见签名也无法解析。

**修复**：有界 tokenize 提取声明，再逐条 AST 验证函数头；只承认实际连续送达、可溯源且图中存在的直接方法签名，拒绝注释/字符串伪造、缺字间隙及同批猜选。内部池最多 256，提示按源码顺序最多 12，并说明遗漏；不是相关性排名。双层 JSON 转义超预算问题已有回归。两次补读上限、原轮次/字节/请求/终局门限不放宽。网页/CLI/付费计划没有启用该实验功能，默认关闭。

**验证**：最终相关 150 项通过，外层网络/模型尝试为 0。默认关闭路径与独立旧源码的完整请求及结果逐字节一致。旧 Flask 预览离线诊断识别 21 个直接方法，但它是旧题诊断，不能算新题效果或模型实际选择。全量两臂日志分别有失败、错误与跳过；执行时源码变动影响过一轮全量，之后冻结重跑仅限相关 150 项；取消的全量记录不是完成验收。

证据：[v2 报告](verification/autonomous-reread-20261110/REPORT_V2_ZH.md)、[最终相关测试](verification/autonomous-reread-20261110/v2-final-focused.log)、[结构化验证范围](verification/autonomous-reread-20261110/validation-summary.json)。

## 2026-11-10｜三题六臂真实先导：结果未提升

本节引用已完成的独立实验，不是在日志整理时执行。供应商响应时间为 **08:49:38–08:50:05 UTC**。同一冻结 v2 代码关闭/开启补读，各题各臂 3 次请求，共 18 次，均已结算，六臂正常终局、无未知请求或未结算预留。两臂目标方法覆盖均为 **2/3**；三个开启臂均未调用 `reread_visible_entity`。协议 success 不等于定位正确。

- **pytest-7220**：两臂命中 `src/_pytest/nodes.py` 文件，却均漏掉 `Node._repr_failure_py` 方法；完整目标正文均未送达。开启臂各轮补读候选始终为空。它曾调用普通 `read_tool_output` 读取 output-1 的后续页，这是分页，不能算自主方法补读。困难首先在自然检索路径，没有依据声称模型主动拒绝了一个已具备资格的目标方法。
- **pytest-11143**：两臂均包含 `AssertionRewriter.run`。关闭臂完整读到目标正文 660–742 行，开启臂仅到约 727 行；开启臂第二轮另一条搜索触发工具正文总字节预算，第三轮只可 finish。此处不是人民币预算耗尽。第二轮补读简表来自 Node；目标 AssertionRewriter 签名直到收束前才出现，不能直接归因为模型不愿补读。
- **pytest-8365**：两臂均通过普通读取收到 `TempPathFactory.getbasetemp` 完整正文 102–125 行，均包含目标；属于无需类预览补读的负对照，不能说整文件都读完。

**用量与限制**：供应商 usage 合计输入 118,494、输出 2,584 token。按全 miss 配置价估算 CNY 0.257660，按原始 cache hit/miss 分项估算 CNY 0.14752368，均非账户实扣账单。三题同仓、每臂单次，不支持统计显著性、泛化或补读收益结论。旧授权已消费，不据此自动再跑。

**后续只读诊断补充**：7220 的原始返回没有目标签名，相关候选正文未读，第三轮强制 finish；不能把“出现候选名称”当作读完候选正文。11143 的源码正文可用空间为 14,336 字节，先前结果已用 14,335 字节，后续结果未送达。该数字是正文预算，不是 token 数、费用或模型上下文窗口。证据位于上述独立实验的 `paired-live-ledgers/class-method-20261110-approved1/`：7220 的 `raw-006.json`、`raw-007.json`、`request-008.json`、`pytest-7220-on-result.json`；11143 的 `raw-003.json`、`raw-004.json`、`raw-005.json`、`request-004.json`、`request-005.json`、`pytest-11143-on-result.json`。

**后续状态**：下文已实现默认关闭的候选下钻入口并做离线验证；是否减少宽泛搜索、改善正文送达和真实终局正确性仍待验证。不依据上述分数宣称提升，也不自动增加真实题数或模型调用。

证据：[独立先导完整报告](../locagent-class-method-paired-runner-20261110/COMPLETED_REPORT_ZH.md)、[逐臂分析](../locagent-class-method-paired-runner-20261110/completed-analysis.json)。外部目录不随本项目复制；报告引用的原始账本保持原样，不嵌入此日志。

## 2026-11-10｜候选列表下钻正文：默认关闭的离线改进

**实现完成**：新增核心选项 `candidate_drilldown=True`，默认 False。可信工具提示中完整送达的函数候选可进入既有 `reread_visible_entity` 集合；模型自行选择读取正文，再用原工具追查正文中的调用线索。不自动选答案、不遍历邻接图、不读取标注或按已知目标加特例。共享原两次补读上限、轮次及字节预算，提示会占用正文空间。CLI、网页、服务和历史付费计划未启用新选项。

**排错与修复**：首轮两个脚本测试未触发真实列表折叠，因为同名候选不足四个，且根目录夹具不匹配默认 `**/*.py`；改为 src/ 下至少四个同名候选，未修改生产检索规则。独立复审又发现已读函数可能只返回重复通知，初版 delivered 容易被误读为正文已送达；现新增 `returned_content=repeat_notice` 与 `repeat_notice_delivered`，加第九项回归。新 `candidate_drilldown.combined_delivery_bytes` 是字节预算核算量：累计工具消息及反馈，加两类提示各自峰值，仅预算 closing 时计入 finish 收束提示。它不是跨轮累计流量、token 或费用，自然最后轮 finish 提示不计入该字段。

**7220 的证据边界**：录制重放显示 Node.repr_failure 提示完整落入原送达范围，可进入新候选集合；后续未完整送达的候选不会获准。但原第三轮只允许 finish，不能改变历史无补读结果。独立四轮脚本能沿候选→正文→被调用方法走通，只证明机制可达，不是模型自行选中、不是真实准确率提升。

**实际验证**：最终聚焦 **93/93** 通过，包含新增 **9** 项，不相加；五个变更 Python 文件 AST 语法检查通过。复审前全量 791 项有 1 failure、13 errors、19 skipped：11 个 error 项缺历史冻结工件（含 setUpClass），2 个 error 缺 torch，1 个 failure 因 macOS 缺 Linux prctl/PDEATHSIG 导致子进程未进入被测阶段。未伪造夹具、安装依赖或改旧断言消除失败。最终代码全量已完成：**792 项，129.773 秒，1 failure、13 errors、19 skipped**，两轮失败名称逐项一致，不称全绿。独立只读复审确认重复通知与预算核算修正解决原问题，未发现新阻断；复审未独立运行测试。未运行 PostgreSQL、Compose 或真实模型效果评测。

证据：[实现与排错报告](docs/CANDIDATE_DRILLDOWN_20261110.md)、[93 项聚焦日志](verification/candidate-drilldown-20261110/focused-tests.log)、[复审前全量日志](verification/candidate-drilldown-20261110/full-tests.log)、[最终全量日志](verification/candidate-drilldown-20261110/full-tests-final.log)。本项目没有 .git，不宣称已提交、推送或执行 git diff 检查。

## 2026-11-10｜等源码空间与固定调查轮次：离线控制

**原因**：7220 第二轮候选送达后第三轮已只许 finish；11143 的工具消息额度也会提前触发收束。轮次与源码空间是独立变量，不能将两个同时放宽后的差异归因于补读。

**实现**：新增严格布尔核心选项 `equal_source_budget=True`，默认关闭，仅 bounded-v1 可用。所有提示开关组合统一保留 10240 字节控制空间，工具消息额度均为 14336 字节（含 JSON 包装，不是纯源码或 token）。没有增加总 24576 字节额度、单条 8192 上限、请求门限、批次或两次补读限制。轮数复用 `max_iterations`：实验中双方同设 3 或 5，分别最多 2 或 4 轮调查，最后一轮只许 finish；不自动续轮，不改旧计划/账本。候选到最后调查轮才出现仍无法越过硬终局，预算耗尽仍提前收束。

**公平实验与边界**：8 臂离线矩阵分别控制 3/5 轮、旧/等空间、候选下钻 off/on。固定 candidate_guidance 时旧空间 off/on 为 16384/14336，等空间均为 14336。每个格子内两臂同轮数、同空间；跨格改变预算不可宣称纯机制收益。固定脚本验证第二轮候选或类签名在五轮配置下可继续读正文、追调用，三轮则无机会。所有工具选择由脚本指定，不是模型自主选择或真实准确率改善。CLI、Web、服务及付费 runner 未自动启用，新真实实验须重新绑定源码、明确双方预算并获批准。

**排错与复审**：首轮12项有3个 error，因不存在的占位查询触发未配置 BM25；改用已有图查询后通过，未改生产检索。独立复审后增加实际图全部八种布尔组合、Unicode/转义、超长 call-id 和压缩类签名测试。新 `source_budget.accounted_delivery_bytes` 含自然末轮 finish 提示、工具反馈及已发送替换提示峰值，旧诊断语义保持兼容；该数值不是跨轮累计流量或费用。复审没有独立跑通测试，下面通过数来自本轮执行日志。

**实际验证**：最终聚焦 **109/109** 通过，包含新增 **16** 项，不相加；5个Python文件AST与行尾空白检查通过；8臂mock矩阵生成成功。首轮全量 **804项，122.861秒，1 failure、13 errors、19 skipped**，均与原有环境/工件失败名称一致；复审后最终生产源码全量 **807项，121.787秒，1 failure、13 errors、19 skipped**，失败/错误名称与前次候选下钻全量逐项一致，不称全绿。最终全量 discovery 启动时新增15项，补充第16项由最终109项聚焦覆盖，不混加计数。没有真实模型调用、没有读取 key、没有改写原始账本或干扰现有服务，没有 .git，不声称已提交或推送。

证据：[完整设计与复现报告](docs/EQUAL_SOURCE_BUDGET_20261110.md)、[最终聚焦109项](verification/equal-source-budget-20261110/focused-tests-final2.log)、[离线矩阵](verification/equal-source-budget-20261110/matrix.json)、[全量复审后日志](verification/equal-source-budget-20261110/full-tests-final.log)、[源码哈希](verification/equal-source-budget-20261110/source-hashes.json)。**真实质量收益尚未验证。**

## 后续记录模板

每次新增记录写明：日期/时区、现象、证据和原因、修改文件及范围、实际运行的验证与结果、尚未解决及下一步、证据链接。模型实测与离线合成测试分开；只写真正执行过的命令和数量。复现失败及取消日志保留，不覆盖历史授权或原始响应。

## 2026-11-10 UTC｜Loc-Bench 最小对接与离线验证

**结论**：可以接入，但尚未完成全量筛题或真实质量评测。独立目录 `../locagent-locbench-adapter-20261110/` 保存固定数据revision `c44cf3b74e07ca642cec841b471a9939907c12a7`、官方评分源码commit `4935b557326c154bad8e8dcf3747cc8d32d1f387`、适配脚本与审查队列。实际560题、165仓库，全部通过现有四字段LocalizationRequest；gold/patch/hints留在scoring-only，不进入运行输入。

**重要口径**：官方把Class.__init__归为Class，64题涉及此类标签，与现有严格AST函数指标不同；官方found_entities分支的重复预测、Acc/MAP及max_k处理也不能等同严格Recall。保持两套指标分开，未执行官方torch实现，不声称数值复现论文。数据卡未声明dataset license，不把代码Apache-2.0当成数据授权。

**验证**：5项契约/隔离/源码检查、7项公式边界/既有严格评分器检查通过；loguru、networkx、pypdf三个固定commit真实仓库图与BM25构建成功，3/3目标可达；906个Python文件905个成图，唯一缺失pypdf的.github脚本属于原有跳过规则。便利抽样、固定commit归档哈希核验，不是全560覆盖或独立Git树逐blob核验。实际准备/候选任务合并34题、本地live15题及上游预测300题与本次均无ID重叠；Chainlit-1441只见源码/名单提及，需单列审查。语义去重仍待完成。

**范围**：未调用模型、未读取key、未执行下载源码、未改生产逻辑/旧任务/账本，也未跑全项目回归。仅新增独立工件并追加本日志。下一步由独立筛题审查冻结可用子集、排除理由和指标分母，再申请真实调用预算。

证据：[完整报告](../locagent-locbench-adapter-20261110/REPORT_ZH.md)、[实际图覆盖](../locagent-locbench-adapter-20261110/graph-check.json)、[历史审计](../locagent-locbench-adapter-20261110/audit-prior.json)、[离线检查日志](../locagent-locbench-adapter-20261110/offline-check.log)、[评分检查日志](../locagent-locbench-adapter-20261110/scoring-tests.log)。外部目录不随本项目自动分发。

## 2026-11-12 UTC｜只读工具独立化，并验证 OpenHands SDK 底座

**方向**：本轮先参考 learn-claude-code 的最小循环建立只读工具和离线回归；用户随后明确选择
OpenHands Software Agent SDK，已保留现有工作并把 SDK 1.62.0 作为优先底座。新工作在
`/Users/xiaomu/Documents/Codex/2026-11-12/task`，未改旧生产 harness、实验输入、结果或账本。

**实现**：显式白名单源码快照、列表/字面搜索/分页读取、独立 LocAgent 精确实体与 module BM25
检索接口；两个环境通过受限 JSON 本地进程接口连接，检索端恢复全局状态，静态分析临时副本。
OpenHands 原生工具接入后，实际 Agent/LocalConversation 负责同一循环、工具分派、事件和 finish。
两组只有检索工具开关不同；相同提示、源码与预算。每 case/arm 新进程、新会话，不续用旧轨迹。
预算关闭后保留 finish；不存在有效终答、请求越界或协议错误记失败，不自动增加轮次。

**环境**：官方 openhands-sdk 1.62.0 和共 134 个解析 wheel 固定版本/哈希，仅安装到本任务的
`.venv-openhands`（约 443 MB）。未升级原 LocAgent venv，未安装源码构建包或运行陌生仓库脚本。
SDK/import/API 源码先静态检查；原项目没有适用 AGENTS.md，CONTRIBUTING 是占位模板，未执行其中安装建议。

**实际验证**：核心及真实 LocAgent 集成 26/26，SDK 7/7。真实 SDK 双组离线样例都
completed/finished，各 2 次脚本响应；基础工具 77 字节，检索工具 852 字节，均在相同 14336
字节上限内。两臂 contract 只在 retrieval 与 script_hash 不同。父进程网络尝试 0，成功子进程
通过离线 guard；真实模型调用和费用均为 0。旧引擎 145 个行为文件运行前后哈希不变。

**排错**：初次 SDK Conversation 工厂不接受 profile_store_dir，失败记录保留；已使用该版本的
LocalConversation。官方在线 custom-tool 文档与 wheel registry 对工厂函数支持不一致，采用
已实测的绑定工具实例注册方式。没有把协议夹具成功计作模型定位效果。

**限制/下一步**：当前只实现只读和离线 SDK 验收；corpus BM25、图邻接探索、写代码和跑待测仓库
测试尚未开放。真实供应商接入前须将旧 durable reservation/未知请求处理适配至 SDK 调用边界，
明确模型、题目、定价与金额上限后另获授权；SDK 自带费用统计不能代替预留账本。
旧第二阶段基础组 15 题收尾缺陷继续保留作诊断，不能据旧分数声称 harness 更强或更弱。

**证据**：[完整说明](../2026-11-12/task/README.md)、
[核心/LocAgent 测试](../2026-11-12/task/verification/final-tests.log)、
[SDK 测试](../2026-11-12/task/verification/openhands-tests-v1.log)、
[基础组](../2026-11-12/task/verification/openhands-baseline-v2/result.json)、
[检索组](../2026-11-12/task/verification/openhands-retrieval-v1/result.json)、
[固定安装依赖](../2026-11-12/task/requirements-openhands.lock)。
当前工作区无 Git，不宣称提交或推送。

## 2026-11-12 UTC｜OpenHands + DeepSeek 真实调用准备与前后端复用审查

**本轮范围**：用户确认先准备真实调用，再考虑接回页面。只做免费开发/离线验收，不修改现有服务、
安全设置、旧实验、旧账本或已消费授权。没有读取真实 API key 或发起付费请求。

**实现**：独立 SQLite 持久预算账本，FULL 事务先提交 reservation 与原始请求；回包先持久化再核验
原始 usage/model，最后结算。每 arm 一次 claim、全局/每臂次数与金额限制，复制路径/状态损坏拒绝。
超时、断流、非 200、未知 model/usage、进程退出或落盘失败均保留未结算预留并禁止自动重试。
协议错误若发生在有效 usage 结算后，保留已知费用并 halt。计费全用整数 micro-CNY。

新增 OpenHands→DeepSeek Chat Completions 序列化/响应适配；只发送文字、固定 deepseek-flash
与官方 endpoint、非思考/非流式，最后一轮强制 finish，拒绝无配对工具结果/坏 JSON/异常整数。
当前 transport 仅接受 httpx.MockTransport，真实入口仍无条件拒绝；未制造任何真实授权。

**实际验证**：SDK/预算最终 25/25（原 SDK 7 + 新增18），原核心/LocAgent 回归26/26。
新增真实子进程在 reservation commit 后 os._exit(17) 验证重开账本仍阻止续跑；HTTP 模拟断流保留
原始前缀；并发只有一个 in-flight；8 次最大 usage 为16.842752元、低于17元停止线。
完整双组预算仿真各2次请求、共4条 settled，待核对预留0，network_attempts=0；真实调用/费用0。
仿真账本0.0112元来自人为固定1000/100 token，只是模拟核算，非真实费用或费用预测。

**排错**：首轮新增15项因macOS /var→/private/var临时路径别名被canonical校验拒绝；只修正测试
夹具resolve，未放宽生产边界。初轮失败日志保留。原旧引擎仍未修改。

**可批准方案**：一个自写greeting/farewell样例，不带评测gold；同一SDK两臂各最多4次，总8次；
deepseek-flash，输出1024、源码正文14336字节。2026-11-12官方人民币高峰价输入全miss2元/百万、
输出8元/百万，完整1,048,576上下文保守预留2.105344元/次，总停止线17元。需要新用户批准及账户
计价确认，旧授权不继承。真实授权领取/网络入口尚未启用；批准后仍须接入消费一次的批准标记，
不能把本次simulation.sqlite当作真实可用授权。

**前后端**：已只读审查local_web.py/local.py/local_web_assets/app.js和异步api/store/worker。
建议优先复用本地页面的计划、轮询、结果、源码、轨迹和费用组件；后端增加白名单SDK执行器及
SQLite→accounting、SDK event→messages投影。保留Host/Origin/session/CSP/密钥及paid开关。
未启动网页、PostgreSQL或改schema；不是“已经接回页面”。

**证据**：[真实调用准备](../2026-11-12/task/REAL_CALL_PREPARATION.md)、
[前后端建议](../2026-11-12/task/FRONTEND_BACKEND_INTEGRATION.md)、
[25项测试](../2026-11-12/task/verification/preparation-tests-final.log)、
[26项回归](../2026-11-12/task/verification/core-regression-after-prep.log)、
[冻结proposal](../2026-11-12/task/verification/deepseek-preparation-v1/proposal.json)、
[仿真账本汇总](../2026-11-12/task/verification/deepseek-preparation-v1/budget-summary.json)。

## 2026-11-12 UTC｜锁定的真实传输、一次性授权与离线验收

- 接续 OpenHands 只读 Agent，不替换旧 harness、检索、评测或账本。工作目录 `/Users/xiaomu/Documents/Codex/2026-11-12/task`。
- 新增 `authority.py`、`live_transport.py`、`transport_worker.py`、`live_session.py`、`live_run.py`；SDK 同一循环接入真实传输分支，默认锁定。方案/代码/源码/依赖/引擎绑定；24 小时授权、一次领取、固定账本、每个请求一次传输票据。
- 每次先提交 SQLite FULL 预留，再传输，原始响应先落盘再结算；未知请求保留全额、不重试。HTTP helper 固定官方端点、禁代理继承/重定向/重试、60 秒总时限；两组独立进程，父管道存活检查及取消清理。
- 密钥仅在未来获授权后的本地隐藏终端输入，内存/匿名管道传递；不从环境或文件读取，不进入 SDK/模型正文/账本。当前没有读取、保存真实密钥或发起付费请求，也没有创建本方案真实 grant。
- 官方价格复核：deepseek-flash（DeepSeek-V4.1-Flash-1017），高峰 cache-miss 输入 ¥2/百万、输出 ¥8/百万；每次最保守 ¥2.105344，8 次 ¥16.842752，拟授权 ¥17。账户币种/全包价未核实，须用户确认。
- 新增 15 项测试，SDK/预算/授权 40/40 + 核心/真实 LocAgent 26/26 = 66/66。真实传输分支全部用模拟 helper/MockTransport 验收，没有网络付费调用。首次 6 项因时间取值差导致期限多出微秒被拒；统一时间后通过，失败记录保留。
- `verification/deepseek-preparation-v2`：两组各 2 次模拟 HTTP、4 条 settled，完整 SDK + 真实 LocAgent 检索完成，网络尝试 0；¥0.0112 仅虚构 usage 核算。v1 证据未覆盖。
- 新方案 hash：`7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f`。精确范围、发送内容、运行命令和限制见 `LIVE_PILOT.md`。
- 仍待：用户对该方案和人民币账户价格明确批准、本地安全输入 key、第一条真实供应商回包验收。没有改前后端或安全设置，无 Git 提交/推送。旧基础组 15 题未终答结果不用于性能优劣结论。

## 2026-11-12 UTC｜用户批准后的价格与重复启动检查

- 父线程提供可信会话证据：用户同意单个自写样例、基础/检索各最多 4 次、总共 8 次、费用上限 ¥17 的一次试跑，不覆盖后续评测。
- 冻结方案 hash `7f03d3dd6d1c39a47ac401f294ed95273d8caf52a65ca3823f17328b4a2a916f` 与当前代码/源码/依赖/引擎绑定一致；检查时不存在 grant、claim 或真实账本，没有重复启动记录。
- 通过浏览器只读查看当前登录的 DeepSeek 官方账户：CNY；“产品定价”跳转官方中文价格页，deepseek-flash 高峰输入 cache miss ¥2/百万、输出 ¥8/百万，符合预算假设。未进入 API keys 页面，未读取密钥。
- 已记录上述范围的一次性 24 小时 grant；未消费领取票据、未创建真实账本、付费请求 0 次。详情 `verification/APPROVED_PREFLIGHT.json`。
- 运行等待用户在本机终端隐藏输入该账户 key，不能发到聊天。可见余额 ¥2.86 低于总保守预留，未充值；如余额不足或任何供应商/协议异常，停机不重试。当前尚不能把未输入的 key 与可见账户验证绑定。

## 2026-11-12 北京时间｜首次真实试跑终答协议诊断与离线修复

- 用户报告 `Stopped: RuntimeError. No automatic retry.`。只读检查真实账本：基础组 3 次 DeepSeek HTTP 200，均 settled；模型成功 list_files/read_file 并找到 greeting 函数；检索组未启动。
- 结算费用上界 ¥0.008236，未知预留 ¥0；不是供应商实扣核验金额。保留原始失败结果、轨迹、授权和账本，未续跑、未消费剩余次数、未读取密钥。
- 根因：原生 SDK FinishTool 的 message schema/描述是自由文本，而本地适配器额外要求内嵌 JSON。模型返回自然语言终答，JSON 解析失败；正向脚本测试预先构造 JSON，漏掉协议矛盾。
- 修复：模型端显式 object schema（files/entities/answer），校验后转换为 SDK 原生字符串；原始回包不改写。保留第一个停机原因，终端输出可读原因和预算状态，不输出原始异常文本。
- 新增 6 项真实回包回归；SDK/预算等 46/46，核心/真实 LocAgent 26/26，总计 72/72。新双组完整离线回放各 2 次模拟 HTTP 均完成；没有新增真实模型请求。
- 修复方案 hash `6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd`，未授权。原授权限定一次试跑、出错即停；不自动新建 grant 或重试。
- 交付 `FIRST_LIVE_FAILURE.md`、`verification/FIRST_LIVE_INCIDENT.json`、`tests_sdk/fixtures/first_live_finish_incident.json`、`verification/deepseek-preparation-v3-finish`。原终答不自动改判成功，不作两组效果比较。

## 2026-11-12 北京时间｜修复版获准试跑，等待本地密钥输入

- 用户明确“批准试跑修复版”。核对冻结代码/源码/引擎一致、新方案无重复启动；公开价格再次核实 ¥2/¥8，高峰预算假设不变。
- 新方案 hash `6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd`，一次性 grant 已记录；每组最多 4 次，总计 8 次，新一轮上限 ¥17。到期时间北京时间 2026-11-13 16:53:43。旧轮 3 次请求及费用上界 ¥0.008236 保留独立账本。
- 当前未领取授权、未创建真实账本、新增付费请求 0 次。未读取或保存密钥。
- 尝试通过电脑操作工具打开本地 Terminal 输入提示，被工具明确禁止控制 com.apple.Terminal；操作未执行。已检查父线程消息，没有新的相关权限依据，不重试或绕过限制。需用户在本机终端手动执行新命令并隐藏输入 Key。
- 记录见 `verification/REPAIRED_PILOT_APPROVAL.json`。本次未改代码，无需重复测试。

## 2026-11-12 北京时间｜修复版首次真实双组试跑完成

- 用户在本机终端完成隐藏 Key 输入并报告“好了”。只读检查真实账本、两组结果、工具审计和原始回包，修复版 hash `6f90eb47be9dd29ced74ae7ed85bf65fd83cf394516d851e1754ae4e098f0bcd` 绑定一致。
- 两组均 completed/finished，均定位 `src/greeting.py:greeting`，各 3 次模型请求；6 次均 HTTP 200、settled，源码工具调用均无错误，两个 arm token 均 finished。
- 基础组实际调用 list_files/read_file，检索工具可用组实际调用 search_text/list_files/read_file，**没有调用 locagent_retrieve**。不声称真实模型检索执行验收或检索收益；样例非 benchmark。
- 本轮账本费用上界 ¥0.019130，未知预留 ¥0，未 halt；加上失败轮共 9 次请求，上界 ¥0.027366。不是供应商实扣金额。
- 验收期间未读取密钥、未追加模型调用、未修改原账本/结果或重置授权；无需改代码和重复运行离线测试。前后端尚未接新 Agent。
- 交付 `LIVE_PILOT_RESULT.md` 与 `verification/LIVE_PILOT_ACCEPTANCE.json`；保留前一轮失败诊断及全部历史证据。

## 2026-11-12 北京时间｜跨文件检索自主选择试跑的离线准备

- 新增自写 10 文件、2710 字节 webhook 投递开发样例：跨文件追踪重试资格、delivery_id 复用、已确认投递拦截及防重局限。未执行待理解源码。
- 新增只读审计器：原始调用 → SDK Action/Observation → 紧接的出站 tool 消息 → 正常 finish，以 call ID、原文内容哈希与源码/运行绑定核对。区分 scripted_fixture、live_auto_selection 和 live_forced_tool_policy；不将证据进入上下文或答案路径交集解释为因果收益。
- 双组离线回放各 3 次模拟 HTTP 均完成。检索脚本调用真实 LocAgent 一次，返回 1642 字节源码证据并原样进入下一轮上下文，正常终答；属于脚本连通性，不是自主选择。
- 10/10 新增可观察性/样例选择测试，46/46 SDK/预算/授权回归通过。旧真实试跑审计正确报告未选检索；两个既有付费账本哈希保持不变。
- `live_run.py` 增加固定 `--case crossfile` 选择并传入隔离 worker；错误样例与 grant 不符时，在密钥提示及领取前拒绝。未改变工具描述、检索算法或预算；新旧样例都需匹配自己的方案哈希。
- 新提案：baseline + retrieval 同题对照，各最多 4 次、总计 8 次 deepseek-flash，请求只发送通用提示/题目/工具定义及白名单源码证据。高峰 ¥2/¥8 公开单价复核；完整预留 ¥16.842752，拟独立上限 ¥17。
- 调查阶段 auto、不在题面/提示强制检索；若模型仍未选择，记 not_selected，不能自动换题、补跑或转强制调用。强制工具调用的真实连通性诊断不在本次付费提案中。
- 最终 hash `7295139e58ac88d2d500f50e7b8c0fcafca1d9d9df5b4d114dc8d1a0b8b56a2a`，未授权、未创建 grant、未读取密钥、新付费请求 0 次。详见 `RETRIEVAL_CHOICE_PREPARATION.md` 和 `verification/crossfile-choice-v2`。
- 当前检索仅文件/实体标识 BM25 与精确实体读取，不是代码语义检索；此样例不代表 benchmark，也不保证自主调用。本轮未修改前后端。

## 2026-11-12 北京时间｜跨文件自主选择试跑获准，等待本地输入

- 父线程提供用户明确同意：10 文件自写 webhook 样例、基础与检索组各最多 4 次请求、总最多 8 次、新一轮上限 ¥17；自主选择检索，不强制、不补跑。
- 新方案 7295139e58ac88d2d500f50e7b8c0fcafca1d9d9df5b4d114dc8d1a0b8b56a2a 当前代码/源码/引擎绑定匹配；无该方案 grant/claim/真实账本，旧轮均无未知预留。再次核实官方高峰 ¥2/¥8 单价，与原人民币账户预算假设一致。
- 已通过 --case crossfile 记录一次性 grant，到期北京时间 2026-11-13 17:40:08；当前尚未领取或创建真实账本，新增付费请求 0 次，未读取或保存 Key。
- 因已知电脑操作工具禁止控制 Terminal，不重复尝试或绕过限制；需用户在本机终端执行新命令并隐藏输入同一人民币账户 Key。
- 详细记录 verification/CROSSFILE_APPROVED_PREFLIGHT.json。原代码/工具选择策略/预算未改，无需重复测试。

## 2026-11-12 北京时间｜跨文件试跑收尾失败，检索组未运行

- 用户报告完成后，只读检查计划 `7295139e58ac88d2d500f50e7b8c0fcafca1d9d9df5b4d114dc8d1a0b8b56a2a` 的真实账本、出站请求、回包和 SDK 工具审计。
- 基础组第 4 次请求仅提供 finish、tool_choice 指定 finish、非思考模式；HTTP 200 回包仍返回 read_file(metrics.py) 与 read_file(reports.py)。本地 normalize 在仅允许 finish 时离线复现 unavailable_or_invalid_tool_call；两个越界工具未执行。
- 前 3 轮共执行 10 次调查工具；4 次付费请求均 settled，账本费用上界 ¥0.018574，未知预留 ¥0。halted/needs_review 是协议错误，不是未结算费用。所有三轮累计 13 次，上界 ¥0.045940。
- 按异常停止约定，检索组没有启动；记 not_run，不误记为自主未选择检索，不作检索收益结论。没有第 5 次请求或自动补跑。
- 官方 Chat Completions 文档支持非思考模式指定工具；当前回包与请求约束不符，不能据此确定供应商内部原因。现有本地执行边界正确拒绝越界工具。
- 尚未增加显式收尾消息，作为后续离线改进方向；本轮只检查和归档，没有修改运行代码、权限、授权或模型参数，未读取密钥。
- 交付 `CROSSFILE_LIVE_RESULT.md`、`verification/CROSSFILE_LIVE_INCIDENT.json` 和 `verification/crossfile-closing-exchange.json`；原结果和账本保持不变。

## 2026-11-12 北京时间｜显式收尾控制与硬预算保护修复

- 复盘跨文件第 4 轮：出站仅 finish、非思考且指定工具，回包仍要求 read_file；本地正确拒绝。确认没有逐轮剩余预算或末轮显式控制消息，可能助长模型继续遍历文件；不声称已确定供应商内部原因。
- 新增 control.py：逐轮预算通知、最后一次响应预留 finish、调查关闭时明确禁止继续读取并允许证据不足终答。消息只进入当前请求，不改写源码证据或累积历史。
- 调查额度关闭时主动封闭 ToolSession 执行器；保持出站工具收窄、入站允许列表、请求/工具/源码/费用限额。仍各最多 4 次，无第五次修复调用、无自动重试。
- 新增明确协议错误分类及结果/终端说明；原始 usage 先结算再校验协议，已知费用保留 settled，未知费用保留预留。controller_policy 随代码/方案/授权绑定。
- 本轮 56 项 SDK/预算等、10 项可观察性、26 项核心/真实 LocAgent，共 92/92 通过。首次两项失败为历史消息测试夹具缺 SDK name 字段，修正夹具后通过，失败日志保留。
- 双组 3 轮提前终答及双组 4 轮最终收尾回放均完成；真实检索返回 1642 字节仍进入下一请求。原失败回包在 SDK+模拟 HTTP 下仍被拒绝，额外工具不执行、无第 5 次调用，预算正常结算。
- 三个历史付费账本哈希未变，原结果保留。本轮没有读取密钥、创建新 grant 或发出付费请求；模拟成功不等于真实模型收尾率已提高。
- 下一提案保持 10 文件 crossfile、deepseek-flash、两组各最多 4 次，总最多 8 次、上限 ¥17；新增逐轮预算与明确收尾消息，其余自主检索原则不变。
- 新 hash `487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35`，未授权。详见 CLOSING_REPAIR.md、verification/CLOSING_REPAIR_SUMMARY.json 与 crossfile-closing-final-turn-v1。

## 2026-11-12 北京时间｜收尾修复版试跑授权与启动检查

- 用户已批准同一 10 文件 webhook 样例修复版试跑；绑定方案 `487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35`，两组各最多 4 次 deepseek-flash 请求，总计最多 8 次、17 元。模型自主选择调查工具，不强制检索，不自动补跑。
- 当前源码、依赖锁、LocAgent 引擎及控制策略与冻结 proposal 完全一致。官方价格重新核实，高峰缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens；8 次最保守预留 16.842752 元。账户范围仍为此前核实的同一 DeepSeek 人民币直连账户。
- 一次性 grant 已登记，24 小时有效；尚未 claim，尚无新运行账本。三个历史账本无未结预留，SHA256 均保持原值；没有重复启动。详细时间和检查记录见 `verification/CROSSFILE_CLOSING_APPROVED_PREFLIGHT.json`。
- 本阶段新增付费请求 0 次，未读取密钥。等待用户本机终端隐藏输入 Key 后执行；Terminal 的电脑控制此前被工具拒绝，不重复尝试或绕过。运行异常即停止，后续只检查结果。
- 本次仅登记授权，没有修改已通过 92 项离线测试的运行代码。初始只读核对脚本误把 proposal 当成包装对象，KeyError 后改正读取结构；未涉及模型、传输或运行重试。

## 2026-11-12 北京时间｜收尾修复版真实试跑验收完成

- 用户本机执行方案 `487db3f3f70cd32b3b136a4f462158d4096e2a6921c5e3b0bdecb5fd484f5b35` 后，两组均 completed / SDK finished，各 4 次请求，第 4 次均提交单个 finish；原始出站控制、原始回包和 SDK 事件链核对通过。
- 总计 8 次 HTTP 200，均 settled，固定保守价格费用上界 ¥0.051510，未结预留 0，未自动重试或追加请求。当前一次性授权已消费；此次验收本身新增请求 0。
- LocAgent 在检索组已开放，但模型只选择普通搜索、列文件和读文件，检索调用 0；准确结论为“未选择”，不可宣称检索收益或真实自主检索链已验证。
- 两份终答人工核对覆盖身份保持、重试条件、发送前回执检查及内存/竞态限制。基础组另有 cleanup 证据，检索可用组未读并标注不确定性；不作质量评分或因果比较。
- 三个历史账本 SHA256 保持原值，原失败结果保留。本次账本 SHA256 为 `3c8f1a736296e8a970b1f2f16a69047a68a93db9ecb4e769961a9f118366221a`。
- 详细证据：工作区 `verification/CROSSFILE_CLOSING_LIVE_ACCEPTANCE.json` 与 `CROSSFILE_CLOSING_LIVE_RESULT.md`。本轮未改运行代码、未读取密钥、未追加付费试跑；后续自主检索验证仍待另行设计和授权。

## 2026-11-12 北京时间｜自主检索未选择的离线分析与说明修订

- 审阅原始真实请求/回包：LocAgent 在前三轮均开放且 tool_choice=auto；模型选正文搜索 webhook、列出 10 路径后批量读取 7 文件，第 4 轮正常 finish。无检索失败记录、无公开放弃检索理由；不能强行归因。
- 五个人工选择查询通过现有离线 LocAgent 接口验证：webhook 在正文命中但实体索引为空；retry、delivery_key、完整实体 ID 返回源码，随机不存在词为空。工具能力区别得到验证，但模型当时未看过这些检索输出，不能用它们解释模型内部选择。
- 仅补清 RETRIEVE 工具描述：标识符词法检索、精确 ID、最多五候选、源码片段与正文搜索的区别，明确无语义检索/调用图遍历。无题目专属提示、不强制检索；题面、预算、工具顺序、协议和算法未改。
- SDK 7/7 测试通过；双组离线回放各 3 次模拟响应正常 finish；一次脚本指定检索的 1642 字节观察结果进入下一次模拟请求，分类仍为 scripted_fixture。五个查询探针网络尝试 0。真实模型调用 0，未读取 Key、未创建新 grant。
- 新首轮出站请求与旧真实请求仅检索描述不同；新方案 hash `fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f`。未来试跑拟同样两组各最多 4 次、总 8 次/17 元，未授权；启动前核价，异常停止，不补跑。
- 四个真实账本 SHA256 均未变。详见工作区 `RETRIEVAL_CHOICE_ANALYSIS.md`、`verification/RETRIEVAL_CHOICE_OFFLINE_REVIEW.json` 及 `verification/retrieval-choice-query-probes.json`。未证明模型会自主选择或存在检索收益。

## 2026-11-12 北京时间｜工具说明修订版试跑授权与启动检查

- 用户批准同一跨文件样例、两组最多共 8 次 deepseek-flash 请求、17 元上限的自主工具选择试跑。方案 `fb1fca68df8be5273ab7d458a44f0075c614f24c7599ba5927e1cf940b925b9f` 与离线冻结 proposal 及当前代码完全一致。
- 官方当前价格重新核实：高峰缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens；八次完整保守预留 16.842752 元。沿用此前核实的同一 DeepSeek 人民币直连账户范围；未读取密钥。
- 创建了独立、24 小时有效的一次性授权。检查时尚未 claim、尚无新账本、无重复启动；历史四个账本均无未结预留，SHA256 保持原值。
- 本阶段新增付费请求 0 次，等待用户在本机终端隐藏输入 Key。此前 Terminal 电脑控制被工具拒绝，未重复尝试或绕过；异常停止，不自动重试或补跑。
- 精确时间和启动检查记录见工作区 `verification/RETRIEVAL_DESCRIPTION_APPROVED_PREFLIGHT.json`。本次未修改已验证的运行代码。

## 2026-11-12 北京时间｜复用本地 .env 与显式密钥加载

- 用户要求后续不反复输入 DeepSeek Key。仅检查文件元数据发现原项目已有当前用户所有、普通单链接、0600 的 `.env`；未读取或输出其内容，未复制、覆盖、改权限。当前工作区没有 `.env`，优先复用原配置。
- 当前工作区新增 `.gitignore`（忽略 .env 变体、私有授权/验收目录及依赖）和无密钥的 `.env.example`。两个目录目前均非 Git 工作树；加载器在有 Git 时额外拒绝已跟踪或未有效忽略的 .env，避免误以为 ignore 能保护已跟踪文件。
- `readonly_agent.local_env` 提供 setup/check/status：用户本机 setup 先复用有效现有配置，缺失时隐藏输入并排他创建 0600 明文文件，不接受 Key 参数、不回退可见输入、不覆盖旧配置。status 只检查元数据，本次只对真实文件运行此命令。明确 .env 是本机明文而非加密。
- 复用已有 python-dotenv 解析能力，但不使用会导入旧付费开关的旧 configure 加载器。只提取 DEEPSEEK_API_KEY，不插值/执行、不导出环境变量；拒绝重复/坏配置、链接、其他用户所有、宽权限和过大文件，错误不输出内容或 traceback。
- live_run 新增互斥 `--env-api-key`，仅在当前授权、方案、未领取状态和本机 TTY 检查通过后读文件；原隐藏输入保留。密钥继续仅经匿名管道传给 helper，不进入 SDK、源码工具、轨迹或账本。
- 新增合成 Key 配置测试 12/12；SDK 全套回归 68/68，提取安全 CLI 错误入口后配置测试再跑 12/12。无真实 Key 读取、供应商请求、软件安装或系统安全设置改动。
- 历史四个真实账本哈希不变，已有 `fb1fca68…` 授权仍未领取且未改写；运行代码哈希变化使它与新代码不匹配。此次没有创建、迁移或消费真实授权，也没有执行旧试跑命令。后续继续试跑需另行审阅绑定当前代码。
- 用户只需在工作区运行 `.venv-openhands/bin/python -B -m readonly_agent.local_env setup` 做本机就绪检查；有效旧 Key 可直接复用，无需重复输入。不要求用户在聊天提供 Key。
- 交付：工作区 `LOCAL_ENV.md`、`verification/LOCAL_ENV_SETUP.json`、`verification/local-env-tests-final.log`、`verification/local-env-sdk-regression.log`。

## 2026-11-12 北京时间｜.env 换绑授权与首次真实自主 LocAgent 检索

- 根据用户对同一样例、最多 8 次请求/17 元的既有批准，先检查旧工具说明版试跑未领取、无运行目录/账本，全部历史账本无未结预留。当前官方高峰输入/输出价格仍为 2/8 元每百万 tokens。
- 在内存反向还原 .env 相关改动后，整体 runtime hash 精确匹配旧批准版本；新旧 plan 除 runtime_hash 外完全一致。冻结新方案 `5cb8a59ad54ba444acf50b9015236b396645254094b493e3a3cbee60decdf8b2`。
- 旧 `fb1fca68…` grant 原字节归档为 grant.superseded.json 后，移除 grant.json 可执行入口、fsync，并复核无 claim/run；保留 supersession.json。之后才将同一用户批准绑定至新方案，无两份同时可用的授权。
- 通过受控 CLI --live --env-api-key 执行一次。程序在授权/范围/TTY 检查后复用原私有 .env；Key 不显示、不复制，不放入模型、日志或子进程环境。没有自动化 Terminal 应用、改系统安全设置或要求用户再输入 Key。
- 两组均 4 次真实请求、SDK finished；8 次 HTTP 200 全部 settled，总保守费用上界 ¥0.052532（基础组 ¥0.025462、检索组 ¥0.027070），未结预留 0，无重试/补跑。新授权已消费，旧授权已失效且仍无运行；四个历史账本哈希不变。
- **首次观察到真实自主检索**：第一轮 tool_choice=auto，模型自行调用 locagent_retrieve，query 为 webhook delivery retry；工具成功返回 retry.py 相关源码。call ID/参数、SDK action/observation、完整 1642 字节观察结果进入第 2 次真实请求、正常 finish 的链路全部核验通过，分类 live_auto_selection，chain_verified=true。
- 两组第一轮出站与 .env 改动前冻结的工具说明版第一轮出站完全一致。单次结果不证明描述调整的因果效果或检索收益；检索组未读 http.py，缺少 Idempotency-Key 的证据，其超时重试表述未由已读代码确立，不做质量评分。
- 当前账本 SHA256：d5da0c98137ec3b637a578733813ee18faf8f88309dbf5e3189cfbc5778cdc94。交付 `ENV_REBOUND_LIVE_RESULT.md`、`verification/env-rebound-v1/live-acceptance.json`、`retrieval-observability.json` 及冻结 proposal/preflight。无剩余用户操作或未结请求；后续新试跑不自动执行。

## 2026-11-12 北京时间｜六题配对开发集冻结与离线准备

- 盘点当前 greeting/webhook 既有真实暴露：5 个账本、29 次请求，均排除新汇总；旧真实仓库题曝光未全面重审，未导入。新题为开发者可见的自写开发集，不称独立测试。
- 冻结六题：租户缓存、配置覆盖、文档权限、分片上传、任务租约、CSV 导入；每题 6 个文件，共 36 文件/7851 字节。题面、源码、评分与工具预算绑定 manifest `97cdebd2b53e53bd9d5793a85a82feb00d81bd8e1ab1883f8284ac34e211a063`。
- 同 SDK/DeepSeek 模型/题面/源码/预算，仅检索组多 LocAgent；每组 4 次响应、末轮保留 finish，调查 auto；固定顺序并交替组别先后，新进程/会话隔离。每题17元/8请求，总提案102元/48请求，完整保守预留101.056512元；本阶段官方峰值输入/输出2/8元每百万token已核实。
- 评分冻结为精确文件/实体 P/R/F1/RR、每题四项人工证据标准；盲化组别后评分，记录失败/not_run、全计划分母与完成配对结果，不剔除失败后声称收益。记录自主检索链、定位、费用、进程耗时与失败；脚本结果不评分质量。
- 新离线 BatchGuard 持久整题预留与固定顺序单次领取，累计102元，pending/未知/失败阻断后续，不重试。现有题内账本保留4/组8/题17元保护。真实批量入口目前仍拒绝 live；用户确认后还需整套真实授权及执行适配的离线验收，不能直接用旧单题入口启动六题。
- 新测试8/8；12隔离SDK分组全部正常finish，共48模拟请求。六次脚本LocAgent调用全部成功、结果传入下一模拟请求；5题返回源码，d06 invoice查询为空，负例保留未调参。所有调用仍标scripted_fixture，无自主选择或模型质量结论。
- 真实付费请求0、密钥读取0、新真实授权0；五个历史账本SHA256未变，未执行题目源码。交付 `DEV_SUITE_PREPARATION.md`、`development_suite/v1/manifest.json`、独立rubrics/exposure文件、`verification/dev-suite-v1/acceptance.json` 与 measurements。

## 2026-11-12 北京时间｜六题真实批量执行适配与离线验收

- 在不改变六题源码/题面/评分/顺序/工具预算的前提下，新增 experiments.dev_batch 的整套一次性授权、子授权和真实CLI适配。原规范97cdebd2…保持不变；可执行方案冻结为 d172860ae92d532c0ff60d6eded56b2d11de63a7672737076611c8be8610badb。
- SuiteAuthority绑定完整hash、CNY价格2/8及总上限102元，24小时一次性领取；外层SQLite固定6题/12组顺序和整题17元预算占用。子授权不能被普通单题Authority读取；每次传输重新检查套件及当前题/组状态，保留题内4/组8/题17元账本和一次性请求票据。
- 生产执行每组固定新进程，stdin管道传凭据，清洁环境，无Key参数/日志；360秒超时终止整个进程组。任意失败停止全套，保留完成组、失败组和后续not_run；没有resume或自动补跑入口。私有.env只在有效授权/未领取/TTY检查后由程序加载。
- 新结果报告记录定位、usage、保守费用/未知预留、进程耗时、自主检索链和失败；真实完成组生成盲化人工评分包，模拟组标mocked_live_transport/scripted_fixture且不评分质量。
- 全SDK测试89/89（新增批量13项）；覆盖并发领取、重复运行、最大48次/101.056512元用量、超限拒绝、子授权停机约束、坏Key不领取、超时进程清理及密钥管道。首版最大用量夹具漏id被正确拒绝，补齐合成id通过，旧失败日志保留，未放宽生产校验。
- 真实SDK/授权/账本路径通过MockTransport验收：正常6题12组48模拟请求completed；首题第二组收尾越界在第8次停机，1完成1失败10未运行且无待结；首题第二组首轮超时在第5次停机，保留2.105344元请求预留和17元整题占用，没有后续题或重试。全部网络尝试为0。
- 当前官方价格再次核实高峰输入cache-miss2元/百万、输出8元/百万。拟真实范围最多48请求、102元硬上限；101.056512元是全上下文最大保守预留，不是预估/实际扣款；已结上界也未与供应商账单对账。
- 本阶段真实供应商请求0、真实Key读取0、新真实授权0；测试授权仅在临时/verification目录，authority-batches尚未创建。五个历史真实账本哈希不变。交付 DEV_BATCH_LIVE_READY.md、development_suite/live-v1/manifest.json、verification/DEV_BATCH_READY.json，以及正常/收尾/超时验证记录和89项测试日志。
- 剩余启动条件：用户明确批准六题48次/102元，启动前核价和模型别名/无重复运行，再登记套件授权并运行一次；不能沿用旧单题17元批准。本阶段没有启动真实批次。

## 2026-11-12｜六题批准试跑：首题 finish 输出截断后停止

- 用户明确批准六题最多48次DeepSeek请求、总上限102元后，复核官方价格2/8元每百万tokens、同一既有私有.env元数据、冻结hash d172860a…及无重复启动，登记并领取一次性套件授权，运行一次。未显示或复制Key。
- d01_cache基础组进行了4次真实请求，前3次执行list_files×1、search_text(cache)×1、read_file×6，读取全部6文件；源码返回累计2915字节，耗时15.719秒。
- 第4次仅提供并指定finish；供应商实际返回finish但finish_reason=length、completion_tokens=1024。适配器以model_output_truncated拒绝，无有效终答。整套停止，无自动重试、补答或续跑。
- 基础组1失败5未运行；检索组6未运行；完成配对0。不能说模型未自主选择检索，也不能比较检索收益。盲评包为空；失败0分与未运行空分分开记录。
- 4次HTTP200 usage均已结算，输入7307/输出1476tokens；保守费用上界0.026422元，无待结请求预留。外层17元为首题本地预算占用，不是扣款，实扣尚未与供应商账单核对。剩余44次没有使用，授权已消耗。
- 停止后只读审计确认冻结代码/题目/评分未变，五个历史真实账本哈希未变；新增d01暴露记录，不改旧冻结快照。未修改运行代码或创建新授权。
- 交付DEV_BATCH_LIVE_RESULT.md、verification/DEV_BATCH_LIVE_INCIDENT.json、verification/DEV_BATCH_EXPOSURE_DELTA.json及原始批次measurements/stopped/receipt/SDK轨迹。下一步可离线检查终答长度与格式；更改输出上限需重算预算、重新冻结并另获试跑授权。

## 2026-11-12｜六题终答长度修复与离线验收

- 核对d01基础组真实第4次请求/回包：只提供且指定finish，回包也为finish；finish_reason=length、输出1024tokens，4066字符参数未闭合。旧answer schema允许4096字符、提示仅泛称简洁；确认直接故障是截断，不能证明模型长文选择的全部原因，不把半截答案补齐计分。
- 最小通用修复：answer上限1200字符，系统/工具描述/收尾提示共同明确简洁长度及证据/不确定性；输出预算2048tokens，同步SDK、wire、usage、独立helper和预算预留。两组相同，每组仍4请求、无补答或重试。截断或超长终答继续严格拒绝，已知usage先结算，未知费用保留。
- 97/97 SDK、23/23核心测试通过。新增真实截断、Unicode/转义边界、1201字符拒绝、旧/新token上限截断、helper固定cap、旧批次启动前不读Key等测试。首轮3处测试夹具问题（旧预期费用、两处macOS临时路径未resolve）修正，未放宽保护，失败日志保留。
- 五条完整批量模拟：正常48请求12组完成；原始/新上限截断均4请求后1失败11未运行；收尾越界8请求后1完成1失败10未运行；超时5请求后同样停止并保留2.113536元待结。全部MockTransport/合成Key，网络尝试0、真实请求0、真实Key读取0、新真实授权0，不代表模型质量或自主选择。
- 53个历史账本、v1源码/题面/评分/暴露记录及manifest哈希不变。新base冻结f37d1e81…，新live方案4958a23e559dd53269cb04cebfb00cb5c1d73d527c29baf2fb6cc0fb0fc5dffd；旧已消耗授权不能复用。
- 官方高峰价格再次核对输入全miss2/输出8元每百万；新每次保守预留2.113536元，每题8次16.908288元，全套48次101.449728元，仍在每题17/整套102元硬上限内。这是最大预算保护，不是预计/实际花费；新试跑前还要核对账户适用价。
- 建议另获批准后从头重跑同六题的双组开发复测，不拼接旧结果或续跑旧批次。d01已真实暴露并用于调试，其余五题此前未发送真实评测模型；整个集合仍为自写开发集，不是独立测试。真实模型能否遵守新长度约束尚未验证，不声称彻底消除截断。
- 交付FINAL_LENGTH_REPAIR.md、verification/FINAL_LENGTH_REPAIR_ACCEPTANCE.json、原始回归fixture、v2基础和执行manifest以及所有测试/批量模拟日志；本阶段没有付费调用。

## 2026-11-12｜修复版六题重跑：完整终答被正文硬上限拒绝

- 用户明确同意修复版同六题从头重跑，范围48请求/102元。复核官方价格2/8元每百万tokens、冻结4958a23e…、旧批次halted及无新批次，检查既有私有.env元数据后登记一次性新授权并启动一次；没有显示或复制Key。
- 首题基础组3次HTTP200：list_files×1、search_text(cache)×1、read_file×4，源码返回2434字节，耗时12.741秒。第3次自主提前finish，完整JSON、finish_reason=tool_calls、输出542tokens，正文1527字符。
- 新增1200字符硬校验拒绝完整终答，reason=finish_message_contract_error；这是本地协议门槛问题，不是再次token截断。诊断副本移除正文后其余字段/源码成员校验通过，但未将副本或拒绝答案评分、未放宽规则改写原结果。
- 整套按冻结规则停止：基础组1失败5未运行、检索组6未运行、配对0。无第4次请求，无自动重试/追加/续跑；不能声称检索没被选择或比较检索收益。一次性授权已消耗，剩余45次未使用。
- 真实usage合计输入5279、输出859tokens；输入缓存命中2304/未命中2975。按高峰全miss保守已结上界0.017430元，无待结请求预留。17元是外层本地题目预算占用，不是扣款；供应商实扣未对账。
- 53个历史账本/v1冻结数据文件哈希不变，当前冻结代码/题面/评分不变。新增d01暴露记录，两批累计7次真实请求，其余五题仍未发真实模型；仍仅开发排错数据。
- 交付DEV_BATCH_V2_LIVE_RESULT.md、verification/DEV_BATCH_V2_LIVE_INCIDENT.json、DEV_BATCH_V2_EXPOSURE_DELTA.json和原始receipt/测量表/停止状态。建议下一步离线区分简洁风格目标与解析硬上限；本轮不修改实现、不创建新授权、不继续调用。

## 2026-11-12｜取消终答字符硬限制与异常证据报告修复

- 本地工作区可访问并实际执行离线开发。核实v2原始三次回包：最后finish JSON完整、正文1527字符、输出542tokens；失败来自本地1200字符硬限制，非token截断。原失败结果和费用不改写、不回溯评分。
- 1200字符改为明确的软风格目标，answer schema及两层校验取消字符上限，完整答案不截断、不缩写、不调用模型修复。仍保持2048输出tokens、原始回包64KiB、字段类型/文件实体来源约束。离线response_bytes从8KiB对齐真实64KiB；真实传输容量未增加。
- 超大回包模拟发现事后审计解析不完整JSON导致报告失败；修复为先验hash，再明确标记未结/不完整/缺失receipt的证据缺口，异常工具参数不可验证，不能误报未选择检索。执行停机、未知费用预留、篡改检测均保留。新manifest绑定审计模块hash。首轮失败日志保留。
- SDK99、核心23项通过；报告修复后审计12项及受影响批量13项通过，13为SDK子集。覆盖历史完整终答原样接受、1201/1527/5000字符及Unicode/转义、字节上限、token超限、截断、收尾越界、费用上限与重复启动。
- 最终六条模拟：正常48请求12组完成；真实三次回包离线重放+其余夹具47请求12组完成，原1527正文相等；截断4请求停机；越界8停机；超时5/超大回包3停机且各保留2.113536元未知预留。全部MockTransport和合成Key，网络尝试0，不代表新模型表现或自主检索。
- v1/v2历史数据和账本保留，新base冻结2bc53a6a…，新live方案34246247d2f59a8626aae8338b92f1183904874835f9fcc63b41f3775848f56e，未授权。本阶段真实请求0、真实Key读取0、新真实授权0。
- 下次提案仍同六题双组从头开发复测，最多48请求/102元，每题17元；保守最大预留101.449728元不变。官方高峰2/8价格再次核对，启动前须核账户价及新批准。d01已暴露7次且用于修复，整套不称独立测试；真实新提示表现尚未验证。
- 交付ANSWER_POLICY_REPAIR.md、verification/ANSWER_POLICY_ACCEPTANCE.json、v3 manifests、原始回归fixture及全部测试/模拟日志。无真实试跑启动。

## 2026-11-12｜v3六题真实配对试跑全部完成

- 父线程先前启动被审核拦截且未执行；新直接确认明确覆盖向DeepSeek发送六题题面、工具定义、相关源码和本题历史，48请求/102元。通过用户历史读取核实确认，复核官方价格、v3冻结34246247…、旧批次halted、新批次不存在和既有私有.env元数据；登记一次性授权，启动获准并执行一次，退出0。未显示或复制Key。
- 6题12组全部正常finish，45次HTTP200完整receipt已结算，0失败、0调查工具错误、0重试；没有使用剩余3次或启动其他样本。基础组23请求/47调查工具，检索可用组22请求/42调查工具。
- 基础工具分布list6/search6/read35；检索组list6/search8/read27/LocAgent1。仅文档权限题检索组第1请求auto选择LocAgent，query为share token access check document，2048字节observation含源码、进入第2次实际请求，SDK事件和终答链均验证。
- 基础组输入41356/输出6349tokens，费用保守上界0.133504元；检索组43876/5994tokens，上界0.135704元。全套85232/12343tokens，合计0.269208元；无待结请求预留，外层题目占用全部释放。实扣未对供应商账单，不能将保守上界当实扣。
- 文件宏F1基础0.808862/检索0.827381；实体宏F1 0.855159/0.855820；两组全部题的关键文件与实体recall均1。分差来自多报项；唯一实际检索题两组定位分相同，不推断检索收益。进程耗时合计74.739/69.836秒，含启动开销，单次无性能结论。
- 人工答案内容标准评分尚未完成，定位命中不等于回答正确。发现原匿名包仍按题/组顺序导出，可能泄露组别；另存按标签排序包供独立复核，本次不声称可靠盲评，不修改原导出或冻结评分。部分缓存答案的TTL/写失败后数据库状态推断需复核。
- 冻结材料及57个历史文件哈希不变，原失败批次保留；新增各题真实暴露记录。全部仍是开发复测，不是独立测试，未拼接旧结果。交付DEV_BATCH_V3_LIVE_RESULT.md、verification/DEV_BATCH_V3_LIVE_ACCEPTANCE.json、暴露delta、排序评审包和原始测量/receipt/SDK轨迹。本次授权已消耗，无后续调用。

## 2026-11-12｜六题回答盲化AI评审完成并解盲

- 用户要求完成盲评。重建随机编号、独立乱序的A/B评审包，移除原标签/题组顺序/轨迹/费用/模型元数据；问题、完整答案、四条冻结标准及36源码文件不变并核验hash。未发现正文显式分组或工具名。
- 两位评审使用不继承原对话的全新上下文，仅分配各自包和源码，独立保存12答案×4标准的二元评分、答案引文、源码行号、理由、不确定性及额外准确性备注。主线程已看过原结果，不参与打分。
- 分歧规则在两份评分产生前固定：一致保持，分歧给第三位全新上下文评审，不提供原分数理由，按多数裁决。A/B 47/48项一致，唯一分歧为配置题第4条“跨句等价表达是否充分”；C判1并标中等不确定性。全评分SHA封存后才读取组别映射汇总。
- 最终基础17/24、检索可用19/24，均分2.83/3.17；逐题缓存3/4、配置3/4、文档3/3、上传2/3、租约3/3、导入3/2。A原始总分17/18、B为17/19；严格解释下差距只有1分。评审失败0，原运行12组完成不变。
- 关键遗漏集中于跨进程/外部依赖假设、令牌验证/有效期、完成及异常状态、ack/renew状态变更、其他异常/额外列处理。另保留TTL一致性保证、DB写失败即无副作用、并发token必定不同等超出源码保证的推断；未解盲后临时加扣分。
- 唯一真实调用LocAgent的文档题两组均3/4；其他分差均在没有调用检索的题上，不能作检索收益或泛化结论。仍为自写开发集，非独立测试。
- 如实限定为盲化AI复核：非独立人类评审，评审模型家族/环境相同，信息边界是任务约束而非OS隔离，不能排除从措辞推断组别。三位均声明未接触映射、其他评分或网络API；无新增DeepSeek/外部模型API请求。
- 冻结源码/标准/runtime及原始套件和六题账本hash保持不变，不覆盖原measurements。交付BLIND_REVIEW_V3_RESULT.md、blind_review/v3内原始评分、裁决、评分前规则、解盲前seal、unblinded_summary及acceptance。开发日志追加保留历史。

## 2026-11-13｜LocBench 两道已曝光开发题接入 OpenHands，离线验收

- 当前工作目录 `/Users/xiaomu/Documents/Codex/2026-11-12/task`。新增 `experiments/locbench_dev/`，冻结 `locbench_openhands/v3/manifest.json`，hash `45688f8a1c3a705b542d39573fcca9176d1e514edc81114de72f636fc0ddbf1c`；报告 `LOCBENCH_OPENHANDS_PREPARATION.md`。
- 旧流水线最新完整 batch101，当前引擎 strict-ready 106（development 29/test 77），历史任意引擎 113；batch102 只有目录，未见结果与验收，不声称已运行。仅检查总体元数据及选中开发题，没有打开未解封测试题内容。
- 选择 `Delgan__loguru-1239@65fe4a8db9a8f297ae3648f51b5e3050b30945a9` 与 `tobymao__sqlglot-3417@e1b6483d5e26d556f6a3dd82c6d35f475c189c2b`；既有开发曝光明确，不称独立测试。全仓 297/325 文件重新核验 SHA-256、Git blob/tree 和缓存提交证据；两组相同非隐藏 Python 投影 163/147 文件。题面逐字对齐，标签独立保存，映射到 AST 与补丁 old-blob；参考修改函数不等于唯一根因。
- 首次离线发现 LocAgent 源码校验按整行比较，误拒 AST 段末行注释：Loguru 13 节点受影响。改为 AST 类型/限定名称/起止行/精确 segment 校验，增加末行注释、Unicode、字符串空白与内容/跨度/名称伪造回归；不放宽来源检查。
- 第二次离线的 `traceback` 查询正确为空，但验收过严。保留词查询及空结果，另加文件列表首路径的显式脚本连通性查询；不修改检索算法或真实提示，不声称自主选择。v1/v2 冻结与中止记录全部保留。
- 最终四组正常 finish，16 次模拟请求，0 网络尝试、0 付费调用；检索结果均进入下一请求（包括空结果）。耗时 Loguru 基础1.88s/检索6.97s，SQLGlot 基础2.00s/检索30.74s，属离线本机开销。65 项测试通过，22 上游证据及746历史文件摘要不变。机器验收 `verification/LOCBENCH_PREPARATION_ACCEPTANCE.json`。
- 拟议真实范围：SDK1.62.0 + `deepseek-flash`（非思考），两题两组每组≤4请求，共≤16请求，每题≤17元、总≤34元，最保守预留33.816576元而非预计花费。2026-11-13 公价输入未命中2/输出8元每百万；账户未核验。发送题面、工具/系统提示、该题本组源码证据及历史，不发评分/补丁/另一组答案。
- 仍需完成两题真实批量入口、一次性授权与预算编排的离线验收，再核实账户/无重复并取得新批准。当前入口仅模拟；未读取密钥、未访问.env、未创建grant、未复用旧授权。实体ID BM25/精确取回、Python投影、小样本、曝光及图重建耗时是明确限制。


## 2026-11-13｜LocBench 两题真实批量入口完成离线授权与预算验收

- 新增 `experiments/locbench_batch/{control,live,report,offline_verify}.py`。复用已验证的 LiveSession/单请求传输/SQLite 子账；独立两题授权域 `authority-locbench/`（已忽略），不修改旧六题驱动或原 LocBench 适配。生产授权目录当前不存在。
- 冻结 `locbench_live/v1/manifest.json`，hash `6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9`；原题面/源码/评分冻结 hash 仍为 `45688f8a1c3a705b542d39573fcca9176d1e514edc81114de72f636fc0ddbf1c`。Loguru-1239、SQLGlot-3417 的已曝光开发属性、提交及分组顺序均不变。
- 一次性 24 小时授权绑定全部代码与数据，原子领取阻止重复/并发启动，子授权依赖当前题/组和总账状态。每题17元占用，每请求2.113536元传输前持久化预留；每组4、每题8、共16请求/34元，最坏33.816576元。跨题账本替换、负费用和组序篡改拒绝；无重试/恢复/追加。
- 60 项测试通过（批量16、live16、终答10、预算18）。真实 SDK+LiveSession+账本通过8场景、53次模拟传输：正常16；第二组超时5；收尾继续读8；第二题超时9；截断4；非法finish4；缺finish4；超大回包3。超时/超大回包保留2.113536元未知预留；已收完整但协议错误的调用按usage结算；剩余组保持not_run。超时杀进程组、密钥仅走匿名管道的单测通过。
- 模拟授权仅在verification目录，合成假密钥，真实.env加载器被替换为报错；网络尝试0、供应商请求0、实际费用0。报告强制区分mocked_live_transport，不对脚本答案打分、不称自主调用。1958份历史材料摘要不变。
- 正式锁定SDK1.62.0，deepseek-flash（公开版本DeepSeek-V4.1-Flash-1017），非思考、temperature0、输出2048；2026-11-13公价复核输入未命中2/输出8元每百万。未访问账户/读取密钥，账户实际全包价格尚待确认；别名由供应商维护，启动前需再核对版本。
- 发送范围仅系统/收尾提示、题面、工具定义、当前组源码证据和历史；不发gold/参考补丁/另一组答案。真实入口现已完成，启动只待新范围批准、账户价格/冻结材料/无重复核查及本机TTY中的已有私有.env加载。本阶段未启动、未创建生产grant、不继承旧批准。
- 报告 `LOCBENCH_BATCH_LIVE_READY.md`；机器验收 `verification/LOCBENCH_BATCH_READY_ACCEPTANCE.json`。保留开发曝光、小样本、Python投影、实体ID检索及图重建开销局限，不声明检索收益。


## 2026-11-13｜批准的 LocBench 两题真实试跑停止：终答额外字段

- 用户明确批准两题数据范围、最多16次DeepSeek请求/34元。当前登录账户CNY，“产品定价”跳官方中文页，deepseek-flash当前版本DeepSeek-V4.1-Flash-1017、峰值输入2/输出8元每百万符合预算。复用既有私有.env，仅运行器加载，不展示密钥。13份旧生产子账按各自冻结预留规则/receipt/hash核对，无未决调用；新生产授权目录此前不存在。
- 冻结hash `6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9` 未变；新一次性grant登记后仅启动一次，审核通过。真实入口退出1，12请求后 `finish_message_contract_error` 停整批，无重试、补跑、修改执行代码或放宽规则。
- Loguru基础4请求，正常finish，7调查调用，11.44s，费用上界0.034822元；检索可用组4请求正常finish，7调查调用，10.07s，费用上界0.035708元。两组都将参考文件放第5位，文件F1=1/3、MRR=.2；参考函数_format_list均未命中，实体F1=0。回答重点为增加测试，自动定位分不等于人工内容判定。
- SQLGlot检索可用组4请求、6调查调用、10.90s，费用上界0.035968元。末轮HTTP200完整JSON，563输出tokens，message多出 `entities_note:null`，违反实际schema的additionalProperties:false，触发字段集合校验；不是截断/字符长度/网络故障。外层summary为SDK合法可选字段。原始终答虽含参考函数，但无有效finish，不计成功；SQLGlot基础组not_run。
- 两个已运行检索组均未自主调用LocAgent（0），没有强制补跑。SQLGlot读取offset5960/5969返回约145行，符合字符游标语义；模型可能误当行号，尚未修复验证。保留原回包和结果；仅对副本做三字段结构诊断，未追认答案。
- 全部12原receipt已结算，输入41977、输出2818（缓存命中17408/未命中24569）；高峰全未命中费用上界0.106498元，账单实扣未对账。未知请求费用0；总账17元案例hold只是失败额度占用，不是新增费用。授权已领取，不可重复启动。
- 报告 `LOCBENCH_LIVE_RESULT.md`；验收 `verification/LOCBENCH_LIVE_ACCEPTANCE.json`；故障原响应/schema `verification/LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json`；生产run下stopped/measurements/账本/SDK轨迹保存。当前计划及13旧账本未变。新增模型曝光：Loguru两组、SQLGlot检索组；一题完整配对、实际检索0，不声明检索收益/退化或独立测试结果。


## 2026-11-13｜SQLGlot 已知空扩展字段最小兼容：仅离线

- 原回包完整、563输出tokens，旧schema拒绝finish.message.entities_note:null；不是截断、缺失必填字段或类型错误。为什么生成该字段无证据，不作模型归因。
- 新wire schema仅显式允许可选entities_note:null；canonical只保留原样files/entities/answer。原回包字节/arguments和账本不变，新增finish_normalization审计事件及报告字段。其余未知字段、非空说明、错误/缺失字段、外层异常参数继续拒绝，不截断或丢弃内容。
- 124项测试与9条完整MockTransport路径通过。原SQLGlot四份回包逐字节重放，SDK正常finish，核心答案一致且仅1条兼容事件；错误字段/路径、截断、收尾越界、超时、超大回包仍停止，未知结果保留预留，不重试、不重复启动。初次测试误把实体语义正确性当协议校验，已修正测试，生产格式验证规则不变，失败日志保留。
- 1,960个历史文件hash不变；312个源码/评分文件不变。原真实运行仍失败，没有追认成功。旧授权不能重启或加载Key；新生产授权未创建。本轮不加载.env，真实模型调用0、费用0。
- source v4 hash 8e178f5756b7e7b16b66cf8ed571702e5a09b7a056cb6a0b0907355cc87751e4；live v2 hash eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83。拟议仍两道曝光开发题/两组最多16请求、34元，需新批准及实际账户价格核查。官方价格再次核实deepseek-flash输入未命中2/输出8元每百万，34元不是预计费用。无检索收益结论；游标混淆未改。
- 报告 FINISH_NULL_COMPAT_REPAIR.md，验收 verification/FINISH_NULL_COMPAT_ACCEPTANCE.json，测试 verification/finish-compat-tests-v2.log，历史夹具 tests_sdk/fixtures/locbench_extra_field_incident.json。

## 2026-11-13｜批准的 LocBench 两题修复版补测完成

- 用户明确批准重新运行两题四组，向DeepSeek发送题面、提示、工具定义、相关源码证据和各组会话历史，最多16请求/34元。当前账户刷新CNY、官方产品报价输入未命中2/输出8元每百万符合预算；15份旧子账无未决请求、无运行中的Python试跑，新生产授权此前不存在。.env元数据未变，仅运行器加载、不展示Key。
- live v2 hash eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83登记一次性授权并仅启动一次；运行后冻结校验不变。16真实请求全部HTTP200/完整/settled，4组正常SDK终答，失败0、重试0、未决费用0、case hold0。
- Loguru基础4请求/6调查工具/12.11s/费用上界0.033304元，检索可用4请求/7工具/11.34s/0.036858元；两组参考文件第5、文件F1=1/3，实体0。SQLGlot检索可用4请求/6工具/12.11s/0.036442元，基础4请求/6工具/12.84s/0.034958元；两组参考文件第1、实体第2，检索可用少报候选使F1 .5高于基础1/3，但没有实际检索，不能归因LocAgent。
- 两个检索可用组locagent_retrieve均0次。四个finish均仅files/entities/answer，兼容事件0；真实schema可用，但本次没有触发已知空字段分支，不能把正常完成直接归因于兼容修复。
- 输入55357、输出3856，cache hit22528/miss32829；全输入按高峰未命中上界0.141562元，不是供应商实扣。34元是最大保护额度。1,960历史文件及15旧账本hash不变，旧失败未追认成功。
- 报告 LOCBENCH_V2_LIVE_RESULT.md；验收 verification/LOCBENCH_V2_LIVE_ACCEPTANCE.json；原账本、16回包、SDK轨迹、答案和measurements保留。已曝光开发样本，不是独立评测；SQLGlot游标混淆仍待离线处理。本授权消耗完毕，没有新增调用或后续评测授权。

## 2026-11-13｜LocBench 两题轨迹、检索与参考映射离线诊断

- 对修复版四组原回包/工具结果/评分核对；两个检索组前三轮实际开放LocAgent且auto，调用0。无模型选择动机证据，不归因“不信任检索”。Loguru实际走测试文件路线，参考函数未读；题面强调补单测而参考补丁改实现，分开看任务建议与定位分。
- SQLGlot两组都从普通搜索获得参考函数名称，但read_file offset5960/5969是字符游标，实际完整行146～270/271，第二页3931/3940字符重复；未读到5969～5987行正文。Loguru offset100同样落到第7行。剩余工具/字节未耗尽，固定第4请求收尾。
- 固定当前实体ID BM25/精确读取，17组与普通搜索配对探测。全文题面999/1386字符均超256上限，显式拒绝，未静默截断。Loguru标题仅Logger.add约49KB，traceback/RecursionError/recursion均无候选；traceback普通搜索65行、含目标文件11行。SQLGlot标题前5无参考函数，SetItem仅表达式类；轨迹已有_parse_set_item_assignment检索目标第1，19行正文第一页1244字节。Loguru参考派生_format_list可第1/761字节，但标明oracle，不当自主发现。整文件检索Loguru耗尽14KiB也到不了目标函数。
- 原标签、base commit、old blob、AST区间及参考patch旧行匹配；四组分数精确复算。Loguru补丁实现重复帧压缩；SQLGlot明确把_parse_id_var换成_parse_column。精确实体返回源码与AST片段逐字一致。仅内存重建文本并ast.parse，不执行目标代码、不改标签。参考函数不是唯一根因/全面答案评分。
- 建议先给两组共同提供按行读取并保留独立分页游标，再验证短候选/正文索引等检索发现能力，最后研究自主选择；预先固定查询、预算和指标，oracle/强制调用单列。没有修改生产工具、提示、预算、检索或冻结方案。
- 17个检索子进程均用已审查工具与offline拒绝保护；不读取凭据，付费请求0、费用0。2,263份历史/冻结文件hash不变，未新增生产授权。报告 LOCBENCH_OFFLINE_DIAGNOSIS.md；证据 verification/locbench-offline-diagnosis-v1/acceptance.json 及轨迹、查询、静态检查JSON。已曝光开发题、知晓参考后的诊断，不是独立测试或盲评。

## 2026-11-13｜共享按行读取修复与检索选择假说：仅离线

- read_file改为start_line/end_line包含端点，一基源码行号；续页采用当前会话/快照/路径/范围绑定的不透明cursor，已签发游标可稳定重放并计预算。拒绝旧numeric offset、伪造或跨范围游标，不静默转换；返回实际行列范围，整行优先，长行可分片，空文件/空行/Unicode/CRLF均处理。两组同一schema/执行器/系统说明；其他工具next_offset保持原协议。
- core respond与SDK均进入LineReader，内部旧字符渲染仅保留历史诊断；搜索行号同步物理CR/LF规则。完整成功JSON计页/总字节预算，超预算保留终答。LocAgent实现和描述未改。
- 153项测试通过，覆盖行边界/类型/路径/冻结快照/Unicode/长行/重复与错误游标/证据编号/预算/SDK/终答/授权账本。SQLGlot原offset5960/5969错页与原回包逐字复现；分析者仅在离线夹具中显式迁为start_line，两组SDK各4脚本请求正常finish，实际含5969～5987函数及5977关键行，正文一致。未声称真实模型学会新接口或消除显式重叠请求。
- 三条批量MockTransport路径：正常16调用完成；收尾越界8调用停机；超时5调用保留模拟预留2.113536元。不发真实请求、不读凭据、不执行目标仓库代码；旧两份授权在读Key前拦截。历史2,263文件hash不变，未新增生产授权。
- source v5 hash 6d742955688ac21b2405cfea1f0cc1807560333e61aa72053ee6ab87c1cc9b79；live v3 hash 1286c563b5825f3ff56ee1b992f0502f4152311eb1430e5e465941b5d3202bd6，只冻结未授权。若日后真实验证仍最多16请求/34元，须新批准/价格核查。
- 仅基于旧轨迹及17组离线探测整理可检验假说：已知文件默认read_file、ID索引首步发现不足、普通搜索已给出候选、调查轮数限制、大结果预算利用率；每项区分证据与推测。优先在共同读取修复后再单因素研究描述/索引/预算，不强制检索、不宣称因果或独立评测。
- 报告 READ_LINES_REPAIR.md；验收 verification/read-lines-repair-v1/acceptance.json；回归 regression.log；SQLGlot回放sqlglot-replay.json。新真实模型请求0、费用0。

## 2026-11-13｜未选检索的逐项假说与区分检查

- 展开H0接入、H1预算、H2发现覆盖、H3搜索功能重叠、H4描述/顺序/名称、H5Loguru题意/评分、H6回包膨胀、H7查询协议，每项列支持、反例、判定及离线可验证/不能验证的边界；不再只笼统称“已整理假说”。
- 原wire核对：检索组6/6调查机会工具在场、auto，固定第四个位置，实际调用0。SQLGlot第2/3轮已收到parser.py:5969和目标符号，尚余14/12调用、12277/7434字节，实体结果1244字节；排除这些轮次的调用数/证据字节硬性阻断。Loguru目标符号从未入真实上下文，oracle查询不能伪称可自主提出。
- 新做2次分析者指定的原生SDK工具调用，网络/模型拒绝保护：Loguru traceback成功但空结果49字节，SQLGlot已见符号成功返回完整正文1244字节；不是模型自主选择。修复后基础read_file只用已见文件+起始5969行，不提供gold结束行，第一页4069字节也包含目标正文。返回范围不同，字节少不等于收益。
- 新发现执行器256字符上限没有出现在历史或当前实际wire schema（仅type:string）。诊断脚本最初假定maxLength保留，检查失败后纠正；长题面校验拒绝、短符号执行成功。仅记录接口说明缺口，未改策略/schema；没有过长真实调用，不能归因本次未选择。
- 当前检索实现/描述/排序/预算/冻结版本均未改，旧结果保留。新模型请求0、费用0、不读凭据、不执行目标仓库代码。报告 RETRIEVAL_CHOICE_HYPOTHESES.md；证据 verification/retrieval-choice-hypotheses-v1/ 下三份JSON。后续行为因果需另行授权的单变量自主选择实验，现有离线证据不能代替。

## 2026-11-13｜SQLGlot 共用读取修复后的单题验证准备

- 从已冻结 v5 SQLGlot 子计划准备独立单题入口；保留原题、147 个 Python 文件、SDK 1.62.0、deepseek-flash、温度0/非思考、工具描述/检索策略、检索组先行顺序。两组共享修复后 read_file，仅检索可用性不同，每组4请求、合计8请求/17元，未创建生产授权。
- 新冻结 df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277；旧两题 1286c563… 冻结与所有旧结果保留。新命名空间 experiments/sqlglot_validation；未来独立 authority-sqlglot-validation 账本仍不存在。
- 新增 post-run 读取审计：SDK事件与回包链接、行号/正文比对、issued cursor、工具观察是否进入下一模型请求、完整目标19行是否送达；不使用续页记未观察，未使用read_file不判接口失败。参考行号仅本地事后评分使用，不进入模型请求。
- 52项相关测试最终通过（17单题授权预算、3观测、32共享读取/收尾/传输）。首次组合中的1项测试将新增plan_hash与无此字段的源清单直接比较而失败，纠正测试断言后17项重检通过；保留失败日志，无运行代码改动。9种原生SDK模拟场景通过，正常/无需续页完成两组，超时、收尾违规、缺字段、截断及超限均停止，无自动重试；未知费用保留预留。
- 17份旧调用账本无未决请求；2,584份旧文件哈希不变。官方公开峰值价仍为输入2/输出8元每百万token；8次完整预留16.908288元。账户本次价格未核查，批准/账户价格/别名版本/冻结/重复运行检查仍是启动条件。
- 本轮真实模型调用0、费用0，未加载凭据或执行目标仓库代码。题目已曝光，脚本指定行号的离线成功不代表模型自主行为，不宣称泛化或检索收益。报告 SQLGLOT_READ_VALIDATION_READY.md；证据 verification/sqlglot-validation-v1/acceptance.json。

## 2026-11-13｜批准的 SQLGlot 单题读取验证完成

- 按用户对单题两组、发送题面/提示/工具/源码证据/组内历史、最多8请求/17元的明确批准运行。启动前核对CNY账户和其链接的官方价格、冻结hash、17份无未决旧账本及无重复进程；用专用一次性授权及既有私有.env，未显示Key。
- 冻结 df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277 未变；8次真实请求全部结算，2组正常finish，0失败/重试/未知费用，授权已消费。
- 检索可用组4search+2read+1finish：5960–6010与6010–6030；基础组5search+1read+1finish：5960–6015。三次read均按正确源码行号返回，原样进入下一请求；两组目标函数5969–5987完整19行送达，参考函数/文件均排第1。未用offset。
- 所有read范围单页返回且next_cursor为空；检索组另读相邻段不是cursor续页。真实游标行为未观察，LocAgent调用0（检索组提供但未选），不宣称检索收益或续页能力。
- 输入24125、输出1927 tokens，回包缓存命中9728/未命中14397。按全输入峰值未命中计成本上界0.063666元（检索0.034158、基础0.029508），待结0；不是账户逐笔实扣对账。两组墙钟11.280/12.071秒。
- 原始响应、轨迹与账本保留，旧17份账本及2584份材料哈希不变。题目已曝光、两组各单次；定位命中不等于回答语义全对，回答中解析机制仍有未核实推断，不进行额外付费调用。
- 报告 SQLGLOT_READ_LIVE_RESULT.md；预检 verification/SQLGLOT_READ_APPROVED_PREFLIGHT.json，验收 verification/SQLGLOT_READ_LIVE_ACCEPTANCE.json。

## 2026-11-13｜原题与真实已见线索的 LocAgent 免费能力检查

- 核对旧诊断后复用12条主查询，新增4次离线检索（Loguru raising_recursion/tail_recursion，SQLGlot _parse_set/_parse_primary）；另复用2条oracle结果单列。检索适配器、引擎、源码、分页函数及标签一致，旧输出hash校验通过；没有重复跑已知查询。
- 两题完整原文999/1386字符超过256接口上限，均在执行前被拒，标记未评估而非未命中；原标题57/55字符逐字等于第一行，不混用全文。16条主查询在新增检索前保存，但仍为已曝光开发集的分析者选择。
- 来源仅从原题和实际请求的tool消息取证，逐条记录run/arm/turn/message/hash及摘录。Loguru已见文件/测试basename来自A批第2轮list_files；SQLGlot新符号在B检索组第3轮已见、基础组第4轮才见，关闭调查后的信息不冒充可用机会。
- Loguru标题只返回Logger.add（49465原始bytes/4096首JSON页）；题目短词和新增两条basename均空（19/49）。已见_better_exceptions.py可精确读全文件24272bytes，原始含完整目标9行，但4096首屏和14336总预算均未交付目标。_format_list从未进入所查真实请求；oracle第1且761bytes完整返回，仅证明已知名读取。
- SQLGlot标题及SET TAG/SetItem未命中参考；已见_parse_set_item返回分派函数并含后续线索；已见_parse_set_item_assignment第1，原始1178/首JSON1244bytes，完整19行与源码匹配。新增_parse_set与_parse_primary分别返回对应非目标函数684/730、2559/2647bytes。
- 2732份历史/生产/冻结/诊断材料哈希不变；真实调用0、费用0、未读凭据、未执行目标代码、未改策略或授权。建议下一步免费研究发现覆盖与大结果预算、查询长度契约；不以oracle查询或反事实检查宣称模型自主调用、因果或检索收益。
- 报告LOCAGENT_CAPABILITY_CHECK.md；证据verification/locagent-capability-v1/results.json与acceptance.json。

## 2026-11-13｜未选检索的状态对照与正例核验

- 继续免费研究模型未选检索，检查旧Loguru/SQLGlot与读取修复后SQLGlot三条检索组轨迹，共9个开放auto调查机会，均未选检索，定义/顺序一致。按实际请求中的工具证据判定状态，不从终答反推。
- 找到并复核两个既有自主调用正例：webhook第1轮query webhook delivery retry；文档权限第1轮query share token access check document。其LocAgent完整定义及工具名称顺序与当前相同，1642/2048字节观察均进入下一请求并正常终答。系统提示/题目/时期不同，不是假定全条件相同的因果实验。
- 新发现：旧SQLGlot第2/3轮有“已见目标符号但正文缺失”的可用机会；新SQLGlot第2轮还没见完整符号，第3轮看到符号时完整19行正文也已送达，故新自然轨迹此类机会为0。不能将两种0检索调用解释为相同的放弃补证行为，更不能宣称读取修复因果改变选择。
- 形成更具体假说：任务路由与基本读取已满足需求，说明“known file用read_file”可能影响实体正文工具分工。正例反驳普遍不会调用/绝不选择；无法证明说明、名称、排序或训练偏好是根因。
- 准备离线说明单变量配对：取旧SQLGlot第2请求纯搜索后的未满足状态，两份均使用当前修复后基础工具/系统，仅tools/3/function/description不同，明确已知名但缺正文时的用途。人工构造重放，不冒充自然轨迹；未运行、未授权、无自动重试/补跑计划。
- 2685份生产/冻结/实现材料哈希不变，未读Key、未执行目标仓库代码、新模型调用0/费用0。报告RETRIEVAL_CHOICE_STATE_FINDINGS.md，证据verification/retrieval-choice-state-v1/。

## 2026-11-13｜工具说明配对离线试跑完成

- 按用户要求完成免费离线试跑，使用已保存的说明单变量配对输入，递归确认仅tools/3/function/description不同；原始人工历史状态剩14调用/12277bytes，未重置满预算。
- 两说明各8场景：模拟检索、读取、直接finish、257字符查询、未知工具、截断、超时、执行器关闭。最终v3共16/16按预期通过；成功工具目标19行完整送入下一模拟请求并模拟finish，故障均停止，未自动重试。
- 原生本地检索返回1244bytes，按行读取1037bytes，累计证据3303/3096bytes。读取夹具指定参考范围，仅验证管道，不用于模型效率或答案质量结论。动作选择均为脚本指定，未测自主选择概率或说明因果作用。
- v1 SDK不可变对象赋值在模拟请求前失败，改为独立工具副本；v2场景通过后复核发现模拟终答复用工具ID，改为唯一ID并在v3重跑验证。v1/v2历史保留；生产工具未改。
- 最终20次MockTransport交换/2次本地检索；计入v2本任务40次模拟交换/4次本地检索。所有真实模型调用0、费用0、不读Key、不执行目标仓库代码、不创建生产授权。2690份历史/生产/冻结/配对材料hash不变。
- 报告RETRIEVAL_CHOICE_OFFLINE_RESULT.md；证据verification/retrieval-choice-pair-offline-v3/acceptance.json与final-review.json。

## 2026-11-13｜真实工具说明配对准备完成，自动审核阻止启动

- 用户要求“调用模型跑一次”，按已准备的配对材料解释为控制/候选各1次，最多2请求/5元，deepseek-flash，固定原题与历史搜索证据，仅说明不同；不执行模型选出的工具、不追加回合。
- 新建独立入口experiments/choice_pair/run.py及choice_pair/v1冻结，hash 64dee9be8533dd47b3543e0d17b7e20c87ed5faf57e1a5c15a197c1c3f4f18b9。12项免费测试通过，覆盖最坏预留4.227072元、重复启动/票据、价格、过期、精确payload、首/次请求超时和错误参数。
- CNY账户/官方峰值价已复查，18份旧账本无待结，无重复模型进程；本地grant已创建但未claim。真实启动命令被自动审批审核在进程创建前拒绝，理由为用户未明确授权具体数据/DeepSeek目的地/两次配对。
- 未绕过、未重试；无claim、无run目录、Key未加载、真实请求0、费用0。等待用户明确确认具体两请求与数据范围，不能把助手解释当作用户逐项确认。报告CHOICE_PAIR_LIVE_BLOCKED.md，证据verification/choice-pair-live-v1/。

## 2026-11-13｜明确批准的工具说明真实配对首请求后停止

- 用户对DeepSeek目的地、发送数据、原说明/新说明各1请求、2请求/5元、异常停止不重试明确答“同意”；保留前次审核拒绝并记录新增确认。复核冻结、价格、无claim/run、18旧账本无未决、无重复进程后，经审核启动一次。
- 实际1请求HTTP200结算；原说明下模型返回read_file(parser.py,5960–6015)和search_text(_parse_set_item_assignment)，未选LocAgent。未执行工具；候选说明未请求，不能作配对比较。
- 新入口直接Action.model_validate遗漏SDK summary提取步骤，合法wire summary被extra_forbidden拒绝。这是新适配器缺陷，不是模型错误；原始响应保留，副本离线去掉summary后两项参数均有效。SDK源码提取顺序已核实；旧12测试正常夹具漏测summary路径。
- 账本halted/授权已消费，无重试/补跑。输入2820、输出151、cache hit1920/miss900；保守费用上界0.006848元、未决0，不作账户逐笔实扣声明。
- 2667份历史材料hash不变，未改冻结代码或旧结果。报告CHOICE_PAIR_LIVE_RESULT.md；验收verification/choice-pair-live-v1/live-acceptance.json，诊断failure-diagnosis.json。下一步先离线修适配与测试，再另定真实方案，不续用已停授权。

## 2026-11-13｜工具说明入口 summary 适配修复及授权复跑

用户要求“修复入口适配，再试跑一次”。新增隔离的 experiments/choice_pair_v2/run.py；只提取 wire schema 明确声明的字符串 summary，再执行原有严格 Action 校验。原始回包、原参数、辅助 metadata 与适配后参数分别保留；不接受其他未知字段，不执行模型返回工具。旧冻结入口和失败结果不改写。

离线 32 次检查全部通过（20 个不同用例，含 12 个重复预算/授权回归）；真实旧回包的两个带 summary 调用可通过，错误类型、未知字段、截断、超时、预算与重复启动仍拒绝。冻结 hash 327f2b94b2394808f75ef609f9a01aa2d855f8673b602d32664e0c0716daf3a2。

核对官方当前价格、已登录账户 CNY 状态、无旧运行或未结请求、.env 非秘密元数据后，用新的一次性授权运行同一 SQLGlot 历史构造检查点。原说明与新说明各 1 次 deepseek-flash 请求，共 2 次 HTTP 200 正常结算，无重试、无追加、无残留预留；费用按高峰全 cache miss 上界合计 ¥0.013754（用户上限 ¥5），尚未逐笔核对账户扣费。

两种说明都选 read_file(parser.py, 5960–6015) + search_text；原说明搜索 _parse_alter_table_set，新说明搜索 _parse_set_item_assignment，均未选 LocAgent。说明调整在本次单检查点未引出检索；不能断言模型动机、普遍无效或检索收益。没有执行工具或测量终答。2667 个历史文件与旧配对运行 5 个文件 hash 不变。完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/CHOICE_PAIR_V2_RESULT.md；审计：verification/choice-pair-live-v2/live-acceptance.json。

## 2026-11-13｜多种信息状态的离线工具证据与成本对照

按小目同意的调查范围，核对 7 个实际请求检查点和 1 个明确构造的符号状态，共验收 22 条离线路径。使用 Loguru/SQLGlot 两题旧批、SQLGlot 读取修复后批次，以及 webhook/文档权限两个真实自主检索正例。查询来自题面、真实先前工具证据或当次真实模型查询；参考标签只用于操作结束后的覆盖判断，不作为查找线索。

复用 6 条既有检索结果，新增模型请求 0、检索引擎调用 0、网络尝试 0；普通搜索/读取使用固定源码及现有修复后的工具，仅静态读取，不执行目标代码、不读取凭据。每条路线使用实际检查点剩余预算，分页计工具次数，字节按完整 JSON 工具回包计数。2751 个历史/冻结/生产文件哈希不变。没有修改生产检索策略或旧结果。

SQLGlot 符号+路径+行号已知时，直接读取 1 次/2102 字节，检索 1 次/1244 字节，均交付目标完整正文；人工仅符号状态，普通搜索+读取 2 次/2850 字节 vs 检索 1 次/1244 字节。后者未找到对应自然轨迹，不能称真实选择机会。正文已到达时可零新增调用复用，额外检索的 1244 字节为该正文重复。

跨文件真实首轮检索：webhook 1 次/1642 字节取得两个重试函数；题面 retry 搜索+读取命中文件 4 次/2312 字节，同时取得 worker，仍有不同缺口。文档权限检索 1 次/2048 字节取得两个权限函数；题面 token 搜索+读文件 4 次/1879 字节，还包含入口；全六文件可 7 次/1995 字节读完。少工具步数不必然少字节或覆盖完整任务。短词普通路线是初次对照后补充的分析者路线，声明与结果单独保存，不伪称独立预注册。

Loguru traceback 普通搜索能暴露相关文件与测试，当前 ID 检索为空；已知大文件时，两种工具均在该检查点 10210 字节剩余预算内未送达参考函数。SQLGlot SET TAG 初始查询两种工具也未取得目标正文。不能把这些离线结果当作模型经历或不选检索的因果解释。

报告列出 H1 位置未知时少步骤、H2 跨文件词到实体、H3 已有正文的边际信息、H4 自然措辞及大文件匹配等假设及否证条件。建议优先免费寻找自然符号未知位置/跨文件缺口检查点，再决定是否申请模型选择试验；本轮没有新增授权或真实调用。

完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/EVIDENCE_STATE_COMPARISON.md。证据及验收：verification/evidence-states-v1/{results,literal-followup,acceptance}.json。脚本：diagnostics/compare_evidence_states.py 与 diagnostics/compare_evidence_states_literal_followup.py。

## 2026-11-14｜自然符号位置与跨文件缺口的离线验证

环境可用。扫描 18 份历史账本、93 个仍开放调查工具的请求，校验请求哈希；启发式产生 37 个含噪声/重复候选记录，未把它们全称为有效机会。人工选择 4 个未经改写的自然状态，查询只来自真实先前工具证据或原题，不使用评分标签/补丁。验收 10 条路线，新增 4 次本地免费检索、0 模型调用、0 网络尝试，不读取密钥、不执行目标仓库源码、不改生产策略；2757 个历史/源码/冻结/旧调查文件哈希不变。

自然 d06 第2请求已见 parse_row 调用而无定义/import映射，但 parser.py 的文件名与搜索内容已给出强线索：检索 1次/1083字节；搜索定义再读 2次/1011字节；按可见 parser.py 线索直接读 1次/987字节。历史模型实际选择了读 parser.py；不构成必须检索的场景。webhook 第3请求已有 identity 的明确相对导入与路径，缺正文：检索1次/487字节，直接读取1次/377字节，后者也是历史实际选择。

d03 第2请求已收权限/分享检查正文，原题的 audit 问题仍有跨文件缺口：检索audit 1次/638字节取得 record_access；普通audit搜索+读取两文件3次/1030字节补齐 record_access 和 open_document。单独搜索首屏其实已含完整两行 record_access，不能宣称检索对该正文有独占一步优势。

最有区分度的自然候选是 SQLGlot 读取修复后第3请求：已见 self._parse_id_var 调用而未见定义，且仅剩当前1个调查响应。检索1次/2921字节返回 Parser/TSQL/Snowflake 三个完整同名实现；定义搜索1次/197字节只返回位置，依赖下一轮的读取被阻止；直接读已知parser.py开头1次/4091字节未到相关定义，续页同样被阻止。需注意历史模型实际读取 _parse_set 并搜索 _parse_primary，未提出 _parse_id_var 查询。本轮由分析者选此已见符号，不代表它是模型意图或原题必须补的证据，也未证明动态分派或最终答案收益。

本轮补齐上一报告缺少的“调查轮数”限制：工具次数不等于可依赖前一步结果继续的响应轮。搜索后再读、取得cursor后续页需下一轮；独立已知路径读取可同轮。5项专门离线测试全部通过。旧报告和历史数据不改写，仅在本报告解释适用限制。

建议保留 SQLGlot 最后一轮辅助方法缺口为后续自然自主选择候选，配以 d06/webhook 的已知文件线索对照及 d03 短词搜索可直接交付正文的反例。下一次真实试验须另列范围，当前未创建授权或调用模型。

完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/NATURAL_EVIDENCE_GAPS.md。来源/状态/查询/预算/步骤/回包/验收：verification/natural-gaps-v1/。脚本：diagnostics/probe_natural_gaps.py、diagnostics/accept_natural_gaps.py；测试：tests_sdk/test_natural_gap_rounds.py。

## 2026-11-14｜SQLGlot 自然检查点工具选择方案准备（未授权启动）

按小目仅准备的要求，冻结读取修复后 SQLGlot 检索组真实第3请求，原请求 hash b203e951bb9f3fc57f3ab47dfb9013db5d4d57bb031accf429e2a92b2cc48172；当前核心代码与SDK系统提示 hash 均一致。历史4次普通工具已消耗5346字节，复算剩余12次/8990字节/1个调查响应；无历史LocAgent调用、无悬空tool结果。有检索组与原请求逐字节一致，基线仅从工具列表删除locagent_retrieve，没有改提示或追加辅助函数名/离线证据。

拟各组仅取一次自主响应，共最多2次DeepSeek请求、5元总上限；不执行返回工具、不补发终答、不重试。deepseek-flash非思考、temperature0、max_tokens2048，固定基线先行。反例仅保留离线参照，不加本轮付费样本。方案明确小样本、固定顺序、自然前缀条件重放而非完整自然基线、不能把基础组必然不能检索当作调用率因果证据，也不测最终答案或检索收益。

公开价格页2026-11-14核对仍为Flash高峰输入未命中2元/百万、输出8元/百万，版本参考V4.1-Flash-1017；账户实际价格待获准启动前核对。每次最大上下文预留2.113536元，两次4.227072元低于5元；预留不是预计费用。新隔离入口绑定精确payload及代码、一次性授权/claim、持久化账本、最多两次和异常整轮停止，保留summary兼容且拒绝错误参数。18项offline mock测试通过；生产authority-natural-choice目录不存在，Key未读取，真实模型请求为0。

冻结plan hash：664680ac971ed7520b7d84de8ce38c9635608107219f340d869d73ed89a4e895。基础/检索payload分别13732/14704字节，将来只发送SQLGlot题面、提示、工具定义与已收到的源码证据/历史到https://api.deepseek.com/chat/completions，不上传标签、补丁、新离线结果、其他题目或.env内容。此轮只有公开价格页查询，没有发送项目数据。2757个历史文件哈希未变。

完整方案与明确确认语句：/Users/xiaomu/Documents/Codex/2026-11-12/task/NATURAL_CHOICE_EXPERIMENT_PLAN.md。冻结/验收：natural_choice/v1/manifest.json、verification/natural-choice-prep-v1/acceptance.json。当前未创建生产授权，不沿用此前试跑批准；需用户另确认范围并完成启动前检查后才可运行。

## 2026-11-14｜SQLGlot 自然检查点已批准真实两组单步完成

主对话用户对完整范围明确“同意”后，复核冻结方案664680ac971ed7520b7d84de8ce38c9635608107219f340d869d73ed89a4e895、价格、账户CNY与定价链接、.env非秘密状态、旧账本无未结请求和无重复运行。新一次性授权执行基础组与开放LocAgent组各一次，共2次真实DeepSeek请求，均HTTP200正常完成。没有执行返回工具、没有续答、没有自动重试或追加样本。

基础组提出read_file(parser.py,6010–6030) + search_text(SET_REQUIRES_ASSIGNMENT_DELIMITER)，输入3797/输出157tokens，保守费用上界0.008850元；开放检索组提出同范围read_file + search_text(SET_TRIE)，输入4006/输出151，费用上界0.009220元。检索组本次没有选择LocAgent，也未选择分析者关注的_parse_id_var。三个查询线索均已在原检查点工具证据中，无新离线结果泄漏。

总计输入7803、输出308、总8111tokens；账本按高峰全输入cache miss价上界0.018070元，低于批准5元上限，无残留预留。预留2.113536元/请求不是实际用量收费；上界未扣缓存或空闲优惠，尚未逐笔核对账户实际扣费。启动前账户显示余额2.52元、当日0请求；公开模型参考V4.1-Flash-1017，价格仍在2/8元每百万token预算假设内。

本次只观察工具选择；基础组不能选检索是设置，不能算自主拒绝。每组一次、固定顺序，不能推断动机/因果，也没有最终答案质量或检索收益证据。自然状态下可补某辅助函数的能力，不等于模型必须补该函数。d06/webhook/d03离线反例保留，未加付费样本。

审计确认2个真实transport_started、settled与原始request/response哈希，2777个历史材料不变。原结果和一次性授权保留，不再运行本授权。报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/NATURAL_CHOICE_LIVE_RESULT.md。账本：authority-natural-choice/664680ac971ed7520b7d84de8ce38c9635608107219f340d869d73ed89a4e895/run/ledger.sqlite；验收：verification/natural-choice-live-v1/acceptance.json。


## 2026-11-14｜batch134 与 OpenHands 引擎差异离线核验

按小目“来确认差异影响吧”的要求，复算 batch134 runtime-engine 159 文件聚合 2222b6bac8ac393a7aeb29e571edefe351146320e62384627cecdaeba9a3f196，当前 OpenHands 所用 LocAgent 146 文件聚合 975172d7d0a1590be5033779d1349462fa5cba497b3b0554fce815a1f5a0d944，均与冻结记录一致。更正此前计数：12 个共有文件内容差异、1 个当前独有 requirements-demo-test.txt、14 个 batch134 独有文件，并非 13 个共有文件差异。逐项分类与 diff 已保存。

当前 OpenHands 每次从源码构图并建立实体 ID BM25，不加载旧 graph.pkl 或正文 corpus。两道已曝光题全部 bundle 文件先验证哈希，再在临时隔离进程做受限图读取/本地查询；没有改正常版本门禁。正常 load_manifest 在 batch134 接受两个旧 manifest，在当前引擎均拒绝 Engine changed。实体/正文索引的小范围格式兼容，不等于生产授权或全批兼容。

同一 Python 3.12 环境、同一冻结 Python 源码下，batch134 比当前新建图多 SQLGlot 48、Loguru 38 个构造函数相关实体，共有节点属性一致。5 个已有查询在两引擎×新建/归档图四组合的 20 次本地检索中原始输出相同；正文 BM25 两索引也可加载，所测查询结果相同。两个已曝光参考函数名称、行号与正文映射一致。人工样例则复现构造函数及 pkg.github 目录覆盖导致的检索差异；因此不能推断所有检索结果相同。

130 题仅查 manifest 元数据与文件 stat，发现 7 题有 14 个隐藏 Python 路径，而当前 Snapshot 拒绝隐藏路径。人工 CRLF 样例在两套图构建器下均被当前逐字校验拒绝，未放宽检查。归档 prepare 另有根节点 /→. 归一，旧构建 Python 3.10 与当前 3.12 的 except* 解析差异对应 Loguru 两个测试函数，未复跑旧容器。旧路径 replace 的相对路径反例也可复现。未查看未曝光题的题面/标签/正文调参。

建议复用固定源码及来源证据，新建 OpenHands 适配清单并显式固定源码范围、解释器/依赖、引擎、索引及评分；先处理覆盖和换行保真，再逐题技术门禁，不能去掉引擎哈希校验或把旧 130 technical-ready 直接升级为当前通过。只完成小范围离线检查，没有全批重建或引擎改动。

验证：6 个隔离重建/查询 worker、4 次正常 manifest 门禁检查；23 项结果断言通过，1,728 个既有受保护文件哈希未变。真实模型请求 0、费用 0；没有读取密钥或 .env，没有向外发送数据、安装依赖或执行目标仓库代码。Python 网络/模型防护不声称为 OS 级沙箱。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/ENGINE_COMPATIBILITY_REPORT.md。
证据与验收：/Users/xiaomu/Documents/Codex/2026-11-12/task/verification/engine-compatibility-v1/，包括 acceptance.json、preflight.json、manifest-gate-probe.json、manifest-metadata-audit.json、exposed-label-mapping-check.json 及逐文件 diff。


## 2026-11-14｜130 题源码适配：构造函数与保真读取

按小目指定顺序离线实施。原图显式跳过同步 __init__，旧设计不满足精确函数定位覆盖要求。建立当前引擎的隔离副本，移植 batch134 图构建器的构造函数/嵌套实体、目录组件与软链接处理，保留禁止新增构造函数参与后缀模糊调用解析的保护；没有迁移旧 Agent 循环。图文件读写改为 UTF-8 原始换行，CRLF/Unicode 保留，继续校验原始文件与精确 AST 正文。新增文件/实体覆盖门禁，不能静默漏建。

## 2026-11-14｜130 题源码适配：隐藏路径端到端修复

Snapshot 增加独立逐文件 hidden_python_paths，默认仍拒绝隐藏路径；只容许源码清单内显式 .py，管理/凭据目录、软链接及越界继续拒绝。策略绑定计划并传入隔离 IPC。第一版建图后端到端查询发现 _entity_input 会去掉 .ci 开头点；v2 保留点后，真实题又发现 get_entity_contents 默认排除 test 名称文件。v3 修正明确指定的已入图实体读取，仍保留关键词 BM25 的测试文件过滤。前两版结果、失败和 superseded 记录全部保留，没有将建图成功冒充检索通过。

第三版组合边界回测通过构造/嵌套实体、带点普通目录、无错误构造调用边、CRLF、隐藏路径 IPC、伪造正文/漏建实体/漏建文件拒绝和行号；真实 7 题的 14 个隐藏路径逐个精确读取成功。41 个单元测试、4 个现有集成测试通过。一个旧隔离测试手工构造的不完整图现按新门禁拒绝，已为其补全真实函数节点以保持隔离测试意图，另有缺实体负向检查。

## 2026-11-14｜130 题源码适配：新冻结计划与全量技术检查

最终引擎哈希 8ae12c2eb8a66dea80e78d8bf0342c4b132c3c70338ac755ac44a1ab5fc98707；新副本146文件，仅图构建和 repo_ops 两文件与原当前引擎不同，原两引擎均未修改。先人工样例、已曝光 SQLGlot/Loguru 两题及隐藏路径7题，全部通过后扩展剩余121题；每题新临时源码/进程，最多3并发，CPU90秒/墙钟120秒。最终130题：128题技术通过，2题阻塞。失败不自动重跑，不算题目无效或评测零分。实际阻塞ID：AzureAD__microsoft-authentication-library-for-python-454, AzureAD__microsoft-authentication-library-for-python-407。

追加只读语法探针定位 MSAL 四个文件的 UTF-8 BOM 被字符串 AST 解析拒绝；这是原先未显露的编码适配缺口，尚未修复，不能靠删文件或放宽字节校验过关。语义、曝光与评分映射仍 pending。130题索引准备不等于130题可独立评测。

产物在 /Users/xiaomu/Documents/Codex/2026-11-12/task/engine_adaptation/v3：manifest/plans 绑定父 source_id、提交、源码与隐藏白名单、引擎和 harness；成功项含 JSON 图与数值 BM25 索引、哈希证明。失败目录保留。人工/两题的持久化索引加载回测通过。全部22897个来源 Python 文件引用的路径检查无越界或软链接。

现有实时接口仍从源码构图，未把缓存索引接入付费入口；新实验需选择新引擎并重新冻结，旧授权未换绑，哈希校验未关闭。旧受保护材料中只6个预期 harness 源文件变化，其余1722个哈希不变，旧索引、账本、模型结果保留。真实模型调用0、费用0；未读取密钥/.env、安装依赖、执行目标仓库代码或外发数据。Python 防护非 OS 沙箱。

完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/SOURCE_ADAPTATION_REPORT.md；逐题状态见 engine_adaptation/v3/adapted-manifest.json 和 full-validation-results.json，验收见 acceptance.json。


## 2026-11-14｜MSAL UTF-8 BOM 修复与 v4 的 130 题技术验收

按小目后续授权继续离线修复 MSAL 407/454。根因是 ast.parse(str) 不把解码后的开头 U+FEFF 视为编码签名。v4 仅在 AST/import 解析及实体提取的解析视图中去掉一个初始 U+FEFF；适配器采用相同规则。原 Snapshot、文件节点、SHA256、IPC 和 read_file 内容完整保留 BOM；非 BOM 文本、CRLF 和行号不变，内部 U+FEFF 不删，重复或非首位 BOM 仍拒绝。

新引擎副本 hash：da03769bb8166f8ff4738f54de02c488c1088eeea68a3c6d7bde7d1c24c2160e。相对 v3 只改图构建器；harness 仅 readonly_agent/locagent.py 修改，修改前原文已备份在新目录。没有修改原引擎、v3 产物或旧授权。

两道 MSAL 题重新静态构图与建索引，均43个 Python 文件、4个 BOM 文件；407新图508节点，454新图525节点；每题4个 BOM 文件含34个类/函数实体，原始文件字节和 AST 实体绑定通过。没有运行目标 setup.py、模块或测试。先通过含首行 BOM/CRLF/中文、内部 U+FEFF 和 import 的隔离组合样例及两题门禁，再复验其他128题。

128题确认无开头 BOM，新增解析视图对这些源码为恒等变换。逐题验证旧索引哈希与源码快照；在新适配器下重新验证 JSON 图的文件/实体覆盖与精确正文，重建内存实体 BM25，并比较持久化索引全部 corpus 文本及固定 __init__ 查询返回 ID；隐藏 Python 路径再次精确读取。没有重算这些题的图边，保留 v3 build 来源。最终130/130题技术通过：2题重建、128题复验复用，不能说130题全部重建。

45个单元测试、4个现有集成测试通过；先前构造函数/隐藏路径/CRLF/伪造正文与缺实体拒绝/IPC/行号回归通过。新增测试覆盖一个初始BOM、非首位/重复BOM拒绝、BOM首行函数与Unicode、内部字符保留、非BOM与原AST一致。旧1280个索引产物哈希复核未变，v3的2题失败与128题通过记录保持历史原貌。

最新清单：/Users/xiaomu/Documents/Codex/2026-11-12/task/engine_adaptation/v4/adapted-manifest.json，分别记录 index_build_engine_hash 与 validated_engine_hash；验收 acceptance.json、逐题 validation/。报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/BOM_ADAPTATION_REPORT.md。

仅技术验收完成。语义、曝光、评分仍pending，未宣称独立测试集或正式评测。没有真实模型请求/费用、密钥/.env读取、依赖安装、目标代码执行或数据外发。真实模型入口未运行或切换，缓存尚未接入实时运行器，旧授权未换绑；未来执行需选择新版本并重新冻结。Python防护不声称OS沙箱。


## 2026-11-14｜130 题评测前检查：评分、曝光与模拟入口

基于 v4 130/130 技术验收开展免费离线检查。v4 引擎 da03769bb8166f8ff4738f54de02c488c1088eeea68a3c6d7bde7d1c24c2160e 和 harness 均未修改；新增 experiments/eval_preflight 独立代码、tests/test_eval_metrics.py 与 verification/eval-preflight-v1/v2 产物。旧受保护材料除此前6个适配文件之外1722个哈希不变，历史结果不重算。

新增 localization-metrics-v1，明确 Acc@k 为达到 min(k,参考数) 的命中覆盖条件，Recall@k 为全部参考召回，Hit@k 另列。兼容口径对预测和参考双向归一构造函数并去重，修复旧 official_reference 仅归一参考端的问题；保留旧评分器及结果。拒绝模拟质量评分，将技术失败与完成后定位错误分开。10项评分单测通过。130题中10题参考实体超过5、18题涉及构造函数、空标签0；不能把Acc@5=1解释为全部参考均命中。

语义审查仅对已曝光 SQLGlot3417 与 Loguru1239 作静态初查，不称独立盲评。25条历史指针不等于完成审查，旧checklist可核实交集8条含conditional、constructor_panel、hint_only、excluded及control_only。Chainlit1441旧excluded、Loguru1239旧control_only不能被技术清单自动覆盖。另冻结6道开发题抽查模板，新增4题尚未开展题意/补丁审查，不用未解封测试题调参。

本地37开发/93test按仓库无交集，但开发20、test67题带已知仓库曝光标记，共87；剩余43仅未标记，不能证明未曝光。旧登记明确限制24个仓库未来独立保留集复用。仅authority-locbench历史账本扫描得到Loguru至少16、SQLGlot至少12条transport_started，未穷尽其他历史目录，不能据此判其余题未曝光。保留逐题状态和来源。

最新SQLGlot模拟：同一OpenHands两组共8次MockTransport请求，检索组实际加载并校验新持久化实体BM25；正常finish，重复组启动和错误索引绑定拒绝。另本地改造bounded-v1 GraphLocalizer完成4次provider脚本响应；不是原版上游，也未形成公平完整系统对照。加保留v1共24次脚本响应，真实请求0。18项现有预算/故障回归通过；旧live计划因代码变化正常拒绝，授权未换绑。

阻碍明确：原生正文BM25尚未接入，不能用实体索引冒充；原生默认分页8192、源码预算约20480、每响应16工具、终答20，与SDK4096/14336/累计16/终答5不同；共同输出token、收尾及持久化真实准入尚未连通。缓存适配仅接入离线入口。须统一契约、补后端并重新冻结；原始LocAgent-vs-harness与同SDK检索可用性对照不可混报。

准备有条件单题真实草案：已曝光SQLGlot，两组最多8请求，拟deepseek-flash、2048输出token、17元上限。历史输入2/输出8元每百万token假设下总最坏预留16.908288元，不是预计花费或当前价格；本轮零外发，未核查账户价格。发送范围仅题面、提示、工具定义、选取源码证据及该组会话，排除标签/参考补丁/审查笔记/环境文件。草案未获新授权、当前不可执行，先解决离线阻碍再核价与确认。

真实调用/费用0；未读密钥或.env、未安装依赖、未执行目标仓库代码、未向外发送数据。Python网络防护不声称OS级沙箱。报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/EVALUATION_PREFLIGHT_REPORT.md；主要证据：verification/eval-preflight-v2/{acceptance,cohort-semantic-audit,execution-lock,preservation,conditional-live-proposal}.json。


## 2026-11-14｜共同评测约束、正文后端与后续语义抽查

按小目授权继续免费离线准备，新增 experiments/eval_preflight 下独立适配层，未修改 v4 引擎或 readonly_agent 原 harness，之前 preflight 代码和历史结果保留。v4 引擎仍为 da03769bb8166f8ff4738f54de02c488c1088eeea68a3c6d7bde7d1c24c2160e；130题技术清单不变。1722个旧受保护非预期变动文件哈希保持原状，另6个harness变更仍仅来自此前适配。

正文后端仅从固定源码创建80行分块本地BM25，保存源码/行范围/corpus与数值索引哈希，加载时完整复核。SQLGlot3417生成1005块，原生search_code_snippets实际触发SET TAG正文回退，读取结果并续页。不是把实体ID索引充当正文索引；该分块不等价上游EpicSplitter，不称原版LocAgent复现。仅一个已曝光开发题完成该正文后端接入，未扩至130题。

两套适配后的完整系统共用4请求/组（最后预留finish）、累计16调查工具、14336源码工具内容UTF8字节、4096单页、65536精确wire请求和原始响应上限、2048输出token，以及相同finish(message) schema和5项排名上限。页内容含JSON包装，消息外层计入请求体；重复页扣额度。旧两边不同的请求估算门槛由共同精确序列化门禁替代。超剩余额度整批拒绝、跨轮重复ID拒绝；格式合法但不存在的符号视为定位错误，两边不使用不同的图成员终答裁判。工具/提示/排序仍不同，完整系统对照不能归因为检索收益。

新增ComparisonAuthority/SharedLiveWire，默认锁定的新比较计划要求专属授权类型、适配源码、索引、源码、计划与预算绑定；旧普通授权拒绝。原生provider和SDK传输路径均接已有一次性票据与持久化账本，先预留再传输、保留原始回包、异常停止不重试。仅以人工凭据占位符和临时合成授权替代HTTP helper测试，无真实凭据读取或网络。当前计划live_transport_enabled=false，未创建真实授权；真实命令行批量入口未发布，须完成比较定义与审查后重新冻结。

最新verification/eval-fair-v3两系统各4次模拟请求正常finish，共8次；原生3次调查/12288字节，SDK3次调查/1481字节。实际用量不同但共同上限一致，不作定位分数或费用收益比较。v1/v2/v3成对集成共24次脚本响应，均保留，单测人工响应另计；v2/v3留存精确适配源码副本。最新计划hash8892b16fb8d50c89105edfeb6238b5ede567a0ebb7daf3411e2033b6a855f04f。

验证：评分及故障分类20项、共同契约/新授权传输25项、正文索引2项、既有预算回归18项，共65项通过。包括归一化/类预测保留/空终答/未知符号、超时截断与失败分类、字节边界、累计工具额度、重复ID、Unicode分页、正文篡改、旧授权拒绝、一次性票据与模拟helper超时停止。测试使用隔离人工样例；模拟结果禁止质量评分，技术失败和定位错分开记录，历史评分不重算。

对上轮预先冻结的4个新增开发样本，先保存题面/源码初查理由后揭示标签及补丁。单人静态审查，不是盲评，第二评审待做。MSAL454补丁修改4个Python文件而标签只涵盖authority.py，另3个直接修改的既有函数未列标签，标记hold_label_coverage_review，不擅自改gold；Luigi3308位置提示且补丁/标签一致；matchms187题意不足、补丁含快照外依赖文件及新增函数，标记hold；TRL2450含明确答案提示，与补丁一致。评分材料独立保存，未传入运行器/检索输入/模型上下文，未查看未解封测试题调参或打开外链。

曝光核查扩至本工作区authority*/**/ledger.sqlite，仅只读快照ID/调用计数。确认SQLGlot历史至少20次、Loguru至少16次，另16个未映射/缺列项保留，不推断其余未曝光，也未穷尽外部旧工作区。4个新增语义审查仓库覆盖9个当前题，更新开发组已知曝光29/未确认8，test已知曝光67/未确认26，全体96/34。未确认不等于独立未曝光；旧Chainlit excluded与Loguru control_only保留，追加准入覆盖表不覆盖旧清单。

真实模型请求、费用、数据外发均0；未读取实际密钥/.env、安装依赖或执行目标仓库代码。Python防护不声称OS沙箱。当前不是130题正式评测：仍需明确适配系统对照定义、扩展正文索引和批量保护、复核语义/标签/曝光及第二评审。未来单题可仍最多8请求/17元草案，17元仅历史单价保守预算而非当前报价；真实执行前需核实账户价格、新冻结及明确批准。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/EVALUATION_FAIR_ADAPTER_REPORT.md。
验收：verification/eval-fair-v3/{acceptance,final-verification,proposal}.json，native.json、sdk/和adapter-source/。
语义与曝光：verification/eval-fair-review-v1/scoring-only/及exposure-eligibility.json。


## 2026-11-14：130 题全量离线入口与评测边界复核

- 本轮仅离线开发与模拟；真实模型请求 0、实际费用 0，未读密钥/.env，未对外发送数据，未执行目标仓库代码。报告：`/Users/xiaomu/Documents/Codex/2026-11-12/task/COHORT_PREFLIGHT_REPORT.md`；证据：同工作区 `verification/cohort-preflight-v1/final-verification-v2.json`。
- 130/130 固定源码与原实体/图索引哈希通过，未查 0；共 22,897 个题内源码引用、269,624,775 字节。新建严格源码运行条目，拒绝评分/补丁字段及跨题索引错配。原 v4 引擎、现有 harness 和此前适配器保持原哈希；原 gold 未改。历史保护集 1,728 个文件中 1,722 个未变，其余 6 个均为已记录的此前 harness 变更。
- 在隔离新目录完成 130/130 physical-line80-v2 正文 BM25 索引构建、持久化回读与 corpus 核验，失败/未处理均 0；106,139 块、512,568,166 字节。该后端为物理行分块适配版，不是上游 EpicSplitter。
- 修复旧入口写死 SQLGlot；新分块仅按 CR/LF/CRLF 计行并直接呈现经哈希证明的原文，避免 Unicode 分隔符被当作源码行及 LF 切片错位。合成回归复现；130 题源码未发现这类特殊分隔符，不能归因旧真实结果。
- 发现 2/130 完整题面超出旧 SDK 8 KiB 门禁（最大 12,537 字节）。新模拟 SDK 保留题面、不截断，共享 65,536 字节精确请求门禁。130/130 首请求模板预检通过（最大保守上界 27,281 字节），不是完整全量轨迹验收。
- 新增批次异常停止/不重试和固定分母评分汇总，模拟成绩为空，缺 gold/重复/异题结果显式拒绝；完成题口径和计划分母失败计零分开。18 项入口、物理行、汇总及批次回归 + 3 项长题面/共同门禁/live 锁定回归通过，共 21 项。首次有 1 项 macOS 临时路径 fixture 非规范错误，修正 fixture 后通过，生产校验未放宽。
- 最新 pilot-v2：Loguru1239、SQLGlot3417 两题各两组，独立进程/会话/账本/缓存；2 完成、0 失败、0 未启动，共 16 次模拟响应；两题原生路径均触发正文回退。54 个冻结源文件复核一致，未混入另一题题面。旧 pilot 的 16 次也保留；本轮两轮成对模拟 32 次，长题面单测另 1 次。130 题中完整 E2E 仅 2，另 128 未运行；不产生自主选择或定位质量结论。
- 分组仍开发 37/test 93，仓库交集 0；130 任务对应 128 个不同源码快照。程序性标签结构检查 130/130：gold 在基准图缺失 0；15 题疑似遗漏改动函数、16 题涉及快照外补丁文件，重叠 2、合计 29 个风险提示，非已判错，不自动改 gold。本阶段人工初查 6、未查 124，独立第二评审 0；正式计分准入 0，互斥状态为历史排除 1、开发控制 1、人工暂缓 2、待最终审查 126。
- 只读核验本工作区 21 个历史账本：13 个自写样例、8 个对应当前两道真实开发题，当前范围未映射 0；SQLGlot 历史传输下界 25、Loguru 16。仓库已知曝光仍 96、未确认 34（未确认不等于未曝光）；外部历史工作区未穷尽，未查运行数量未知。
- 比较准确命名为“LocAgent 图工具 + physical-line80 正文 BM25（适配版）”与“OpenHands 基础文件工具 + 实体 ID BM25（适配版）”。共享预算但提示/工具/检索不同，是完整系统比较，不是单变量检索增益。所有 gold 审查材料隔离在 scoring-only，未用于生成查询。
- 新通用真实入口仍明确拒绝 live。待离线绑定并冻结一次性真实授权入口、核对当前账户价格和用户批准后，才可小规模真实试跑；不复用旧授权。建议 SQLGlot 单题两组最多 8 次/暂拟 17 元，或两题最多 16 次/34 元。沿用历史输入 2、输出 8 元/百万 token 的保守假设，每对预留 16.908288 元，不是当前报价或预计费用；本轮未联网核价。拟发题面、提示、工具、选取源码证据及本组会话，不发 gold/参考补丁/审查结果/其他题及环境文件。
- Python 离线防护并非 OS 沙箱。所有旧产物保留；早期 final-verification.json 与 code-lock.json 未覆盖，最新证据另存 v2。


## 2026-11-14：SQLGlot 单题授权接线离线验收

- 环境恢复。原项目上一轮 cohort-preflight 完整条目读取核对为 0 次、无成功回执；此次追加请求再次自动审核超时，未继续重试。结束前复核仍缺失。保留上一轮及本轮独立条目，后续须去重追加。
- 新增 experiments/cohort_admission，不修改旧 v4/harness/cohort/eval 代码、历史索引、gold 和结果。冻结 v2 方案 digest 为 8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585，绑定 41 个适配源文件及既有 engine/runtime/SDK 锁、SQLGlot3417 题面/快照/实体/正文索引。
- 接入一次性 CohortAuthority、持久化账本、原生与 SDK 共用 wire；演练使用不同票据格式/类型，真实传输直接拒绝演练票据，演练不接受密钥。真实 CLI 未提供，库入口仍需明确授权和本机安全提供凭据；无凭据发现、自动批准、补跑或重试。
- 新增父进程退出保护；将请求预留数与真实启动传输数分开，后者仍不保证供应商收到。旧 v1 冻结及成功模拟保留，但其代码哈希已过期；最新是 v2。
- 14 项新增回归 + 3 项既有授权回归通过，覆盖精确范围/哈希、模式隔离、票据/路径/代码、预算、超时、截断保留、父进程丢失、重复启动、第二组未启动及生产桥接的模拟传输。首次两处测试 fixture 缺 model/id，被原校验拒绝；补齐 fixture，未放宽协议。测试使用临时合成授权和假字符串，全部清理，无真实凭据读取及请求。
- 最新 SQLGlot 两系统 E2E 演练 4+4 共 8 次模拟，原生正文回退触发，两组末轮仅 finish，均完成。另保留较早 8 次，本轮成对 E2E 模拟共 16 次，单测合成响应另计。真实传输 0、真实费用 0、未读取 .env、未外发、未执行目标仓库代码，项目持久化真实授权 0。
- 只读复核 21 个历史账本哈希均未变；当前仓库曝光仍 96 已知/34 未确认，外部历史未穷尽。人工语义初查仍 6、未查 124、第二评审 0；未新增语义审查或更改 gold，正式计分准入仍 0。
- 待批准范围：仅 SQLGlot3417，deepseek-flash API，两系统每组最多 4 次、共 8 次，上限 17 元；发送题面/提示/工具定义/该题源码证据/本组会话，不发 gold/补丁/审查结果/其他题/环境文件。历史价格上限输入 2、输出 8 元/百万 token，总最坏预留 16.908288 元；本轮未核当前价格，不能当报价或预计费。须当前账户价格确认与数据范围明确批准后方可创建真实授权。
- 这是固定物理行正文 BM25 的适配系统比较，并非原版 LocAgent 或单变量检索效果对照。SQLGlot 已曝光，只验证接入。完整报告 COHORT_ADMISSION_REPORT.md，证据 verification/cohort-admission-v2/final-verification.json。


## 2026-11-14：SQLGlot 已批准试跑的启动前核查受阻

- 用户已批准 SQLGlot3417 两组 deepseek-flash、最多 8 次、17 元上限及题面/提示/工具/源码证据/本组会话发送范围。冻结方案 8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585 验证通过；同方案既有 grant 为 0。
- 官方价格页本次查询确认模型版本 DeepSeek-V4.1-Flash-1017，高峰输入缓存未命中 2、输出 8 元/百万 token，符合预留假设。账户实际计费条件未确认：platform.deepseek.com 只读页面访问及一次重试均自动权限审核超时，没有读取页面内容，没有绕过访问限制。
- 停止在真实授权创建和密钥读取之前，真实模型请求 0、费用 0、生产 grant 创建 0。用户对试跑范围的批准保留，但不能把公开价冒充账户价核查。下一步需确认账户实际币种、价格及必付附加费用不超上限，或恢复正常授权访问。
- 前两轮原项目日志条目均仍缺失（完整条目计数 0），未重复追加。此次独立日志和证据保存在 verification/cohort-live-precheck-v1。


## 2026-11-14：SQLGlot 真实启动审核超时，未执行

- 主对话已确认同一 SQLGlot 两组最多 8 次、17 元及数据发送范围；另转述用户对人民币输入/输出 2/8 元每百万 token 及必付费用上限问题回复“不超过哦”。结合明确人民币总额和官方直接计费，按有效人民币上限确认记录；未声称已读取账户 UI。
- 官方当前价格再次核查符合冻结假设；原模型/题面/源码/索引/代码/预算均未变，计划 8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585。已有 .env 仅检查非秘密元数据，未读内容。
- 新增单次调用脚本及哈希锁，调用既有冻结 run_pair 与已有 runtime 哈希覆盖的安全密钥加载器。先前授权不存在。启动请求及确认无启动后的唯一审核重试均被自动权限审核超时拒绝创建进程；不是风险否定判定。未再尝试，也未绕过审核。
- 最后读取确认启动标记、grant、ledger、result 均不存在。真实模型请求 0、费用 0、密钥读取 0、生产授权创建 0。没有调用模型，不能汇报模型表现或费用消耗。
- 当前阻碍仅执行审核服务；用户的既有批准保留，无需重复要求同意。后续恢复执行能力前应重新确认无启动并验证当前价格/冻结版本；本机命令亦受独占标记和一次性账本保护。
- 保留 scope-and-pricing-confirmation.json、invocation-lock.json 和 blocked-status.json 于 verification/cohort-live-launch-v1；未覆盖历史产物。原项目此前两条日志仍未补写，本轮使用独立条目。


## 2026-11-15：SQLGlot 启动被外发授权审核拒绝

冻结方案和启动脚本哈希通过，之前无启动；今日官方 deepseek-flash 价格仍符合既有预算上限。依主对话转述的既有批准尝试启动一次，自动权限审核明确拒绝，理由是未识别到向 DeepSeek 披露题面、源码证据和会话的明确授权。未重试、未绕过。复核 launch-claimed、grant、ledger、result 均不存在，模型请求/费用/密钥读取均为 0。主对话批准记录保留，但需用户直接明确确认数据范围与目的地以解决此拒绝。未覆盖历史产物；本条独立留存，原项目日志未追加。


## 2026-11-15：SQLGlot 单题两系统真实验证完成

- 用户对具体题面/提示/工具定义/源码证据/各组会话发送至 DeepSeek、deepseek-flash 两组最多 8 次/17 元、不发送标准答案或参考补丁、异常停止的完整提问回复“同意！”。今日价格和冻结哈希复核通过，旧启动标记/grant/账本均不存在，本次审核通过后执行一次。
- 原生适配组 3 次、OpenHands 适配组 4 次，共 7 条实际启动并收到 HTTP 200 和有效 usage 的响应，均正常 finish。无失败/重试/超额，预留余额 0，授权已消费，不补跑。
- 原生组调用目录图探索 1 次、search_code_snippets 3 次（正文后端 10 个子查询），工具证据 14,336 字节；OpenHands 普通文本搜索 4 次、按行读取 2 次，证据 9,309 字节，没有调用 locagent_retrieve。两组均输出 Parser._parse_set_item_assignment 等目标候选；解释存在不一致、部分实体限定名/类型仍待语义评分。协议完成不等于定位和解释全正确。
- 输入 29,480、输出 1,944 token；缓存命中 9,344、未命中 20,136。保守全未命中高峰账本上界 0.074512 元；按周末公开价及缓存回包估算 0.02809888 元，未核供应商最终账单。原始请求/响应/用量/账本保留。
- 本轮为已曝光 SQLGlot 开发题的适配完整系统比较，不是正式评测或检索增益结论。旧 contract.live_enabled=false 描述性元数据保留并在报告披露；真实身份由 live 账本和回执证明。未修改冻结代码、gold 或历史结果。密钥仅既有安全加载器内存/匿名管道使用，未输出/另存。
- 报告 COHORT_SQLGLOT_LIVE_RESULT.md；统计 verification/cohort-live-explicit-confirmation-v1/run-summary.json；运行 authority-cohort/8f6b84e7f66fbeaafd8404bc6ad9d38c96c2b6a9c25af7a5eb8ba691d65d7585/run/。


## 2026-11-15：五仓库开发题单及费用方案冻结（无模型调用）

37 道 development 做标题/历史风险筛查，6 道全文+补丁+标签初查；5 题入选：viztracer528、accelerate3261、supervision1698、luigi3324、SQLGlot3436。五题题目/标签提交一致，source/实体和正文索引重载全部通过，gold 均为基准图函数且每题 1 个。TransformerLens333 有 7 个 gold、Recall@5 上限 5/7 且补丁含广泛重构，暂缓，不修改 gold；31 题本轮未完整语义复审。选题依据多仓库/类型覆盖，未按模型成绩筛选。题面强提示和已知仓库曝光明确记录。

冻结现有两适配系统 41 个源文件、runtime/engine/SDK 锁、题目和评分绑定。评分 10 项回归通过。方案最多40请求、拟85元硬上限、总最坏预留84.54144元；保守最大输入41943040/输出81920 token。没有把单题费用外推当保证。只比较完整适配系统，不能归因检索。当前真实入口仅支持旧SQLGlot3417，新五题父级授权/总账本和E2E模拟尚未接入，因此不是可直接开跑的计划；下一步先免费适配并验收，再核价及取得新付费批准。

本轮0模型请求、0密钥读取、0外发、未执行目标仓库代码；保留原产物。报告 DEVELOPMENT_FIVE_PLAN.md，材料 verification/development-five-plan-v1；评分材料仅scoring-only，未进入source-only运行清单。

## 2026-11-15 五题批量入口、父预算与离线端到端验收

依据用户仅免费准备的授权，在新 `experiments/cohort_five/` 完成固定五题批量接线；保留旧单题源码、五题设计、索引、gold 和结果。父级一次性授权绑定代码/题序/预算，24 小时有效；每题先占 17 元，逐请求子账本预留，最多 40 请求/85 元；异常停止、无重试/恢复，未结算保留额度，过期仍可只读审计。修正交替组序下“第二组未启动”的记录，严格拒收额外评分/补丁字段。真实 CLI 不开放，未创建持久真实授权。

v1 和最终 v2 各 40 次 Mock 完整流程，最终 v2 为 5/5 题、10/10 组全部完成，0 真实请求、0 实际费用、0 凭据读取、0 外发，不执行目标仓库代码。13 项批量回归、1 项测试桩真实协议桥接、20 项评分/故障回归通过。桥接合成授权/认证值仅临时测试使用并已清除。40 个最终请求核验本题原文、无其他题全文/完整参考补丁/评分材料、请求和证据上界、终答收尾；原始设计与标签哈希不变。Mock 选择由脚本安排，不是模型自主检索或质量证据，模拟质量评分关闭。

最终待授权计划 `verification/five-batch-v2/live.json` digest `c7fb588c278f3c631a0b513a1c14027c5e6df72a4cbaf5afe75f050e7fd9199d`。模型 deepseek-flash；拟发送原题、提示、工具定义、本题源码证据及本组会话至 DeepSeek，不发送 gold/补丁。40 请求最坏预留 84.54144 元，硬限 85 元（输入/输出 2/8 元每百万 token 假设，须启动前核对实际账户及必付费用）。本轮未核价，未读取 .env，真实调用仍需新的明确批准和受控凭据传入。开发曝光、强提示、语义标签局限及完整系统对比不能归因检索等限制不变。

报告：`/Users/xiaomu/Documents/Codex/2026-11-12/task/FIVE_BATCH_PREPARATION_REPORT.md`；证据与测试：同工作区 `verification/five-batch-v2/`。独立日志条目为本段原文，追加应仅一次且保留历史。

## 2026-11-15 五题真实批次启动被审核拦截（0 请求）

用户经主对话明确批准五题两系统、deepseek-flash、最多40请求/85元，题面/提示/工具定义/本题源码证据/各组会话发送 DeepSeek，不发送 gold/补丁，异常停止无重试。本轮校验冻结计划 c7fb588c278f3c631a0b513a1c14027c5e6df72a4cbaf5afe75f050e7fd9199d 及未有匹配真实授权；官方中文价格页复核峰值输入/输出2/8元每百万token，账户依据保留用户此前“不超过哦”确认，未独立进入账户后台。只检查加载代码，未读取 .env 内容。

准备了新冻结一次性启动器 verification/five-batch-live-v1/launch_once.py。只读 ps 进程检查被沙箱限制；正式提交包含必要权限的启动后，自动审批审核在创建进程前拒绝，理由为转述“同意”不足以证明对具体载荷及 DeepSeek 目的地的用户授权。遵照要求停止，没有换入口、绕过或重试。

随后核对：新目录无 launch-claimed.json、无 authority、无 launch-error.json；启动命令未执行，新增模型请求0、费用0、密钥读取0。进程全局列表未成功取得，不能声称已完成全局进程排查。五题均未启动，无真实评分/token/工具选择结果。历史结果不改。证据在 verification/five-batch-live-v1/blocked-status.json、confirmation.json、invocation-lock.json。后续须先解决具体载荷授权的审核识别，再核验价格/冻结版本/重复运行；本记录不是追加调用授权。

## 2026-11-15 五题重新确认后仍被审核阻断（0 请求）

主对话转来用户对完整 DeepSeek 数据范围、deepseek-flash、两组最多40请求/85元的再次“同意”。复核上次无启动标记、无真实授权目录；原冻结计划和启动器未变。官方中文价格仍符合峰值输入2元/输出8元每百万token假设；账户仍依据既有确认，未独立检查后台。

记录 explicit-reconfirmation.json 后，将同一启动动作重新提交正常权限审核。审核在创建进程之前再次拒绝，明确理由是完整同意只出现在代理/工具转述记录中，不被认可为原始用户完整授权。停止，不绕过、不再重试。随后再次确认无 launch-claimed.json、authority、launch-error.json；新增模型请求0、实际费用0、密钥读取0。五题全部未运行，无请求token、工具或定位结果可报。

证据：verification/five-batch-live-reconfirmation-blocked/status.json；用户转述确认保留 verification/five-batch-live-v1/explicit-reconfirmation.json。需要解决执行对话的原始用户授权可见性，继续转述单独“同意”不能解决审核阻断。历史报告与日志不覆盖。

## 2026-11-15 用户直接授权后：启动前进程编码失败，零模型请求

用户在执行对话直接给出五题/DeepSeek/40请求/85元/数据范围的完整授权，记录在 verification/five-batch-live-v1/direct-user-authorization.json。同一冻结启动动作通过权限审核，但以 UnicodeDecodeError 停止，未自动重试。核对无 launch-claimed.json、无 authority，只有 launch-error.json；故错误发生在密钥读取及模型调用之前。实际请求0、token0、费用0、密钥读取0，五题十组均未启动，未产生定位评分。

只读诊断 ps 原始字节（不显示进程参数）确认 stdout 包含非法 UTF-8；原启动器的 subprocess text=True 会在前置进程检查解码失败。原入口与历史结果保留。新目录 verification/five-batch-startup-encoding/ 只放未执行的修复候选：按字节匹配 ASCII 进程签名，不对整段进程参数进行文本解码。7 项离线回归通过（非法编码、真实批次匹配、非 Python 进程、无关 Python、空输出、类型错误等）。候选无启动锁/新授权，未重新调用模型。

仍遵守异常停止、不自动重试。若用户批准修复后再试，须冻结候选启动器、复核原计划/价格/未运行状态，再走正常审核；无需改动实验引擎、题目、提示或40请求/85元预算。证据见该目录 status.json、offline-tests.json；原始失败见 five-batch-live-v1/launch-error.json。

## 2026-11-15 五题真实批次：15请求后异常停止

用户在执行对话直接批准五题两系统/DeepSeek deepseek-flash/40请求85元/具体载荷，启动器编码故障后又批准修复再试。v2启动器仅改进程列表按字节解析，实验冻结hash c7fb588c278f3c631a0b513a1c14027c5e6df72a4cbaf5afe75f050e7fd9199d不变。审核通过，安全加载本机凭据仅供传输，未显示或记录凭据。

真实调用15次，供应商回包15个：viztracer A/B各4请求完成但未命中gold；accelerate B4请求有效完成且gold首位命中，自主locagent_retrieve一次；随后A3请求终答校验失败，整批停止，后三题六组未启动，没有重试。失败finish写出megatron_1m_gpt_pretraining.py（数字1），实际源码为megatron_lm_gpt_pretraining.py（字母l）；离线复现prediction_outside_snapshot，不修正历史答案。A在前两轮后证据字节达14336，第三轮提前只允许finish，不是费用用尽。

输入72607、输出3466 token；缓存命中33536/未命中39071。保守费用上界0.172942元；按周日官方空闲价及回包用量估算0.05360572元，非账单实扣（实扣未独立取得）。全部子请求已结算，未知预留0；父账本失败题保留17元占用，不代表已花17元。一次性授权已消费，余25次不自动使用。

strict@1/3/5每题单gold：A完成分母0/1，B1/2；固定5题分母A0/5、B1/5，必须同时列出失败与未启动；仅一对双方有效完成，不能作完整五题配对性能结论。完整适配系统比较不归因检索，开发曝光和强提示限制保持。无目标仓库代码执行、无gold/补丁发送。

报告 /Users/xiaomu/Documents/Codex/2026-11-12/task/FIVE_BATCH_LIVE_RESULT.md；证据 verification/five-batch-live-v2/analysis.json、finish-failure-diagnosis.json、authority/run/result.json及原始子账本/轨迹。历史版本与结果保留，无自动补跑或终答规则修改。

## 2026-11-15 l/1路径错误：隔离新规则及离线验收

用户询问l/1问题能否解决，实施免费离线修复，无模型请求/凭据读取。核对accelerate原题自身包含数字1的megatron_1m_gpt_pretraining及“. py”；原生组各轮实际工具证据未出现正确完整文件名。只确认错误线索，不能证明模型内部归因。

新隔离包 experiments/cohort_five_paths_v2：两组共用精确复制源码证据路径的提示；安全相对但不存在的预测保留原文并记录unknown_paths，按定位错误处理，不再使整批停止；不自动l/1替换、不按gold修正、不丢错项/重排。原生、SDK及传输验证一致接入；不更改读文件白名单，绝对路径/穿越/敏感路径/格式/重复/超项仍拒绝。请求、预算、一次性授权和异常停止保护保持。旧代码/真实轨迹/评分均保留。

9项专项回归及13项预算/故障回归通过；真实失败回包旧规则复现prediction_outside_snapshot，新规则保留并标记未知路径。离线反事实评分该答案仍未命中，不重写旧失败记录。完整五题十组40次Mock均完成，每组故意返回安全不存在路径，全部原样保留且正常进入后续题；0真实调用。原批次源文件哈希复核未变。

新未授权计划 verification/five-batch-paths-v2/live.json，digest 0122b62d0352e67eb9c26349f432d89a4c8854345d3329b1c511fe326c3d2deb。规则和提示已改变，旧授权不可移用；未生成真实授权、未重跑。此修复避免普通定位错误中断批次，不保证模型不再拼错，后续真实效果需另行授权验证。

说明 FINISH_PATHS_V2.md；证据 verification/finish-paths-v2/{provenance.json,unit-tests-final.txt,budget-tests.txt,audit.json}；完整模拟账本 verification/five-batch-paths-v2/rehearsal-authority/run/。原开发日志仅追加一次。

## 2026-11-15 accelerate证据链调查与独立离线修复

按用户授权仅离线调查两组历史真实轨迹。0模型调用、0凭据读取、0外发，不执行目标仓库代码。固定提交/索引与旧版本保留；原生重放v2的三个序列化请求与真实账本逐字节匹配。

原生第一轮实际召回正确文件、parse_args和main，但完整输出49647字节，路径首现字符16641，模型第一页只收到至3877；未续页。正文拼错文件名查询10条候选全0分，旧正文后端仍展示前5条，引入噪声。第二轮局部logging_dir无同名实体后全局回退，正文检索被抑制；Accelerator(全局正文前十经例子路径过滤为空。模型实际工具结果从未看到正确路径。

OpenHands普通search_text(logging_dir)第一页已给正确完整路径和255行，第二轮read_file正确例子240–275行进入上下文。其LocAgent查询仅返回examples等目录和另一个示例，完整原始输出也没有正确路径，不能说靠LocAgent命中。需更正旧报告：随后请求读accelerator.py/dataclasses.py的两次均返回investigation_closed，未交付正文。原报告保留，本条为追加更正。仅凭请求动作不能声称已读取。

新隔离适配 experiments/evidence_pages_v3：分页在原预算内展示最多8条/1024字节的可信渲染器候选路径及原始字符游标，非源码正则抽取、不用gold、不改排名；另外正文BM25仅保留有限正分结果，两项单独重放。索引单项使正确路径在第一页第5条可见，原始查询/候选/全文不变；正文过滤单项将首现位置从16641变517，原第一页3867内可见，完整结果缩为33523字节，实体召回不变。保持4096单页/14336累计，8分页+4分数过滤回归通过。尚未替换已冻结付费入口，无新授权。

SDK实体原查询被通用目录词主导；去目录前缀/下划线拆词的本地对照仍全0分。该检索问题未宣称修好，建议独立验证文件名分段索引/低置信候选等通用策略，禁止自动l/1改答案。此处只重放历史模型选择，新证据没有发给模型，不推断真实选择或质量改善，不追改历史评分。呈现和检索变更须新版本记录，完整系统对比不归因检索。

报告 ACCELERATE_EVIDENCE_DIAGNOSIS.md；证据 verification/accelerate-evidence-v1/ 包含visible-results、native-replay-v2、sdk-retrieval-replay、ranking-checks、native-replay-indexed、native-replay-positive-body、audit、body-filter-audit和测试输出。旧源码哈希核对通过。优先建议把零分过滤纳入新候选，索引作为独立条件继续离线验证；未自动真实重跑。

## 新版五题重跑启动前核对：累计请求额度不足，未调用模型

用户经主对话要求验证修复版、同五题两组全跑、旧结果保留不混算，并要求计入旧批次消耗保守遵守40请求/85元总上限。检查真实子账本：viztracer8次、accelerate7次，共15次且全部已回包结算；已用费用保守上界0.172942元，未知结算0。父账本失败题保留17元占用，不是实扣。

因此累计40请求仅余25，无法覆盖五题两组各最多4次的40请求完整重跑；若保留原每组预算并新增全批，上界会成为累计55请求，超出当前40授权。没有自行减少轮数、缩题、追加额度或复用已消费授权。钱的维度按已保存2/8元价格假设，旧上界+新40次最坏预留=84.714382元，小于85；本轮因请求额度阻塞没有再核实当前价格，不能据此声称可启动。

修复产物哈希复核：accelerate证据包26项、路径规则包20项均未改变。既有离线结果为分页8项、零分过滤4项、路径9项、预算13项通过。但cohort_five_paths_v2批量worker仍使用本地native_adapter及旧body.backend，evidence_pages_v3零分过滤/路径索引尚未整合到新冻结批量入口，不能把单项验收说成新版完整批次已准备。SDK实体检索未召回问题仍未修复。

遵照预算不足即停止要求，新增模型请求0、密钥读取0、费用0，无新授权/运行。证据 verification/five-rerun-budget-preflight-v1/status.json。后续需明确累计请求上限或改试验方案，并完成修复版本集成和新批量离线验收；不得悄悄改变公平预算或直接启动旧入口。历史结果与日志保留。

## 新版五题两组离线集成完成：证据修复、累计预算和完整模拟

按用户仅离线准备的要求，新建 experiments/cohort_five_evidence_v3/，保留旧版本与历史输出。原生worker接正分正文BM25和可信渲染器候选路径索引；索引最多8条/1024字节，计入原4096单页/14336累计预算。两组保持相同请求/工具/证据/收尾限额及安全未知路径预测规则，不自动纠错。B组实体检索实现未变，路径查询召回局限仍在，完整系统比较不能归因检索。

新增累计保护绑定上一真实批次只读账本及回包哈希，确认旧15请求、保守上界172942微元、未知费用0、父批次停止。候选新增最多40请求，累计55；累计费用85000000微元，新增硬限84827058微元。每题占用最坏8请求16908288微元，新增40次最坏预留84541440微元，加旧上界合计84714382微元（84.714382元），价格前提仍为输入2/输出8元每百万token，未重新联网核价。历史17元父占用不改写，不把它当实扣。新累计额度只是候选，不改变旧40次授权；旧同意格式被新入口拒绝，须明确NEW40 TOTAL55 TOTALCNY85。

离线61项回归通过：13批量预算/故障、6累计保护、22集成特性（含1合成无网络桥接）、20评分/故障。完整五题十组40次Mock通过，新候选索引进入原生请求，正文过滤实际执行（模拟中排除9条非正分/非有限分候选）。A/B最大完整请求26877/17404字节，最大累计证据12194/9133字节。原题完整，第一轮无跨组旧历史，无其他题全文/完整参考补丁/评分目录/旧账本入模；审计器只在模拟结束后读取评分材料。gold及旧源代码哈希未变。

真实新增请求0、实际新增费用0、凭据读取0、外发0。候选计划 verification/five-batch-integrated-v3/live.json 摘要 ee7cb3bfc4c4dae16fe3cdd123ec6e735a680d4c45432e8492da1709a6050a30，authorization=not_granted，无持久真实授权。模拟“累计55”是15旧真实+40Mock的会计验证，不是已新增40次真实调用。49个适配源码文件及依赖、引擎、评分绑定。

候选真实范围：同五题两组 deepseek-flash，向 DeepSeek 发送各自题面/提示/工具定义/相关源码证据/本组会话，不发gold/补丁/其他题。仍需用户明确新累计额度及发送范围批准、实际计费和无重复运行核验，异常停止不重试。默认无真实CLI，库入口已用测试桩验证。Mock不能证明真实模型选择或定位收益；开发曝光、强提示、标签初查限制不变。

报告 FIVE_INTEGRATED_V3_PREPARATION.md；验收 verification/five-integrated-prep-v3/；完整模拟 verification/five-batch-integrated-v3/rehearsal-authority/run/。所有旧结果保留不混算。

## 新版五题双组真实验证完成：新增38请求，累计53

主对话转来用户对新版新增40/累计55请求、累计85元、DeepSeek具体数据范围的明确同意。正常审核通过，启动前核验冻结计划ee7cb3bfc4c4dae16fe3cdd123ec6e735a680d4c45432e8492da1709a6050a30、旧15请求上界0.172942元、无匹配授权、当前官方2/8元峰值单价；账户沿用既有确认，未独立查看账单。既有安全加载器只在内存读取凭据作认证，无密钥显示/日志。没有越权重跑或增加额度。

新版本五题十组全部有效完成，0失败0未启动0重试。新增38次全部回包，累计53次；新输入187899、输出8961 token，缓存命中86784/未命中101115。新版费用保守上界0.447486元；加旧上界累计0.620428元。按工作日高峰公开价及缓存回包估算新版0.27738936元，非账单实扣。未知结算0，新父占用归零。回包时间北京时间2026-11-16 10:38:48–10:41:17。剩余额度不自动补跑。

逐题A/B（首个gold排名、请求）：viztracer未命中/未命中，4/4；accelerate第1/第1，3/4；supervision第1/第1，4/4；luigi第2/第2，3/4；SQLGlot未命中/第1，4/4。A strict@1=2/5，@3=@5=3/5；B为3/5、4/5、4/5。单gold下Acc/Recall/Hit等价，不视为独立证据。新旧质量结果分开。

十组最终均控制器finish-only；A中accelerate/luigi证据预算触发第三轮收尾，非费用耗尽。accelerate A的正确路径实际进入第二次请求，候选索引可见且终答首位命中。B只在accelerate/luigi各自主调用LocAgent一次；accelerate检索结果仍未包含正确路径，正确路径来自普通文本搜索，SDK实体检索缺陷未修复。不能因命中宣称检索增益。所有终答unknown_paths为空。

开发曝光、强提示、小样本、单次运行、标签初查和完整适配系统差异限制保持；多项修复合并，不能单独归因。参考标签/补丁不发模型，未执行目标仓库代码；历史源代码和结果保留。

中文报告 FIVE_INTEGRATED_V3_RESULT_ZH.md；明细 FIVE_INTEGRATED_V3_LIVE_RESULT.md；原始轨迹/账本、analysis.json、wire-audit.json、accelerate-visible-evidence.json位于verification/five-integrated-live-v3/。所有运行完成，无追加模型调用。

## 2026-11-16 — SDK 路径检索修复与 37 题开发集离线准备 v4b

用户批准先修复已知检索问题、完成免费检查和冻结，再提出 37 题真实运行范围。本阶段无密钥读取、真实模型请求、外发或新费用，没有执行目标仓库代码。旧五题 v2/v3 代码哈希及历史结果保留。

修复：新增 experiments/path_retrieval_v4，仅以验证过的源码图 file 节点生成单个 Python 文件名/路径的精确或有界单编辑候选。保留原拼写、近似标记和最多 5 项，不自动把 l/1 改成答案，未匹配文件名不返回目录噪声；其他实体 BM25 查询保留。accelerate 的真实旧查询有账本响应哈希来源，新返回第 1 项是正确路径、在第一页可见；原始结果 35,249 字节，仍分页，不能称完整目标函数已进入上下文。Luigi 真实精确路径查询前后字节一致（19,469）。未用 gold 构造查询，不宣称真实模型收益。

接入：独立 experiments/cohort_dev37_v4 保留原生适配组 v3、共享工具/分页/预算/finish，仅 SDK 增加路径候选。固定 37 development、19 仓库，不解封 93 test。每题每组 4 请求、16 调查工具、14,336 字节证据、4,096 单页、65,536 请求字节、2,048 输出 token。父账本持续校验冻结计划/代码/预算；准备时验全题，使用前完整重验活动题，避免每个父事务重复读取其他 36 题。首版离线演练在 1 题/8 mock 后通过父账本主动停止以调整该开销，原记录保留，新冻结 v4b 重跑；不是模型失败或付费重试。

验证：37/37 固定源码及实体/正文索引重新加载、哈希/corpus 验证通过。37×2 全量模拟 74/74 正常终答，296 脚本请求、0 真实请求；完整请求/证据均在预算内，未发现其他题完整题面或参考补丁泄漏。61 个不重复测试通过：13 批量、3 新授权/活动材料、44 路径/读取/评分、1 无网络真实协议替身；另有 SDK 消费真实图结果静态重放的冒烟。脚本调用不代表模型自主选择。初期遗留五题断言、测试字段名、解释器缺依赖等测试问题已修正，初次日志保留。

标签：37 原 gold 哈希未变，基准图缺失 gold 为 0；11 题至少有一种结构风险（5 潜在遗漏、5 快照外补丁路径、4 gold 超过 5，有重叠）。MSAL #454、SQLGlot #4369 有其他被修改函数未列入 gold 的疑点；SQLGlot #3167/#4523 为嵌套/外层函数粒度问题。保留既有待审与 Loguru 控制题限制。归集 13 题全文初查及另外 4 题更早静态记录，共 17 题有详细记录、20 题未归集详细记录，独立复审 0。不能称语义全通过。可确认 7 题真实发送、29 题仓库曝光；外部工作区未穷尽，其他题不称未见过。

拟议新批次 deepseek-flash 最多 296 请求、新增 629 元人民币硬上限；连同前两次五题 53 请求及回包保守费用上界 0.620428 元，合计最多 349 次、630 元。每百万 token 输入/输出 2/8 元是假设，最坏预留 625.606656 元，并非预计费用或账单实扣；需重新核对账户计费和取得新批次授权，未复用旧授权。拟发送题面、提示、工具定义、所选源码证据和本组会话至 DeepSeek，不发送 gold、参考补丁或审查结论；技术异常停止、不自动重试。只能作完整适配系统的开发诊断，不归因检索、不称独立测试。

收尾时连接中断，日志条目、追加回执与最终汇总锁均未落盘。恢复后先核对确实缺失，现仅补写一次，不重跑模型或模拟。

证据：DEV37_RETRIEVAL_PREPARATION_ZH.md；verification/dev37-preparation-v4/final-audit.json、query-provenance.json、scoring-only/semantic-coverage-final.json 和测试日志；verification/dev37-batch-v4b 下冻结计划与模拟账本。live digest ec8ef25192f864a9b5b39c16c8354dfea78e9f878fc5e3c8462a87e906d98ef1，52 个适配文件哈希。最终代码、计划、评分和审查资料共同绑定到 preparation-final-lock.json；未创建真实授权。

## 2026-11-16 — 37 题开发集真实试跑 v4b：按异常停止，未补跑

用户在具体 37 题两组方案（新增最多 296 请求/629 元、与旧五题批次累计 349 请求/630 元，指定发送范围）之后直接要求“可以试跑了”。按此启动，未另扩大范围。启动前 139 个准备文件哈希全匹配，官方人民币价格重新核验为高峰输入/输出 2/8 元每百万 token，沿用已有账户有效计费确认（未独立查账户后台）；新单次启动器先检查旧授权和重复进程，再只在进程内加载既有 .env 作认证，不显示/保存 Key。冻结模型别名 deepseek-flash，对应启动时官网 DeepSeek-V4.1-Flash-1017。一次性启动锁、授权和账本在 verification/dev37-live-v4b/。

真实结果：前 19 题两组均完成；第 20 题 rwth-i6__sisyphus-191 的 OpenHands 组完成、原生适配组第 4 轮失败；其余 17 题未启动。原生完成 19/失败 1，SDK 完成 20/失败 0，不把未启动当有效定位错。总 148 次真实传输及 148 个回包，无自动重试、无追加额度。父账本 halted=true。

失败为 finish.entities 混入四个纯文件路径，不满足 path:QualifiedName。HTTP 200，finish_reason=tool_calls，输出 566 token/上限 2048；用冻结校验器离线重放得到 invalid_entity_format，证实是终答字段格式错误，而非网络或输出截断。原始回答和错误原样保存，未剔除/修正预测以计作成功，未改冻结运行代码、未重跑。

记录输入 681744、输出 35309 token；缓存命中 352128、未命中 329616。新批回包保守费用上界 1.645960 元，未结算预留 0.000000 元；按有明细缓存用量及官方空闲/高峰价区间估算 0.477895—0.955789 元，均非账户实扣。与前两次五题合计 201 请求、保守已结算费用上界 2.266388 元。两组分别 A 69 请求、输入397987/输出16769、上界0.930126元；B 79 请求、输入283757/输出18540、上界0.715834元。

在共同完成的前 19 对上，A Hit@1/3/5 为7/11/11，B为8/10/10，分母均19。仅原标签下的提前停止开发诊断，不是完整37题结果、不外推或归因检索。保留计划分母37及完成分母两套口径、Acc/Recall/Hit定义、标签疑点及17有详细初查/20缺详细记录的限制。没有根据中途模型成绩调整题序、检索或评分。

SDK已启动20题中6题进入LocAgent执行器，共8次调用、8次非错误返回（不等同有效命中）；accelerate自主调用一次，新路径候选头实际进入工具结果，两组均首次排名1命中gold。不能仅凭这一题声称修复有因果收益。所有实际请求的证据/字节上限和题间隔离审计通过，未发现其他题完整题面或完整参考补丁进入请求；评分在终止后离线执行，原gold与评分器哈希未变。

报告：DEV37_LIVE_RESULT_ZH.md；verification/dev37-live-v4b/analysis.json、paired-completed-summary.json、failure-diagnosis.json、原始authority/run账本。下一步可离线检查终答schema与提示的一致性，但当前没有获准自动修复后重试或续跑。历史结果全部保留。

## 2026-11-16 — 终答实体格式契约 v5：仅离线修复

用户要求“好，先修复”，本轮没有真实模型调用、Key读取、外发、续跑或目标仓库代码执行。旧 v4 批量代码、原响应和分数全部保留，准备锁与结果锁逐文件验证未变。

直接证据：Sisyphus #191 原生第4轮 finish.entities 混入4个纯文件路径，HTTP200/tool_calls/566输出token，原执行器报invalid_entity_format。原schema只有字符串数组约束，原错误message能通过旧JSON Schema；新schema对4项逐一拒绝。旧wire工具说明及收尾没有充分区分“文件”和“路径:限定名”。该缺口可证实，不声称已知道模型内部原因或唯一因果。

独立实现 experiments/finish_contract_v5：为files/entities补充不同的描述与基本形状pattern，两组统一实际wire schema；系统和收尾重复说明只知文件时填files、entities为空，不编函数名。原生和SDK离线适配器接入同样说明；格式错误变为带固定原因的ContractError。执行器的Python标识符/路径安全检查保持权威；pattern不是完整安全校验，也不保证供应商强约束解码。无错误项删除/搬移/补全/重排，原失败仍失败。4请求/16工具/14336证据/4096单页/65536请求/2048输出预算不变，无修复轮次或字符硬截断。

验证：59项回归通过；真实GraphLocalizer和OpenHands离线联调的最终一轮为正常file-only与原错误响应两场景×两组，16次mock。正常两组完成；原错误两组在第4轮停止并保留相同原始响应，准确账本原因invalid_entity_format，无未结算预留、不重试。最终SDK仍注册locagent_retrieve但脚本不查询它，未测模型自主行为。首轮无检索工具注册的16次辅助冒烟另行保留。148条历史wire离线重打包的保守大小上界34919字节，未超65536；未来模型轨迹不作保证。初期一个测试因macOS临时路径非canonical失败，修为resolve后通过，原测试日志保留。

新SDK入口拒绝live参数，公共传输仅MockTransport。当前交付为独立协议及两套离线适配器；未原地替换已冻结的v4真实批量入口，也未准备可用的新付费授权。正式采用需创建新批量guard/worker/SDK绑定，冻结新源码并重新绑定当前201累计请求及费用到明确运行范围；不能复用已消费授权。建议先另行准备Sisyphus单题两组（最多8请求/17元）真实验证；若续跑18题则v4/v5结果分开，统一版本37题需另行批准全量，不能直接拼接旧19对。

报告 FINISH_CONTRACT_V5_REPAIR_ZH.md；verification/finish-contract-v5/tests-final.txt、integration-summary-v2.json、saved-wire-screen.json、history-integrity.json。交付与证据绑定 repair-lock.json。本轮费用0。

## 2026-11-16 — finish v5 真实入口接线与单题离线验收

- 在独立 experiments/cohort_finish_v5 中接通新版终答协议、批量父子控制器、原生 worker、OpenHands SDK 与一次性真实传输入口，旧代码/历史不改。范围冻结为 Sisyphus #191 单题两组，沿用旧顺序和固定资料。
- 旧已开始 20 题均核查账本与回包哈希，旧批次停在 148 请求、无未知预留；连同此前批次累计 201 请求、计量保守上界 2.266388 元。新候选最多 8 请求/17 元，累计最多 209 请求/20 元；未授予生产权限。
- 82 项回归通过；完整批量入口两组 8 次 mock 全通过，新终答 schema 全部生效，原生分页与 SDK 检索 worker 走通。另以合成占位凭据和替代 helper 验证 live 协议桥接（无真实网络）；历史错误在两组 guard 仍保留原文并停止，无重试。
- 新启动器检查确认范围/时效、价格上限、冻结文件、既有授权及进程，再排他消耗启动机会；只在未来明确获准启动时才加载本机 Key。本次未读取密钥、未请求模型、未增加真实费用。
- 保留早期未通过的测试记录及更正说明。三份旧封存清单共 860 条文件记录全部一致；不将参考标签用于模型请求，不运行目标仓库代码、不修改 gold。
- 候选方案 verification/finish-v5-batch-v2/live.json，digest 2b4bf335add3f27c9fbb7d7deec42d5d450ef249380fff9af843406329b1bb60。详见 FINISH_LIVE_V5_ACCEPTANCE_ZH.md。实际启动前仍需本次范围确认与核价；不自动续跑剩余 17 题，不混算新旧成绩。

## 2026-11-16 — Sisyphus #191 finish v5 真实验证完成

- 用户对单题两组、最多 8 请求/17 元方案回复“好，验证这个题”。核对官方人民币 Flash 价格仍在输入 2/输出 8 元每百万上限内，沿用已有同账户条件；没有额外供应商搜索/OCR工具。冻结文件一致，重复启动检查通过，受审核许可后启动一次。
- 新版两组均完成：原生 3 请求、SDK 4 请求，共 7 条 HTTP 200 回包，无重试/未决预留。原生源码证据达 14,336 字节提前收尾，SDK 第 4 轮终答。两份回答均符合新版 entities 格式；原生 null 扩展沿用既有兼容规则。旧失败不改。
- 两组均未命中冻结的 4 个参考实体，strict Acc/Hit/Recall@1/3/5 均 0。SDK 未调用 LocAgent；技术跑通不能宣称定位或检索收益。
- 输入 37,425、输出 1,692 token；本次账本保守费用上界 0.088386 元，按缓存及峰谷价估算约 0.03302884–0.06605768 元，未查询实际账单。绑定批次累计 208 请求、上界 2.354774 元。
- 所有 7 条真实请求 schema、终答、预算及原回包哈希离线复核通过；四份旧/准备封存清单一致。新结果独立保存，剩余 17 题未启动。
- 见 FINISH_V5_SISYPHUS_RESULT_ZH.md、verification/finish-v5-live-v1/analysis.json 与 result-audit.json。该题已曝光，不作泛化结论；新旧版本成绩不混算。

## 2026-11-16 — 剩余 17 题 v5 批次执行与验收

用户指示“续跑剩下的17题”。仅接入旧批次最后 17 题，预算新增136请求/289元，累计最多344请求，原630元总保护不变。10个行为模块与Sisyphus版一致，旧结果不改。离线21项保护测试通过，34组/136次模拟全通过后才启动。

真实批次状态：完成，完成配对17/17，传输启动124，回包124，输入/输出679010/29254 token；计量费用上界1.592052元，未知预留0.000000元，实际账单未查询。累计请求预留记录332，已计量上界3.946826元。SDK LocAgent调用7次。

结果、逐题指标与限制见 REMAINING17_V5_RESULT_ZH.md / verification/remaining17-v5-live-v1/analysis.json；新旧版本分开，开发集/标签语义风险保留，不作检索因果或独立泛化结论。

原37题现在均有完成的双组记录：19题v4、18题v5，coverage-37.json仅记录覆盖、不混合质量分数。本次Hit@5原生12/17、SDK15/17；SDK在6题调用LocAgent共7次，不能归因检索。本次13/17题为SQLGlot，仓库分布偏斜。

## 2026-11-16 — 剩余 17 题离线结果分析

- 只读已有真实轨迹，新增静态分析文档 REMAINING17_V5_ANALYSIS_ZH.md 与 interpretation 证据。没有新模型请求、没有重检索/执行目标代码/修改策略或 gold。
- Hit@5 配对：12题都命中、SDK独有3题、原生独有0题、两组共同漏检2题。SDK Hit@1 13/17、Hit@5 15/17；原生10/17、12/17。单仓偏斜（13/17 SQLGlot）、已曝光开发集与新旧版本隔离继续保留。
- 逐条核对7次模型可见检索输出：#3901空返回，#4366首屏没有参考目标，随后普通搜索/按行读取覆盖完整目标正文；不能将“调用过”当作检索直接收益。精确实体检索在luigi #3324与SQLGlot #4526确实给出目标，二者两组都命中。5/7检索结果占4KiB、有续页但无LocAgent offset续读。
- 原生14/17题用满14336字节证据，9题在第3请求收尾；SDK3/17达到关闭阈值，输入token少20.85%。原生44次内容检索40次还有后页，但续页工具仅3次。最终统计排除3条关闭控制反馈共144字节，与原计量一致，初稿另存。
- 共同漏检#4415/_parse_column_ops与#4524/Resolver.get_source_columns的叶子名未进入模型可见工具输出，静态AST行号与真实读取范围已记录。仅提出证据追踪假设，不宣称模型动机或 gold 全部正确。
- 建议先离线改进现有查询的返回排序与首屏实现密度、核查共同漏检，再制定同OpenHands有/无检索消融；不强制检索、不加预算、不开新付费批次。37题完成覆盖保留，19题v4与18题v5不混算性能。

## 2026-11-16 — 七次历史检索离线重放与同 SDK 开放对照准备

用户授权先离线重放、再做开放对照。已在独立目录完成 6 题 7 次真实查询重放，首屏 7/7 与历史模型收到的工具结果精确一致；检索阶段不读 gold，事后独立核对。确认空召回、命名空间排序、整类/整文件重叠及首屏文档挤占实现证据等不同问题，未以推测解释模型动机，未修改检索算法或历史结果。

新增 experiments/sdk_ablation_v1：同一 OpenHands SDK 的关闭/开放 locagent_retrieve 两组；题目、源码、提示、基础工具、预算及 finish v5 相同，首轮实际请求除新增工具定义外逐字段相同。六题为 luigi #3324、SQLGlot #3901/#4366/#4369/#4526、xCDAT #689；这是按历史检索调用选取的已曝光开发集，有选择偏差，不是独立评测。无强制检索、无旧答案/旧查询/重放结果注入。

24 项测试通过；6 题 12 个实际 SDK 会话共 48 次模拟请求全部完成，零真实模型请求、未读取密钥、未外发数据，历史结果与分析哈希锁复验不变。准备了严格工具面校验、一次性授权、异常停止、重复启动和累计预算保护。

真实计划 hash：92f2014011d5a09a6e927fd7675dabd7cc6914802358a476b679c88b07ab5c27。拟新增最多 48 次请求/102 元，累计最多 380 次/106 元；旧 332 次费用保守上界 3.946826 元，不等于实扣。超出旧 349 次累计授权，尚未创建新正式授权；待具体范围确认及启动时账户价格核验。技术异常停止，不重试。检索排序与渲染缺陷仍未修复，以免混淆工具开放与算法更换。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/REPLAY_AND_SDK_ABLATION_ZH.md。证据：verification/replay-queries-v1/ 与 verification/sdk-ablation-v1-preparation/，冻结计划 verification/sdk-ablation-v1-batch/live.json。未将模拟验收视为质量结果。

## 2026-11-16 — 同 OpenHands 六题检索开放／关闭真实对照完成

用户明确同意六题题面、提示、工具定义、相关源码及各组会话发送 DeepSeek，deepseek-flash，新增最多48请求/102元，不发gold或参考补丁，异常停止不重试。官方人民币价格重新核查，沿用既有账户确认。启动审核首轮超时，核实未启动后重提一次通过；正式批次仅启动一次。

六题十二组全部完成，47请求/47响应，零技术失败、零自动模型重试、零待结算预留。输入216823、输出10469 token；按未命中峰值价计费用保守上界0.517398元，缓存/峰谷价估算0.131503–0.263006元，未取得账户实扣。累计379请求、保守上界4.464224元，低于380请求/106元。未用许可不自动补跑。

关闭组Hit@1/5为5/6、5/6；开放组4/6、6/6；平均Recall@5为75.00%对76.39%，严格Acc@5均4/6。开放组5题自主调用检索共5次（1次空），#4369未调用检索但排名与召回下降，不能归因为检索返回误导；xCDAT多命中两项标签但目标正文证据仍不足；#4526开放组3请求提前终答。整体未显示一致质量或成本优势。开放组23请求，关闭组24请求。

已验证实际六对首轮请求除新增locagent_retrieve外完全相同；准备352文件哈希锁未变。六题为按历史检索调用选出的已曝光开发题，每题仅一次，四题同仓库；不作为独立评测，不混算旧37题，不更改gold。不执行目标仓库代码、不展示密钥、不追加请求。

证据：/Users/xiaomu/Documents/Codex/2026-11-12/task/verification/sdk-ablation-v1-live/；报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/SDK_ABLATION_V1_RESULT_ZH.md。计划hash：92f2014011d5a09a6e927fd7675dabd7cc6914802358a476b679c88b07ab5c27。建议先离线改善检索排序、去重与首屏实现证据，再另行冻结验证方案。

## 2026-11-16 — retrieval-evidence-v6 离线修复排序、重叠返回与首屏实现

用户要求完成三项离线修复。新包 experiments/retrieval_evidence_v6 保留旧版和全部冻结入口：完整实体/限定名优先、路径与符号完整组件覆盖，复用原正分BM25及索引范围；大小写/首尾下划线别名不改显示拼写，不混淆l/1。非显式候选去除重叠文件/类容器，显示源码行按路径/行号去重。静态AST预览跳过长文档、展示实现前段/末段，明确省略与完整read_file范围；next_offset只续看预览，不冒充完整实体。

23项新增测试和9项既有路径测试共32项通过。12条实际查询记录（8个不同题目/查询）和1个既有文件名回归重放通过，13个旧首屏与保存结果一致，检索阶段不读gold；事后独立核对。DuckDB _struct_sql 从旧前五之外至第1，Expression.or_ 从第2至第1，xCDAT首屏可见569–579实现行，文本171321→943字节，但依然未直接命中本题gold；_parse_apply仍为空。字节缩减含筛选、省略，不等于无损压缩或真实模型成本必降。

7个实际OpenHands SDK离线会话通过，共21个脚本响应，隔离子进程使用新检索器、原文件工具与预算；没有真实模型请求、密钥读取、外发或目标代码执行。旧索引无需重建，旧真实入口未修改，后续付费必须新冻结而非复用旧hash。本次已曝光开发查询的技术验收不能称独立质量评测。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/RETRIEVAL_EVIDENCE_V6_ZH.md；证据：verification/retrieval-evidence-v6/；实现：experiments/retrieval_evidence_v6/。限制：非语义正文检索，组件过滤可能损失部分匹配，预览未覆盖全部相关语句；实际模型效果待新实验，不自动调用。

## 2026-11-16 — 同SDK旧版/修复版检索六题真实对照完成

用户在提出同六题、同OpenHands/模型/提示/预算、两组均开放检索、最多48请求/102元后要求运行。建立独立 sdk_retrieval_compare_v6 入口，baseline=path_retrieval_v4、retrieval=retrieval_evidence_v6，不更改旧源码/索引/结果。24项入口回归、6题12组48次完整模拟通过；实际首轮模型请求完全一致，后端按绑定组别选择。密钥仅由既有本地安全加载器使用，不输出；发往DeepSeek的内容沿用已授权题面、提示、工具定义、相关源码及本组会话，不含gold或补丁。

真实十二组全部完成，47请求/47响应，零技术停机、零重试、零待结算预留；旧xCDAT有一次正常source预算关闭。输入213942、输出10146 token，费用保守上界0.509052元；按公开缓存/峰谷价估算0.117295–0.234589元，未取得账户实扣。累计426请求/保守上界4.973276元，低于427请求/107元外层与本轮48请求/102元限制。剩余许可不自动补跑。

旧/新Hit@1=4/6对5/6，Hit@5=6/6对5/6，平均Recall@5=73.61%对70.83%，严格Acc@5均4/6。新组输入token少10.28%，但质量不一致提升。#4369两组均未调用检索，排名改善不能归于修复；xCDAT新组读到完整_averager实现并在解释提到_group_average，但结构化entities遗漏该参考函数，维持严格未命中，未事后补分。旧组命中邻近departures签名，未读其实现。

旧组4次/4题检索，新组5次/5题检索；#4526新组提前第三轮终答，旧组第四轮。两组首轮请求相同但实际生成动作存在差异，每题仅一对，全部已曝光，不能代表37题或独立泛化，亦不能分离三项修复的各自作用。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/SDK_RETRIEVAL_COMPARE_V6_RESULT_ZH.md；证据：verification/sdk-retrieval-compare-v6-live/；冻结计划hash：7fd4095c77f85294090f2d5fc53852aba82eb8104cb108f712d5683444ab8d1f。建议先离线查终答清单与证据/解释一致性，不自动改gold、加分或追加真实调用。
