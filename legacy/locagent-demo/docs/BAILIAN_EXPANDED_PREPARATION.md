# 扩样离线准备：3 题可核实子集，50 题尚未完成

2026-10-16；基线 `657aca1258547d43abae73aee01812e19f13b711`，preview 分支 `work/rag-offline-preview`。本轮只有公开资料读取与本地静态准备，没有 embedding/LLM 调用、排名计算、数据库启动、安装、commit 或 push。

## 完成与阻塞

目标仍为 50 条新查询、多仓库；本次交付 **3 条单仓库准备子集**，不是 50 条样本，也不能支持独立多仓库结论。Hugging Face SWE-bench Lite 原始数据下载在 WSL 直接连接出现 TLS reset、现有 requests 连接出现 ConnectionError，Windows HTTPS 失败。没有猜测代理或服务器根因，没有修改代理。网页数据预览可读，但不能代替完整、可校验的原始任务文件。

本地有限范围盘点未找到可用 parquet/arrow/SWE-bench 原始任务集；发现旧实验索引和已曝光任务 ID，未重用。原 itsdangerous 源码/10题已曝光，本轮整个仓库排除。GitHub 连接器可读取公开 API，改用小型 Blinker 的 issue/PR 作为可核实准备子集。**GitHub 路径并未被阻断，继续人工审核更多 issue 是可行的；本次停在完整子集交付点，而非宣称所有数据获取都不可能。**

## 来源、查询与标注

统一采用原始标题逐字作为查询；不发送正文、评论、hints、补丁、测试或标签。173 正文含完整建议修复，标题策略避免直接带入该补丁。这相对旧手工行为描述是明确的输入分布变化，信息更少。148/149 来自修复 PR 标题，存在事后措辞偏差，不等价于修复前真实用户问题；149 明示 WeakNamespace，独立标为符号提示层。保留这些来源差异，不把三题称为无泄漏盲测。

| ID / 来源 | 原始查询 | base commit | 静态修复标签 |
| --- | --- | --- | --- |
| [issue173](https://github.com/pallets-eco/blinker/issues/173)，[PR174](https://github.com/pallets-eco/blinker/pull/174) | Exceptions (ignored) in finalizers running during interpreter shutdown | dcce3e97743494433025e0b68f742f3582b6ba6a | base.py；Signal._make_cleanup_receiver.cleanup；另有模块级 import，因此函数主指标 NA |
| [PR148](https://github.com/pallets-eco/blinker/pull/148) | restore identity handling for str and int senders | 3f9f1c9dd560588c118d5b5e23bce2e47f8fbf9d | _utilities.py:make_id；测试修改另列 |
| [PR149](https://github.com/pallets-eco/blinker/pull/149) | fix deprecated WeakNamespace import | 0068cb4ce6a8d63f6628ba0a02450b7bae5110e9 | base.py:__getattr__ |

标签是 **base 源码上的静态 patch-overlap 代理相关性**，不是执行验证的因果真值。删除行和新增行的旧行锚点映射到最深层包含函数，不将整个 hunk 上下文都当金标。不从 hunk 标题猜函数。不运行外部项目、测试、安装脚本或任何仓库代码。173 没有测试重现，不能声称修复已在本机验证。production 补丁产生定位标签；tests/ 补丁仅为修复证据，但测试源码仍保留为候选干扰项。

三题函数目标互不重叠；与旧10题最高 token-Jaccard 为 .043478 / 0 / 0，人工语义核对属于新的信号生命周期、发送者标识与弃用导入问题。词面指标并非语义独立证明。与旧显式任务 ID 无匹配。三题同仓库、候选源码跨 commit 大量重叠，不能当成三个独立仓库样本。每题仅检索自身 base commit，不能合并跨 commit 候选。

## 全候选与协议

三个 commit 均通过 commit→实际 root tree→全部 .py blob 的 SHA1/大小检查；保存 14 个不同 Python blob。最初 connector 内容经文本补丁保存多出一个 LF，严格检查阻止了准备；仅当去除该一个 LF 后完全匹配 Git SHA1/大小才恢复原字节。原 commit别名 tree 响应也保留，不用于最终 root tree 绑定。

每个 commit 全部 **7 个允许的 Python 文件**（含 tests、docs/conf.py）进入原 AST 分块器，不从金标文件筛选。非 Python 和原 allowed() 明确排除的路径均记录。各 commit 块/实体数为 **79/79、85/85、85/85**，源码字节 **35961、38211、38756**。249 个成员按最终完整 path:symbol+代码输入完全相同去重为114文档输入；成员仍按 repo/commit 分隔。

沿用 python-ast-lines-v2、max_chars=12000、只取函数区域（含嵌套与 overload）、path:symbol 换行原代码、1024维、原 query instruct。支持的完整 Python 语料≠所有语言或所有模块级语句都可检索；独立模块/类修改必须标 NA。所有异常/超限阻止完整快照，不静默丢源文件。

三臂固定：BM25 Lucene k1=1.5,b=.75、English stemmer/stopwords、仅正分；dense 精确归一化点积 fsum；RRF k=60、dense权重2/BM25权重1、无 topN 截断。实体分数为最大块分，平分按实体字符串。RRF 权重来自已暴露开发集，必须披露，不继续调参。bm25s 0.2.3，PyStemmer 2.2.0.3。

Hit@K=是否命中任一 gold；Recall@K=命中不同 gold 数/全部不同 gold 数，K=1/3/5，按问题宏平均。无 gold 为 NA，不当作0或1；有有效标签但缺排名为0。函数主分母2、NA1，文件分母3；部分函数映射单独报告，不混入主分母。文件排名按函数最优名次投影并去重；未来文件没有候选函数则须在冻结前列为 file-NA。分层报告仓库、issue/PR来源、单/多gold、显式符号提示，列样本数；不能将多个 gold 当多道题扩分母。当前仅单 gold，未假称已覆盖多gold实证。

## 缓存、批次与预算预检

**旧向量缓存复用0，历史账本不改不重放。** 新一轮内部仅可复用完全相同 endpoint/model/dimension/role/instruct/preprocessing/chunker/input 内容，并且必须先有 settled 账本、原 body 和绑定哈希；manifest 的114去重只是输入计划，不表示向量已存在。query/document 严格分角色。

计划114文档+3查询=117输入，60,825 UTF-8字节；按16一批，8个document请求+1个query请求=9请求。不重试，不将未知状态当作缓存命中。所有请求精确 body 和 SHA256 已保存在 manifest。

沿用历史 **0.125元/百万输入token** 作为未重新核价的计算假设：bytes/4粗估15,206.25 tokens，约 **0.00190078125元**，不是tokenizer计数或上界，也未计准确的模型指令开销。按旧保守规则每输入131072 tokens完整预留，新增 **1.916928元**；旧 **1.277952元已占满**，其中unknown **0.557056元不释放**，条件式累计预留 **3.194880元**。

这些是 **3题子集** 的数字；50题尚无实际完整块数/请求数，预算为 null，不能用3题线性外推或悄悄改成只嵌入目标文件。现有旧执行器针对原数据/预算封闭，新 manifest 不能直接塞入旧授权运行。真实运行前需要核对现行价格、确认子集或完整50题范围，并完成对应新 manifest 的预算/授权执行器接入；不得修改旧 CAP、旧 engine 哈希或释放旧预留来绕过限制。

供父对话后续确认的明确范围（不是当前执行授权）：公开 Blinker 三个固定commit的114个完整代码块输入和3条公开原标题，发送到原阿里云百炼北京 workspace endpoint（manifest沿用原角色参数），模型 qwen3.7-text-embedding-flash、1024维，仅检索对比目的；不发送patch/gold、本机私有项目、密钥或私有配置；9请求、无重试；在费率核对无变化前提下新增最高预留1.916928元。**不建议用此3题授权代替用户期待的50题实验。**

## 冻结、验证与后续

子集 manifest SHA256：`cb77ac3211a17d8605e10b1bb3e612ab864ac0809b1daf3ec4077a35c6113a5a`。位置 `outputs/bailian-expanded-preparation-20261016/frozen-subset/manifest.json`。政策、问题、标签、候选、源证据哈希、脚本哈希和请求计划均在首次排名前冻结；本次没有计算任何排名。包版本与去重/保护核对见同级父目录 audit.json。剩余47题尚未冻结，不得宣称全材料已冻结。

通过：新7项单元测试（多gold、NA、缺结果、重复gold、插入/删除映射、错误hunk、拒绝覆盖）、原RRF7项回归；git diff --check；204个历史输出/原4文件/学习README哈希不变。准备阶段失败检查已修复：commit别名与真实tree绑定不同、保存额外LF。未运行：真实模型、真实项目测试、数据库、50题指标、当前价格核对、真实tokenizer计数。

建议下一阶段先补至 **12题、至少3仓库** 的原始 issue 子集，再扩50；优先真实问题正文但在统一政策下排除solution/hint段，必须保留逐字段变换审计，并与本标题子集分层，不能临时按结果改写。可继续 GitHub issue/合并修复证据采集；SWE-bench数据恢复后可另建完整候选池。对50题候选池先固定数据版本与issue排序/抽样seed，按仓库轮转、每仓最多10题，排除旧目标/近改写/新题重复目标后冻结最终名单；不足50就如实报告，不补写合成问题。先全快照计数和报价，再批准预算，最后跑固定三臂。已选题在看到任何排名后不得替换。

复核命令（preview目录）：
```
/home/lenovo/projects/LocAgent/.venv/bin/python -B -m unittest discover -s tests -p test_expanded_preparation.py
/home/lenovo/projects/LocAgent/.venv/bin/python -B -m unittest discover -s tests -p test_offline_bailian_rrf.py
git diff --check
```
准备脚本 `scripts/prepare_expanded_subset.py` 对现有输出拒绝覆盖。复现须用新的不存在输出路径调用 prepare，并核对原政策/源文件/engine哈希；不改现有 manifest。

静态解析在受限CPU/地址空间的本机Python进程运行，并禁止该脚本socket连接；不称为完整沙箱。没有可公开部署的安全保证。GitHub connector读取路径没有由本代码实施网络pinning，返回源依靠固定commit/root tree/blob校验；未提取可执行仓库、未安装或运行其代码。

执行前封存附录 `outputs/bailian-expanded-preparation-20261016/execution-preparation-seal.json` 绑定原 endpoint、model、角色参数、包版本、subset/audit哈希；SHA256 `baacdb02edf4428672f86a8709439738290b4ae0c92fdb203572f0841c5966e3`。状态明确为未授权，不能运行。
