# Loc-Bench 对接验证（2026-11-10 UTC）

## 结论

**可以接入现有输入、图/BM25和离线评分流程；还不能直接把560题当作已审查的新测试集，更不能声称定位效果提升。** 最小适配独立于现有生产源码、数据、账本和服务；没有调用模型、没有读取key、没有运行下载仓库的代码。

## 固定版本与实际数据

- 数据：`czlll/Loc-Bench_V1`，revision `c44cf3b74e07ca642cec841b471a9939907c12a7`，default/test，实际读取560行、560唯一ID、165仓库。
- 官方代码：`gersteinlab/LocAgent`，commit `4935b557326c154bad8e8dcf3747cc8d32d1f387`；保存官方 `evaluation/eval_metric.py`、README、LICENSE，下载内容 SHA256 见 provenance.json。
- 类别：Bug Report 242，Feature Request 150，Performance Issue 139，Security Vulnerability 29。
- 14列实际类型见 summary.json；repo、instance_id、base_commit、patch、test_patch、problem_statement、hints_text、category为字符串；edit_functions、added_functions为列表；labels可为列表或null；created_at、edit_functions_length、__index_level_0__为整数。
- 数据卡和该数据仓库文件未声明数据集许可证。官方代码LICENSE是Apache-2.0，**不能据此推断数据、issue文本或各仓库源码都获得同一许可**。后续对外分发前需核对相应许可/使用条款。

## 最小适配与信息隔离

adapter.py为每题创建 inputs/<instance_id>/task.json，严格白名单仅为 instance_id、repo、base_commit、problem_statement，全部560题通过现有 LocalizationRequest.as_task()。patch、test_patch、hints_text、edit_functions、added_functions、类别和审查信息不进入运行输入。官方原始数据、标签、审查队列均置于scoring-only；索引只读取samples/*/repo中的预修复Python源码。

这种分离用于避免流程误送标签，不是对同一操作系统账号的访问权限隔离。后续runner只能加载明确的task.json和repo索引，不应扫描整个适配根目录，也不能把scoring-only交给模型。原始problem_statement自身可能包含定位线索，未篡改它，需在筛题时单列审查，而非声称其绝无答案线索。

adapter.py及下载/建图脚本的创建操作有意拒绝覆盖已有文件/目录。重复运行请使用独立新目录，或直接读取本次已完成工件，不要删除旧实验。score_adapter.py的合成检查仅更新本适配目录的检查报告。

## 函数标签与指标，必须分开

1. 官方函数真值来自edit_functions，不是added_functions，也不是从所有patch文件直接推导。
2. 官方把 `path.py:Class.__init__` 归并成 `path.py:Class`。560题中有64题包含构造器标签；现有图构建器同步跳过直接同步构造器节点，将类作为定位对象。这和现有严格AST函数评分器的“类不算函数命中”不是同一任务。
3. 官方 `cal_metrics_w_dataset` 的 found_entities 分支只标准化gold，不归并预测构造器，也不去掉重复预测；docs分支还有不同的路径转换。重复预测可令Recall大于1，不能用严格评分结果冒充官方指标。
4. 官方Acc@k比较命中槽数与min(k, max_k截断后的真值数)，并非通常的任意命中Hit@k；MAP除以k；Recall真值数还受max_k截断。保留这些差异，不能悄悄“修正”后称论文口径。
5. score_adapter.py提供不依赖torch的小型公式参考，并实际调用未修改的既有 `locagent-expanded-eval-prep-20261107/scoring/scorer.py` 验证严格AST通路。**本机未执行官方torch评分器，参考公式不是独立数值一致性认证。** 本轮测试发现并明确保留了constructor/重复预测口径差异。
6. 建议后续同时报告“官方兼容指标”和“严格函数子集指标”，分母各自冻结。包含构造器的64题先单列；其余496题仍须做真实源代码/图解析、模糊定义和标签质量审查，不能直接宣称全部可用。

## 真实仓库抽样

便利样本，预选三个较小仓库后各取字典序首题，不代表随机抽样或整体准确率：

- Delgan__loguru-1239：163/163个Python文件成图，1648节点、5381边，目标ExceptionFormatter._format_list可达。
- networkx__networkx-7721：662/662个Python文件成图，8253节点、50611边，目标traveling_salesman_problem可达。
- py-pdf__pypdf-2644：80/81个Python文件成图，1527节点、8060边，目标decompress可达。唯一遗漏`.github/scripts/check_pr_title.py`由现有SKIP_DIRS规则跳过，不涉及该题目标。

三题均实际完成现有 build_indexes 的图与BM25构建；3/3目标标签存在，3题严格AST标签可解析。906个下载Python文件中905个成图。保留所有源码哈希、归档哈希和base_commit。来源为固定commit codeload归档，**未额外进行独立Git树逐blob验证**。这不是模型命中率。

## 历史去重

初步history-dedup.json仅覆盖顶层inputs任务及既有标签（44文件、22ID），作为中间证据保留，**最终范围以audit-prior.json为准**。

扩大审计：实际prepared task 51文件/26题；candidate task 12文件/12题，两者合并34题；本地live结果30文件/15题；离线或未证实运行结果202文件/18个ID；上游附带预测9文件/300题。各层与本次560题的ID重叠均为0。复制工件不重复计题，上游附带预测不冒充用户运行。

旧historical-exclusions.json的82项保守排除与本次只有1题重叠：Chainlit__chainlit-1441，来源为代码/名单提及而非实际运行证据。它需要单列“已提及”审查。不能把旧文件中的“79 benchmark overlap”套用到本次Loc-Bench。尚未逐题完成语义机制、目标重叠和问题内容独立性人工审查，不能声称全部是全新题。

## 实际验证与边界

- check_offline.py：5项通过，含560题真实契约、输入白名单、污染字段丢弃、构造器转换、3仓源码哈希。
- score_adapter.py：7项通过，含官方公式边界和未修改严格评分器的3题合成gold答案通路。
- 三仓现有图+BM25离线构建成功，现有offline_engine守卫成功退出而未抛错；它未导出计数，不是操作系统级网络审计。
- 未运行模型、未运行官方torch指标、未跑全项目回归、未跑全部560仓库快照。生产源码没有修改，因此不以本轮12项检查替代历史全项目验收。
- 首次下载误用官方main分支返回422，改读API确认的默认分支后成功；首次去重遇历史标签元数据字符串，增加类型分支后重跑成功，没有更改旧数据。保留事实，不把失败的首次运行算成功。

## 交给后续小Co的可执行步骤

1. 读取本报告、provenance.json、audit-prior.json和scoring-only/review-queue.json；队列只是560候选，不是已冻结实验集。
2. 先以Bug Report为主，按仓库分层取少量候选；构造器64题、已提及Chainlit-1441单列。不要只挑现成易命中标签。
3. 每题核对原始问题是否足以独立提出、是否含明显修复/定位提示；核对base_commit、官方edit_functions与实际AST/图、新增函数和跨文件变更，记录无法映射/歧义，不静默丢弃。
4. 按audit-prior证据做实例、问题文本、目标符号与缺陷机制去重，区分“跑过”“准备过”“仅提及”；冻结候选及排除理由、源码版本、排序、评分口径和分母。
5. 在最终候选上重做离线索引/评分契约检查。保持双方同一题、源码空间、调查轮数和候选预算；控制变量不与更换数据集混为一谈。
6. 给用户呈现建议题数、预计调用量与预算并获取新真实调用授权；本次验证不授权任何真实模型批跑。

复现入口：在本目录使用 ../locagent-demo-20261108/.venv/bin/python -B score_adapter.py 可重跑7项评分检查；其余已完成的不可覆盖工件与日志直接查阅。首次完整复现需在新独立目录复制脚本与固定原始数据，依次adapter.py、fetch_samples.py、check_offline.py、score_adapter.py。下载脚本需要公共网络，其余检查离线。脚本保留当前Mac绝对项目根路径依赖，不声称是跨机器安装包。

只读复审：未发现适配阻断；修正了原graph-check中硬编码network_attempts_observed=0的过强字段，改为守卫成功退出布尔说明；评分参考函数增加1 <= k <= max_k校验并重跑7项。历史审计未读取私人web-runs/隐藏目录/凭据，8个空或不可解析结果文件已列明，因此不宣称覆盖所有历史。
