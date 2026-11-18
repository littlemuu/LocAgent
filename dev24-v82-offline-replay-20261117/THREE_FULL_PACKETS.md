# 三题 v8.2 最终交付包全文

选取三种情况：sympy-13480 的真实 R1 缺口、django-13925 的真实 R4 缺口与未知实体、sphinx-11445 的稀疏搜索边界。为便于阅读，每包按“元数据及候选”和“answer 全文”分块展示，包含最终 localization.json 的全部字段与完整正文，无省略。

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
