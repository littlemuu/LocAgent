# 五题旧定位终答逐句静态审计

这是对历史 B 终答及当时实际收到源码的规则审计，不是真实 v8 定位效果。原句完整保留；没有执行日志里的命令，也没有使用参考补丁。

规则：R1 函数体/关键链读全或明确未读完；R2 事实—推断—未核验点三段；R3 未核验只能假设、不得强断言、须有最小验证；R4 事实附完整文件:行号且引用实际收到。

五题共同的整包违规：R2 无指定三段结构；R3 无一条明确的最小验证命令或断言。表中“—”只表示该句无新增实质违规，并非整包通过。

## astropy__astropy-12907

历史请求数：4。静态校验触发保守回退：True。

| 句号 | 原句（完整） | 规则 | 审计判定 |
|---:|---|---|---|
| 1 | This is a genuine bug, not expected behavior. | R3 | 关键调用链未读全，直接定性 genuine bug 应降为假设。 |
| 2 | The root cause is in `_coord_matrix` (astropy/modeling/separable.py:171-216), which builds the per-model coordinate matrix used by `_cstack` for the `&` operator. | R3 | _coord_matrix 已读全，但 _separable 未读完；完整读某个 helper 不能确认它是根因。 |
| 3 | When a child of `&` is itself a CompoundModel (e.g. `cm = Linear1D(10) & Linear1D(5)`), `_coord_matrix` does not recurse into it. | R1,R3 | 未读到 304–309 的递归分发，不能断言嵌套 CompoundModel 在实际调用路径直接进入该 helper。 |
| 4 | Instead it only checks `model.separable` (line 202). | R4 | 202 行确实已读，但只说 checks model.separable 忽略 189–201 Mapping 分支；且须写完整路径。 |
| 5 | For a separable compound model it falls into the `else` branch (lines 209-215), which builds a diagonal matrix `mat[i, i] = 1` for `i in range(model.n_inputs)` and, for a right child, rolls it by `noutp - model.n_outputs`. | R3,R4 | 209–215 已读，条件分支描述可保留为源码事实；实际嵌套输入会走此分支尚未核验。 |
| 6 | That diagonal construction assumes the child's outputs map one-to-one onto its own inputs in order, which is wrong for a nested compound whose internal structure is not a simple identity-like diagonal. | R3 | 把局部矩阵构造推成嵌套对象错误机制，缺少调用链证据。 |
| 7 | The result is that the nested `cm` contributes a full 2x2 block of True values instead of the correct diagonal, producing the observed `[[T,T,F,F],[T,T,F,F],[F,F,T,T],[F,F,T,T]]`. | R3 | 把观察到的全 True 子块归因于对角构造，无验证；245 行右矩阵分支已返回却未考虑。 |
| 8 | By contrast, the flat case `Pix2Sky_TAN() & Linear1D(10) & Linear1D(5)` works because each `&` operand is a simple (non-compound) model, so `_coord_matrix`'s diagonal path is correct for each leaf. | R3 | 扁平组合路径未经完整分发核验，不能用此断言排除其他分支。 |
| 9 | The fix would be to make `_coord_matrix` recurse into compound models (calling `_separable`/`_cstack` on the nested model) rather than treating any separable model as a diagonal. | R1,R3 | 提出对 _coord_matrix 递归的修复假设可以，但必须标明调用链缺口并附最小验证，不能承接确定根因。 |
| 10 | I did not read the full `_separable` dispatch (lines 271-313) or `_cdot`, so I cannot rule out related issues for `\|` with nested compounds; that remains uncertain. | — | 明确承认 _separable/_cdot 未读完值得保留；但只把不确定性限定在 \| 操作不足以支持前文 & 的强断言。 |

## django__django-13964

历史请求数：4。静态校验触发保守回退：True。

| 句号 | 原句（完整） | 规则 | 审计判定 |
|---:|---|---|---|
| 1 | Root cause is in ForwardManyToOneDescriptor.__set__ (django/db/models/fields/related_descriptors.py:203-268). | R3 | __set__ 正文已读全；保存链未读完，不能把赋值阶段确认为根因。 |
| 2 | At assignment time it copies the related object's PK into the local FK attname: `for lh_field, rh_field in self.field.related_fields: setattr(instance, lh_field.attname, getattr(value, rh_field.attname))` (lines 256-257). | R4 | 256–257 的赋值循环有实际源码支持；应补全文件:行号并放在事实段。 |
| 3 | When `Product()` is created without a sku, `value.sku` is '' (CharField default), so `order.product_id` is snapshotted as ''. | R3 | CharField 默认值及保存表现没有在定位阶段行为验证，应作为由题面与代码推得的假设。 |
| 4 | Later setting `order.product.sku = "foo"` mutates only the Product instance; the already-copied `product_id` on Order is never refreshed, so `order.save()` writes ''. | R1,R3 | never refreshed 涉及未读的保存函数；不能据此断言保存路径不刷新。 |
| 5 | The descriptor also caches the related object (line 261), so `__get__` returns the in-memory Product and hides the stale FK. | R1,R3,R4 | 261 缓存写入有支持；__get__ 未完整读取，把其行为接入因果链需标注缺口。 |
| 6 | In the working case, `Product(sku="foo")` is assigned after the PK exists, so the copy is correct. | R3 | 工作示例因果解释未执行验证，应放入推断。 |
| 7 | A likely fix location is save-time reconciliation: Model._prepare_related_fields_for_save (django/db/models/base.py:911) is where Django validates/refreshes related fields before writing, and it could re-sync local FK values from the cached related object's current PK. | R1,R4 | 只搜索到 _prepare_related_fields_for_save 定义 911 行；likely 的措辞合适，但定义命中不能支持其正文行为。 |
| 8 | Note get_instance_value_for_fields (django/db/models/fields/related.py:652-660) has a special case using `instance.pk` when the field is a primary key, which is relevant to how non-auto PKs are read. | R1 | 读取到 660 的 if field.primary_key，后续分支正文未读完；注释不是完整实现证据。 |
| 9 | I did not read the full bodies of _prepare_related_fields_for_save or get_instance_value_for_fields (investigation closed at the call limit), so the exact fix site and whether the bug is purely the stale copy versus also a PK-fetch issue remain partly unverified. | — | 已主动标注两个未读完函数；保留此不确定性，但仍需最小验证并改写首句强断言。 |

## django__django-13033

历史请求数：4。静态校验触发保守回退：True。

| 句号 | 原句（完整） | 规则 | 审计判定 |
|---:|---|---|---|
| 1 | This is a genuine bug, not a misunderstanding. | R3 | 关键调用链未读全，定性应降为待验证假设，即使历史 B 最后修复成功。 |
| 2 | The root cause is in SQLCompiler.find_ordering_name (django/db/models/sql/compiler.py:715-749). | R3 | find_ordering_name 715–749 已读全，但不能据此确认完整根因。 |
| 3 | After resolving the join path, it checks whether the final field is a relation with model-level ordering: `if field.is_relation and opts.ordering and getattr(field, 'attname', None) != name and name != 'pk'`. | R4 | 730 行条件确实收到；需补完整文件:行号，放事实段。 |
| 4 | For `record__root_id`, the resolved field is the self-referencing FK `root`, whose attname is `root_id`; the comparison `attname != name` compares `'root_id'` against the full lookup string `'record__root_id'`, so it is unequal and the branch is wrongly taken. | R3 | name 与 attname 比较是有源码支持的有效假设；字段解析来自未读全的 query.setup_joins，应标条件。 |
| 5 | Django then appends OneModel.Meta.ordering (`-id`) relative to the joined alias, producing the extra LEFT OUTER JOIN to T3 and the unexpected DESC. | R3 | 额外 join 与排序方向解释需行为验证，不能作为已核验事实。 |
| 6 | The `-record__root_id` case flips the inherited direction via get_order_dir (query.py:2302-2313), explaining the ASC result. | R4 | get_order_dir 2302–2313 已读全，可支持方向转换；query.py 缺完整路径，具体 ASC 因果仍属推断。 |
| 7 | The `record__root__id` form works because the final piece is the pk `id`, not the relation, so the ordering-inheritance branch is skipped. | R3 | 关联字段解析链未读全；针对不同 lookup 的解释应写为假设。 |
| 8 | The annotate(F(...)) workaround also avoids it since the ordering target is an annotation. | R1,R3 | annotation 排序入口 get_order_by 未读，绕过分支机制未核验。 |
| 9 | The fix should compare the last path segment (or the field's name) rather than the whole dotted name, so that `record__root_id` is recognized as targeting the FK's attname and does not inherit Meta.ordering. | R3 | 比较 pieces[-1] 的修复方向有依据，应保留为待验证假设并给一条最小验证。 |
| 10 | I did not read get_order_by (compiler.py:271) or the full setup_joins path, so the exact minimal patch is unconfirmed. | — | 明确指出 get_order_by / setup_joins 未读完；_setup_joins 751–762 已完整收到，须区分 compiler helper 与 query 方法。 |

## sympy__sympy-18698

历史请求数：4。静态校验触发保守回退：True。

| 句号 | 原句（完整） | 规则 | 审计判定 |
|---:|---|---|---|
| 1 | The user's report is a misunderstanding of the output, not a bug in the algorithm. | R1,R3 | 表达式包装层未读，直接断言 misunderstanding / not a bug 应拦下。 |
| 2 | In sqf_list, the second element of each (factor, multiplicity) pair is the multiplicity, and the factors are grouped by multiplicity. | R3 | 文档支持二元组格式；是否对表达式输入按重数合并仍需验证，不应混为同一已知事实。 |
| 3 | For (x**2+1)*(x-1)**2*(x-2)**3*(x-3)**3 the correct square-free decomposition is indeed (1, [(x**2+1, 1), (x-1, 2), (x-2, 3), (x-3, 3)]): the two distinct cubic-multiplicity factors (x-2) and (x-3) each have multiplicity 3, so they appear as two separate entries both with exponent 3. | R3 | 对未验证的表达式输出宣称 correct，且据此认定两个同重数条目合理，证据不足。 |
| 4 | They are NOT combined into (x**2-5x+6, 3) because square-free factorization returns irreducible-ish square-free factors, not products of distinct factors sharing a multiplicity. | R3 | 对不合并的算法语义作强断言；与已读底层按 i 递增的循环不相符，包装层未读。 |
| 5 | The second example, x**5-2x**4-2x**3+4x**2+x-2 = (x-2)(x**2-1)**2, correctly yields (1, [(x-2, 1), (x**2-1, 2)]) because x**2-1 is itself square-free (it factors as (x-1)(x+1), both multiplicity 2, but sqf_list over ZZ does not split it further since x**2-1 is square-free). | R3 | 这个示例不能推出两个接口契约一致；因果解释未核验。 |
| 6 | So both outputs are consistent with the documented semantics. | R3 | both outputs consistent 是未经验证的契约结论。 |
| 7 | Evidence: dup_sqf_list (sympy/polys/sqfreetools.py:281-335) builds result by appending (g, i) for each multiplicity i, so distinct factors with the same multiplicity i are appended as separate tuples with the same exponent. | R3 | 281–335 已读全，但 333 行 i += 1 不支持“同一重数多次追加”这一推论；是误读已有证据，不只是漏读。 |
| 8 | Poly.sqf_list (sympy/polys/polytools.py:3210-3237) simply wraps this. | R1,R3 | Poly.sqf_list 3210–3237 已读全；它调用 f.rep.sqf_list，未读完整 DMP 路径，不能称简单直接包装已读低层。 |
| 9 | The docstring examples (lines 3222-3229) confirm the (factor, multiplicity) format. | R4 | 3222–3229 示例已收到，格式描述可保留，补完整文件:行号。 |
| 10 | Uncertainty: I did not inspect dup_gf_sqf_list or the exact ordering logic, but the reported behavior matches the documented contract, so no code change is warranted; the user's expectation of merging same-multiplicity factors is the inconsistency. | R1,R3 | 虽标部分未读，仍断言无需修改；遗漏 _generic_factor_list/_symbolic_factor_list 的表达式链是关键缺口。 |

## django__django-13925

历史请求数：4。静态校验触发保守回退：True。

| 句号 | 原句（完整） | 规则 | 审计判定 |
|---:|---|---|---|
| 1 | The W042 warning is emitted by Model._check_default_pk (django/db/models/base.py:1298-1320). | — | 1298–1320 完整收到，W042 检查位置及引用有支持。 |
| 2 | Its condition is simply `cls._meta.pk.auto_created and not settings.is_overridden('DEFAULT_AUTO_FIELD') and not cls._meta.app_config._is_default_auto_field_overridden`. | R4 | 1301–1303 条件有支持，应加完整文件:行号。 |
| 3 | It does not distinguish a PK that was auto-created on the model itself from one inherited/promoted from a parent, so any model whose `_meta.pk.auto_created` is True triggers the warning. | R3 | any auto_created triggers 忽略另外两个门控条件；应表述为三个条件同时成立。 |
| 4 | Where auto_created comes from: Options._prepare (django/db/models/options.py:271-287). | R3 | Options._prepare 252–287 已读全，但仅此不能穷尽 auto_created 来源，需限定范围。 |
| 5 | For a model with no explicit pk and no parents, it creates `pk_class(verbose_name='ID', primary_key=True, auto_created=True)` (line 286). | R4 | 286 行构造语句有支持，补完整文件:行号。 |
| 6 | For a child model with parents, it promotes the first parent link and sets `field.primary_key = True` (lines 272-283) without clearing auto_created, so the inherited PK keeps auto_created=True from the ancestor's auto field. | R1,R3 | 272–283 仅显示提升 parent link；未读 ModelBase 创建 parent link，不能断言继承祖先 AutoField 的 auto_created。 |
| 7 | That is why models inheriting from a base like `Entity` (whose PK is an auto-created AutoField) still report W042 even though the user never asked for a new auto PK on the child. | R3 | 承接未核验的 auto_created 来源解释，应降为待验证假设。 |
| 8 | So the report is consistent with a real bug/limitation in the 3.2 check: the check keys off `pk.auto_created` rather than whether the model itself defined the PK. | R3 | 检查条件方向有价值，但诊断仍需区分继承关系字段来源和局部字段判据。 |
| 9 | The fix would be in _check_default_pk (e.g. also require the PK to be a local field / not inherited), not in _prepare. | R3 | 可提出检查处修复的假设；local field 与 parent link 不能直接等同，也不能排除 _prepare。 |
| 10 | I could not read the W042 tests (tests/check_framework/test_model_checks.py read failed), so I cannot confirm whether a test already covers inherited PKs; that is the main uncertainty. | — | 明确报告测试读取失败符合诚实披露；缺口还应包括 ModelBase，且提供最小验证。 |
| 11 | The hint text and app-config override logic (django/apps/config.py:64-70) are unrelated to the false positive. | R1,R3,R4 | AppConfig 仅搜索片段，完整 getter 未读；64–70 并未全部由 read_file 返回，不能据此排除配置链。 |
