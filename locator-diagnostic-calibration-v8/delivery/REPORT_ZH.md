# C 组定位诊断校准 v8：离线实现与验收报告

日期：2026-11-17（北京时间）。本轮完成实现、零 API 验收、五题静态审计及独立冻结。真实 dev24 × C × 1 次：**未运行**。不开机、不 SSH、不查询云账户、不调用付费 API、不重跑 A/B、不读取 holdout 50 的题面、补丁或结果。报告后停止。

## 1. 改动清单（diff 摘要）

所有新增内容位于 `locator-diagnostic-calibration-v8/`。无 Git 仓库，因此提供逐文件 SHA256 比对及可读差异，不伪造 git diff。

| 范围 | 实际改动 |
|---|---|
| C 定位器 `calibration/locator.py` | 从冻结 SDK 执行方式提取独立定位入口；保留模型、SDK、工具、请求/字节/token/时间预算；附加证据覆盖提示、正文阅读优先级与终答校验。 |
| 定位策略 `calibration/policy.py` | 记录实际返回字符及行覆盖；不把请求范围、预览声明或搜索命中计作完整函数体。合并已收到的续页字符；按 AST 范围检查函数、装饰器、docstring 以及同名重复定义。AST 只检查范围，不向模型提供未返回源码。 |
| 终答 | `answer` 三段为“已读到的事实（附文件:行号）”“推断”“未核验点”。推断限定为待验证假设；缺失函数体/分页必须标注未读完；必须给一条未执行的最小验证命令或断言。 |
| 预算内控制 | 第 2 次请求起，如存在未读完的已返回实体候选或未续读分页，新的 list/search/retrieve 返回正文优先提示，原调用次数和字节仍计费到原预算；read_file 可继续。第 4 次仍只可 finish，不重试、不增加请求。 |
| 不合规终答 | 仅替换 answer 为保守三段内容，files/entities 原顺序原样保留。原回答及违规原因保存于 `diagnostic-audit.json`；不把被拒绝强断言送入 Coding Agent 定位包。 |
| 定位包 | 外层仍是 `version / instance_id / base_commit / result`，result 仍是 `files / entities / answer`；保持 14,336 字节上限。 |
| B 与其他组件 | 42 个冻结依赖字节完全一致，原 B 入口未改。未修改 Coding Agent 提示、40 次预算、stuck_detection=False、harness、容器配置或检索算法；未加入编码循环防护。 |

新目录内 `baseline/` 只是精确提取的冻结依赖。没有覆盖项目已有 `runtime/experiments/sdk_hybrid_v8`、`tests/test_hybrid_v8.py` 或 `freezes/encoding-dev37-v8.1`，C 入口不导入混合检索。模型仍为 **deepseek-flash**，检索仍为 v6 标识符/BM25 源码预览与 v7 候选格式/自检规则。

定位预算仍是最多 4 次请求、每次 2,048 输出 token、累计 128,000 输入/8,192 输出 token、14,336 源码字节、16 工具调用、65,536 请求字节、300 秒。提前结束允许；五道审计题历史均为 4 次，但整个 B 实际定位请求总数为 93，而不是假定的 96。

证据：[逐文件 B/C 比对](B-C-COMPARISON.json)、[定位器提取差异](B-agent-to-C-locator.diff)。后者比较冻结共享 agent 与新定位入口，只用于审阅提取内容，并不表示替换了原 agent 文件。

实际资源状态按 v5 保留：Coding 容器 6 CPU / 6 GiB / network none；harness 实际 Memory=0、NanoCpus=0、network bridge，历史资源包装未生效。本轮没有顺手修复。源证据为 v5 交付 `runtime-resource-observations.jsonl`，未连接云端复查。

## 2. 离线验收结果

先核对 v5 `preflight.json` 的 22 项声明，再定位其冻结归档内五个测试文件：`test_preparation.py`、`test_resume_and_boundaries.py`、`test_completion_and_edits.py`、`test_checkpoint_gates.py`、`test_smoke_subset.py`。这五个文件与 CHECKPOINT_FREEZE 以及现存冻结运行目录逐字节一致。没有使用项目根目录另一套 48 项测试替代。

| 验收 | 结果 |
|---|---|
| 原有 e2e 离线测试 | **22/22 通过**，失败 0、错误 0、跳过 0；原测试文件无修改。 |
| 新校准测试 | **22/22 通过**，失败 0、错误 0、跳过 0。 |
| 请求/网络 | 新 API 请求 0；测试期间网络/DNS/子进程拦截触发 0。测试全为合成 SDK 响应、只读解析及本地 fixture。 |
| 分页 | 实际 LineReader 的长行、Unicode 跨页续读；请求终点不算已读；指定范围结束也不等于函数结束；遗漏行/列不可拼为完整范围。 |
| 函数覆盖 | 未读装饰器、docstring、搜索命中、截断预览、重复定义，以及正文外提到的未读 helper 均覆盖。 |
| 诊断 | 三段缺失/乱序/重复、缺少最小验证、未标假设、未标未读完、错误文件/行号/范围缺口会被拒绝。完整单函数不授予关键链已核验状态。 |
| 真 SDK 协议 | B/C 定位工具 schema 在各请求逐项相同，第 4 次仅 finish；预算完全一致；原 B 仍原样返回旧终答；C 保留原回答审计并给校准结果。 |
| Coding 契约 | 使用完整 version=1 定位包，去除唯一变量 localization_packet 后，两次首请求完全相同；编码提示哈希、工具 schema 哈希及预算相同。 |
| 旧回答静态回放 | 五题共 50 句；10 个输入文件哈希对上既有 SHA256SUMS。Astropy/Sympy 的强断言独立触发 R3，不只是因为旧回答没有三段标题。 |
| 冻结 | 51 个新版本配置/代码/测试依赖文件可复核；42 个原 B 文件及 4 份历史冻结记录保持原哈希。 |
| dev24 C / A/B 重跑 / holdout | **未运行 / 未运行 / 未读取**。 |

原有虚构 holdout 路径负面测试只确认拒绝访问，没有读取任何真实 holdout 文件。受控测试入口和命令见 [README](../README_ZH.md)。原测试出处见 [provenance](baseline-provenance.json)，测试结果见 [原 22 项](baseline-tests.json)、[新 22 项](new-tests.json)，协议证据见 [locator](locator-contract-evidence.json) 与 [coding](coding-contract-evidence.json)。

机械校验能证明已收到的行和函数范围，不能证明自然语言推理正确或调用链已经穷尽。因此本版始终不给“已确认根因”权限；自然语言词法拦截也不是完备语义证明。实际效果、误拦率、真实回退率与 resolve rate **未运行、未测量**。违规整段回退可能损失有用推断；合规的具体假设能保留，已有合成测试覆盖。默认回退中的 `python -m pytest -q` 只是一般回归入口，并不宣称能单独证实特定根因。

## 3. 五题旧终答违规检查表

规则：R1 函数体及关键链读全或明确未读完；R2 三段结构；R3 未核验只能假设、禁止强断言、给最小验证；R4 事实引用必须是实际收到的完整文件:行号。

| 开发题 | 旧证据与重点违规 | 静态处理 |
|---|---|---|
| astropy__astropy-12907 | 实际 read_file 60–161、161–271，两次都有 next_cursor；未读到 304–309 分发。`_coord_matrix` 171–216 和 `_cstack` 219–247 已收到，不能把漏读作为全部错误的解释。旧第 2 句仍断言 root cause 是 `_coord_matrix`，后续把嵌套行为当事实。R1/R3；第 10 句披露部分未读不能抵消前文。 | 强断言被拦下；候选列表不变；标未读完与待验证。 |
| sympy__sympy-18698 | 完整收到低层 281–335 与 Poly 3210–3237，但表达式包装链 `_generic_factor_list/_symbolic_factor_list` 未读。第 1 句 not a bug、第 10 句 no code change is warranted 均为 R3；第 7 句还误读了已返回的 `i += 1`。 | 两处预期强断言均被拦下；不将“无需修改”交给编码器。 |
| django__django-13964 | `__set__` 203–267 已读完，保存函数只有定义命中；`get_instance_value_for_fields` 只到 660 条件行。第 1 句确认根因、第 4 句 never refreshed 超出证据。已披露部分缺口应保留。 | R1/R3；不能把所有编码失败都归因定位。 |
| django__django-13033 | `find_ordering_name`、compiler `_setup_joins`、`get_order_dir` 已读完整；query 的 `setup_joins` 和 `get_order_by` 未读。比较 name 与末段的建议有依据，但第 1–2 句仍超额确认。 | 正向方向不等于全链已核验；新规范要求假设与最小验证。 |
| django__django-13925 | `_check_default_pk`、Options `_prepare` 已读全；从提升 parent link 推出继承祖先 AutoField 的 auto_created，缺 ModelBase 来源证据；auto_created=True 的概括忽略另外两个门控。AppConfig 只有搜索片段，测试读取失败。 | R1/R3；保留检查入口价值，拒绝未核验的来源和排除断言。 |

全部五题整包都违反新 R2，并缺明确的最小验证命令/断言。完整 **50 句原文、逐句规则和判定**见 [逐句审计表](OLD_ANSWER_AUDIT_ZH.md)，机器记录见 [old-answer-audit.json](old-answer-audit.json)。没有省略无新增实质违规的句子，也没有把旧题的成功结果当作诊断每句话正确的证明。

`*-STATIC-REPLAY.json` 是把历史回答送入校准器的离线回放；**不是模型在 v8 提示下重新定位**。五题全部回退不能解释为未来 v8 的真实回退率或性能。

## 4. v8 配置哈希

- B 核心 binding（重新计算一致）：`a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036`。
- 新 v8 `config.json` 文件 SHA256：`ba2853f4824b54ab32f6091b916f11fed05bd80eb9fb41d95040668a2b588ab5`。
- 新 v8 代码＋配置＋测试依赖 binding：`c072f4f8c9764f0311fabb7f52dfabbcdc04ba0369473296cba75547d54edf3a`。

[FREEZE.json](../FREEZE.json) 列明 51 个文件逐项哈希，binding 算法为“相对路径→SHA256 映射的 sorted compact UTF-8 JSON 再做 SHA256”。配置同时绑定新定位提示与只读 B 配置；顶层标识 C，嵌入的 baseline experiment 仍保留历史 A/B 字段，未拿旧驱动自动运行 C。

历史冻结记录完全只读。`verify_frozen.py` 已复核新绑定、42 个原 B 文件和 4 份历史冻结记录。交付文档/日志/历史输入的独立校验和见 [SHA256SUMS.json](SHA256SUMS.json)。

## 5. C 组运行估算

**dev24 × C × 1 次未运行。** 以下只是按 v5 B 的 24 条逐题记录外推；未查询最新价格、账户或账单。

| 历史 B 用量 | 定位 | 编码 | 合计，作为 C 的同轨迹假设 |
|---|---:|---:|---:|
| 请求 | 93 | 434 | 527 |
| 输入 token | 401,268 | 4,229,714 | 4,630,982 |
| 输出 token | 23,195 | 73,866 | 97,061 |
| 原缓存/时段混合折算 API 元 | 0.39551608 | 1.07981640 | **1.47533248** |
| 全输入按历史高峰未命中价格折算元 | 0.988096 | 9.050356 | **10.038452** |

最后一行是**相同 token 用量**的价格参考，不是新 C 费用的保证上界。新提示、覆盖提示、三段输出、工具控制与校准后的编码路径都可能改变 token、缓存和请求数量。原请求总上限依旧是 24 × (4 + 40) = 1,056，并非预计一定用满。

B 逐题“定位＋编码＋评测”合计 **3,303.580949 秒 = 55.06 分钟**，其中定位 624.29 秒，编码与评测 2679.29 秒。原 A+B 合计 129.45 分钟；扣除 A 与 B 的逐题耗时后，共享镜像拉取/清理等开销约 **27.36 分钟**，没有直接把 A+B 总时间当 C 实测。

沿用历史 16 核/64 GiB 主机报价 **4.09 元/小时**（本轮不查价），给出三个开销情景：

| 假设 | C 单路估算分钟 | 主机费用元 | 加原混合 API 后合计元 |
|---|---:|---:|---:|
| 只使用 B 的逐题耗时，不分摊共享开销 | 55.06 | 3.75 | 5.23 |
| 分摊历史共享开销的一半 | **68.74** | **4.69** | **6.16** |
| 承担全部历史共享开销 | 82.42 | 5.62 | 7.09 |

这些情景不是置信区间或保证上下界。主机启动/环境恢复、镜像缓存与下载速度、模型输出与编码循环、缓存命中、运行时段及评测环境都会影响结果；流量与停机磁盘保存费没有足够用量证据，**未估算**。若按相同 token 全高峰未命中参考价加中间主机情景，约 14.72 元，同样不是新 C 费用上限。

逐题依据见 [B-measured-per-task.csv](B-measured-per-task.csv)，完整计算与假设见 [C-RUN-ESTIMATE.json](C-RUN-ESTIMATE.json)。A=10/24、B=11/24、McNemar 精确 p=1.0 仅复用原结果，没有重新评测；本轮不提出 C 修复率数字。

本轮到此停止。是否开机执行 dev24 × C × 1 次，由用户下一步决定；没有自动执行或重复。
