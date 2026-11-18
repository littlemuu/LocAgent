"""Post-unblinding presentation only. Does not change frozen scores or controls."""
import collections,csv,hashlib,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
P=Path(__file__).resolve().parents[1];D=P/'delivery'
def load(n):return json.loads((D/n).read_text())
def write(n,x):(D/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def link(n,label=None):return f'[{label or n}]({D/n})'
def plink(p,label):return f'[{label}]({P/p})'
def cell(v):
 if v is None:return '未观测'
 if type(v) is bool:return '是' if v else '否'
 return str(v).replace('|','\\|').replace('\n','<br>')
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+['| '+' | '.join(cell(v) for v in r)+' |' for r in rows])
def money(x):return f'{x:.6f}'
def tm(x):return datetime.fromtimestamp(x,ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
rows=load('ABC-per-task.json');s=load('summary.json');u=load('usage-cost-time-supplement.json');integrity=load('integrity-and-execution-audit.json');manual=load('manual-judgments.json');ms=load('manual-review-summary.json');ha=load('raw-harness-audit.json')
by={(x['instance_id'],x['arm']):x for x in rows}
assert len(manual)==89 and {(x['instance_id'],x['arm']) for x in manual}=={k for k,v in by.items() if v['resolved'] is not True}
for m in manual:
 a=load(m['audit_path']);a.update({k:m[k] for k in ['no_progress_loop','evidence_requests','reason']})
 if m['arm']=='C':a.update({k:m[k] for k in ['wrong_localization_adoption','adoption_evidence']})
 a['manual_review_completed']=True;a['manual_review_scope']='post-unblinding trajectory review; no model/harness rerun'
 write(m['audit_path'],a)
with (D/'manual-judgments.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in manual for k in r)));w.writeheader();w.writerows(manual)
audittext='''# 未解决组别逐项审阅（89/89）

审阅范围为原始 resolved 不为 True 的全部组别，包含11个原始 null。请求号均为本组 Coding Agent 的本地请求号，不是跨定位/编码的 ledger 序号。“用满40次”与“循环”分别记录。循环指重复行动且未获得新增有效源码编辑或诊断信息；可判定局部持续循环，不要求整段轨迹完全没有进展。“未运行”包括定位失败而编码未启动，以及编码首个API请求被拒、未产生模型行动。

判断来自揭盲后的单次人工轨迹审阅，存在主观性，没有额外模型裁判或独立双人复核。只描述观察到的行为，不将相关性直接解释为因果。源码编辑事件即使很多，也可能是同一补丁的添加/撤销；反之，没有修改也可能仍在获得新诊断信息。

各“证据”链接包含完整定位原文、工具调用参数、源码编辑事件和最终回答。原始工具结果与模型交互另保存在 `evidence/run/trial/<ID>/<arm>/wire/` 和 `agent/`；本地辅助索引为 review-packets.json（不作为原始证据替代）。

'''
audittext+=table(['题号 / ID','组','编码请求','用满40','无进展循环','证据请求号','审阅依据'],[[f"{m['number']} / {m['instance_id']}",m['arm'],m['coding_requests'],m['used_all_40'],m['no_progress_loop'],','.join(map(str,m['evidence_requests'])) or '无',m['reason']+' '+link(m['audit_path'],'证据')] for m in manual])
audittext+='\n\n## C 是否沿用错误定位方案（全部30个未解决C组别）\n\n'
audittext+=table(['题号 / ID','判断','证据与边界'],[[f"{m['number']} / {m['instance_id']}",m['wrong_localization_adoption'],m['adoption_evidence']+' '+link(m['audit_path'],'定位原文与编码轨迹')] for m in manual if m['arm']=='C'])
(D/'FAILURE_REVIEW_ZH.md').write_text(audittext+'\n')
cs=[r for r in rows if r['arm']=='C'];fields=['number','instance_id','resolved','disclosure_count','rule_counts','full_fallback','validator_error','read_file_error_count','read_file_errors']
write('C-disclosures-per-task.json',[{k:r.get(k) for k in fields} for r in cs])
ct='''# C 组50题披露与工具错误

定位交付45/50。共44条披露，27题至少一条；R1=22、R2=0、R3=2、R4=20。交付45题中全回退0、validator_error非空0。5题定位首个请求HTTP 402，相关字段未观测，不记为0。read_file错误按单份locator tool_audit的记录去重计数，共20次、14题；未交付5题没有完整工具审计，标未观测。validator_error在已交付题中原值为null（无错误），在未交付题中null表示未观测，表内区分。

'''
ct+=table(['题号 / ID','原评分','披露条数','R1/R2/R3/R4','全回退','validator_error','read_file错误'],[[f"{r['number']} / {r['instance_id']}",str(r['resolved']),r.get('disclosure_count'),'/'.join(str(r['rule_counts'][k]) for k in ['R1','R2','R3','R4']) if r.get('rule_counts') is not None else None,r.get('full_fallback'),'null（无错误）' if r.get('disclosure_count') is not None and r.get('validator_error') is None else r.get('validator_error'),r['read_file_error_count']] for r in cs])
ct+='\n\n逐项错误参数和原错误内容见 '+link('C-disclosures-per-task.json')+'；定位原文与披露审计位于 '+plink('evidence/run/trial','原始证据目录')+'。\n'
(D/'C_DISCLOSURES_ZH.md').write_text(ct)
text='''# Verified holdout50 最终一次性实验报告

冻结 holdout50 的原始评分为 **A 21/50（42%）、B 20/50（40%）、C 20/50（40%）**。主比较 C−A 为 −2 个百分点；C−B 为0。三项预注册精确双侧 McNemar 的原始 p 和 Holm 调整 p 均为1。本轮没有提供 C 优于 A 或 B 的证据；这不等同于证明三者等效。

结论受供应商余额不足、缺失评分及冻结 harness 日志/评分不一致的限制。全部保留原结果，没有补跑、重抽、修改评分或在揭盲后调整实验组件。这里的150指150个组别均被调度处理，不代表150个Coding Agent都成功运行完毕。

**已完成关机不计费：用户完成本人微信验证后，2026-11-18 06:24:12（上海时间）核验实例“已关机 / 关机不计费模式 / 按量计费-部分停止计费”，公网IPv4已释放。临时API凭证已删除，实验容器已清空；保留云盘仍可能计费。** 当前凭据与缓存核验见 '''+link('final-remote-verification.json')+'，关机状态见 '+link('shutdown-receipt.json')+' 和 '+link('shutdown-confirmed.jpg','关机截图')+'。\n\n'
text+='## 原评分、补丁与首次编辑\n\n'
text+=table(['指标','A','B','C'],[
 ['resolved / 固定50','21/50 (42%)','20/50 (40%)','20/50 (40%)'],
 ['原始False / null','28 / 1','25 / 5','25 / 5'],
 ['实际获得有效harness评分','49','45','45'],
 ['编码阶段从未启动','0','5','5'],
 ['编码首个API请求402、无模型行动','4','0','0'],
 ['技术或预算失败组别','6','5','6'],
 ['空补丁 / 实际补丁产物','8/50 (16.00%)','4/45 (8.89%)','6/45 (13.33%)'],
 ['缺失补丁产物','0','5','5'],
 ['首次源码编辑请求中位数（有编辑人数）','5.5 (42)','4 (41)','4 (39)'],
 ['所有组别中用满40次编码请求','14','12','13']])
text+='\n\n技术失败与null不是互斥口径：例如首个API失败后生成的空补丁仍可能被harness评分False；缺失评分保持null。主分析比较固定50题是否获得原始 resolved=True，未把null篡改为harness False。空补丁只对实际补丁产物计算；首次源码编辑中位数只纳入真正出现源码编辑的组别。完整150行及原始错误：'+link('ABC-per-task.json')+'、'+link('ABC-per-task.csv')+'。\n\n'
text+='## 固定50题的预注册比较\n\n'
text+=table(['比较','前者独自解决','后者独自解决','同时解决','均未获True','精确双侧p','Holm p'],[[k.replace('_',' '),len(v['first_resolved_other_not']),len(v['first_not_other_resolved']),len(v['both_resolved']),len(v['neither_observed_resolved']),v['McNemar_exact_two_sided_p'],v['Holm_p_three_predeclared_comparisons']] for k in ['C_vs_A','C_vs_B','B_vs_A'] for v in [s['primary_fixed_50_pairs'][k]]])
text+='\n\n以下是全部双向不一致名单。“独自解决”仅指该配对的另一组没有原始True，可能是False或null。\n\n'
for k in ['C_vs_A','C_vs_B','B_vs_A']:
 v=s['primary_fixed_50_pairs'][k];a,b=k.split('_vs_')
 text+=f"- **{a} vs {b}**：{a}独自解决："+'、'.join('`'+i+'`' for i in v['first_resolved_other_not'])+f"。{b}独自解决："+'、'.join('`'+i+'`' for i in v['first_not_other_resolved'])+'。\n'
text+='\n`pylint-dev__pylint-6903` 的A原评分为null，因此C/B相对A的这项胜出不是“对方测试失败”的证据。\n\n'
text+='## 仅双组均有效评分的缺失敏感性表\n\n'
text+=table(['比较','配对数','前者独自解决','后者独自解决','精确双侧p','Holm p'],[[k.replace('_',' '),v['paired_count'],len(v['first_resolved_other_not']),len(v['first_not_other_resolved']),v['McNemar_exact_two_sided_p'],v['Holm_p_three_predeclared_comparisons']] for k in ['C_vs_A','C_vs_B','B_vs_A'] for v in [s['complete_scored_pair_sensitivity'][k]]])
text+='\n\n该表按预注册口径完整披露，不替代主表。以下列出全部敏感性名单：\n\n'
for k in ['C_vs_A','C_vs_B','B_vs_A']:
 v=s['complete_scored_pair_sensitivity'][k]
 text+='- **'+k.replace('_',' ')+'**：前者独自解决：'+ '、'.join(v['first_resolved_other_not'])+'；后者独自解决：'+'、'.join(v['first_not_other_resolved'])+'；排除未评分：'+'、'.join(v['excluded_unscored'])+'。\n'
text+='\n所有p值来自冻结统计实现；预注册公式与三项Holm调整口径见 '+plink('PREREGISTRATION_ZH.md','PREREGISTRATION_ZH.md')+'，机器可读统计见 '+link('summary.json')+'。\n\n'
text+='## 一次性运行中的技术失败与harness异常\n\n'
text+='''17个技术或预算失败组别完整保留：

- `pylint-dev__pylint-6903/A`：编码7次后，harness构建TestSpec找不到该base commit的`requirements_test.txt`；evaluation缺失结果，原评分null。
- `sphinx-doc__sphinx-8265/C`：编码26次，`missing_tool_or_truncated_response`；保留部分补丁并按冻结流程评分False。
- `sympy__sympy-13091/A`：编码34次到达token预算；保留部分补丁，评分False。
- 最后5题（sympy 13091、13757、13877、15809、22914）的B/C：定位首个请求HTTP 402；定位未交付，编码/评分未启动，共10个null。
- 最后4题的A：编码首个请求HTTP 402，没有模型行动，空补丁仍进入冻结评分流程，均False。

14次HTTP 402的供应商响应写明 `Insufficient Balance` / `insufficient_balance_error`。这是供应商余额拒绝；外层调度确实没有API总金额上限，也没有自动重试或充值后续跑。完整记录：'''+link('technical-failures.json')+'。\n\n'
text+='另有**17个组别**出现“原始测试最后汇总有passed且无failed/error/exception，但report.resolved=False”。下表仅披露日志与冻结评分的不一致迹象，不把汇总行当成替代评分，不断言它能证明所有目标标签通过。Astropy部分有测试名/路径匹配问题的迹象，Sphinx部分仅输出进度点；具体解析原因未通过改动或重跑验证。\n\n'
text+=table(['题号 / ID','组','原始最后测试汇总','原评分'],[[f"{x['number']} / {x['instance_id']}",x['arm'],x['raw_test_summary_lines'][-1],False] for x in ha if x['raw_last_summary_all_pass_but_report_false']])
text+='''

环境或兼容性信号还包括：Astropy14096的leap-second自动更新异常与依赖导入问题；Requests1724/1766的SSL证书错误，1766的旧pytest调用不兼容；Requests2931缺失httpbin_secure夹具（C同时有目标binary PUT类型断言失败）；Requests5414有缺失mocker/trustme文本；Pylint4661缺失appdirs；Pylint8898日志中有_distutils_hack导入信号（C同时有正则列表回归）。这些信号可能与真实补丁错误并存，且有些出现在成功组别；不能统一归因为“全是环境问题”。pytest7521的missingarg/xyz42123来自测试内嵌失败场景，不当作独立环境失败统计。

全部150组的原report、摘要、环境文本信号和原文件位置见 '''+link('raw-harness-audit.json')+'。所有原始日志位于 '+plink('evidence/run/trial','封存证据目录')+'，未修改任何证书、依赖、harness或评分。\n\n'
text+='## 失败轨迹审阅与C定位披露\n\n'
text+=table(['未解决组别的循环审阅','A (29)','B (30)','C (30)'],[[key,*[ms['by_arm_loop_judgment'][a].get(key,0) for a in 'ABC']] for key in ['是','否','证据不足','未运行']])
text+='\n\n这89个未解决组别中用满40次的数量分别为11/12/11。循环与用满预算不能互相替代；例如反复撤销同一修改会产生很多编辑事件，仍属于无净进展循环。C的1例证据不足涉及反复随机样本验证，不能仅凭命令相似断定没有获得新信息。\n\n'
text+='C的30个未解决组别中，沿用错误定位方案判为明确是5、未见明确证据17、不确定3、未运行5。5个明确案例分别为：astropy8872的反向cast检查建议；seaborn3069的无mark空图验证方案；requests2931的统一UTF-8文本转换分支；pylint4970将内部短路等同于完全静默；pylint8898先整体编译导致逗号列表语义回归。seaborn案例指错误验证方案，不能据此认定定位是失败的唯一原因。另有pytest10081/5787、sklearn26323等属于实现遗漏或未完整执行建议，未归入明确错误定位采纳。\n\n'
text+='完整89项循环判定、30项C判断、请求号和定位原文/编码行为链接：'+link('FAILURE_REVIEW_ZH.md')+'；结构化文件：'+link('manual-judgments.json')+'、'+link('manual-judgments.csv')+'。这些是揭盲后的主观审阅，没有另做双人复核。\n\n'
text+='C定位成功交付45/50，27题产生44条披露：R1=22、R2=0、R3=2、R4=20；已交付45题全回退0、validator_error非空0；read_file错误20次、涉及14题。未交付5题相应值均标未观测。每题完整清单及错误原值：'+link('C_DISCLOSURES_ZH.md')+'、'+link('C-disclosures-per-task.json')+'。\n\n'
text+='## 请求、token、费用和时间\n\n'
text+=table(['指标','A','B','C'],[[label,*[f"{u['arms'][a]['total_cost'][k]:,}" for a in 'ABC']] for label,k in [('请求尝试（含402）','requests'),('收到usage的请求','received_requests'),('没有usage的402请求','uncertain_requests'),('输入token','input_tokens'),('输出token','output_tokens'),('总token','total_tokens'),('缓存命中输入token','cache_hit_tokens'),('缓存未命中输入token','cache_miss_tokens')]])
text+='\n\n'+table(['费用口径（元）','A','B','C'],[[label,*[money(u['arms'][a]['total_cost'][k]) for a in 'ABC']] for label,k in [('usage/缓存/时段推算','metered_cny'),('同usage统一高峰、保留缓存参考','peak_cache_adjusted_cny'),('同usage统一高峰、无缓存参考','upper_cny'),('无usage请求的保守reservation（非费用）','uncertain_reservation_cny')]])
api=sum(u['arms'][a]['total_cost']['metered_cny'] for a in 'ABC');ref=sum(u['arms'][a]['total_cost']['upper_cny'] for a in 'ABC')
text+=f'\n\n收到usage请求的推算费用合计 **{api:.6f}元**；同usage统一高峰无缓存参考合计{ref:.6f}元。**均不是服务商实扣账单**。冻结算法按上海工作日09–12/14–18点为高峰，其他时段乘0.5；本轮收到usage的调用均落在0.5系数时段。14个402没有usage，ledger仍保留reserved状态；29.655040元reservation只是发送前预算保守量，既不算已扣款，也不加到估算费用中。没有读取服务商账单核销这些请求。\n\n'
text+=table(['组 / 阶段','请求尝试','输入token','输出token','推算元','阶段秒'],[[a+' / '+stage,u['arms'][a][field]['requests'],u['arms'][a][field]['input_tokens'],u['arms'][a][field]['output_tokens'],money(u['arms'][a][field]['metered_cny']),f"{u['arms'][a]['stage_seconds'][stage]:.2f}"] for a in 'ABC' for stage,field in [('locator','localization_cost'),('coding','coding_cost')]])
text+='\n\n'+table(['组','定位秒','编码秒','harness秒','三阶段合计秒'],[[a,*[f"{u['arms'][a]['stage_seconds'][k]:.2f}" for k in ['locator','coding','evaluation']],f"{sum(u['arms'][a]['stage_seconds'].values()):.2f}"] for a in 'ABC'])
stage=sum(sum(u['arms'][a]['stage_seconds'].values()) for a in 'ABC');rest=u['run_seconds']-u['image_seconds']-stage
text+=f"\n\n整轮从上海时间 **{tm(u['run_started_at'])} 至 {tm(u['run_finished_at'])}**，共 **6小时28分35.8秒**。其中镜像阶段{u['image_seconds']:.2f}秒，定位/编码/harness阶段合计{stage:.2f}秒，其余编排、校验、归档与清理约{rest:.2f}秒。阶段时间包括启动/校验等待，不是纯模型响应时间；不同阶段缓存、镜像和时段条件不能直接解释为模型效率差异。\n\n"
text+=f"历史主机报价4.09元/小时仅对这6.4766小时运行窗口折算约{u['run_seconds']/3600*4.09:.2f}元；这**不是本轮主机总费用或账单**，不含开机准备、收证和等待本人验证期间的运行时间。现已核验关机不计费；上述06:24:12为观测时间，不是精确停机时间。等待验证期间的运行费用、流量与停机后保留存储费用未通过账单核验。完整费用与时长明细："+link('usage-cost-time-supplement.json')+'。\n\n'
text+='## dev24与74题的描述性汇总\n\n'
text+=table(['范围 / 组','resolved','空补丁 / 已观测','首次编辑中位数（人数）'],[[name+' / '+a,f"{v['resolved']}/{v['tasks']} ({100*v['resolved_rate_fixed_denominator']:.2f}%)",f"{v['empty_patch_count']}/{v['empty_patch_observed']}",f"{v['first_edit_median_among_edited']} ({v['edited_count']})"] for name,key in [('dev24','dev24_descriptive_arms'),('holdout50','holdout_arms'),('合并74，仅描述','combined_74_descriptive_arms')] for a,v in [(a,s[key][a]) for a in 'ABC']])
text+='\n\n74题的中位数由逐题记录重算，没有平均两个中位数。开发集C为15/24，而holdout为20/50，开发集优势没有在本轮holdout中复现。74题C=35/74对A/B=31/74仅描述，不做确认性合并检验；最终推断只依据冻结holdout50。历史逐题数据见 '+plink('history/dev24-ABC-per-task.json','dev24逐题记录')+'。\n\n'
text+='## 冻结、离线核验、资源与证据完整性\n\n'
text+='''只新增最小holdout数据适配入口与外层调度。A/B原42文件绑定、C原57文件绑定、Coding Agent、定位器、SDK及harness commit未变。离线适配核验24/24数据行字节一致、实例集合和选择顺序一致、捕获的harness评分输入/参数字节一致；spec_for/evaluate/main尾部保持逐字相同。该核验使用隔离替身捕获入口输入，模型API、Docker及真实harness执行均为0；不冒充一次真实评分重跑。

holdout名单SHA-256：`5226d5870987a2f9d161b98077aa64788f6e3426d1cea326385694c47922acd6`。

A/B绑定：`a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036`。

C绑定：`031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7`。

开机后的首个付费请求前复核：openhands-sdk1.62.0、swebench3.0.0、bm25s0.2.3、PyStemmer2.2.0.3、pyarrow18.0.0；harness commit `d83e1001739f4d96add351d9ec0d56f4594a0d82`。主机16CPU/65,961,148,416字节内存；agent容器6CPU/6GiB/network none，stuck_detection=False。冻结harness实际容器为Memory=0、NanoCpus=0、network bridge：原冻结封装未对它施加agent资源限制，本轮原样保留，没有将它误报为6CPU/6GiB。

'''
text+=f"预检剩余77.30GiB；运行健康采样最低{integrity['minimum_observed_free_bytes']/1024**3:.2f}GiB，未低于30GiB。379条容器资源观测均匹配冻结基线（240条agent、139条harness）；采样不是连续监测证明。50题按固定顺序与ABC/BCA/CAB轮转，480个阶段独占started标记及区间均无重叠：50次镜像、100次定位、140次编码、140次评分尝试、50次归档清理。3257条API reservation序号连续且每组预算未超，收到usage3243条，实际返回模型标识均为deepseek-flash；没有重新发送失败请求。\n\n"
text+='50题的A/B/C逐题共用同一镜像ID/digest，三组产物（或明确的失败缺失项）记录和哈希完成后才删除该题新拉镜像。50个新题镜像均按此处理，旧24个镜像ID最终核验完全一致；没有全局prune。81个部署文件哈希一致，50份证据清单中21,072个产物哈希全部匹配。\n\n'
text+='核验附件：'+link('ADAPTER_ACCEPTANCE_ZH.md')+'、'+link('adapter-equivalence.json')+'、'+link('evaluation-adapter.diff')+'、'+link('remote-preflight.json')+'、'+link('integrity-and-execution-audit.json')+'、'+link('image-digests-and-cleanup.json')+'。\n\n'
text+='模型只收到各自题面、base_commit源码与本组定位包；测试patch/评分标签由隔离evaluator读取。运行期间仅读取不含结果的健康信息。完成后备份封存证据并一次性揭盲，收据见 '+plink('unblinding-receipt.json','揭盲收据')+'。压缩包包含24,194个成员，大小39,582,904字节，SHA-256 `2011b95dd19512da53b21ac69e489d64398b1445e7f22d7d9fd1d98526c51668`；'+plink('sealed-evidence.tar.gz','原始封存证据包')+'，'+link('sealed-backup-verification.json','备份验证')+'。\n\n'
text+='本地派生分析中的显示/索引修正不触发模型或harness执行：旧Python不支持tarfile的filter参数后改用安全路径/文件类型检查解包；审阅索引按Controller本地请求号匹配工具结果；原始日志的ANSI颜色只在派生摘要中去除。冻结实验、原始证据及原评分均未修改。\n\n'
text+='## 收尾完成\n\n用户完成本人微信验证后，恢复页面已显示“关机中 / 操作成功”；未再次提交关机。随后核验实例“已关机”、关机不计费模式、按量计费-部分停止计费，公网IPv4栏为空。2026-11-18 06:24:12（上海时间）保存最终截图与关机收据，历史MFA阻塞收据另存shutdown-mfa-block-receipt.json。实验、报告与关机收尾全部完成；冻结代码、原始证据与评分未改动。\n'
(D/'FINAL_REPORT_ZH.md').write_text(text)
readme='''# 交付索引

最终结论与所有限制：'''+link('FINAL_REPORT_ZH.md')+'。\n\n逐组评分：'+link('ABC-per-task.csv')+'；预注册统计：'+link('summary.json')+'；89项完整人工审阅：'+link('FAILURE_REVIEW_ZH.md')+'；C逐题披露：'+link('C_DISCLOSURES_ZH.md')+'。\n\n`failure-judgments-pending.json`是冻结统计程序首次输出的历史待审阅清单，保留其原内容；最终判定以`manual-judgments.json`及已补充标注的`failure-audit/`为准。`review-packets.json`仅为中间阅读索引，其中初始待审阅字段不代表最终状态。\n\n原始证据目录和封存压缩包不可改写；所有报告与人工标注均在揭盲后生成，未重新调用模型或harness。交付SHA256清单覆盖最终文件，不包括清单自身；关机收据后续完成时应更新清单。\n'
(D/'README_ZH.md').write_text(readme)
print('Reports written; manual coverage 89/89; C disclosure rows',len(cs))
