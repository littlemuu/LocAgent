# Verified holdout50 最终一次性实验报告

冻结 holdout50 的原始评分为 **A 21/50（42%）、B 20/50（40%）、C 20/50（40%）**。主比较 C−A 为 −2 个百分点；C−B 为0。三项预注册精确双侧 McNemar 的原始 p 和 Holm 调整 p 均为1。本轮没有提供 C 优于 A 或 B 的证据；这不等同于证明三者等效。

结论受供应商余额不足、缺失评分及冻结 harness 日志/评分不一致的限制。全部保留原结果，没有补跑、重抽、修改评分或在揭盲后调整实验组件。这里的150指150个组别均被调度处理，不代表150个Coding Agent都成功运行完毕。

**已完成关机不计费：用户完成本人微信验证后，2026-11-18 06:24:12（上海时间）核验实例“已关机 / 关机不计费模式 / 按量计费-部分停止计费”，公网IPv4已释放。临时API凭证已删除，实验容器已清空；保留云盘仍可能计费。** 当前凭据与缓存核验见 [final-remote-verification.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/final-remote-verification.json)，关机状态见 [shutdown-receipt.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/shutdown-receipt.json) 和 [关机截图](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/shutdown-confirmed.jpg)。

## 原评分、补丁与首次编辑

| 指标 | A | B | C |
| --- | --- | --- | --- |
| resolved / 固定50 | 21/50 (42%) | 20/50 (40%) | 20/50 (40%) |
| 原始False / null | 28 / 1 | 25 / 5 | 25 / 5 |
| 实际获得有效harness评分 | 49 | 45 | 45 |
| 编码阶段从未启动 | 0 | 5 | 5 |
| 编码首个API请求402、无模型行动 | 4 | 0 | 0 |
| 技术或预算失败组别 | 6 | 5 | 6 |
| 空补丁 / 实际补丁产物 | 8/50 (16.00%) | 4/45 (8.89%) | 6/45 (13.33%) |
| 缺失补丁产物 | 0 | 5 | 5 |
| 首次源码编辑请求中位数（有编辑人数） | 5.5 (42) | 4 (41) | 4 (39) |
| 所有组别中用满40次编码请求 | 14 | 12 | 13 |

技术失败与null不是互斥口径：例如首个API失败后生成的空补丁仍可能被harness评分False；缺失评分保持null。主分析比较固定50题是否获得原始 resolved=True，未把null篡改为harness False。空补丁只对实际补丁产物计算；首次源码编辑中位数只纳入真正出现源码编辑的组别。完整150行及原始错误：[ABC-per-task.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/ABC-per-task.json)、[ABC-per-task.csv](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/ABC-per-task.csv)。

## 固定50题的预注册比较

| 比较 | 前者独自解决 | 后者独自解决 | 同时解决 | 均未获True | 精确双侧p | Holm p |
| --- | --- | --- | --- | --- | --- | --- |
| C vs A | 4 | 5 | 16 | 25 | 1.0 | 1.0 |
| C vs B | 2 | 2 | 18 | 28 | 1.0 | 1.0 |
| B vs A | 3 | 4 | 17 | 26 | 1.0 | 1.0 |

以下是全部双向不一致名单。“独自解决”仅指该配对的另一组没有原始True，可能是False或null。

- **C vs A**：C独自解决：`psf__requests-5414`、`pydata__xarray-6721`、`pylint-dev__pylint-6903`、`pytest-dev__pytest-7236`。A独自解决：`astropy__astropy-8872`、`psf__requests-2931`、`pytest-dev__pytest-10081`、`pytest-dev__pytest-5787`、`scikit-learn__scikit-learn-26323`。
- **C vs B**：C独自解决：`pydata__xarray-4695`、`pytest-dev__pytest-7236`。B独自解决：`psf__requests-2931`、`scikit-learn__scikit-learn-26323`。
- **B vs A**：B独自解决：`psf__requests-5414`、`pydata__xarray-6721`、`pylint-dev__pylint-6903`。A独自解决：`astropy__astropy-8872`、`pydata__xarray-4695`、`pytest-dev__pytest-10081`、`pytest-dev__pytest-5787`。

`pylint-dev__pylint-6903` 的A原评分为null，因此C/B相对A的这项胜出不是“对方测试失败”的证据。

## 仅双组均有效评分的缺失敏感性表

| 比较 | 配对数 | 前者独自解决 | 后者独自解决 | 精确双侧p | Holm p |
| --- | --- | --- | --- | --- | --- |
| C vs A | 44 | 3 | 5 | 0.7265625 | 1.0 |
| C vs B | 45 | 2 | 2 | 1.0 | 1.0 |
| B vs A | 44 | 2 | 4 | 0.6875 | 1.0 |

该表按预注册口径完整披露，不替代主表。以下列出全部敏感性名单：

- **C vs A**：前者独自解决：psf__requests-5414、pydata__xarray-6721、pytest-dev__pytest-7236；后者独自解决：astropy__astropy-8872、psf__requests-2931、pytest-dev__pytest-10081、pytest-dev__pytest-5787、scikit-learn__scikit-learn-26323；排除未评分：pylint-dev__pylint-6903、sympy__sympy-13091、sympy__sympy-13757、sympy__sympy-13877、sympy__sympy-15809、sympy__sympy-22914。
- **C vs B**：前者独自解决：pydata__xarray-4695、pytest-dev__pytest-7236；后者独自解决：psf__requests-2931、scikit-learn__scikit-learn-26323；排除未评分：sympy__sympy-13091、sympy__sympy-13757、sympy__sympy-13877、sympy__sympy-15809、sympy__sympy-22914。
- **B vs A**：前者独自解决：psf__requests-5414、pydata__xarray-6721；后者独自解决：astropy__astropy-8872、pydata__xarray-4695、pytest-dev__pytest-10081、pytest-dev__pytest-5787；排除未评分：pylint-dev__pylint-6903、sympy__sympy-13091、sympy__sympy-13757、sympy__sympy-13877、sympy__sympy-15809、sympy__sympy-22914。

所有p值来自冻结统计实现；预注册公式与三项Holm调整口径见 [PREREGISTRATION_ZH.md](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/PREREGISTRATION_ZH.md)，机器可读统计见 [summary.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/summary.json)。

## 一次性运行中的技术失败与harness异常

17个技术或预算失败组别完整保留：

- `pylint-dev__pylint-6903/A`：编码7次后，harness构建TestSpec找不到该base commit的`requirements_test.txt`；evaluation缺失结果，原评分null。
- `sphinx-doc__sphinx-8265/C`：编码26次，`missing_tool_or_truncated_response`；保留部分补丁并按冻结流程评分False。
- `sympy__sympy-13091/A`：编码34次到达token预算；保留部分补丁，评分False。
- 最后5题（sympy 13091、13757、13877、15809、22914）的B/C：定位首个请求HTTP 402；定位未交付，编码/评分未启动，共10个null。
- 最后4题的A：编码首个请求HTTP 402，没有模型行动，空补丁仍进入冻结评分流程，均False。

14次HTTP 402的供应商响应写明 `Insufficient Balance` / `insufficient_balance_error`。这是供应商余额拒绝；外层调度确实没有API总金额上限，也没有自动重试或充值后续跑。完整记录：[technical-failures.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/technical-failures.json)。

另有**17个组别**出现“原始测试最后汇总有passed且无failed/error/exception，但report.resolved=False”。下表仅披露日志与冻结评分的不一致迹象，不把汇总行当成替代评分，不断言它能证明所有目标标签通过。Astropy部分有测试名/路径匹配问题的迹象，Sphinx部分仅输出进度点；具体解析原因未通过改动或重跑验证。

| 题号 / ID | 组 | 原始最后测试汇总 | 原评分 |
| --- | --- | --- | --- |
| 2 / astropy__astropy-7166 | B | =============== 8 passed, 1 skipped, 1 warnings in 0.10 seconds ================ | 否 |
| 2 / astropy__astropy-7166 | C | =============== 8 passed, 1 skipped, 1 warnings in 0.10 seconds ================ | 否 |
| 3 / astropy__astropy-7336 | C | ==================== 340 passed, 1 warnings in 1.53 seconds ==================== | 否 |
| 3 / astropy__astropy-7336 | A | ==================== 340 passed, 1 warnings in 1.49 seconds ==================== | 否 |
| 3 / astropy__astropy-7336 | B | ==================== 340 passed, 1 warnings in 1.49 seconds ==================== | 否 |
| 41 / sphinx-doc__sphinx-8035 | B | ======================== 3 passed, 7 warnings in 0.30s ========================= | 否 |
| 42 / sphinx-doc__sphinx-8265 | C | ======================== 39 passed, 7 warnings in 0.03s ======================== | 否 |
| 42 / sphinx-doc__sphinx-8265 | A | ======================== 39 passed, 7 warnings in 0.03s ======================== | 否 |
| 43 / sphinx-doc__sphinx-8269 | A | ======================= 6 passed, 229 warnings in 0.99s ======================== | 否 |
| 43 / sphinx-doc__sphinx-8269 | B | ======================= 6 passed, 229 warnings in 1.14s ======================== | 否 |
| 43 / sphinx-doc__sphinx-8269 | C | ======================= 6 passed, 229 warnings in 0.97s ======================== | 否 |
| 44 / sphinx-doc__sphinx-8551 | B | ====================== 33 passed, 1244 warnings in 0.90s ======================= | 否 |
| 44 / sphinx-doc__sphinx-8551 | C | ====================== 33 passed, 1244 warnings in 0.91s ======================= | 否 |
| 44 / sphinx-doc__sphinx-8551 | A | ====================== 33 passed, 1244 warnings in 0.91s ======================= | 否 |
| 45 / sphinx-doc__sphinx-9281 | C | ======================== 39 passed, 7 warnings in 0.48s ======================== | 否 |
| 45 / sphinx-doc__sphinx-9281 | A | ======================== 39 passed, 7 warnings in 0.48s ======================== | 否 |
| 45 / sphinx-doc__sphinx-9281 | B | ======================== 39 passed, 7 warnings in 0.48s ======================== | 否 |

环境或兼容性信号还包括：Astropy14096的leap-second自动更新异常与依赖导入问题；Requests1724/1766的SSL证书错误，1766的旧pytest调用不兼容；Requests2931缺失httpbin_secure夹具（C同时有目标binary PUT类型断言失败）；Requests5414有缺失mocker/trustme文本；Pylint4661缺失appdirs；Pylint8898日志中有_distutils_hack导入信号（C同时有正则列表回归）。这些信号可能与真实补丁错误并存，且有些出现在成功组别；不能统一归因为“全是环境问题”。pytest7521的missingarg/xyz42123来自测试内嵌失败场景，不当作独立环境失败统计。

全部150组的原report、摘要、环境文本信号和原文件位置见 [raw-harness-audit.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/raw-harness-audit.json)。所有原始日志位于 [封存证据目录](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/evidence/run/trial)，未修改任何证书、依赖、harness或评分。

## 失败轨迹审阅与C定位披露

| 未解决组别的循环审阅 | A (29) | B (30) | C (30) |
| --- | --- | --- | --- |
| 是 | 8 | 11 | 8 |
| 否 | 17 | 14 | 16 |
| 证据不足 | 0 | 0 | 1 |
| 未运行 | 4 | 5 | 5 |

这89个未解决组别中用满40次的数量分别为11/12/11。循环与用满预算不能互相替代；例如反复撤销同一修改会产生很多编辑事件，仍属于无净进展循环。C的1例证据不足涉及反复随机样本验证，不能仅凭命令相似断定没有获得新信息。

C的30个未解决组别中，沿用错误定位方案判为明确是5、未见明确证据17、不确定3、未运行5。5个明确案例分别为：astropy8872的反向cast检查建议；seaborn3069的无mark空图验证方案；requests2931的统一UTF-8文本转换分支；pylint4970将内部短路等同于完全静默；pylint8898先整体编译导致逗号列表语义回归。seaborn案例指错误验证方案，不能据此认定定位是失败的唯一原因。另有pytest10081/5787、sklearn26323等属于实现遗漏或未完整执行建议，未归入明确错误定位采纳。

完整89项循环判定、30项C判断、请求号和定位原文/编码行为链接：[FAILURE_REVIEW_ZH.md](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/FAILURE_REVIEW_ZH.md)；结构化文件：[manual-judgments.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/manual-judgments.json)、[manual-judgments.csv](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/manual-judgments.csv)。这些是揭盲后的主观审阅，没有另做双人复核。

C定位成功交付45/50，27题产生44条披露：R1=22、R2=0、R3=2、R4=20；已交付45题全回退0、validator_error非空0；read_file错误20次、涉及14题。未交付5题相应值均标未观测。每题完整清单及错误原值：[C_DISCLOSURES_ZH.md](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/C_DISCLOSURES_ZH.md)、[C-disclosures-per-task.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/C-disclosures-per-task.json)。

## 请求、token、费用和时间

| 指标 | A | B | C |
| --- | --- | --- | --- |
| 请求尝试（含402） | 1,064 | 1,067 | 1,126 |
| 收到usage的请求 | 1,060 | 1,062 | 1,121 |
| 没有usage的402请求 | 4 | 5 | 5 |
| 输入token | 12,725,543 | 10,435,741 | 11,664,509 |
| 输出token | 167,149 | 200,012 | 219,277 |
| 总token | 12,892,692 | 10,635,753 | 11,883,786 |
| 缓存命中输入token | 11,698,176 | 9,253,888 | 10,369,280 |
| 缓存未命中输入token | 1,027,367 | 1,181,853 | 1,295,229 |

| 费用口径（元） | A | B | C |
| --- | --- | --- | --- |
| usage/缓存/时段推算 | 1.929927 | 2.166979 | 2.379723 |
| 同usage统一高峰、保留缓存参考 | 3.859853 | 4.333958 | 4.759445 |
| 同usage统一高峰、无缓存参考 | 26.788278 | 22.471578 | 25.083234 |
| 无usage请求的保守reservation（非费用） | 8.519680 | 10.567680 | 10.567680 |

收到usage请求的推算费用合计 **6.476628元**；同usage统一高峰无缓存参考合计74.343090元。**均不是服务商实扣账单**。冻结算法按上海工作日09–12/14–18点为高峰，其他时段乘0.5；本轮收到usage的调用均落在0.5系数时段。14个402没有usage，ledger仍保留reserved状态；29.655040元reservation只是发送前预算保守量，既不算已扣款，也不加到估算费用中。没有读取服务商账单核销这些请求。

| 组 / 阶段 | 请求尝试 | 输入token | 输出token | 推算元 | 阶段秒 |
| --- | --- | --- | --- | --- | --- |
| A / locator | 0 | 0 | 0 | 0.000000 | 0.00 |
| A / coding | 1064 | 12725543 | 167149 | 1.929927 | 2959.69 |
| B / locator | 178 | 696198 | 40558 | 0.519867 | 1104.72 |
| B / coding | 889 | 9739543 | 159454 | 1.647111 | 2285.26 |
| C / locator | 179 | 809838 | 57991 | 0.640269 | 1286.17 |
| C / coding | 947 | 10854671 | 161286 | 1.739454 | 2697.78 |

| 组 | 定位秒 | 编码秒 | harness秒 | 三阶段合计秒 |
| --- | --- | --- | --- | --- |
| A | 0.00 | 2959.69 | 2366.12 | 5325.81 |
| B | 1104.72 | 2285.26 | 2283.84 | 5673.82 |
| C | 1286.17 | 2697.78 | 2283.27 | 6267.22 |

整轮从上海时间 **2026-11-17 22:19:43 至 2026-11-18 04:48:19**，共 **6小时28分35.8秒**。其中镜像阶段5980.30秒，定位/编码/harness阶段合计17266.85秒，其余编排、校验、归档与清理约68.64秒。阶段时间包括启动/校验等待，不是纯模型响应时间；不同阶段缓存、镜像和时段条件不能直接解释为模型效率差异。

历史主机报价4.09元/小时仅对这6.4766小时运行窗口折算约26.49元；这**不是本轮主机总费用或账单**，不含开机准备、收证和等待本人验证期间的运行时间。现已核验关机不计费；上述06:24:12为观测时间，不是精确停机时间。等待验证期间的运行费用、流量与停机后保留存储费用未通过账单核验。完整费用与时长明细：[usage-cost-time-supplement.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/usage-cost-time-supplement.json)。

## dev24与74题的描述性汇总

| 范围 / 组 | resolved | 空补丁 / 已观测 | 首次编辑中位数（人数） |
| --- | --- | --- | --- |
| dev24 / A | 10/24 (41.67%) | 7/24 | 5 (17) |
| dev24 / B | 11/24 (45.83%) | 2/24 | 3.0 (22) |
| dev24 / C | 15/24 (62.50%) | 4/24 | 4.0 (20) |
| holdout50 / A | 21/50 (42.00%) | 8/50 | 5.5 (42) |
| holdout50 / B | 20/50 (40.00%) | 4/45 | 4 (41) |
| holdout50 / C | 20/50 (40.00%) | 6/45 | 4 (39) |
| 合并74，仅描述 / A | 31/74 (41.89%) | 15/74 | 5 (59) |
| 合并74，仅描述 / B | 31/74 (41.89%) | 6/69 | 4 (63) |
| 合并74，仅描述 / C | 35/74 (47.30%) | 10/69 | 4 (59) |

74题的中位数由逐题记录重算，没有平均两个中位数。开发集C为15/24，而holdout为20/50，开发集优势没有在本轮holdout中复现。74题C=35/74对A/B=31/74仅描述，不做确认性合并检验；最终推断只依据冻结holdout50。历史逐题数据见 [dev24逐题记录](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/history/dev24-ABC-per-task.json)。

## 冻结、离线核验、资源与证据完整性

只新增最小holdout数据适配入口与外层调度。A/B原42文件绑定、C原57文件绑定、Coding Agent、定位器、SDK及harness commit未变。离线适配核验24/24数据行字节一致、实例集合和选择顺序一致、捕获的harness评分输入/参数字节一致；spec_for/evaluate/main尾部保持逐字相同。该核验使用隔离替身捕获入口输入，模型API、Docker及真实harness执行均为0；不冒充一次真实评分重跑。

holdout名单SHA-256：`5226d5870987a2f9d161b98077aa64788f6e3426d1cea326385694c47922acd6`。

A/B绑定：`a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036`。

C绑定：`031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7`。

开机后的首个付费请求前复核：openhands-sdk1.62.0、swebench3.0.0、bm25s0.2.3、PyStemmer2.2.0.3、pyarrow18.0.0；harness commit `d83e1001739f4d96add351d9ec0d56f4594a0d82`。主机16CPU/65,961,148,416字节内存；agent容器6CPU/6GiB/network none，stuck_detection=False。冻结harness实际容器为Memory=0、NanoCpus=0、network bridge：原冻结封装未对它施加agent资源限制，本轮原样保留，没有将它误报为6CPU/6GiB。

预检剩余77.30GiB；运行健康采样最低67.06GiB，未低于30GiB。379条容器资源观测均匹配冻结基线（240条agent、139条harness）；采样不是连续监测证明。50题按固定顺序与ABC/BCA/CAB轮转，480个阶段独占started标记及区间均无重叠：50次镜像、100次定位、140次编码、140次评分尝试、50次归档清理。3257条API reservation序号连续且每组预算未超，收到usage3243条，实际返回模型标识均为deepseek-flash；没有重新发送失败请求。

50题的A/B/C逐题共用同一镜像ID/digest，三组产物（或明确的失败缺失项）记录和哈希完成后才删除该题新拉镜像。50个新题镜像均按此处理，旧24个镜像ID最终核验完全一致；没有全局prune。81个部署文件哈希一致，50份证据清单中21,072个产物哈希全部匹配。

核验附件：[ADAPTER_ACCEPTANCE_ZH.md](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/ADAPTER_ACCEPTANCE_ZH.md)、[adapter-equivalence.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/adapter-equivalence.json)、[evaluation-adapter.diff](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/evaluation-adapter.diff)、[remote-preflight.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/remote-preflight.json)、[integrity-and-execution-audit.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/integrity-and-execution-audit.json)、[image-digests-and-cleanup.json](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/image-digests-and-cleanup.json)。

模型只收到各自题面、base_commit源码与本组定位包；测试patch/评分标签由隔离evaluator读取。运行期间仅读取不含结果的健康信息。完成后备份封存证据并一次性揭盲，收据见 [揭盲收据](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/unblinding-receipt.json)。压缩包包含24,194个成员，大小39,582,904字节，SHA-256 `2011b95dd19512da53b21ac69e489d64398b1445e7f22d7d9fd1d98526c51668`；[原始封存证据包](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/sealed-evidence.tar.gz)，[备份验证](/Users/xiaomu/Projects/LocAgent-OpenHands/holdout50-final-run-20261117/delivery/sealed-backup-verification.json)。

本地派生分析中的显示/索引修正不触发模型或harness执行：旧Python不支持tarfile的filter参数后改用安全路径/文件类型检查解包；审阅索引按Controller本地请求号匹配工具结果；原始日志的ANSI颜色只在派生摘要中去除。冻结实验、原始证据及原评分均未修改。

## 收尾完成

用户完成本人微信验证后，恢复页面已显示“关机中 / 操作成功”；未再次提交关机。随后核验实例“已关机”、关机不计费模式、按量计费-部分停止计费，公网IPv4栏为空。2026-11-18 06:24:12（上海时间）保存最终截图与关机收据，历史MFA阻塞收据另存shutdown-mfa-block-receipt.json。实验、报告与关机收尾全部完成；冻结代码、原始证据与评分未改动。
