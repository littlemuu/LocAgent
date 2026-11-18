"""Post-unblinding manual annotations; never executes model/harness calls."""
import json
from pathlib import Path
P = Path(__file__).resolve().parents[1] / 'delivery'
old = json.loads((P/'manual-judgments.json').read_text())
packets = json.loads((P/'review-packets.json').read_text())
decisions = [
 (32,'B','是',[25,26,27,28,37,38,39],'后半段不断添加、删除同一段注释，差异在空与同一注释间交替；未推进类级skip实现。'),
 (32,'C','否',[4,5,10,12,14,17,18,19],'21次内多次修改tearDown条件并运行不同回归检查；存在功能回归，但不是无进展循环。'),
 (34,'B','是',[25,26,27,28,37,38,39],'连续在两个源码MD5之间往返，重复添加/撤销chain序列化字段，未形成完整往返序列化实现。'),
 (34,'C','是',[21,25,26,27,37,38,39],'后段反复写入相同反序列化模板，差异统计维持40增20删；未修复与新增chain结构的衔接。'),
 (35,'A','是',[33,34,35,36,37,38,39],'重复相同runtest_setup搜索并返回相同结果；无源码修改，耗尽40次请求。'),
 (35,'B','是',[14,33,34,35,36,37,38,39],'持续重复setup/teardown搜索，输出相同且没有源码修改，耗尽40次请求。'),
 (40,'C','是',[26,33,34,35,36,37,38,39],'重复打印transformer和remainder配置，remainder一直缺少输出配置；第4次后的补丁未继续修正。'),
 (41,'A','否',[8,13,18,22,26,28,31,38],'40次内持续修改选项解析、成员过滤、测试夹具和断言，并核对基线；未见持续无进展循环。'),
 (41,'B','否',[4,6,8,9,12,15,16,18],'19次内完成多处实现和测试修改，检查基线与兼容性；重复测试之间有实际变化。'),
 (41,'C','否',[4,6,11,13,15,18,23,27,29,31],'32次内持续修改过滤逻辑和测试预期并检查结果；错误实现及调整测试预期不等同于机械循环。'),
 (42,'A','否',[11,14,17,19,22,26,29,31,33],'修复tuple/subscript AST及类型注解；后段多次测试但改变测试集合/输出检查和基线，未达到明确循环判定。'),
 (42,'B','否',[5,6,7,8,9],'10次内修改object_description并核对测试和基线；没有长重复链。'),
 (42,'C','否',[12,15,18,21,23,25],'独立排查到AST，修复tuple并处理subscript兼容，26次响应截断前仍有实际修改。'),
 (43,'A','否',[5,9,10,11,12],'13次内添加HTTP状态检查、更新测试并核查基线。'),
 (43,'B','否',[2,11,12,13,15,16,17,18],'19次内加入状态检查和mock测试，验证补丁前后差异。'),
 (43,'C','否',[2,5,6,7,8,9],'10次内完成一行修复、运行测试及对照基线；未见循环。'),
 (44,'A','否',[9,19,20,23,26,29,30],'31次内修复xref上下文与refspecific，构造复现、补回归测试并对照基线。'),
 (44,'B','否',[11,12,14,16,18,19,20,23],'24次内修复上下文，逐步改进HTML结果提取并运行回归/基线；短暂重复grep后转向新解析方式。'),
 (44,'C','否',[7,8,11,12,14,18,19,20,21],'22次内修复xref、构造验证、切换测试组合并对照基线；重复测试不构成长循环。'),
 (45,'A','否',[5,6,8,9],'10次内完成Enum描述修复及测试。'),
 (45,'B','否',[3,5,6,7],'8次内完成Enum修复与测试，纠正导入位置。'),
 (45,'C','否',[3,4,5,7,8],'9次内完成Enum修复、复现和回归检查。'),
 (46,'A','否',[15,16,17,20,21,22,23,24,25,26,29,31,32],'34次请求期间跨不同类型逐步修改NotImplemented比较处理；结束于token预算，未见机械重复循环。'),
]
adoption = {
 32:('未见明确证据','定位指出应覆盖类级skip；编码自行以实例检查替代方法检查，导致函数级skip回归。定位没有要求删除原检查，不能将该遗漏归为直接采纳错误定位方案。'),
 34:('未见明确证据','定位要求完整处理异常链的序列化和反序列化；最终仅新增序列化结构，反序列化衔接未完成，属于未完整执行建议。'),
 40:('未见明确证据','定位明确要求对remainder调用_safe_set_output；编码仅移除过滤条件，未补入remainder，反复探针也显示配置缺失。'),
 41:('不确定','定位建议ALL/名单语义并提示保持无参兼容，编码采用后原有private-members测试仍失败。合并函数和测试调整由编码自行实现，现有证据不能把失败明确归因于定位建议本身。'),
 42:('未见明确证据','定位关注object_description，但编码验证后转到AST tuple/subscript实现；未持续照搬最初假设。原始日志39 passed而harness仍False，保留原评分。'),
 43:('未见明确证据','按定位在带anchor分支补raise_for_status；原始日志6 passed而harness仍False，没有明确错误方案采纳证据。'),
 44:('未见明确证据','补齐xref模块/类上下文及refspecific；原始日志33 passed而harness仍False，不能仅凭False判定定位错误。'),
 45:('未见明确证据','采用Enum专门分支并添加验证；原始日志39 passed而harness仍False，没有明确错误方案采纳证据。'),
}
for n,a,v,rs,why in decisions:
 d=dict(number=n,arm=a,no_progress_loop=v,evidence_requests=rs,reason=why)
 if a=='C': d.update(zip(['wrong_localization_adoption','adoption_evidence'],adoption[n]))
 old.append(d)
for x in packets:
 n,a=x['number'],x['arm']
 if n>=46 and a in 'BC' or n>=47 and a=='A':
  d=dict(number=n,arm=a,no_progress_loop='未运行',evidence_requests=[],reason=('定位首次请求被供应商HTTP 402拒绝，编码阶段没有启动。' if a in 'BC' else '编码首次API请求被HTTP 402拒绝，没有模型回复或工具行动；无循环可审阅。'))
  if a=='C': d.update(wrong_localization_adoption='未运行',adoption_evidence='定位未交付，编码未启动。')
  old.append(d)
assert len(old)==89 and len({(x['number'],x['arm']) for x in old})==89
assert {(x['number'],x['arm']) for x in old}=={(x['number'],x['arm']) for x in packets}
old.sort(key=lambda x:(x['number'],x['arm']))
for d in old:
 p=next(x for x in packets if (x['number'],x['arm'])==(d['number'],d['arm']))
 d.update(instance_id=p['instance_id'],coding_requests=p['coding_requests'],used_all_40=p['used_all_40'],resolved=p['resolved'],audit_path=f"failure-audit/{p['instance_id']}/{d['arm']}.json")
(P/'manual-judgments.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
print('Manually reviewed all',len(old),'unresolved episodes')
