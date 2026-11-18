# batch134 与 OpenHands LocAgent 引擎差异核验

日期：2026-11-14。结论：**可以保留并复用已验证的固定源码和来源证据，但不能直接把 batch134 的 130 题技术就绪状态、旧索引或检索结果当作当前 OpenHands 的就绪证明。** 当前接口不加载持久化索引；正式迁移需要新适配清单及覆盖检查。此次没有修改运行引擎、配置、历史结果或授权。

## 冻结版本与差异计数

两套引擎逐文件复算均与冻结记录一致，0 个漂移文件。聚合算法为文件相对路径→SHA256 映射的 UTF-8 canonical JSON（sort_keys、无多余空格、ensure_ascii=False）再 SHA256。

| 项目 | 文件数 | 聚合 SHA256 |
|---|---:|---|
| batch134 题集准备引擎 | 159 | `2222b6bac8ac393a7aeb29e571edefe351146320e62384627cecdaeba9a3f196` |
| 当前 OpenHands 所接 LocAgent 引擎 | 146 | `975172d7d0a1590be5033779d1349462fa5cba497b3b0554fce815a1f5a0d944` |

batch 根目录：`/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113/runtime-engine`。当前根目录：`/Users/xiaomu/Documents/Codex/locagent-demo-20261108`。依据分别为 batch134 的 `ENGINE_LOCK.json` 和工作区 `sqlglot_read_validation/v1/manifest.json` 内冻结的 `locagent_engine`。

**纠正先前“13 个共有文件差异”的说法：共有 145 个文件，其中 12 个内容不同、133 个相同；当前独有 1 个文件，batch134 独有 14 个文件。** 从当前 146 文件清单逐项比较，会得到 13 项“不同或缺失”，其中 `requirements-demo-test.txt` 在 batch134 实际不存在，并非共有文件。

## 原先 13 项逐项分类

方向均为当前引擎 → batch134。下表的调用路径判断来自静态检查；具体实测另列。

| 文件 | 改动与影响 | 当前 OpenHands 路径 |
|---|---|---|
| `dependency_graph/build_graph.py` | v2.3→v2.5；纳入同步 `__init__` 及其后代；保留构造调用指向类，避免新节点进入后缀模糊调用解析；目录排除改为完整 `.git` 路径组件，纳入 `.github`，剪枝目录软链接。改变实体集合、边和潜在 BM25 排名。 | 直接使用，主要差异。 |
| `dependency_graph/traverse_graph.py` | 明确 `source_available` / `location_available`，不为缺正文或不一致跨度虚构行号。字段在查询时生成，不是新增 pickle 必填字段。 | 直接使用；有效旧图可被新格式化器读取，异常证据表现有差异。 |
| `plugins/location_tools/repo_ops/repo_ops.py` | 消费上述可用性字段；缺源码/跨度时返回说明，防止空行号运算、排序或伪正文。 | 直接使用；须与 traverse/result_format 配套，不能任意混搭单文件。 |
| `plugins/location_tools/utils/result_format.py` | 明示缺正文/行号，不把完整图查找等同成功读源码；正文长度取实际代码。 | 直接使用；正常样例的输出一致不代表异常输入也一致。 |
| `plugins/location_tools/retriever/bm25_retriever.py` | 正文索引元数据路径由字符串 replace 改为受限相对路径函数。实体 ID BM25 算法本身未变。 | 模块被导入；当前使用的是 `build_module_retriever_from_graph`，不调用这次改动的正文索引构建函数。 |
| `repo_index/index/code_index.py` | 同样修正入库路径、拒绝越界和源文件软链接。 | 当前实体 ID 检索不走该索引构建流程。 |
| `repo_index/codeblocks/codeblocks.py` | pre_code 校验兼容 CRLF，并使用 fullmatch。影响旧正文切块建索引。 | 当前图/实体检索不走该切块流程；不能据此认为当前 Snapshot 的 CRLF 问题已解决。 |
| `locagent_service/local.py` | 授权落盘目录绑定、失败边界、部分结果保全。 | 当前 OpenHands 的传输/账本另有实现，不调用该旧启动入口。 |
| `util/candidate_drilldown.py` | 区分没有源码与重复读取提示。 | 当前接口不使用旧候选钻取循环。 |
| `util/localization_contract.py` | 增加错误恢复、summary-first v1/v2、保留正文预算、可选跟进配置及 FAILED 状态。 | 可被导入，但当前未启用这些旧循环选项。 |
| `util/localization_protocol.py` | 旧循环增加摘要/正文预算分配、参数反馈、有限终答反馈和失败轨迹保全；仍受原请求上限。 | 当前 OpenHands 循环不调用 `run_bounded_search`；不能把旧修复误认为当前已接入功能。 |
| `util/localizer.py` | 连接上述旧协议/失败保全选项。 | 当前仅借用 `_ENGINE_LOCK`、`_graph_session`；本次这些被借用函数本身未变。 |
| `requirements-demo-test.txt`（当前独有） | 只是引用 runtime/service requirements 的测试依赖入口；batch134 不含该文件。 | 不是索引 schema 变化，不影响此次已安装环境中的检索调用。 |

14 个 batch134 独有文件也已记录：准备/快照/固定提交/精确 blob/恢复/隔离索引 8 个服务模块（`benchmark_prepare`、`benchmark_snapshot`、`blob_http`、`exact_blobs`、`isolated_index`、`pinned`、`recover_snapshot`、`verified_recovery`）；`repo_index/source_path.py`；旧循环辅助 `failure_persistence`、`finish_feedback`、`summary_delivery`、`summary_delivery_v2`、`tool_error_recovery` 5 个模块。完整逐文件哈希和 unified diff 在 [核验目录](verification/engine-compatibility-v1/)。

## 接口与旧索引的真实关系

当前 `readonly_agent/bridge.py` 每次把不可变源码快照交给新子进程；`locagent_worker.py` 调用 `build_graph(global_import=True)`；`readonly_agent/locagent.py` 逐个校验已有实体的路径、AST 名称、行号和正文，再构建**实体 ID BM25**。不加载 `graph.pkl`，不使用正文 corpus BM25，不做嵌入或图扩展。

旧 bundle 含 NetworkX MultiDiGraph pickle，以及正文 BM25 的 JSON/JSONL、CSC 数值 NPY 文件。检索算法和数据源必须区分：旧 corpus 是正文切块；当前模块索引只搜索实体 ID。二者不是可直接互换的同一个检索配置。

对两个已曝光 bundle，先复核 manifest 地址哈希、全部 640 个 bundle 文件哈希，再在隔离临时进程内用仅允许两个 NetworkX 类型的受限读取器检查图；拒绝 REDUCE、外部引用及其他类型。NPY 加载使用库默认 `allow_pickle=False`。这只是受控离线兼容性检查，没有修改正常运行门禁。

**正常 `load_manifest` 门禁的实测：** 两个旧 manifest 在 batch134 下通过；在当前引擎下都以 `Engine changed; prepare a new manifest/experiment` 拒绝。这是正确的版本绑定行为，不能通过改旧哈希或去掉校验来迁移。

## 小范围实测

全部使用同一已安装 Python 3.12.16 环境和相同源码；两套引擎各在独立、清空环境变量的临时进程内执行。仅 AST/本地索引操作，不导入或执行目标仓库。NetworkX 3.4.2、bm25s 0.2.3、llama-index-core 0.11.22、llama-index-retrievers-bm25 0.4.0、tree-sitter 0.21.3 与旧记录对应包版本一致；旧构建记录的 Python 为 3.10.22/Linux，操作系统和解释器没有完全复现。

| 已曝光题 | 固定提交 | 同一非隐藏 Python 投影 | 当前新建节点 | batch134 新建节点 | 新增实体 |
|---|---|---|---:|---:|---:|
| SQLGlot 3417 | `e1b6483d5e26d556f6a3dd82c6d35f475c189c2b` | 147 文件 / 2,791,727 字节 | 4,341 | 4,389 | 48 个构造函数相关实体 |
| Loguru 1239 | `65fe4a8db9a8f297ae3648f51b5e3050b30945a9` | 163 文件 / 550,940 字节 | 1,648 | 1,686 | 38 个构造函数相关实体 |

SQLGlot 精确提交与所有源码 SHA256 以 `preflight.json.cases[].commit/source_hashes` 为审计依据。两个投影均逐文件等于此前 OpenHands v5 冻结投影。两版本新建图的共有节点属性全部相同；新增节点均为同步构造函数或其作用域后代，没有删除旧节点。

每题分别测试“当前引擎新建图、当前引擎读取归档图、batch134 新建图、batch134 读取归档图”。4 种组合的以下 5 个既有查询返回文本逐字一致，共 20 次本地实体检索：

| 查询 | 结果 | 原始 UTF-8 字节 |
|---|---|---:|
| SQLGlot `_parse_id_var` | Parser、TSQL.Parser、Snowflake.Parser 三处实现，顺序一致 | 2,817 |
| SQLGlot `_parse_set_item_assignment` | Parser 对应函数 | 1,178 |
| SQLGlot `SET TAG` | Tag、Set、Expression.set | 2,265 |
| Loguru `traceback` | No locations found | 19 |
| Loguru `loguru/_better_exceptions.py` | 整文件 | 24,272 |

这些是原始返回字节，**不等于模型实际收到的证据量**；24,272 字节整文件超过当前单页及总工具预算，后续必须按真实分页/预算处理。本轮未运行模型，没有终答或性能收益测量。查询使用先前已曝光题和已有轨迹线索，未用新标签生成查询。

两个归档正文 BM25 索引（SQLGlot 1,073 块、Loguru 105 块）均能被当前库加载并查询；两引擎加载同一索引得到的本轮结果一致。所有块的路径都指向投影内文件，基本跨度类型/正序检查通过。这验证局部格式兼容，**没有证明每个 corpus 块正文/跨度完全正确，也没有将该 corpus 接入 OpenHands。**

在上述查询执行完成后，单独核对两个早已曝光的参考实体：`Parser._parse_set_item_assignment` 和 `ExceptionFormatter._format_list` 在两图中都存在，名称、行号及正文 SHA256 一致。参考补丁中的改动函数不是唯一根因答案；未打开其他题目的评分标签。

## 不能忽略的差异与边界

1. **构造函数与目录覆盖会改变结果。** 人工 3 文件样例中，当前图 4 个节点，batch134 图 12 个节点；查询 `__init__`、`visible_task` 在当前引擎无结果，在 batch134 返回对应正文。`pkg.github` 是普通目录，也会被旧 substring 排除逻辑误删。当前图校验只要求图文件集合是源码集合的子集，因此可以接受这种不完整图；“验证通过”不保证实体覆盖完整。
2. **隐藏源码的接口边界不同。** 对 130 题仅检查 manifest 元数据和文件 stat，发现 7 题有 14 个隐藏路径 Python 文件。当前 Snapshot 对这些路径返回 `hidden_source_path`；即使换成 batch134 图构建器，外层接口仍拒绝。必须明确统一两组可见源码范围，不能静默删除后还沿用原“覆盖通过”结论。130 题可见 Python 的数量/总大小/单文件大小均未超过当前静态限额；这不代表每题解析、编码或语义已通过。
3. **CRLF 是共同阻碍。** 两引擎对人工 CRLF 源码构图都会将换行归一化；当前 Snapshot 保留原字节，随后实体适配返回 `graph_source_content_mismatch`。旧切块器的 CRLF 修复不能替代这个检查。本次只报告，没有更改源码或放宽校验。
4. **归档图不等于在本机直接重建。** 旧 prepare 将根节点 `/` 改为 `.`；当前 worker 直接 build_graph，未走这一步。SQLGlot 归档与 batch134 本机重建的非根节点属性相同。Loguru 还多出两个测试函数 `a`/`b`，来自 `except*` 文件：旧 Python 3.10 无法解析，3.12 可以。3.12 的 feature_version 语法探针支持这一解释，但不是实际复跑旧 3.10 容器。两图的边也不能宣称逐字相同；当前检索未用这些边展开。
5. **路径修复可复现，但有范围限制。** 对相对根 `relative-repo` 和文件 `relative-repo/relative-repo_utils.py`，逐字复现旧 metadata 表达式得到错误 `_utils.py`；batch134 的真实 `source_relative_path` 返回 `relative-repo_utils.py` 并拒绝 `..`。这不是完整正文索引重建测试，且本轮两个现存 corpus 未出现该错误路径。
6. **评分规范须另行冻结。** 当前 strict 指标按 `path:QualifiedName` 精确比较，另列的 upstream-reference 指标会将 gold 的 `.__init__` 归一到类。增加构造函数节点后不能混用这两种口径或将类命中当作 strict 函数命中。现有 label_mapping 文件两版本相同，但图覆盖变化仍需逐题映射核验。

## 建议的迁移方式

保留 batch134 固定源码、提交/树/blob 来源及旧产物；新建 OpenHands 适配清单，显式记录父 manifest、源码投影、引擎/解释器/依赖、索引配置和评分版本。已有结果保持原版本归属。

优先在开发资料上解决当前图构建的构造函数/目录覆盖，以及 Snapshot 的隐藏路径与换行保真问题；保留严格字节/AST 校验，不用关闭校验来“兼容”。是否移植 batch134 的图与格式化修复，应作为独立代码变更审查，而不是直接替换 159 文件整套旧循环。

然后给每题做不含答案的技术门禁：源码范围一致、每个应纳入文件/实体的覆盖情况、span/body 保真、限额和失败状态。评分侧再独立检查标签映射，不能依据未曝光标签调检索。若以后增加图缓存，先建立只读、哈希绑定且可校验的安全格式，避免在新生产路径添加任意 pickle 加载。

此次资源检查足以支持这两题的小范围重建：约 24 GiB 物理内存、约 649 GiB 可用磁盘；单工作进程、CPU 90 秒/墙钟 120 秒、256 MiB 文件输出上限。未检查旧容器运行条件，未重建全部 130 题，不能据此估计全批耗时。下一步不需要模型调用，先准备新适配版本及技术验收。

## 证据、复现与保存

- [完整证据目录](verification/engine-compatibility-v1/)：版本/源码/资源 `preflight.json`，每个 worker 的 JSON、stderr、执行状态；旧索引门禁 `manifest-gate-probe.json`；130 题元数据 `manifest-metadata-audit.json`；已曝光参考实体 `exposed-label-mapping-check.json`。
- [主探针](diagnostics/compare_engine_compatibility.py)、[隔离 worker](diagnostics/engine_compatibility_worker.py)、[正常 manifest 门禁探针](diagnostics/probe_manifest_compatibility.py)。主探针可用 `python3 -B diagnostics/compare_engine_compatibility.py --output /tmp/engine-compat-new-run` 重复；输出目录必须尚不存在。它只处理固定两题和人工样例，不能指定任意 pickle。
- 早期语法探针使用系统 Python 3.9.6，不能判断 3.11 新语法支持；原记录保留，后续 `python312-syntax-probe.json` 明确纠正，不覆盖前次记录。
- 主检查核对 1,728 个既有文件哈希未变；最终保存检查另见 `acceptance.json`。只新增本调查脚本/报告/证据，并向既有开发日志追加说明。
- 真实模型请求 **0**；未读取凭据或 `.env`，未安装依赖、未执行目标仓库代码、未向外部发送数据。Python socket/model 防护及清空进程环境用于防御，不冒称操作系统级沙箱。
