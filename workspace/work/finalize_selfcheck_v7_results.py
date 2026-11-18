import csv,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from experiments.eval_preflight.scoring import ranked_metrics
ROOT=Path.cwd();LIVE=ROOT/'verification/sdk-finish-selfcheck-v7-live'
OUT=Path('/Users/xiaomu/Documents/Codex/2026-11-16/locagent-users-xiaomu-documents-codex-2026-2/outputs')
OUT.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):
 with p.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
a=read(LIVE/'analysis.json');f=read(LIVE/'finish-audit/audit.json');audit=read(LIVE/'audit.json')
assert len(a['rows'])==len(f['rows'])==12
assert not a['batch_halted'] and a['totals']['pending_micro_cny']==0
assert all(r['status']=='completed' for r in a['rows'])
assert all(r['only_initial_wire_delta_is_selfcheck'] for r in audit['rows'])
assert f['gold_read'] is False and f['new_model_requests']==0
assert all(all(r['raw_finish_fields_unchanged'].values()) and r['trace_equals_model_input'] and r['finish_reason']=='tool_calls' for r in f['rows'])
assert all(p['exists_as_definition_id'] for r in f['rows'] for p in r['audit']['predictions'])
gold={g['id']:g['gold'] for g in read(ROOT/'verification/dev37-preparation-v4/scoring-only/gold-binding.json')}
score_rows=[]
for r in a['rows']:
 recomputed={str(k):ranked_metrics(gold[r['id']],r['entities'],k) for k in (1,3,5)}
 assert recomputed==r['strict']
 fr=next(t for t in f['rows'] if t['id']==r['id'] and t['arm']==r['arm'])
 assert fr['answer']['entities']==r['entities']
 score_rows.append({'id':r['id'],'arm':r['arm'],'strict_metrics_identical':True})
save(LIVE/'score-check.json',{'gold_free_audit_sha256':sha(LIVE/'finish-audit/audit.json'),'rows':score_rows,'predictions_and_scores_unchanged':True,'new_model_requests':0})
history=[]
for name in ['verification/sdk-finish-selfcheck-v7-preparation/final-lock.json','verification/sdk-retrieval-compare-v6-live/result-lock.json','verification/finish-evidence-audit-v1/final-lock.json','verification/retrieval-evidence-v6/final-lock.json','verification/sdk-ablation-v1-live/result-lock.json']:
 lock=read(ROOT/name)
 for path,h in lock['files'].items():assert sha(ROOT/path)==h,path
 history.append({'path':name,'sha256':sha(ROOT/name),'files_verified':len(lock['files'])})
for path,h in read(LIVE/'raw-run-lock.json')['files'].items():assert sha(ROOT/path)==h,path
names={'baseline':'原提示','retrieval':'自检提示'};group={};pairs=[]
for arm in names:
 rows=[r for r in a['rows'] if r['arm']==arm];fs=[r for r in f['rows'] if r['arm']==arm]
 group[arm]={k:sum(r[k] for r in rows) for k in ['requests_reserved','prompt_tokens','completion_tokens','cost_upper_micro_cny','sdk_retrieval_invocations']}
 ps=[p for r in fs for p in r['audit']['predictions']]
 group[arm].update(submitted_entities=len(ps),complete_body_visible=sum(p.get('body_lines_all_visible',False) for p in ps),definition_visible=sum(p.get('definition_line_visible',False) for p in ps))
for b in [r for r in a['rows'] if r['arm']=='baseline']:
 t=next(r for r in a['rows'] if r['id']==b['id'] and r['arm']=='retrieval')
 pairs.append({'id':b['id'],'baseline_recall5':b['strict']['5']['Recall'],'selfcheck_recall5':t['strict']['5']['Recall'],'delta_recall5':t['strict']['5']['Recall']-b['strict']['5']['Recall'],'baseline_entities':b['entities'],'selfcheck_entities':t['entities']})
save(LIVE/'interpretation.json',{'group_totals':group,'pairs':pairs,'history_unchanged':history,'quality_is_single_run_exposed_development_only':True,'new_model_requests_by_analysis':0,'input_token_delta_fraction':group['retrieval']['prompt_tokens']/group['baseline']['prompt_tokens']-1,'judgments':{'sqlglot_4369':'_combine newly included at rank 3; definition and call sites visible, body unread; residual is_leaf/repr ordering tension','xcdat_689':'_group_average newly included at rank 3; definition visible, body unread; spatial analogue excluded; top1 still misses','extra_candidates':'Struct and Plan.__init__ added without strict metric improvement; do not equate all additions with improvement','evidence_strength':'complete-body coverage 15/20 baseline versus 10/21 selfcheck; different predictions/evidence trajectories, not a controlled evidence-quality effect'}})
metric_lines=[]
for k in ['1','3','5']:
 bm=a['metrics']['baseline']['metrics'][k]['mean_completed'];tm=a['metrics']['retrieval']['metrics'][k]['mean_completed']
 for m in ['Acc','Recall','Hit']:
  metric_lines.append(f"| {m}@{k} | {bm[m]*100:.2f}% | {tm[m]*100:.2f}% | {(tm[m]-bm[m])*100:+.2f} 个百分点 |")
case_notes={'spotify__luigi-3324':'核心 copy 均排第一；自检组替换了外围候选。','tobymao__sqlglot-3901':'核心 _parse_join 均排第一；自检组加入解释中讨论的 _parse_joins/_parse_table，二者正文未读。','tobymao__sqlglot-4366':'核心 _struct_sql 均排第一；自检组额外列 Struct，未增加命中。','tobymao__sqlglot-4369':'自检组把 _combine 列为第三；见到定义行及调用，未见正文。','tobymao__sqlglot-4526':'两组均在第3次请求提前终答；自检组额外列入口 Plan.__init__，未增加命中。','xCDAT__xcdat-689':'自检组把 _group_average 列为第三，departures 第四；原组仅第四项 departures 命中。'}
case_lines=[f"| {p['id']} | {p['baseline_recall5']*100:.2f}% | {p['selfcheck_recall5']*100:.2f}% | {case_notes[p['id']]} |" for p in pairs]
report='''# LocAgent 六题自检提示验证 v7

2026-11-16（北京时间）。六题十二组真实运行全部完成，46 次请求、46 份响应，无技术中止、无未知或待结算请求。自检组在两题多命中一个参考实体，其余四题严格指标不变；当前结果支持继续考察这段提示，但不能证明稳定增益。

## 实验口径

两组均使用 OpenHands SDK 与固定 EvidenceRetriever v6，仅处理组系统提示增加一次通用自检。账本字段 baseline 为原提示，retrieval 为自检提示，后者不是“唯一可检索的组”。每题新会话，组别先后顺序交替；deepseek-flash、非思考模式、temperature=0，每题每组最多4请求。工具、证据和候选上限一致。6/6 对初始实际请求只差自检段落；后续工具选择和证据轨迹可以不同，不能将效果单独归因于最后一次候选整理。

此次沿用六道已曝光开发题，每组仅运行一次；没有独立测试集或重复试验。标准答案和参考补丁仅用于运行结束后的本地评分，没有加入模型请求。不从解释补实体，不修正排名、路径或分数，不执行目标仓库代码。

## 严格指标

下表为六题宏平均，分母均为6；两组均完成6题。Acc@k 为前k项命中数等于 min(k,参考实体数)，Recall@k 为命中数/全部参考实体数，Hit@k 为至少命中一个。Acc 不是预测精确率，不能据此判断额外候选是否无关。

| 指标 | 原提示 | 自检提示 | 变化 |
|---|---:|---:|---:|
'''+ '\n'.join(metric_lines)+'''

| 题目 | 原提示 Recall@5 | 自检 Recall@5 | 观察 |
|---|---:|---:|---|
'''+ '\n'.join(case_lines)+'''

SQLGlot #4369 有4个参考实体；xCDAT #689 有6个，最多提交5项，因此其 Recall@5 理论上限为5/6，本轮自检组实际只提交4项、命中2项。

## 自检改善了什么，仍未解决什么

- **SQLGlot #4369**：原提示解释讨论 `_combine` 却未提交；自检组提交于第三位，Recall@5 从1/4升为2/4。自检组收到6919行定义和7338/7361行调用，没有收到6926–6938行实现正文，并在解释中承认未读正文。排序仍不完全一致：解释称 `is_leaf` 本身不递归、将 `__repr__` 视为更可疑触发路径，但清单仍把前者排在后者之前。不能宣称语义一致性已全部修复。
- **xCDAT #689**：原组把解释中说“不涉及当前时间问题”的空间 `_averager` 列为第五项，自检组删除此空间类比，加入时间 `_group_average` 为第三项，Recall@5 从1/6升为2/6，首次命中从第四提前至第三。自检组只见 `_group_average` 的定义/位置，未见正文；甚至 `_averager` 正文也没有读到。解释称 `_group_average` 最可能是热点，却仍把 `climatology` 和 `_averager` 排在前面，首位仍未命中。
- **额外候选并不都带来收益**：#4366 新增 `Struct`、#4526 新增 `Plan.__init__`，严格指标均不变。#3901 的辅助候选更贴近解释，但正文未读。没有要求把每个提及名都加入清单，也不把同名搜索命中、内部 helper 或外层入口一律判作遗漏错误。
- **证据强度没有同步提升的证据**：原组20个提交实体中15个完整非文档正文可见；自检组21个中10个可见。两组候选和检索轨迹不同，这个比例不能当作提示导致证据质量下降的因果结论；但足以说明“命中更多”不等于“读到了更多目标实现”。

## 运行与费用

| 项目 | 原提示 | 自检提示 | 合计 |
|---|---:|---:|---:|
| 真实请求 | 23 | 23 | 46 |
| 输入 token | 103,819 | 113,380 | 217,199 |
| 输出 token | 5,192 | 5,191 | 10,383 |
| locagent_retrieve 调用 | 4 | 5 | 9 |
| 响应计量费用上界（元） | 0.249174 | 0.268288 | 0.517462 |

自检组输入 token 多约9.21%，包含新增提示和后续轨迹差异，不是提示本身的独立开销。六题运行计时合计约178.40秒。请求最大29,005字节、证据最大14,165字节，低于65,536/14,336字节限制。#3901自检组有一次 `read_file` 返回 `investigation_closed`，属于调查预算关闭，未触发技术中止，也未重开调查。

按所有输入2元、输出8元/百万token保守计量，新增费用上界0.517462元；加上原426次/4.973276元，累计472次/5.490738元，低于474次/107元授权上限。上界不是账户实际扣款。缓存命中129,790 token、未命中87,409 token均有回包记录；按已核价的空闲/高峰缓存费率估算分别为0.131537/0.263074元，也不冒充账单。[DeepSeek 官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

## 审计与归档

原始运行在分析前封存304文件。先运行不读取标准答案的终答证据检查，再运行本地评分与独立复算：12/12原始 finish 的 files/entities/answer 与保存结果一致，12/12实际模型工具输入与工具审计一致，12/12评分精确复算一致。41个提交实体ID均存在于固定源码图；37个至少见到定义行，25个完整非文档正文可见。仓库图事后校验不冒充模型已知信息。终答输出337–588 token，全部正常 tool_calls 结束，未见截断。

准备阶段26项离线测试、48次模拟为此前已通过的冻结结果，本轮未重复调用；真实结果与提示、评分器、原始证据未改动。冻结准备文件356项和五份历史锁所列文件再次核验通过。真实运行后分析未调用模型、读取密钥或外发数据。

完整工作区记录位于 `/Users/xiaomu/Documents/Codex/2026-11-12/task/verification/sdk-finish-selfcheck-v7-live/`：`analysis.json` 为逐题指标与用量；`audit.json` 为实际请求与工具审计；`finish-audit/` 为可见证据及原始终答核对；`score-check.json` 为评分复算；`interpretation.json` 为配对差异和结论；`raw-run-lock.json` 与 `result-lock.json` 固定原始和最终产物。独立开发日志保存在此目录，未改写旧日志或历史状态条目。

建议暂把自检提示视为候选整理的开发改进：保留不确定性说明，下一步应在未曝光题或预先固定的重复试验中确认效果，并考察被选中的关键函数是否真正读到了实现。此次未启动额外付费验证，也未将提示推广到旧入口。
'''
(LIVE/'REPORT_ZH.md').write_text(report)
(OUT/'LocAgent_v7_六题自检验证报告.md').write_text(report)
log='''# 2026-11-16 六题自检提示 v7 真实验证完成

用户明确确认 DeepSeek 外发范围、48请求/102元新增及474请求/107元累计上限后，原受保护启动器获准启动。六题十二组全部完成，46次真实请求，零待结算、零技术中止；SQLGlot #4526 两组均在3请求提前终答，其余4请求。新增响应计量上界0.517462元，累计472次/5.490738元，未取得账户实际账单。

本轮配对严格指标：Hit@1保持5/6，Hit@3由5/6升至6/6，Hit@5均6/6；宏Recall@5由73.61%升至80.56%。#4369新增_combine命中，#689新增_group_average命中，两者正文均未读；其余四题严格指标不变。仍有排序/解释张力及外围候选，不能宣称提示稳定修复定位。样本均为已曝光开发题、每组单次。

12份终答字段和工具输入逐项一致，41个实体ID均存在，评分12/12复算一致；冻结准备及历史记录均核验。原始304文件先封存，随后进行不读gold的证据审计与独立评分。保留全部模型原答、排名、评分及预算关闭事件。未启动额外验证或自动重试；独立保存此日志，不覆盖工作区外开发日志。
'''
(LIVE/'development-log-entry.md').write_text(log)
with (OUT/'LocAgent_v7_逐题指标.csv').open('w',newline='') as h:
 w=csv.writer(h);w.writerow(['题目','组别','完成状态','请求数','Hit@1','Hit@3','Hit@5','Recall@1','Recall@3','Recall@5','输入token','输出token','响应计量上界_元'])
 for r in a['rows']:w.writerow([r['id'],names[r['arm']],r['status'],r['requests_reserved'],*[r['strict'][k]['Hit'] for k in ['1','3','5']],*[r['strict'][k]['Recall'] for k in ['1','3','5']],r['prompt_tokens'],r['completion_tokens'],r['cost_upper_micro_cny']/1e6])
# Preserve the exact finalizer alongside the audit; no frozen preparation code is edited.
(LIVE/'finalize_results.py').write_bytes(Path(__file__).read_bytes())
files={str(p.relative_to(ROOT)):sha(p) for p in sorted(LIVE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='result-lock.json'}
save(LIVE/'result-lock.json',{'status':'completed_and_audited','created_at':datetime.now(timezone.utc).isoformat(),'new_requests':46,'new_cost_upper_micro_cny':517462,'pending_micro_cny':0,'completed_arms':12,'history_unchanged':history,'files':files})
for path,h in read(LIVE/'result-lock.json')['files'].items():assert sha(ROOT/path)==h,path
assert (OUT/'LocAgent_v7_六题自检验证报告.md').read_bytes()==(LIVE/'REPORT_ZH.md').read_bytes()
print(json.dumps({'status':'complete','final_frozen_files':len(files),'metrics_recomputed':len(score_rows),'group_totals':group,'outputs':[str(p) for p in OUT.glob('LocAgent_v7*')]},ensure_ascii=False))
