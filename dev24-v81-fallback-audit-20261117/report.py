import collections,csv,hashlib,json,statistics
from pathlib import Path
O=Path(__file__).resolve().parent;ROOT=O.parent
cs=json.loads((O/'cases.json').read_text());vs=json.loads((O/'violations-reviewed.json').read_text());summary=json.loads((O/'summary.json').read_text())
policy=ROOT/'locator-diagnostic-calibration-v8.1/calibration/policy.py';readcode=ROOT/'locator-diagnostic-calibration-v8.1/baseline/runtime/readonly_agent/read_lines.py';toolcode=ROOT/'locator-diagnostic-calibration-v8.1/baseline/runtime/readonly_agent/openhands_tools.py';retriever=ROOT/'locator-diagnostic-calibration-v8.1/baseline/runtime/experiments/retrieval_evidence_v6/retriever.py'
def link(label,path,line=None):return f'[{label}]({path}'+(f':{line}' if line else '')+')'
def cell(s):return str(s).replace('|','\\|').replace('\n','<br>')
def ranges(rs):return '; '.join(f'{p}:{a}-{b}' for p,a,b in rs) or '无'
def quotes(v):
 q=[f"L{m['line']}：{m['text']}" for m in v['matches']]
 if v.get('structured_candidate_literal'):q.insert(0,'entities 候选：'+v['structured_candidate_literal'])
 return '\n'.join(q) or '此项由 pending 元数据触发，不是某段强断言原文'
def coverage(v):
 if v['rule']=='R1' and not v['basis'].get('entity'):return '相关文件账本：'+ranges(v['all_credited_ranges'])
 s='校验器按字面路径记账：'+ranges(v['credited_ranges_for_path'])
 if v['canonical_credited_ranges']!=v['credited_ranges_for_path']:s+='；按唯一后缀候选对应：'+ranges(v['canonical_credited_ranges'])
 if v.get('function_span'):s+='；该函数def区间内实际读到：'+str(v['entity_read_intersection'])
 elif v['rule']=='R1':s+='；完整实体边界未留存，不把整文件范围当函数覆盖'
 if v['search_hit_evidence']:s+='；另有实际搜索行：'+','.join(str(x['line']) for x in v['search_hit_evidence'])
 return s
# Verify plain text is an exact extraction of original provider finish data.
index=[]
for c in cs:
 matches=[]
 for name in c['raw_finish_wire_paths']:
  raw=json.loads(Path(name).read_text())
  for choice in raw['choices']:
   for call in choice['message'].get('tool_calls',[]):
    if call['function']['name']=='finish':
     args=json.loads(call['function']['arguments']);p=args.get('message');p=json.loads(p) if isinstance(p,str) else p
     if p==c['raw_packet']:matches.append(name)
 assert matches,c['instance_id']
 assert Path(c['raw_answer_path']).read_text()==c['raw_packet']['answer']+'\n'
 index.append(dict(order=c['index'],instance_id=c['instance_id'],original_status='回退' if c['fallback'] else '合规',raw_answer_exact_text=c['raw_answer_path'],original_provider_finish=';'.join(matches),original_diagnostic_audit=c['raw_audit_path'],audit_report=str(O/'cases'/c['instance_id']/'audit.md')))
with (O/'answer-paths.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
columns=['id','instance_id','rule','recorded_violation','classification','subtype','original_excerpt','matching_basis','actual_C_read_ranges','reason','raw_answer_path','original_audit_path']
with (O/'violations.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
 for v in vs:w.writerow(dict(id=v['id'],instance_id=v['instance_id'],rule=v['rule'],recorded_violation=v['recorded_violation'],classification=v['classification'],subtype=v['subtype'],original_excerpt=quotes(v),matching_basis=json.dumps(v['basis'],ensure_ascii=False),actual_C_read_ranges=coverage(v),reason=v['reason'],raw_answer_path=v['raw_answer_path'],original_audit_path=v['raw_audit_path']))
# Full 55-record table: literal excerpts and evidence, not just a case-level label.
lines=['# 逐条违规审计（55条）','','标签是按原文语义与已交付证据的审计结论；不声称所有误判都属于代码执行偏离规格。尤其 R3 正则按设计会拒绝“根因是/在”，但本报告把明确“待验证假设”限定下的两句判为语义误判。原文路径、匹配正则、搜索行和读取元数据完整保存在 violations-reviewed.json。','',
 '| ID / 题目 | 触发规则及匹配依据 | 原回答原文片段 | C 实际读取/交付证据 | 分类与理由 |', '|---|---|---|---|---|']
for v in vs:
 basis=v['recorded_violation']
 if v['rule']=='R3':basis+='；正则命中：'+','.join(m for item in v['matches'] for m in item.get('matches',[]))
 lines.append('| '+' | '.join([link(v['id'],O/'cases'/v['instance_id']/'audit.md')+' '+v['instance_id'],cell(basis),cell(quotes(v)),cell(coverage(v)),cell(v['classification']+'；'+v['reason'])])+' |')
(O/'violations.md').write_text('\n'.join(lines)+'\n')
for c in cs:
 casevs=[v for v in vs if v['instance_id']==c['instance_id']];counts=collections.Counter(v['classification'] for v in casevs)
 lines=[f'# {c["instance_id"]}', '',f"原结果：{'回退' if c['fallback'] else '合规'}；实际源码计量 {c['source_bytes']}/14336，余 {14336-c['source_bytes']} 字节；请求 {c['requests']} 次。",'',
  link('原回答原文（原始provider内容精确提取）',Path(c['raw_answer_path']))+'；'+link('原始诊断审计',Path(c['raw_audit_path']))+'；'+'、'.join(link('原始provider响应',Path(x)) for x in c['raw_finish_wire_paths']),
  '',link('C全部实际工具输出',O/'cases'/c['instance_id']/'tool-output.txt'),'', 'C完整行账本：'+ranges(c['ranges']), '', '注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。']
 for v in casevs:
  lines += ['',f"## {v['id']} {v['recorded_violation']}",'',f"**{v['classification']}：{v['subtype']}**。{v['reason']}",'','原回答片段：','```text',quotes(v),'```','', '校验器匹配依据：','```json',json.dumps(v['basis'],ensure_ascii=False,indent=2),'```','',coverage(v),'', 'C read_file 请求和实际返回：','```json',json.dumps(v['read_file_observations'],ensure_ascii=False,indent=2),'```']
  if v['search_hit_evidence']:lines+=['','实际搜索原文（仅作已交付片段，不自动认定函数完整）：','```json',json.dumps(v['search_hit_evidence'],ensure_ascii=False,indent=2),'```']
  if v['unread_context']:lines+=['','原答中的未读/未核验相关上下文：','```text','\n'.join(f"L{x['line']}: {x['text']}" for x in v['unread_context']),'```']
  if v['rule']=='R1':lines+=['', '函数长度：'+json.dumps(v.get('function_span') or v.get('possible_referent_span') or v['function_length_status'],ensure_ascii=False),'','预算归因：'+v['budget_assessment']]
 if not casevs:lines+=['','原校验器未记录违规。本轮未另行对合规题做漏判审计，不把“合规”当作诊断正确。']
 (O/'cases'/c['instance_id']/'audit.md').write_text('\n'.join(lines)+'\n')
# R1 table and case-level budget ledger.
r1=[v for v in vs if v['rule']=='R1']
with (O/'R1-lengths.csv').open('w') as f:
 cols=['id','instance_id','entity','definition_start','definition_end','definition_length','status','provenance','source_bytes','budget_assessment']
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for v in r1:
  span=v.get('function_span') or {};w.writerow(dict(id=v['id'],instance_id=v['instance_id'],entity=v['basis'].get('entity','分页规则'),definition_start=span.get('start','未知/不适用'),definition_end=span.get('end','未知/不适用'),definition_length=span.get('length','未知/不适用'),status=v['function_length_status'],provenance=span.get('provenance','详见逐条记录'),source_bytes=v['source_bytes'],budget_assessment=v['budget_assessment']))
budgetrows=[]
for c in cs:
 if not any(v['instance_id']==c['instance_id'] for v in r1):continue
 timeline=[];prev=0
 for ti,t in enumerate(c['tool_audit'],1):
  after=t['source_bytes'];timeline.append(dict(tool_index=ti,tool=t['tool'],capacity_before=min(4096,14336-prev),charged_bytes=after-prev,cumulative=after,error=t['result'].get('error'),next_cursor=t['result'].get('next_cursor'),requested=t['arguments'],returned_start=t['result'].get('start_line'),returned_end=t['result'].get('end_line')));prev=after
 budgetrows.append(dict(instance_id=c['instance_id'],source_bytes=c['source_bytes'],remaining=14336-c['source_bytes'],global_cap_closed=14336-c['source_bytes']<64,requests=c['requests'],pending_count=len(c['pending']),timeline=timeline))
(O/'R1-budget.json').write_text(json.dumps(budgetrows,ensure_ascii=False,indent=2)+'\n')
with (O/'R1-budget.csv').open('w') as f:
 cols=['instance_id','source_bytes','remaining','global_cap_closed','requests','pending_count'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r[k] for k in cols} for r in budgetrows)
# Main report starts with rule definitions as requested.
report=['# dev24 C(v8.1) 回退离线审计','','## 规则定义与判定代码','',
 '| 规则 | 冻结 v8.1 的实际判定 | 代码位置 |', '|---|---|---|',
 f'| R1 | entities 列表及全文 path.py:QualifiedName 的并集；complete_entity=False 且无同一行完整ID+“未读完”即报错。另：pending 非空时，未核验段必须同时含“未读完”和“分页”。完整实体覆盖包括装饰器、def、docstring与全部正文；无AST实体也返回False。 | {link("实体/分页判定",policy,189)}；{link("AST范围",policy,63)}；{link("覆盖判断",policy,122)} |',
 f'| R2 | 首行必须是首标题；三标题固定、顺序正确、无重复，各段非空。 | {link("标题解析",policy,171)}；{link("非空检查",policy,181)} |',
 f'| R3 | 全文 STRONG 正则匹配即报强断言；推断每个非空行去除项目符号后须以“待验证假设：”开头；未核验段须有“最小验证：`…`”。 | {link("正则",policy,31)}；{link("强断言",policy,184)}；{link("格式/命令",policy,205)} |',
 f'| R4 | 全文所有 .py:数字范围都需完整落入覆盖账本；事实段每个非空行需有引用（除固定“尚无…”句）。范围是逐行全部覆盖，不允许跨缺口。 | {link("引用正则",policy,37)}；{link("全文检查",policy,186)}；{link("事实行",policy,202)} |','',
 f'覆盖账本仅接收 read_file 与可还原的检索预览字符，**不接收 search_text**（{link("observe",policy,83)}）。检索器给的def起点不含装饰器（{link("预览范围",retriever,150)}），而校验器取最早装饰器行；这个口径差异必须单独说明。',
 '', '## 审计口径与边界','',
 '本次只读本地日志与代码，输出新审计文件；不开机、不联网、不调用API、不重跑定位器，不修改v8.1或历史冻结件，不访问holdout 50。当前binding仍为 `9def7a0000b202dc8f7127ef6424b596c1155015bc7d248e74203512b02f7cee`。',
 '共审阅20个回退题的55条已记录违规。分类依据是证据与表达语义：真违规=可独立确认的缺口/不当事实陈述且未适当披露；误判=证据或明确限定语足以排除这条指控；边界=字面格式契约与语义冲突、实体身份不确定或原AST范围缺失。属于逐条语义审阅+规则辅助提取，不是外部专家人工复核。',
 '“误判”不表示代码未按既定正则执行。例如R3两条执行符合现有词法规则及旧测试，但忽略了整句的“待验证假设”限定。若坚持禁止短语本身，则应把它们视为边界，见敏感性结果。basename缩写、稀疏搜索连成连续范围等明确格式契约问题，本报告保守归边界。',
 '为核实少数函数终点，只读取了本地历史B定位日志，逐题核验base_commit与本次相同；未读B编码/harness结果，未把B的阅读算给C。参考来源见 '+link('reference-provenance.json',O/'reference-provenance.json')+'。没有完整源快照/AST span的项目保留未知。',
 '本报告只裁定既有55条触发，不保证原答案没有其他诊断错误，也不对4道合规题做漏判审计。回退率估计仅对这批触发做离线扣除，不生成新的运行成绩。',
 '', '## 三类汇总','', '| 规则 | 真违规 | 误判 | 边界 | 合计 |', '|---|---:|---:|---:|---:|']
for rule,counts in summary['counts'].items():report.append(f"| {rule} | {counts['真违规']} | {counts['误判']} | {counts['边界']} | {sum(counts.values())} |")
report+=['| 合计 | 7 | 31 | 17 | 55 |','',
 '**仅去掉31条确定误判、保留全部边界阻断：20/24（83.33%）→14/24（58.33%），下降25个百分点。** 并非31条误判对应31题；一个题只要还剩真违规或边界，就继续回退。',
 '可解除回退的6题：'+', '.join(summary['estimated_after_removing_confirmed_false_positives']['released'])+'。',
 '敏感性：若R3仍坚持词面禁用“根因是/在”，则仅修其余误判后为15/24（62.5%）。若连全部边界也放行，才会降到6/24（25%）；这是乐观政策下界，不是本报告建议或“只修误判”的结果。',
 '', '## 逐题违规表','',
 '每题详细页包含原文逐条摘录、正则/实体/行号依据、实际read_file返回范围、搜索片段和分类理由。全部55条另见 '+link('逐条违规表',O/'violations.md')+' / '+link('CSV',O/'violations.csv')+' / '+link('完整结构化证据',O/'violations-reviewed.json')+'。','',
 '| 题目 | 真违规 | 误判 | 边界 | 只去误判后 |', '|---|---:|---:|---:|---|']
for c in cs:
 if not c['fallback']:continue
 casevs=[v for v in vs if v['instance_id']==c['instance_id']];co=collections.Counter(v['classification'] for v in casevs)
 report.append('| '+link(c['instance_id'],O/'cases'/c['instance_id']/'audit.md')+f" | {co['真违规']} | {co['误判']} | {co['边界']} | "+('继续回退' if co['真违规']+co['边界'] else '解除回退')+' |')
report += ['', '## R1：函数长度与预算归因','',
 '25条R1中，23条是实体检查、2条是分页标注；其中 requests/compat.py:builtin_str 是别名赋值，不能当作函数长度。余22个函数样式ID，能核实精确ID的def到末行范围仅6个；另1个可对应的方法定义有60行，但Figure/FigureBase限定名未确认；其余15个没有可靠完整长度。所有未知均未用请求终点或文件总行数冒充函数终点。',
 '长度以def起始至AST末行计，含docstring、不含装饰器，区别于校验器的带装饰器范围。6个可核实长度为 **15、38、39、51、56、96行**；最小15，中位数45，最大96；1–50行3个，51–100行3个。样本不是随机抽样，不能据此判断全部R1函数都短，也不能给22项总体中位数。',
 '| ID | 函数 | def范围 | 行数 | C该区间实际已读 | 长度来源 |','|---|---|---|---:|---|---|']
for v in r1:
 if not v.get('function_span'):continue
 sp=v['function_span'];report.append(f"| {v['id']} | {cell(v['basis']['entity'])} | {sp['start']}-{sp['end']} | {sp['length']} | {v['entity_read_intersection']} | {sp['provenance']} |")
report += ['',link('全部25条R1长度与未知项',O/'R1-lengths.csv')+'；'+link('17题预算表',O/'R1-budget.csv')+'；'+link('逐工具预算时间线',O/'R1-budget.json')+'。','',
 f'总预算并不等于纯Python正文长度：计量的是工具结果JSON编码字节，包括搜索、列表、元数据等；单页另有4096字节上限（{link("工具记账与关闭",toolcode,55)}）。next_cursor出现本身只表示分页，不能推出14336总预算用尽。',
 '| R1题中总预算触顶者 | 消耗/14336 | 剩余 | 对R1的判断 |','|---|---:|---:|---|',
 '| sympy-21379 | 14325 | 11 | 调查已关闭；但被拦实体涉及模块/别名，不能直接认定该R1由字节截断造成。 |',
 '| pylint-7080 | 14285 | 51 | 总预算限制继续补读715-759缺口；_iterate_file_descrs头部未读有此限制贡献。分页标注报错另属词面误判。 |',
 '| matplotlib-25332 | 14311 | 25 | align_ylabels续页确因剩余总容量截断；align_xlabels所指正文已读完，其报错主要是限定名边界。 |','',
 '17道R1题仅这3道触顶（对应5条R1记录），其余14道未耗尽总字节预算。可直接指出总字节上限限制实体缺口的有07-02、19-02两条，但预算不是其所有问题的唯一原因。',
 '其它机制：django-13033、sphinx-8595、sphinx-8721 的续读改变了原cursor绑定行范围，触发ValueError，不能归为总源码预算耗尽；sympy-18698的后续搜索实际被candidate_body_read_priority阻止，虽然原答称“预算拦截”，总消耗仅3195字节。',
 f"独立核对了20题中{summary['read_line_accounting']['read_file_calls_checked']}次成功read_file、{summary['read_line_accounting']['complete_display_lines_checked']}个完整显示行：没有发现这部分完整行未被账本计入。该核对不能替代缺失的全源码/AST边界核验，也不涵盖所有搜索截断片段。",'',
 '## 24道原回答路径','',
 '原回答txt是provider finish内容的精确提取，已逐题与原始响应核对；原始provider JSON和diagnostic-audit也保留链接。完整机器可读索引：'+link('answer-paths.csv',O/'answer-paths.csv')+'。']
for status in ['合规','回退']:
 report+=['',f'### {status}题（{sum(x["original_status"]==status for x in index)}道）','','| 题目 | 原回答精确提取txt | 原始provider响应 | 原始审计JSON |','|---|---|---|---|']
 for row in index:
  if row['original_status']!=status:continue
  report.append('| '+row['instance_id']+' | '+link('原回答',Path(row['raw_answer_exact_text']))+' | '+'、'.join(link(Path(x).name,Path(x)) for x in row['original_provider_finish'].split(';'))+' | '+link('raw_packet.answer',Path(row['original_diagnostic_audit']))+' |')
report += ['', '## 建议（本轮不实施）','',
 '1. **先修校验器的确定误判，再独立冻结新版本。** R4应区分事实证据、未读声明、验证目标；搜索片段可以支持其明确显示的窄事实，但不能升级为完整函数或连续范围。R1建议用结构化unread_entities/未续读cursor字段，支持明确上下文映射，绝不恢复全文裸名称扫描。变量别名、未知ID、继承方法与正文不完整应分开编码。R3应识别假设/否定/引用作用域，不以“根因是”字串单独决定。',
 '2. **先澄清边界，再考虑局部回退。** 对装饰器、完整相对路径、稀疏搜索范围制定明确口径；记录每个实体的def起点、装饰器起点、终点、缺失行和匹配失败原因。局部回退应删除不受支持的事实/推断，并级联处理依赖它们的结论；不能简单只删触发词或对未证明的内容一律加“可能”。解析失败或依赖关系无法拆开时仍保留固定全回退。',
 '3. **“只给位置”适合作为独立消融组，不宜把本轮C直接这样命名。** 本轮20题为固定回退、4题仍带具体诊断，是混合策略。若后续要比较纯位置组，应独立定义24题统一只传候选位置，不能把这种信息删减称为定位诊断质量提升。当前只有定位预检，没有Coding Agent/harness结果，无法判断局部回退或全回退谁的resolved更高。',
 '', '所有建议未修改、未运行。requests-2317证书问题和历史评分没有重评。dev24只作开发参考，不下最终效果结论。']
(O/'REPORT_ZH.md').write_text('\n'.join(report)+'\n')
print('Wrote report, 55-record table, 24 case pages, answer index, R1 length/budget evidence.')
