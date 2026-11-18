# 等源码空间与固定调查轮次：离线实验控制

2026-11-10。仅离线 mock、合成图与回归测试；没有真实模型调用，没有读取 key，没有改写历史账本或启动/重启用户服务。尚未证明真实定位质量提高。

## 为什么分开处理

历史三题六臂报告中，7220 的相关候选在第二轮送达，第三轮已经只许 finish；11143 开启臂的源码工具消息空间只有 14,336 字节，且目标类签名出现后另一条工具调用触发预算收束。前一问题是调查机会，后一问题是空间和收束。单独增加轮数不能恢复已经耗尽的工具消息额度。

因此不引入“遇见候选就续轮”逻辑，也不自动放大任何旧计划。使用两个独立控制：

1. 轮数使用已有 `max_iterations`，从 3 改成 5 时，双方同为最多 5 次 provider 请求：4 轮允许调查，第 5 轮仅 finish。第 2 轮出现的候选有第 3、4 轮继续调查机会；这是预先设定的预算变化，不是免费额外轮次。
2. 新增 `LocalizationOptions(search_protocol="bounded-v1", equal_source_budget=True)`，严格布尔、默认 False。所有臂统一预留 closing 4096 + candidate guidance 4096 + reread/drilldown 2048 = 10,240 字节，源码工具消息额度均为 24,576 − 10,240 = **14,336 字节**。未使用的控制槽不退还源码，避免关掉提示的一臂反而拥有更多源码空间。

该数值计入工具消息 JSON 的包装、转义、ID、分页提示等，不等同于原始源码字节数、token 或供应商计费。单条消息 8192、请求估算门限 65536、每批最多 16 调用、补读最多两次等原上限不变。候选与类签名仍须真实送达且来自可信渲染器；本轮没有扩大源码权限、自动选择候选或按已知答案特殊处理。

不新加轮数选项，因为 `max_iterations` 已经是总请求硬上限。模型可以提前 finish；预算耗尽仍立即进入只许 finish 的下一轮，context gate 仍可在 provider 调用前拒绝。第四轮才出现的新候选仍无法在第五轮调查，测试明确保留这一边界，不能承诺任意晚到证据都有行动机会。若要真正保护尾段源码，需另行设计分阶段额度，并独立评估其早期信息损失，本轮没有偷偷加入这种行为。

## 公平对照矩阵

固定同一源码快照、图、问题、供应商配置、随机/温度配置、最大输出和失败策略后：

- 固定 3 轮、旧空间：保持原机制的诊断对照，不能作为等空间收益证据。
- 固定 3 轮、等空间：隔离提示/候选机制，仍存在末轮无法调查的问题。
- 固定 5 轮、旧空间：只与同一旧空间的 3 轮结果比较轮数变化。
- 固定 5 轮、等空间：双方拥有相同源码空间与相同请求上限，作为后续机制对照的候选设置。

每个格子内部均跑 off/on，不能拿 3 轮旧空间 off 和 5 轮等空间 on 的差异宣称机制收益。这里 off/on 指**同一新源码快照**关闭/开启候选下钻，并非重用旧代码或旧授权。相同空间是相同容量，不保证真实模型选择相同工具、读到相同内容，亦不保证相同 token/费用；新增提示本身仍有成本。

未来真实实验必须生成绑定当前源码与这些明确选项的新计划、为双方相同轮数重新核算最大请求数及总费用，并取得批准。CLI、网页、服务、旧付费 runner 未自动接入新选项。旧三次调用账本/授权不能因核心支持五轮而继续使用。

## 实现

- `util/localization_contract.py`：默认关闭选项及严格验证。
- `util/localizer.py`：仅 bounded 路径转交选项。
- `util/localization_protocol.py`：统一 reservation；只在启用时新增 `source_budget` 诊断，列出容量、实际送达量、总请求硬上限和最大调查轮数。未改变执行循环或收束规则。
- `tests/test_equal_source_budget.py`：16 项离线回归。
- `scripts/offline_equal_source_matrix.py`：输出 8 臂固定脚本对照，不含真实 provider 调用。

新增测试覆盖六种功能模式的同一超长工具输出逐字节相同送达，以及实际 GraphLocalizer/capture_evidence 的全部八种布尔组合（包括自主补读和下钻同时开启）在固定脚本下的相同观测消息；显式 False/省略选项完整请求和结果一致；关闭时原 2048 字节差异保留；轮数/空间 2×2 独立；第二轮候选在五轮中可读正文再追调用；三轮不可继续；最后调查轮候选不能突破硬终局；单轮、提前 finish、context gate、输出截断、预算提前收束；Unicode/JSON 转义；超长 call-id 使控制反馈无法容纳时拒绝继续。

本轮兼容性检查比较的是当前源码显式关闭/省略选项，并复跑已有相关回归，不冒充重新执行独立旧源码逐字节重放。

## 可复现命令

项目根目录：

```sh
export TMPDIR=/private/tmp LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONPATH="$PWD:$PWD/scripts:$PWD/tests"
.venv/bin/python -B -m unittest test_equal_source_budget test_candidate_drilldown test_autonomous_reread test_visible_signatures test_candidate_guidance test_bounded_protocol test_budget_finish test_engine_binding -v
.venv/bin/python -B scripts/offline_equal_source_matrix.py
.venv/bin/python -B -m unittest discover -s tests -v
```

矩阵使用小固定正文验证调度：3/5 轮实际 mock 请求为 3/5、工具调用为 2/4；candidate_guidance 固定开启时，旧空间 off/on 是 16384/14336，等空间均为 14336。容量饱和与送达逐字节等同性由独立回归验证，不从小正文矩阵推测。工具选择全部由测试作者脚本指定，不是模型自行调查，更不是准确率评测。

## 本轮验证与排错

最终聚焦 **109/109** 通过，含新增 16 项，不相加；五个变更/新增 Python 文件 AST 和行尾空白检查通过。8 臂离线矩阵生成成功，真实模型调用为 0。

首轮新增测试 12 项有 3 个 error：夹具用不存在的查询占位，触发未配置的 BM25 fallback，而非预期纯图查询。改成夹具已有的 `render`，保留初始失败日志，没有为通过测试调整生产检索器或引入远程检索。

全量离线结果见下列附录。没有 .git，不声称已 commit、push 或执行 git diff --check。未运行真实 PostgreSQL、Compose 或模型效果实验。

证据目录：`verification/equal-source-budget-20261110/`：`initial-tests.log`、`focused-tests.log`、`focused-tests-final.log`、`focused-tests-final2.log`、`matrix-output.log`、`matrix.json`、`full-tests.log`、`full-tests-final.log`。历史诊断另见 `CANDIDATE_DRILLDOWN_20261110.md` 和 `../locagent-class-method-paired-runner-20261110/COMPLETED_REPORT_ZH.md`（后者相对项目根目录，保留原文件）。

### 独立复审补充

复审指出六种直接协议模式未覆盖实际图捕获路径上的全部八种布尔组合，已新增实图八组合测试。并补 Unicode/转义和超长 call-id 回归。新 `source_budget.accounted_delivery_bytes` 核算工具消息及反馈、已发送替换提示的各自峰值，并计入实际发送的自然末轮或预算收束 finish 提示，始终受原 24576 字节限额约束；它不是跨轮累计请求流量或 token/费用。旧 `candidate_guidance`/`candidate_drilldown.combined_delivery_bytes` 的自然末轮不计 finish 的历史含义没有改写，新模式应使用新字段。复审者没有独立跑通测试（只读环境缓存限制），上述通过数量来自本轮实现环境日志。

补充的第 16 项验证实际压缩类签名在第二轮到达：同时启用 autonomous_reread 与 candidate_drilldown，3 轮时没有读取机会，5 轮可在第三轮取得正文。最终聚焦 109 项覆盖此测试；最终全量 discovery 启动时尚为 15 项新增，计数须分开看，生产源码在该次全量启动后没有改变。

### 全量完成结果

复审后最终生产源码全量：**Ran 807 tests，121.787 秒，FAILED（failures=1, errors=13, skipped=19）**，日志 `full-tests-final.log`。初轮为804项，122.861秒，同样1 failure、13 errors、19 skipped。两轮失败/错误名称与前次候选下钻最终792项日志逐项一致：11个 error 项缺历史冻结文件（含一个 setUpClass），2个 error 缺 torch，1个 failure 因 macOS 不支持 Linux prctl/PDEATHSIG。没有安装依赖、伪造历史工件、修改旧断言或启动服务以消除此类失败。全量不是全绿。最终全量启动后的唯一测试追加为压缩类签名3/5轮对照，已在最终109项聚焦回归通过，生产源码未再变动。
