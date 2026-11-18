"""Static audit of exactly ten named historical files; no execution of their text."""
import hashlib,json,re,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calibration.policy import EvidenceLedger,STRONG,calibrate
SOURCE=Path('/Users/xiaomu/Documents/Codex/2026-11-16/locagent-users-xiaomu-documents-codex-2026-2/outputs/discordant-review-v1')
# Each annotation corresponds to one original sentence, preserved verbatim below.
NOTES={
'astropy__astropy-12907':[
('R3','关键调用链未读全，直接定性 genuine bug 应降为假设。'),
('R3','_coord_matrix 已读全，但 _separable 未读完；完整读某个 helper 不能确认它是根因。'),
('R1,R3','未读到 304–309 的递归分发，不能断言嵌套 CompoundModel 在实际调用路径直接进入该 helper。'),
('R4','202 行确实已读，但只说 checks model.separable 忽略 189–201 Mapping 分支；且须写完整路径。'),
('R3,R4','209–215 已读，条件分支描述可保留为源码事实；实际嵌套输入会走此分支尚未核验。'),
('R3','把局部矩阵构造推成嵌套对象错误机制，缺少调用链证据。'),
('R3','把观察到的全 True 子块归因于对角构造，无验证；245 行右矩阵分支已返回却未考虑。'),
('R3','扁平组合路径未经完整分发核验，不能用此断言排除其他分支。'),
('R1,R3','提出对 _coord_matrix 递归的修复假设可以，但必须标明调用链缺口并附最小验证，不能承接确定根因。'),
('—','明确承认 _separable/_cdot 未读完值得保留；但只把不确定性限定在 | 操作不足以支持前文 & 的强断言。')],
'django__django-13964':[
('R3','__set__ 正文已读全；保存链未读完，不能把赋值阶段确认为根因。'),
('R4','256–257 的赋值循环有实际源码支持；应补全文件:行号并放在事实段。'),
('R3','CharField 默认值及保存表现没有在定位阶段行为验证，应作为由题面与代码推得的假设。'),
('R1,R3','never refreshed 涉及未读的保存函数；不能据此断言保存路径不刷新。'),
('R1,R3,R4','261 缓存写入有支持；__get__ 未完整读取，把其行为接入因果链需标注缺口。'),
('R3','工作示例因果解释未执行验证，应放入推断。'),
('R1,R4','只搜索到 _prepare_related_fields_for_save 定义 911 行；likely 的措辞合适，但定义命中不能支持其正文行为。'),
('R1','读取到 660 的 if field.primary_key，后续分支正文未读完；注释不是完整实现证据。'),
('—','已主动标注两个未读完函数；保留此不确定性，但仍需最小验证并改写首句强断言。')],
'django__django-13033':[
('R3','关键调用链未读全，定性应降为待验证假设，即使历史 B 最后修复成功。'),
('R3','find_ordering_name 715–749 已读全，但不能据此确认完整根因。'),
('R4','730 行条件确实收到；需补完整文件:行号，放事实段。'),
('R3','name 与 attname 比较是有源码支持的有效假设；字段解析来自未读全的 query.setup_joins，应标条件。'),
('R3','额外 join 与排序方向解释需行为验证，不能作为已核验事实。'),
('R4','get_order_dir 2302–2313 已读全，可支持方向转换；query.py 缺完整路径，具体 ASC 因果仍属推断。'),
('R3','关联字段解析链未读全；针对不同 lookup 的解释应写为假设。'),
('R1,R3','annotation 排序入口 get_order_by 未读，绕过分支机制未核验。'),
('R3','比较 pieces[-1] 的修复方向有依据，应保留为待验证假设并给一条最小验证。'),
('—','明确指出 get_order_by / setup_joins 未读完；_setup_joins 751–762 已完整收到，须区分 compiler helper 与 query 方法。')],
'sympy__sympy-18698':[
('R1,R3','表达式包装层未读，直接断言 misunderstanding / not a bug 应拦下。'),
('R3','文档支持二元组格式；是否对表达式输入按重数合并仍需验证，不应混为同一已知事实。'),
('R3','对未验证的表达式输出宣称 correct，且据此认定两个同重数条目合理，证据不足。'),
('R3','对不合并的算法语义作强断言；与已读底层按 i 递增的循环不相符，包装层未读。'),
('R3','这个示例不能推出两个接口契约一致；因果解释未核验。'),
('R3','both outputs consistent 是未经验证的契约结论。'),
('R3','281–335 已读全，但 333 行 i += 1 不支持“同一重数多次追加”这一推论；是误读已有证据，不只是漏读。'),
('R1,R3','Poly.sqf_list 3210–3237 已读全；它调用 f.rep.sqf_list，未读完整 DMP 路径，不能称简单直接包装已读低层。'),
('R4','3222–3229 示例已收到，格式描述可保留，补完整文件:行号。'),
('R1,R3','虽标部分未读，仍断言无需修改；遗漏 _generic_factor_list/_symbolic_factor_list 的表达式链是关键缺口。')],
'django__django-13925':[
('—','1298–1320 完整收到，W042 检查位置及引用有支持。'),
('R4','1301–1303 条件有支持，应加完整文件:行号。'),
('R3','any auto_created triggers 忽略另外两个门控条件；应表述为三个条件同时成立。'),
('R3','Options._prepare 252–287 已读全，但仅此不能穷尽 auto_created 来源，需限定范围。'),
('R4','286 行构造语句有支持，补完整文件:行号。'),
('R1,R3','272–283 仅显示提升 parent link；未读 ModelBase 创建 parent link，不能断言继承祖先 AutoField 的 auto_created。'),
('R3','承接未核验的 auto_created 来源解释，应降为待验证假设。'),
('R3','检查条件方向有价值，但诊断仍需区分继承关系字段来源和局部字段判据。'),
('R3','可提出检查处修复的假设；local field 与 parent link 不能直接等同，也不能排除 _prepare。'),
('—','明确报告测试读取失败符合诚实披露；缺口还应包括 ModelBase，且提供最小验证。'),
('R1,R3,R4','AppConfig 仅搜索片段，完整 getter 未读；64–70 并未全部由 read_file 返回，不能据此排除配置链。')]
}
# Exact function spans established by the delivered function definitions and following definitions.
KNOWN={
'astropy__astropy-12907':{'astropy/modeling/separable.py:_coord_matrix':[(171,216)],'astropy/modeling/separable.py:_cstack':[(219,247)]},
'django__django-13964':{'django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__set__':[(203,267)]},
'django__django-13033':{'django/db/models/sql/compiler.py:SQLCompiler.find_ordering_name':[(715,749)],'django/db/models/sql/compiler.py:SQLCompiler._setup_joins':[(751,762)],'django/db/models/sql/query.py:get_order_dir':[(2302,2313)]},
'sympy__sympy-18698':{'sympy/polys/sqfreetools.py:dup_sqf_list':[(281,335)],'sympy/polys/polytools.py:Poly.sqf_list':[(3210,3237)]},
'django__django-13925':{'django/db/models/base.py:Model._check_default_pk':[(1298,1320)],'django/db/models/options.py:Options._prepare':[(252,287)],'django/db/models/options.py:Options._get_default_pk_class':[(221,250)]}
}

def run():
    hashes=json.loads((SOURCE/'SHA256SUMS.json').read_text());reports=[];checks={}
    md=['# 五题旧定位终答逐句静态审计','',
        '这是对历史 B 终答及当时实际收到源码的规则审计，不是真实 v8 定位效果。原句完整保留；没有执行日志里的命令，也没有使用参考补丁。',
        '', '规则：R1 函数体/关键链读全或明确未读完；R2 事实—推断—未核验点三段；R3 未核验只能假设、不得强断言、须有最小验证；R4 事实附完整文件:行号且引用实际收到。',
        '', '五题共同的整包违规：R2 无指定三段结构；R3 无一条明确的最小验证命令或断言。表中“—”只表示该句无新增实质违规，并非整包通过。']
    for identifier,notes in NOTES.items():
        loaded={}
        for filename in ['localization.json','locator-evidence.json']:
            rel=f'evidence/{identifier}/{filename}';data=(SOURCE/rel).read_bytes()
            checks[rel]=hashlib.sha256(data).hexdigest();assert checks[rel]==hashes[rel]
            dest=ROOT/'delivery/historical-inputs'/identifier/filename;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            loaded[filename]=json.loads(data)
        packet=loaded['localization.json']['result'];evidence=loaded['locator-evidence.json']['evidence']
        # Reconstruct only delivered read-file characters. Missing lines have an
        # explicit sentinel, never invented source. Do not infer ASTs from fragments.
        source_lines={}
        for item in evidence:
            r=item['result'];path=item['arguments'].get('path')
            if item['name']!='read_file' or 'error' in r:continue
            lines=source_lines.setdefault(path,['UNREAD_SENTINEL']*r['total_lines'])
            for row in r['text'].split('\n'):
                m=re.fullmatch(r'(\d+): (.*)',row)
                if m:lines[int(m[1])-1]=m[2]
        ledger=EvidenceLedger(SimpleNamespace(files={}))
        ledger.lines=source_lines;ledger.spans=KNOWN[identifier]
        for item in evidence:ledger.observe(item)
        calibrated,audit=calibrate(packet,ledger)
        # Lexical interception must independently catch the two requested cases,
        # not merely reject them because their old answer has no new headings.
        if identifier in ['astropy__astropy-12907','sympy__sympy-18698']:
            assert STRONG.search(packet['answer'])
            assert 'R3_unverified_strong_claim' in audit['violations']
        sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',packet['answer'])
        assert len(sentences)==len(notes),(identifier,len(sentences),len(notes))
        rows=[dict(number=i,sentence=s,rules=rules,judgment=note) for i,(s,(rules,note)) in enumerate(zip(sentences,notes),1)]
        assert re.sub(r'\s+',' ',packet['answer'])==re.sub(r'\s+',' ',' '.join(x['sentence'] for x in rows))
        read_ranges=[dict(path=x['arguments']['path'],requested=[x['arguments'].get('start_line'),x['arguments'].get('end_line')],returned=[x['result'].get('start_line'),x['result'].get('end_line')],next_cursor=x['result'].get('next_cursor'),error=x['result'].get('error')) for x in evidence if x['name']=='read_file']
        entry=dict(instance_id=identifier,old_requests=loaded['locator-evidence.json']['summary']['requests'],sentences=rows,read_ranges=read_ranges,global_rules=['R2','R3_missing_minimal_validation'],replay=audit)
        reports.append(entry)
        (ROOT/'delivery'/f'{identifier}-STATIC-REPLAY.json').write_text(json.dumps(dict(execution_mode='static-old-answer-calibration-NOT-live-v8',quality_measured=False,packet=calibrated,audit=audit),ensure_ascii=False,indent=2)+'\n')
        md+=['',f'## {identifier}','',f'历史请求数：{entry["old_requests"]}。静态校验触发保守回退：{audit["fallback"]}。','', '| 句号 | 原句（完整） | 规则 | 审计判定 |','|---:|---|---|---|']
        for row in rows:
            esc=lambda s:s.replace('|','\\|').replace('\n','<br>')
            md.append(f'| {row["number"]} | {esc(row["sentence"])} | {row["rules"]} | {esc(row["judgment"])} |')
    result=dict(mode='static-historical-audit-only',new_api_calls=0,live_v8_run=False,source_hashes=checks,reports=reports)
    (ROOT/'delivery/old-answer-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'delivery/OLD_ANSWER_AUDIT_ZH.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({'cases':len(reports),'sentences':sum(len(x['sentences']) for x in reports),'verified_input_hashes':len(checks),'requested_strong_claims_intercepted':True}))

if __name__=='__main__':run()
