# dev24 C(v8.2) 软门控冻结与离线重放

**完成：全回退0/24，附披露12/24，共16条；validator_error=0。原回答正文24/24逐字保留。**

## 策略与冻结

仅 R2 三段结构不可解析/无效或校验器异常使用固定全回退；R1/R3/R4 保留原文，在末尾追加固定标题“以下内容未在阅读记录中核验：”及带规则编号的文件范围/实体列表。每题 diagnostic-audit.json 记录原包、逐条违规、各规则计数、披露项、异常和证据模式。未发生任何正文删改。

终答检查接受 def 起点或更早的装饰器起点，唯一候选文件缩写，以及搜索片段直接显示的窄事实。搜索不进入完整行/实体覆盖账本，也不认可稀疏或相邻搜索命中为连续范围已读。未读声明与验证目标不再当作已读引用；仅在已明确引用的完整实体集合中解析唯一简称未读声明，不通过裸名称新增实体。假设限定下的“根因是/在”允许，明确确认措辞仍可触发 R3 披露。

保留 v8.1 的调查时 complete_entity/notice/read_priority 原代码，提示文本 INSTRUCTION 逐字不变；宽松完整性只用于终答交付检查。定位入口、预算、检索、Coding Agent、harness 文件保持原样。

冻结：[FREEZE.json](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.2/FREEZE.json)。binding：

`031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7`

与 v8.1 相比，仅修改 calibration/policy.py、tests/test_calibration.py、tests/test_v81.py；新增测试、夹具及测试变更说明。57 个冻结文件核验通过；42 个 B 依赖文件与原 B 完全一致。配置中沿用的 v8 版本/旧描述字符串未改，当前最终门控以 FREEZE.final_policy 和 diagnostic-audit.policy=v8.2 标识。
[B/C 与 v8.1 差异核验](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.2/delivery/V8.2-CHANGE-AUDIT.json)

## 测试

84/84 通过：原基线22 + v8校准22 + v8.1新增11 + 本轮新增29。零失败、零跳过、零被拦截的外部动作。测试使用固定响应和临时合成夹具；历史 SDK 协议测试不构成 dev24 Coding Agent 或 harness 运行。
4 项旧测试与新策略冲突，先逐项说明后调整；其余旧测试保持。[旧测试变更说明](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/OLD_TEST_CHANGES_ZH.md)。[原基线测试结果](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.2/delivery/baseline-tests.json)；[校准测试结果](/Users/xiaomu/Projects/LocAgent-OpenHands/locator-diagnostic-calibration-v8.2/delivery/new-tests.json)。

## 离线重放结果

输入为已存24份原始 provider finish + 同题 C 的 tool_audit/覆盖账本；逐题核验与原始 provider JSON 相同。未调用模型、未重新运行定位调查、未使用 B 阅读扩大 C 的覆盖，也未以人工分类驱动校验器。人工分类只在输出完成后核对。

原日志未持久化全部 AST span：已读行使用 v8.1 原账本，完整性使用已记录候选状态及 C 原检索 def 范围；仅对原答独有实体，依据 v8.1 原始判定条件恢复可证明的已通过状态。其余完整边界保持未知并披露。这个重放验证已存回答的交付策略，不是新定位质量或修复效果实验。

| 指标 | 结果 |
|---|---:|
| 全回退 | 0/24 |
| 附披露 | 12/24 |
| 无需追加披露 | 12/24 |
| 披露条目 | 16 |
| R1 / R2 / R3 / R4 残留 | 9 / 0 / 0 / 7 |
| validator_error | 0 |
| 原正文逐字保留 | 24/24 |
| 最大交付包 / 原上限 | 3309 / 14336 字节 |

| 题目 | 全回退 | 披露条数 | R1 | R2 | R3 | R4 | validator_error |
|---|---|---:|---:|---:|---:|---:|---|
| [sympy__sympy-21379](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sympy__sympy-21379/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [astropy__astropy-14182](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/astropy__astropy-14182/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [matplotlib__matplotlib-23314](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/matplotlib__matplotlib-23314/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [pytest-dev__pytest-7432](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/pytest-dev__pytest-7432/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [scikit-learn__scikit-learn-13779](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/scikit-learn__scikit-learn-13779/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [django__django-13033](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/django__django-13033/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [pylint-dev__pylint-7080](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/pylint-dev__pylint-7080/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [sphinx-doc__sphinx-11445](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sphinx-doc__sphinx-11445/diagnostic-audit.json) | 否 | 1 | 0 | 0 | 0 | 1 | 无 |
| [pydata__xarray-4094](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/pydata__xarray-4094/diagnostic-audit.json) | 否 | 3 | 1 | 0 | 0 | 2 | 无 |
| [psf__requests-2317](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/psf__requests-2317/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [pytest-dev__pytest-7490](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/pytest-dev__pytest-7490/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [sympy__sympy-18698](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sympy__sympy-18698/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [astropy__astropy-12907](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/astropy__astropy-12907/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [sphinx-doc__sphinx-8595](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sphinx-doc__sphinx-8595/diagnostic-audit.json) | 否 | 1 | 0 | 0 | 0 | 1 | 无 |
| [django__django-13158](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/django__django-13158/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [matplotlib__matplotlib-24970](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/matplotlib__matplotlib-24970/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [scikit-learn__scikit-learn-14087](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/scikit-learn__scikit-learn-14087/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [sphinx-doc__sphinx-8721](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sphinx-doc__sphinx-8721/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [matplotlib__matplotlib-25332](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/matplotlib__matplotlib-25332/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [scikit-learn__scikit-learn-10297](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/scikit-learn__scikit-learn-10297/diagnostic-audit.json) | 否 | 1 | 0 | 0 | 0 | 1 | 无 |
| [django__django-13964](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/django__django-13964/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [astropy__astropy-14365](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/astropy__astropy-14365/diagnostic-audit.json) | 否 | 0 | 0 | 0 | 0 | 0 | 无 |
| [sympy__sympy-13480](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sympy__sympy-13480/diagnostic-audit.json) | 否 | 1 | 1 | 0 | 0 | 0 | 无 |
| [django__django-13925](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/django__django-13925/diagnostic-audit.json) | 否 | 3 | 1 | 0 | 0 | 2 | 无 |

[24题机器可读表](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/per-case.csv)；[汇总 JSON](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/summary.json)

## 与55条人工审计核对

7/7 真违规全部进入披露；31/31 确定误判全部消失。17 条边界中8条按新口径不再触发，9条保留披露。没有新增既有55条之外的触发。

| 分类 | 原条数 | 消失 | 披露 |
|---|---:|---:|---:|
| 真违规 | 7 | 0 | 7 |
| 误判 | 31 | 31 | 0 |
| 边界 | 17 | 8 | 9 |

7条真违规逐项：

| 审计ID | 题目 | 进入披露的范围或实体 |
|---|---|---|
| 07-02 | pylint-dev__pylint-7080 | pylint/lint/pylinter.py:PyLinter._iterate_file_descrs |
| 10-05 | psf__requests-2317 | requests/sessions.py:Session.prepare_request |
| 13-01 | astropy__astropy-12907 | astropy/modeling/separable.py:_arith_oper |
| 16-03 | matplotlib__matplotlib-24970 | lib/matplotlib/colors.py:Colormap.__init__ |
| 23-04 | sympy__sympy-13480 | sympy/functions/elementary/trigonometric.py:cot.eval |
| 24-01 | django__django-13925 | django/apps/config.py:64-70 |
| 24-02 | django__django-13925 | tests/check_framework/test_model_checks.py:389-412 |

保留的边界涉及未证明的限定名/函数完整性及稀疏搜索范围；本次宽松口径不推测继承归属，也不把搜索命中升级为整函数或连续范围。已消失项表示不再有这条校验指控，不表示原定位诊断已被证明正确。

[55条逐项核对含原审计理由](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/review-crosscheck.csv)

## 三题最终交付包全文

[独立可读版本](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/THREE_FULL_PACKETS.md)

## sympy__sympy-13480

[完整原格式 localization.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sympy__sympy-13480/localization.json)

元数据及候选（answer 单独全文展示如下）：

```json
{
  "version": 1,
  "instance_id": "sympy__sympy-13480",
  "base_commit": "f57fe3f4b3f2cab225749e1b3b38ae1bf80b62f0",
  "result": {
    "entities": [
      "sympy/functions/elementary/hyperbolic.py:coth.eval",
      "sympy/functions/elementary/trigonometric.py:cot.eval"
    ],
    "files": [
      "sympy/functions/elementary/hyperbolic.py",
      "sympy/functions/elementary/trigonometric.py"
    ]
  }
}
```

answer 全文：

```text
已读到的事实（附文件:行号）
- sympy/functions/elementary/hyperbolic.py:557-607：coth.eval 完整函数体已读完（含 docstring 区段外的全部语句，无分页缺口）。
- sympy/functions/elementary/hyperbolic.py:586-593：arg.is_Add 分支调用 _peeloff_ipi(arg) 得 x, m；随后第 589 行赋值 cothm = coth(m)，但第 590 行判断的是未定义的 cotm（`if cotm is S.ComplexInfinity`），第 592 行注释写 cothm == 0。
- sympy/functions/elementary/hyperbolic.py:558：函数内仅 `from sympy import cot`，未导入或定义 cotm。
- sympy/functions/elementary/trigonometric.py:1304-1311：cot.eval 中对应块先 `cotm = cot(m)` 再判断 cotm，是命名一致的参照写法。
- 搜索命中：cotm 仅出现在 hyperbolic.py:590 与 trigonometric.py:1307-1310。

推断
- 待验证假设：sympy/functions/elementary/hyperbolic.py:coth.eval 第 589-590 行变量名不一致（cothm 赋值、cotm 使用）导致 NameError，属复制自 sympy/functions/elementary/trigonometric.py:cot.eval 时未改名。
- 待验证假设：仅当 arg 为 Add 且 _peeloff_ipi 返回非零 m 时进入该分支，故只有部分数值代入触发，与报告中的 2,3,5,6,8,9… 模式一致。
- 待验证假设：修复方向为把第 590 行改为 cothm（并核对第 592-593 行返回 tanh(x) 的语义是否与 coth 的周期性一致）。

未核验点
- 未读 _peeloff_ipi 实现，无法确认 m 的取值与 coth(m) 是否恒为 0 或 ComplexInfinity。
- 未读 coth 类定义头部与 docstring 之外的上下文（如 _eval_* 方法），未验证其他分支。
- 未运行任何复现或测试，未验证修复后 2,3,5 等输入的实际输出。
- 未检查 tanh/coth 周期性推导是否使第 592-593 行逻辑本身正确。

最小验证：`python -c "from sympy import *; x=Symbol('x'); print(coth(log(tan(x))).subs(x,2))"`（修复前应复现 NameError，修复后应返回数值）。

说明：本只读定位未执行行为验证，也不能证明关键调用链穷尽，以上仅为待验证假设。

以下内容未在阅读记录中核验：
- [R1] sympy/functions/elementary/trigonometric.py:cot.eval
```

## django__django-13925

[完整原格式 localization.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/django__django-13925/localization.json)

元数据及候选（answer 单独全文展示如下）：

```json
{
  "version": 1,
  "instance_id": "django__django-13925",
  "base_commit": "0c42cdf0d2422f4c080e93594d5d15381d6e955e",
  "result": {
    "entities": [
      "django/db/models/base.py:Model._check_default_pk",
      "django/db/models/options.py:Options._get_default_pk_class",
      "django/apps/config.py:AppConfig._is_default_auto_field_overridden"
    ],
    "files": [
      "django/db/models/base.py",
      "django/db/models/options.py",
      "django/apps/config.py",
      "tests/check_framework/test_model_checks.py"
    ]
  }
}
```

answer 全文：

```text
已读到的事实（附文件:行号）
- django/db/models/base.py:1298-1320：`_check_default_pk` 的触发条件只有三项：`cls._meta.pk.auto_created` 为真、`settings.is_overridden('DEFAULT_AUTO_FIELD')` 为假、`cls._meta.app_config._is_default_auto_field_overridden` 为假；三者同时成立才返回 models.W042。
- django/db/models/base.py:1265-1296：`check()` 在 `not cls._meta.swapped` 分支内无条件把 `_check_default_pk()` 加入 errors，未对抽象基类/继承链做额外过滤。
- django/db/models/options.py:221-250：`_get_default_pk_class` 从 `app_config.default_auto_field` 或 `settings.DEFAULT_AUTO_FIELD` 取路径，并校验其为 AutoField 子类。
- django/apps/config.py:64-70：`default_auto_field` 属性与 `_is_default_auto_field_overridden` 仅比较类属性是否被覆盖。
- tests/check_framework/test_model_checks.py:389-412：测试覆盖了 app 级 default_auto_field 与 setting 两种抑制路径。

推断
- 待验证假设：W042 的判定只看 `cls._meta.pk.auto_created`，而继承自带显式主键的父类时，子类 `_meta.pk` 若仍指向父类自动生成的 id 字段（auto_created=True），就会误报；修复方向应是在 django/db/models/base.py:Model._check_default_pk 中排除 pk 来自父类/非本模型自动创建的情形。
- 待验证假设：`_meta.pk.auto_created` 的赋值来源未在本次证据中出现（搜索仅命中 base.py:364、options.py:439 的 manager.auto_created），因此无法确认继承场景下该标志的实际取值路径。

未核验点
- 未读完：`Model._meta` 构建与 pk 自动创建逻辑（options.py 中 pk 相关方法、base.py 中字段继承处理）未读。
- 未核验：`Options._get_default_pk_class` 的调用点（未读）。
- 未运行任何验证，未证明调用链穷尽。

最小验证：`python -m pytest tests/check_framework/test_model_checks.py -q -k default_pk`（仅作回归入口，不能单独证明根因）

以下内容未在阅读记录中核验：
- [R4] django/apps/config.py:64-70
- [R4] tests/check_framework/test_model_checks.py:389-412
- [R1] django/apps/config.py:AppConfig._is_default_auto_field_overridden
```

## sphinx-doc__sphinx-11445

[完整原格式 localization.json](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v82-offline-replay-20261117/cases/sphinx-doc__sphinx-11445/localization.json)

元数据及候选（answer 单独全文展示如下）：

```json
{
  "version": 1,
  "instance_id": "sphinx-doc__sphinx-11445",
  "base_commit": "71db08c05197545944949d5aa76cd340e7143627",
  "result": {
    "entities": [
      "sphinx/util/rst.py:prepend_prolog",
      "sphinx/util/rst.py:append_epilog"
    ],
    "files": [
      "sphinx/util/rst.py",
      "sphinx/parsers.py",
      "sphinx/transforms/i18n.py",
      "sphinx/config.py"
    ]
  }
}
```

answer 全文：

```text
已读到的事实（附文件:行号）
- sphinx/util/rst.py:78-97：prepend_prolog 在 prolog 非空时，先跳过开头连续的 docinfo 行（docinfo_re.match），再在 pos 处插入 prolog 各行，最后插入一个空行。
- sphinx/util/rst.py:94-95：prolog 的每一行以 source='<rst_prolog>' 插入到 content 中，行号取自 prolog 内部 enumerate。
- sphinx/util/rst.py:97：prolog 之后插入一个空行（'<generated>'）。
- sphinx/parsers.py:85（搜索命中）：RSTParser 在解析前调用 prepend_prolog(content, self.config.rst_prolog)。
- sphinx/config.py:128（搜索命中）：rst_prolog 默认 None，类型 [str]。
- sphinx/transforms/i18n.py:60-79（搜索命中）：i18n 变换会临时清空并恢复 config.rst_prolog。

推断
- 待验证假设：sphinx/util/rst.py:prepend_prolog 把 prolog 文本插到文档最前面，使原本位于首行的标题（如 :mod:`mypackage2` 及其下划线）不再处于文档起始位置；docutils 的标题识别/文档标题提升（doctitle promotion）依赖首块结构，插入的 prolog 块可能使该标题被当作普通段落或 section 而非文档标题，从而丢失 toctree 条目。
- 待验证假设：sphinx/parsers.py 中 RSTParser 的解析流程（未读完）在 prepend_prolog 之后未对标题做补偿处理，是问题暴露的调用点。
- 待验证假设：sphinx/util/rst.py:append_epilog 与 prepend_prolog 结构对称，但 epilog 在尾部，不影响标题提升，故非根因候选。

未核验点
- sphinx/parsers.py 的 RSTParser.parse 完整函数体未读完（两次读取均返回 ValueError），无法确认 prolog 插入后是否还有标题相关处理。
- sphinx/util/rst.py:1-69 与 100-110 未读，docinfo_re 定义与 append_epilog 正文未核验。
- sphinx/transforms/i18n.py 与 sphinx/config.py 仅有搜索命中，未读函数体。
- 未运行任何构建或测试，未验证 docutils 版本行为差异。

最小验证：`python -m pytest -q tests/test_util_rst.py::test_prepend_prolog`（仅验证插入位置，需另加断言检查插入后首块是否为标题）

以下内容未在阅读记录中核验：
- [R4] sphinx/transforms/i18n.py:60-79
```

## 执行边界

开机：未运行；新 API 调用：0，新增 API 费用：0元；重新定位：未运行；dev24 Coding Agent：未运行；harness：未运行；resolved：未运行。未访问 holdout 50，未修改 v8.1 或其他历史冻结件。requests-2317 证书问题与历史评分不重评。

所有披露都随原回答交付；本轮只验证门控机制、证据对应和包完整性，不能推导 Coding Agent 会正确利用披露或 resolved 提升。停在离线冻结与汇报，不自动进入完整 C 组。
