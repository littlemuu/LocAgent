# dev24 C(v8.1) 回退离线审计

## 规则定义与判定代码

| 规则 | 冻结 v8.1 的实际判定 | 代码位置 |
|---|---|---|
| R1 | entities 列表及全文 path.py:QualifiedName 的并集；complete_entity=False 且无同一行完整ID+“未读完”即报错。另：pending 非空时，未核验段必须同时含“未读完”和“分页”。完整实体覆盖包括装饰器、def、docstring与全部正文；无AST实体也返回False。 | [实体/分页判定](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:189)；[AST范围](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:63)；[覆盖判断](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:122) |
| R2 | 首行必须是首标题；三标题固定、顺序正确、无重复，各段非空。 | [标题解析](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:171)；[非空检查](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:181) |
| R3 | 全文 STRONG 正则匹配即报强断言；推断每个非空行去除项目符号后须以“待验证假设：”开头；未核验段须有“最小验证：`…`”。 | [正则](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:31)；[强断言](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:184)；[格式/命令](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:205) |
| R4 | 全文所有 .py:数字范围都需完整落入覆盖账本；事实段每个非空行需有引用（除固定“尚无…”句）。范围是逐行全部覆盖，不允许跨缺口。 | [引用正则](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:37)；[全文检查](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:186)；[事实行](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:202) |

覆盖账本仅接收 read_file 与可还原的检索预览字符，**不接收 search_text**（[observe](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/calibration/policy.py:83)）。检索器给的def起点不含装饰器（[预览范围](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/baseline/runtime/experiments/retrieval_evidence_v6/retriever.py:150)），而校验器取最早装饰器行；这个口径差异必须单独说明。

## 审计口径与边界

本次只读本地日志与代码，输出新审计文件；不开机、不联网、不调用API、不重跑定位器，不修改v8.1或历史冻结件，不访问holdout 50。当前binding仍为 `9def7a0000b202dc8f7127ef6424b596c1155015bc7d248e74203512b02f7cee`。
共审阅20个回退题的55条已记录违规。分类依据是证据与表达语义：真违规=可独立确认的缺口/不当事实陈述且未适当披露；误判=证据或明确限定语足以排除这条指控；边界=字面格式契约与语义冲突、实体身份不确定或原AST范围缺失。属于逐条语义审阅+规则辅助提取，不是外部专家人工复核。
“误判”不表示代码未按既定正则执行。例如R3两条执行符合现有词法规则及旧测试，但忽略了整句的“待验证假设”限定。若坚持禁止短语本身，则应把它们视为边界，见敏感性结果。basename缩写、稀疏搜索连成连续范围等明确格式契约问题，本报告保守归边界。
为核实少数函数终点，只读取了本地历史B定位日志，逐题核验base_commit与本次相同；未读B编码/harness结果，未把B的阅读算给C。参考来源见 [reference-provenance.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/reference-provenance.json)。没有完整源快照/AST span的项目保留未知。
本报告只裁定既有55条触发，不保证原答案没有其他诊断错误，也不对4道合规题做漏判审计。回退率估计仅对这批触发做离线扣除，不生成新的运行成绩。

## 三类汇总

| 规则 | 真违规 | 误判 | 边界 | 合计 |
|---|---:|---:|---:|---:|
| R1 | 5 | 10 | 10 | 25 |
| R2 | 0 | 0 | 0 | 0 |
| R3 | 0 | 2 | 0 | 2 |
| R4 | 2 | 19 | 7 | 28 |
| 合计 | 7 | 31 | 17 | 55 |

**仅去掉31条确定误判、保留全部边界阻断：20/24（83.33%）→14/24（58.33%），下降25个百分点。** 并非31条误判对应31题；一个题只要还剩真违规或边界，就继续回退。
可解除回退的6题：astropy__astropy-14182, pytest-dev__pytest-7432, scikit-learn__scikit-learn-13779, django__django-13033, sphinx-doc__sphinx-8721, astropy__astropy-14365。
敏感性：若R3仍坚持词面禁用“根因是/在”，则仅修其余误判后为15/24（62.5%）。若连全部边界也放行，才会降到6/24（25%）；这是乐观政策下界，不是本报告建议或“只修误判”的结果。

## 逐题违规表

每题详细页包含原文逐条摘录、正则/实体/行号依据、实际read_file返回范围、搜索片段和分类理由。全部55条另见 [逐条违规表](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/violations.md) / [CSV](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/violations.csv) / [完整结构化证据](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/violations-reviewed.json)。

| 题目 | 真违规 | 误判 | 边界 | 只去误判后 |
|---|---:|---:|---:|---|
| [sympy__sympy-21379](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-21379/audit.md) | 0 | 1 | 1 | 继续回退 |
| [astropy__astropy-14182](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-14182/audit.md) | 0 | 1 | 0 | 解除回退 |
| [matplotlib__matplotlib-23314](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-23314/audit.md) | 0 | 0 | 2 | 继续回退 |
| [pytest-dev__pytest-7432](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pytest-dev__pytest-7432/audit.md) | 0 | 1 | 0 | 解除回退 |
| [scikit-learn__scikit-learn-13779](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/scikit-learn__scikit-learn-13779/audit.md) | 0 | 1 | 0 | 解除回退 |
| [django__django-13033](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13033/audit.md) | 0 | 1 | 0 | 解除回退 |
| [pylint-dev__pylint-7080](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pylint-dev__pylint-7080/audit.md) | 1 | 2 | 0 | 继续回退 |
| [sphinx-doc__sphinx-11445](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-11445/audit.md) | 0 | 4 | 1 | 继续回退 |
| [pydata__xarray-4094](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pydata__xarray-4094/audit.md) | 0 | 0 | 3 | 继续回退 |
| [psf__requests-2317](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/psf__requests-2317/audit.md) | 1 | 4 | 0 | 继续回退 |
| [sympy__sympy-18698](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-18698/audit.md) | 0 | 2 | 1 | 继续回退 |
| [astropy__astropy-12907](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-12907/audit.md) | 1 | 1 | 0 | 继续回退 |
| [sphinx-doc__sphinx-8595](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-8595/audit.md) | 0 | 3 | 2 | 继续回退 |
| [matplotlib__matplotlib-24970](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-24970/audit.md) | 1 | 2 | 0 | 继续回退 |
| [sphinx-doc__sphinx-8721](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-8721/audit.md) | 0 | 3 | 0 | 解除回退 |
| [matplotlib__matplotlib-25332](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-25332/audit.md) | 0 | 0 | 2 | 继续回退 |
| [scikit-learn__scikit-learn-10297](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/scikit-learn__scikit-learn-10297/audit.md) | 0 | 0 | 1 | 继续回退 |
| [astropy__astropy-14365](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-14365/audit.md) | 0 | 3 | 0 | 解除回退 |
| [sympy__sympy-13480](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-13480/audit.md) | 1 | 0 | 3 | 继续回退 |
| [django__django-13925](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13925/audit.md) | 2 | 2 | 1 | 继续回退 |

## R1：函数长度与预算归因

25条R1中，23条是实体检查、2条是分页标注；其中 requests/compat.py:builtin_str 是别名赋值，不能当作函数长度。余22个函数样式ID，能核实精确ID的def到末行范围仅6个；另1个可对应的方法定义有60行，但Figure/FigureBase限定名未确认；其余15个没有可靠完整长度。所有未知均未用请求终点或文件总行数冒充函数终点。
长度以def起始至AST末行计，含docstring、不含装饰器，区别于校验器的带装饰器范围。6个可核实长度为 **15、38、39、51、56、96行**；最小15，中位数45，最大96；1–50行3个，51–100行3个。样本不是随机抽样，不能据此判断全部R1函数都短，也不能给22项总体中位数。
| ID | 函数 | def范围 | 行数 | C该区间实际已读 | 长度来源 |
|---|---|---|---:|---|---|
| 03-02 | lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw | 389-444 | 56 | [[389, 444]] | C检索元数据；def至末行，不含装饰器 |
| 05-01 | sklearn/ensemble/voting.py:_BaseVoting.fit | 64-101 | 38 | [[64, 94]] | 同base B补足95-101；C只到94；63行为已读装饰器 |
| 12-03 | sympy/polys/polytools.py:sqf_list | 6204-6218 | 15 | [[6204, 6218]] | C检索元数据；def至末行，不含装饰器 |
| 13-01 | astropy/modeling/separable.py:_arith_oper | 130-168 | 39 | [[130, 160]] | 同base B补足161-168；C只到160 |
| 18-03 | sphinx/ext/viewcode.py:collect_pages | 181-276 | 96 | [[181, 204]] | 同base B补足205-276；C只到204 |
| 23-03 | sympy/functions/elementary/hyperbolic.py:coth.eval | 557-607 | 51 | [[557, 607]] | C检索元数据；def至末行，不含装饰器 |

[全部25条R1长度与未知项](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/R1-lengths.csv)；[17题预算表](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/R1-budget.csv)；[逐工具预算时间线](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/R1-budget.json)。

总预算并不等于纯Python正文长度：计量的是工具结果JSON编码字节，包括搜索、列表、元数据等；单页另有4096字节上限（[工具记账与关闭](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.1/baseline/runtime/readonly_agent/openhands_tools.py:55)）。next_cursor出现本身只表示分页，不能推出14336总预算用尽。
| R1题中总预算触顶者 | 消耗/14336 | 剩余 | 对R1的判断 |
|---|---:|---:|---|
| sympy-21379 | 14325 | 11 | 调查已关闭；但被拦实体涉及模块/别名，不能直接认定该R1由字节截断造成。 |
| pylint-7080 | 14285 | 51 | 总预算限制继续补读715-759缺口；_iterate_file_descrs头部未读有此限制贡献。分页标注报错另属词面误判。 |
| matplotlib-25332 | 14311 | 25 | align_ylabels续页确因剩余总容量截断；align_xlabels所指正文已读完，其报错主要是限定名边界。 |

17道R1题仅这3道触顶（对应5条R1记录），其余14道未耗尽总字节预算。可直接指出总字节上限限制实体缺口的有07-02、19-02两条，但预算不是其所有问题的唯一原因。
其它机制：django-13033、sphinx-8595、sphinx-8721 的续读改变了原cursor绑定行范围，触发ValueError，不能归为总源码预算耗尽；sympy-18698的后续搜索实际被candidate_body_read_priority阻止，虽然原答称“预算拦截”，总消耗仅3195字节。
独立核对了20题中46次成功read_file、2863个完整显示行：没有发现这部分完整行未被账本计入。该核对不能替代缺失的全源码/AST边界核验，也不涵盖所有搜索截断片段。

## 24道原回答路径

原回答txt是provider finish内容的精确提取，已逐题与原始响应核对；原始provider JSON和diagnostic-audit也保留链接。完整机器可读索引：[answer-paths.csv](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/answer-paths.csv)。

### 合规题（4道）

| 题目 | 原回答精确提取txt | 原始provider响应 | 原始审计JSON |
|---|---|---|---|
| pytest-dev__pytest-7490 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pytest-dev__pytest-7490/raw-answer.txt) | [response-43.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pytest-dev__pytest-7490/locator-wire/response-43.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pytest-dev__pytest-7490/locator/diagnostic-audit.json) |
| django__django-13158 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13158/raw-answer.txt) | [response-59.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13158/locator-wire/response-59.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13158/locator/diagnostic-audit.json) |
| scikit-learn__scikit-learn-14087 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/scikit-learn__scikit-learn-14087/raw-answer.txt) | [response-66.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-14087/locator-wire/response-66.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-14087/locator/diagnostic-audit.json) |
| django__django-13964 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13964/raw-answer.txt) | [response-82.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13964/locator-wire/response-82.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13964/locator/diagnostic-audit.json) |

### 回退题（20道）

| 题目 | 原回答精确提取txt | 原始provider响应 | 原始审计JSON |
|---|---|---|---|
| sympy__sympy-21379 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-21379/raw-answer.txt) | [response-4.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-21379/locator-wire/response-4.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-21379/locator/diagnostic-audit.json) |
| astropy__astropy-14182 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-14182/raw-answer.txt) | [response-8.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-14182/locator-wire/response-8.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-14182/locator/diagnostic-audit.json) |
| matplotlib__matplotlib-23314 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-23314/raw-answer.txt) | [response-12.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-23314/locator-wire/response-12.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-23314/locator/diagnostic-audit.json) |
| pytest-dev__pytest-7432 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pytest-dev__pytest-7432/raw-answer.txt) | [response-15.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pytest-dev__pytest-7432/locator-wire/response-15.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pytest-dev__pytest-7432/locator/diagnostic-audit.json) |
| scikit-learn__scikit-learn-13779 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/scikit-learn__scikit-learn-13779/raw-answer.txt) | [response-19.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-13779/locator-wire/response-19.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-13779/locator/diagnostic-audit.json) |
| django__django-13033 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13033/raw-answer.txt) | [response-23.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13033/locator-wire/response-23.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13033/locator/diagnostic-audit.json) |
| pylint-dev__pylint-7080 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pylint-dev__pylint-7080/raw-answer.txt) | [response-27.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pylint-dev__pylint-7080/locator-wire/response-27.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pylint-dev__pylint-7080/locator/diagnostic-audit.json) |
| sphinx-doc__sphinx-11445 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-11445/raw-answer.txt) | [response-31.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-11445/locator-wire/response-31.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-11445/locator/diagnostic-audit.json) |
| pydata__xarray-4094 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pydata__xarray-4094/raw-answer.txt) | [response-35.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pydata__xarray-4094/locator-wire/response-35.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pydata__xarray-4094/locator/diagnostic-audit.json) |
| psf__requests-2317 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/psf__requests-2317/raw-answer.txt) | [response-39.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/psf__requests-2317/locator-wire/response-39.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/psf__requests-2317/locator/diagnostic-audit.json) |
| sympy__sympy-18698 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-18698/raw-answer.txt) | [response-47.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-18698/locator-wire/response-47.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-18698/locator/diagnostic-audit.json) |
| astropy__astropy-12907 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-12907/raw-answer.txt) | [response-51.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-12907/locator-wire/response-51.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-12907/locator/diagnostic-audit.json) |
| sphinx-doc__sphinx-8595 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-8595/raw-answer.txt) | [response-55.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-8595/locator-wire/response-55.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-8595/locator/diagnostic-audit.json) |
| matplotlib__matplotlib-24970 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-24970/raw-answer.txt) | [response-62.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-24970/locator-wire/response-62.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-24970/locator/diagnostic-audit.json) |
| sphinx-doc__sphinx-8721 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sphinx-doc__sphinx-8721/raw-answer.txt) | [response-70.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-8721/locator-wire/response-70.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sphinx-doc__sphinx-8721/locator/diagnostic-audit.json) |
| matplotlib__matplotlib-25332 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-25332/raw-answer.txt) | [response-74.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-25332/locator-wire/response-74.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-25332/locator/diagnostic-audit.json) |
| scikit-learn__scikit-learn-10297 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/scikit-learn__scikit-learn-10297/raw-answer.txt) | [response-78.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-10297/locator-wire/response-78.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/scikit-learn__scikit-learn-10297/locator/diagnostic-audit.json) |
| astropy__astropy-14365 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/astropy__astropy-14365/raw-answer.txt) | [response-86.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-14365/locator-wire/response-86.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/astropy__astropy-14365/locator/diagnostic-audit.json) |
| sympy__sympy-13480 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/sympy__sympy-13480/raw-answer.txt) | [response-90.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-13480/locator-wire/response-90.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/sympy__sympy-13480/locator/diagnostic-audit.json) |
| django__django-13925 | [原回答](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/django__django-13925/raw-answer.txt) | [response-94.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13925/locator-wire/response-94.json) | [raw_packet.answer](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/django__django-13925/locator/diagnostic-audit.json) |

## 建议（本轮不实施）

1. **先修校验器的确定误判，再独立冻结新版本。** R4应区分事实证据、未读声明、验证目标；搜索片段可以支持其明确显示的窄事实，但不能升级为完整函数或连续范围。R1建议用结构化unread_entities/未续读cursor字段，支持明确上下文映射，绝不恢复全文裸名称扫描。变量别名、未知ID、继承方法与正文不完整应分开编码。R3应识别假设/否定/引用作用域，不以“根因是”字串单独决定。
2. **先澄清边界，再考虑局部回退。** 对装饰器、完整相对路径、稀疏搜索范围制定明确口径；记录每个实体的def起点、装饰器起点、终点、缺失行和匹配失败原因。局部回退应删除不受支持的事实/推断，并级联处理依赖它们的结论；不能简单只删触发词或对未证明的内容一律加“可能”。解析失败或依赖关系无法拆开时仍保留固定全回退。
3. **“只给位置”适合作为独立消融组，不宜把本轮C直接这样命名。** 本轮20题为固定回退、4题仍带具体诊断，是混合策略。若后续要比较纯位置组，应独立定义24题统一只传候选位置，不能把这种信息删减称为定位诊断质量提升。当前只有定位预检，没有Coding Agent/harness结果，无法判断局部回退或全回退谁的resolved更高。

所有建议未修改、未运行。requests-2317证书问题和历史评分没有重评。dev24只作开发参考，不下最终效果结论。
