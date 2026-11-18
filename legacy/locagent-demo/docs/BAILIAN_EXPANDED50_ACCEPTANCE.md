# 50题公开 Python issue 检索实验：离线准备与冻结验收

日期：2026-10-16。状态：**50题准备完成且已冻结；没有调用模型、生成向量或计算任何检索排名。** 此文记录当前扩展检索评估准备阶段，不代表原公开仓库后端流水线所有需求已验收，也不构成付费执行授权。

## 交付与样本范围

工作区 `/home/lenovo/projects/LocAgent-rag-preview`，分支 `work/rag-offline-preview`，HEAD `657aca1258547d43abae73aee01812e19f13b711`。未切换或修改原学习工作区，未 commit、push、启动数据库或部署。

冻结目录：`outputs/bailian-expanded50-20261016/frozen/`。包含 `manifest.json`、`manifest.sha256`、`queries.csv`、`audit.json`、`test-evidence.log`。

Manifest SHA256：`78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`。

来源 build：`build-1792136849959133503.json`，SHA256 `61dfbe0818bdbe2172af1cfc0491be5c022eddb0f67d599381ac82908364d581`。保留前一检查点全部46题，新增4题，没有重新抽样原46题。

| 仓库 | 题数 |
|---|---:|
| mahmoud/boltons | 8 |
| more-itertools/more-itertools | 9 |
| pallets/click | 6 |
| pallets/markupsafe | 5 |
| pypa/packaging | 6 |
| python-attrs/attrs | 6 |
| python-humanize/humanize | 5 |
| theskumar/python-dotenv | 2 |
| tkem/cachetools | 3 |

**函数主指标分母30，另外20题函数 gold 为部分映射或 NA；文件指标分母50。** 新增4题均归入函数部分/NA，不能将50题宣称为完整函数标注基准。23题存在多个已映射函数 gold（包括部分映射题），6题存在多个文件 gold。样本间没有相同或父子嵌套函数目标重叠。

每题来自真实 GitHub issue，与已合并修复 PR 显式关联；issue 创建早于修复合并。请求只使用 issue 标题，不使用修复 PR 标题、正文、补丁或 gold。2题通过 rename 事件恢复到修复 PR 创建时的标题；其他标题来源/历史确定性随题保留。标识符提示只是词法启发式分类。

按仓库字母序轮转、仓库内 PR 编号降序、多 issue 链接按 issue 编号升序，取最先符合条件的50题，每仓库至多10题。最终使用 `ordered-candidate-pool-v2.json`；探索过的 Tenacity/v3 不进入最终样本。新增 attrs 候选及补丁上下文、重复目标、docstring-only 排除规则发生在任何排名或模型请求前，写入 manifest 的 protocol_amendment。候选排除和源数据失败保留审计，已检查前缀没有 pending；未遍历的候选不是失败或排除样本。

## 候选全集、固定版本与标签边界

每题绑定修复前 base commit。对49个不同固定 commit 的真实公开源码归档重新静态解析，逐一核对缓存文档、源文件清单、归档 SHA256；共享同一快照的题复用快照。下载证据为固定 commit 的 HTTPS codeload 归档及内容哈希，未进行独立 Git tree 校验。

候选包含该版本现有 `rag_offline.allowed` 支持范围内全部 Python 文件的函数区域，包括 tests/docs 中允许的 Python 文件，不按 gold 文件筛选。嵌套函数和重载按现有分块器处理；非 UTF-8 或解析不支持导致整个快照排除，不静默删除困难文件。总计47,793个快照块成员；完整输入文本去重后9,814个文档输入，加50个问题输入。没有复用旧付费向量缓存。

Gold 是修复补丁与旧版本函数区域的静态重叠代理。上下文/删除行先与 base 源码逐行核对；新增函数、模块或类级更改无法完整映射时标记函数部分/NA。测试文件不作 production gold，但保留在候选中。仅注释/docstring 改动经 AST 比较排除；修复后 AST 解析失败时保守保留，不能宣称已验证语义改变。此类标签不等于执行验证或因果真值。公开历史 issue 也不构成未曝光、无预训练污染的盲测证据。

固定实验臂为 BM25、dense、RRF60（dense:BM25=2:1），不再根据本轮结果调参。BM25 k1=1.5、b=.75、English stem；实体取最大块分数、确定性词法平分；K=1/3/5，分别报告多 gold macro Hit 与 Recall。缺失结果对合格题计0；函数 NA 不混入函数主分母，文件指标独立。按仓库、gold 数、词法标识符提示及标题历史确定性分层报告。文件分数通过所属函数结果投影，并非另建文件级编码器。

## 输入安全边界

仅下载固定公开 GitHub 源码归档，不解压到文件系统，不执行仓库安装脚本、测试或代码。归档限制压缩8MiB、展开32MiB、3000成员、单文件1MiB、路径512字符/30层；拒绝符号链接、危险路径、子模块与 LFS。固定 commit 根目录校验；函数块 max_chars=12000，最大20000块，最终文档输入最大16000 UTF-8字节，不静默截断。

静态准备进程使用 CPU 300秒和地址空间3GiB限制，下载有大小和超时约束。这些不是完整沙箱或完整容器资源隔离；下载超时也不能等同于所有外部操作总墙钟硬上限。未证明可安全公开部署。本阶段不验收原后端的任务领取、取消/重启恢复或生产并发隔离。

## 验证结果

| 检查 | 结果 |
|---|---|
| 新50题准备单元测试 | 12通过 |
| 前一扩展准备回归 | 7通过 |
| 原离线 RRF 回归 | 7通过 |
| 合计 | 26通过，0失败、0错误；测试期间禁用 socket 连接 |
| 固定源码归档独立重建 | 49通过 |
| 原有保护文件 | 258份哈希未变 |
| 来源 JSON 证据 | 646份已哈希绑定 |
| 源码仓库测试/安装脚本 | 未运行，按约束禁止执行 |
| embedding、检索排名、真实模型 E2E | 未运行、未授权 |

测试涵盖路径穿越、错误 commit 根目录、符号链接、LFS、完整候选保留、补丁上下文不匹配/不完整 hunk、嵌套目标重复、标题历史、测试 gold 排除、docstring-only 变化与静态补丁应用。测试日志在冻结目录中，其哈希已绑定 manifest。部分旧 Python 源码有 SyntaxWarning，静态解析完成；未执行这些源码。

已执行的测试命令等价于：

```sh
cd /home/lenovo/projects/LocAgent-rag-preview
/home/lenovo/projects/LocAgent/.venv/bin/python -B /mnt/c/Users/Lenovo/Documents/Codex/2026-10-13/task/verify_expanded50_tests.py
/home/lenovo/projects/LocAgent/.venv/bin/python -B scripts/freeze_expanded50.py outputs/bailian-expanded50-20261016/build-1792136849959133503.json
```

两个脚本会拒绝覆盖已有验收日志或冻结目录；上述为已执行记录，不应删除旧证据后原地重跑。复验应采用新输出目录并保留既有冻结物。

## 费用：估计与原规则硬预留分别列示

已核实官方北京地域同步输入价为 **0.125元/百万输入 token**，模型 `qwen3.7-text-embedding-flash`，1024维。来源：[官方模型说明](https://help.aliyun.com/en/model-studio/qwen3-7-text-embedding-flash)、[同步 API 与 token 计费说明](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)。本轮仅读取文档，没有调用计费/tokenizer服务。

| 项目 | 数值 |
|---|---:|
| 唯一文档 + 查询输入 | 9814 + 50 = 9864 |
| 计划请求（每批16） | 614文档 + 4查询 = 618 |
| 实际输入文本 UTF-8 字节 | 6,192,522 |
| bytes/4 经验 token 估计 | 1,548,130.5 |
| 经验费用估计 | 0.1935163125元 |
| 原规则每输入预留 token | 131,072 |
| 新增原规则预留 | **161.611776元** |
| 旧预留继续全部占用 | 1.277952元 |
| 若批准后合计占用 | **162.889728元** |
| 旧 unknown（包含在旧预留内） | 0.557056元，保留占用 |

经验估计和预留差异来自按所有9864个输入均占满上下文的旧规则，而非发现实际需要161元。bytes/4 不是上界，且不包含未知服务附加 token 开销。精确文档字节6,189,608、查询字节2,914；单文档最大12,025字节，query instruct为96字节。UTF-8字节数本身可验证，但已查文档未确立托管服务使用的精确 tokenizer/version、规范化处理、字节回退性质及 instruct/包装计费上界，**目前不能把字节数换算为已证明的更紧硬预算**。

若后续采用更紧规则，需先证明 provider 一致的 tokenizer 或保守 token 上界、确认 instruct/服务附加开销和计费范围、做离线 Unicode/角色边界验证，再单独审查并授权新预算策略。本轮不实现或改动预算执行逻辑，不重放旧账本、不退款/清空 unknown、不重置旧预算。

## 后续可确认方案与剩余阻塞

准备已完成。若继续付费实验，需先审查适配新 manifest 的执行器：原 runner 的42输入/10题及旧 cap 不能直接绕过。新执行器应校验 manifest、engine、批次完整输入哈希与账本，明确失败/unknown 停止规则和禁止自动重试；这是后续开发，不是本次已完成能力。

提交父对话确认的具体范围：向北京百炼 endpoint `https://ws-8t0i3jte6m9op4ad.cn-beijing.maas.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding`，使用上述模型及1024维，发送本冻结清单的公开 `path:symbol + 函数源码`（含允许的测试/docs函数）和50个原 issue 标题；query instruct 为 `Given a code localization question, retrieve Python code that implements the described behavior.`。不发送 issue 正文、评论、补丁、gold、私有文件或凭据。最多计划618次无自动重试请求，执行固定三臂评估。

预算选择需要明确：继续原规则则新增占用161.611776元、总占用162.889728元；若此预留不可接受，先授权验证/设计更紧预算策略，暂不执行。**约0.194元估计不能替代硬预算授权。** 本轮没有获得新的外部发送或付费执行授权，也未进行上述请求。

## 审查文件与提交拆分建议

本50题阶段文件：`docs/BAILIAN_EXPANDED50_POLICY.json`、本文、`scripts/prepare_expanded50.py`、`scripts/freeze_expanded50.py`、`tests/test_expanded50.py`。代码依赖已有 `prepare_expanded_subset.py` 和离线检索模块；导出 diff 只包含本阶段五文件，不能当作脱离前序准备文件的独立完整安装包。

建议后续分为准备/策略与测试、冻结/验收两次提交；本轮未提交。前序离线 RRF 和三题准备文件保留，旧演示、付费原始账本及证据未改。最终 diff、CSV、manifest、audit 与本文另导出到 Windows 任务目录，供父对话审查。
