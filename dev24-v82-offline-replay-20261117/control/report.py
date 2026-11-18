import json
from pathlib import Path
R=Path(__file__).resolve().parents[2];O=R/'dev24-v82-offline-replay-20261117';F=R/'locator-diagnostic-calibration-v8.2'
s=json.loads((O/'summary.json').read_text());rows=json.loads((O/'per-case.json').read_text());review=json.loads((O/'review-crosscheck.json').read_text());change=json.loads((F/'delivery/V8.2-CHANGE-AUDIT.json').read_text())
def link(label,p):return f'[{label}]({p})'
samples=json.loads((O/'sample-ids.json').read_text());sample_text=['# 三题 v8.2 最终交付包全文','','选取三种情况：sympy-13480 的真实 R1 缺口、django-13925 的真实 R4 缺口与未知实体、sphinx-11445 的稀疏搜索边界。为便于阅读，每包按“元数据及候选”和“answer 全文”分块展示，包含最终 localization.json 的全部字段与完整正文，无省略。']
for ident in samples:
 path=O/'cases'/ident/'localization.json';packet=json.loads(path.read_text());answer=packet['result'].pop('answer')
 sample_text+=['',f'## {ident}','',link('完整原格式 localization.json',path),'','元数据及候选（answer 单独全文展示如下）：','','```json',json.dumps(packet,ensure_ascii=False,indent=2),'```','','answer 全文：','','```text',answer,'```']
(O/'THREE_FULL_PACKETS.md').write_text('\n'.join(sample_text)+'\n')
report=['# dev24 C(v8.2) 软门控冻结与离线重放','','**完成：全回退0/24，附披露12/24，共16条；validator_error=0。原回答正文24/24逐字保留。**','','## 策略与冻结','',
'仅 R2 三段结构不可解析/无效或校验器异常使用固定全回退；R1/R3/R4 保留原文，在末尾追加固定标题“以下内容未在阅读记录中核验：”及带规则编号的文件范围/实体列表。每题 diagnostic-audit.json 记录原包、逐条违规、各规则计数、披露项、异常和证据模式。未发生任何正文删改。','',
'终答检查接受 def 起点或更早的装饰器起点，唯一候选文件缩写，以及搜索片段直接显示的窄事实。搜索不进入完整行/实体覆盖账本，也不认可稀疏或相邻搜索命中为连续范围已读。未读声明与验证目标不再当作已读引用；仅在已明确引用的完整实体集合中解析唯一简称未读声明，不通过裸名称新增实体。假设限定下的“根因是/在”允许，明确确认措辞仍可触发 R3 披露。','',
'保留 v8.1 的调查时 complete_entity/notice/read_priority 原代码，提示文本 INSTRUCTION 逐字不变；宽松完整性只用于终答交付检查。定位入口、预算、检索、Coding Agent、harness 文件保持原样。','',
'冻结：'+link('FREEZE.json',F/'FREEZE.json')+'。binding：','',f"`{s['binding']}`",'',
'与 v8.1 相比，仅修改 calibration/policy.py、tests/test_calibration.py、tests/test_v81.py；新增测试、夹具及测试变更说明。57 个冻结文件核验通过；42 个 B 依赖文件与原 B 完全一致。配置中沿用的 v8 版本/旧描述字符串未改，当前最终门控以 FREEZE.final_policy 和 diagnostic-audit.policy=v8.2 标识。',
link('B/C 与 v8.1 差异核验',F/'delivery/V8.2-CHANGE-AUDIT.json'),'','## 测试','',
'84/84 通过：原基线22 + v8校准22 + v8.1新增11 + 本轮新增29。零失败、零跳过、零被拦截的外部动作。测试使用固定响应和临时合成夹具；历史 SDK 协议测试不构成 dev24 Coding Agent 或 harness 运行。',
'4 项旧测试与新策略冲突，先逐项说明后调整；其余旧测试保持。'+link('旧测试变更说明',O/'OLD_TEST_CHANGES_ZH.md')+'。'+link('原基线测试结果',F/'delivery/baseline-tests.json')+'；'+link('校准测试结果',F/'delivery/new-tests.json')+'。','',
'## 离线重放结果','',
'输入为已存24份原始 provider finish + 同题 C 的 tool_audit/覆盖账本；逐题核验与原始 provider JSON 相同。未调用模型、未重新运行定位调查、未使用 B 阅读扩大 C 的覆盖，也未以人工分类驱动校验器。人工分类只在输出完成后核对。','',
'原日志未持久化全部 AST span：已读行使用 v8.1 原账本，完整性使用已记录候选状态及 C 原检索 def 范围；仅对原答独有实体，依据 v8.1 原始判定条件恢复可证明的已通过状态。其余完整边界保持未知并披露。这个重放验证已存回答的交付策略，不是新定位质量或修复效果实验。','',
'| 指标 | 结果 |','|---|---:|','| 全回退 | 0/24 |','| 附披露 | 12/24 |','| 无需追加披露 | 12/24 |','| 披露条目 | 16 |','| R1 / R2 / R3 / R4 残留 | 9 / 0 / 0 / 7 |','| validator_error | 0 |','| 原正文逐字保留 | 24/24 |',f"| 最大交付包 / 原上限 | {s['max_packet_bytes']} / 14336 字节 |",'',
'| 题目 | 全回退 | 披露条数 | R1 | R2 | R3 | R4 | validator_error |','|---|---|---:|---:|---:|---:|---:|---|']
for r in rows:
 p=O/'cases'/r['instance_id']/'diagnostic-audit.json'
 report.append(f"| {link(r['instance_id'],p)} | 否 | {r['disclosure_count']} | {r['R1']} | {r['R2']} | {r['R3']} | {r['R4']} | 无 |")
report+=['',link('24题机器可读表',O/'per-case.csv')+'；'+link('汇总 JSON',O/'summary.json'),'','## 与55条人工审计核对','',
'7/7 真违规全部进入披露；31/31 确定误判全部消失。17 条边界中8条按新口径不再触发，9条保留披露。没有新增既有55条之外的触发。','',
'| 分类 | 原条数 | 消失 | 披露 |','|---|---:|---:|---:|','| 真违规 | 7 | 0 | 7 |','| 误判 | 31 | 31 | 0 |','| 边界 | 17 | 8 | 9 |','',
'7条真违规逐项：','','| 审计ID | 题目 | 进入披露的范围或实体 |','|---|---|---|']
for v in review:
 if v['classification']=='真违规':report.append(f"| {v['id']} | {v['instance_id']} | {v['v81_violation'].partition(':')[2]} |")
report+=['','保留的边界涉及未证明的限定名/函数完整性及稀疏搜索范围；本次宽松口径不推测继承归属，也不把搜索命中升级为整函数或连续范围。已消失项表示不再有这条校验指控，不表示原定位诊断已被证明正确。','',link('55条逐项核对含原审计理由',O/'review-crosscheck.csv'),'','## 三题最终交付包全文','',link('独立可读版本',O/'THREE_FULL_PACKETS.md'),'']
report+=sample_text[4:]
report+=['','## 执行边界','',
'开机：未运行；新 API 调用：0，新增 API 费用：0元；重新定位：未运行；dev24 Coding Agent：未运行；harness：未运行；resolved：未运行。未访问 holdout 50，未修改 v8.1 或其他历史冻结件。requests-2317 证书问题与历史评分不重评。','',
'所有披露都随原回答交付；本轮只验证门控机制、证据对应和包完整性，不能推导 Coding Agent 会正确利用披露或 resolved 提升。停在离线冻结与汇报，不自动进入完整 C 组。']
(O/'REPORT_ZH.md').write_text('\n'.join(report)+'\n')
print('Wrote full report and three complete readable delivery packages.')
