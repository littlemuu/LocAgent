import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
P=Path(__file__).resolve().parents[1];D=P/'delivery';R=P.parent
read=lambda p:json.loads(p.read_text())
def link(label,p):return f'[{label}]({p})'
def val(x):return '未运行' if x is None else '是' if x is True else '否' if x is False else str(x)
def f(x,n=3):return '未知' if x is None else f'{x:.{n}f}'
def ids(xs):return '、'.join(xs) or '无'
def edit_value(row):
 return row['first_source_edit_request'] if row.get('first_source_edit_request') is not None else '未编辑' if row.get('coding_requests') is not None else '未运行'
def main():
 s=read(D/'summary.json');rows=read(D/'C-per-task.json');errors=read(D/'read-file-errors-BC.json');judgments=read(D/'failure-judgments.json');jmap={r['instance_id']:r for r in judgments}
 failed=[r['instance_id'] for r in rows if r.get('resolved') is False]
 assert set(failed)==set(jmap),'every scored unresolved C case requires offline review'
 shutdown=read(D/'shutdown-receipt.json');assert shutdown['completed']
 report=['# dev24 C(v8.2) 完整运行与 v5 A/B 配对比较','','本次只运行 C(v8.2) 一次；A/B 直接复用已有 v5 结果。dev24 仅作开发参考，不作最终效果结论。C 与 A/B 非同时运行，存在批次间模型服务、采样、缓存与时段波动；无随机交错，不能据这次差值单独作因果归因。','',
 '## 冻结、运行与清理','',f"C binding：`{s['binding']}`；B 核心：`{s['baseline_binding']}`。开跑前本地与云端哈希均通过。Coding Agent/40次预算、stuck_detection=False、SDK 1.62.0、harness 3.0.0及其冻结提交均沿用 v5；没有修改任何冻结件。",'',
 '资源口径沿用 v5：编码容器6CPU/6GiB/network=none；v5 harness 包装实际未生效，观测为Memory=0、NanoCpus=0、network=bridge，继续使用专用16核64GiB主机单路评测，未修复或改变这一配置。实际运行资源见 '+link('资源观测',P/'evidence/resource-observations.jsonl')+'。','',
 f"原题序、单路、零外部自动重试。启动时保留18个任务镜像缓存；本轮实际缓存命中{s['C_image_cache_hits']}题，镜像检查/下载累计{s['C_image_pull_seconds']:.1f}秒。镜像缓存继续保留。",'',
 '资金控制：起初按15元保守总上限运行；随后用户明确指示“取消API预算门槛，跑完再停”。在第14题独立harness已完成且无进行中API请求的边界保存结果并交接外层控制器，从第15题接续；前14题未重跑，冻结件未修改。其后取消总费用门槛，仅保留原定位4次、编码40次、单路和失败不自动重试约束。交接期间的等待包含在整轮自然耗时中，不计入各题阶段累计耗时。'+link('预算修订授权',P/'authorization-amendment.json')+'；'+link('控制器交接凭据',P/'evidence/handoff/receipt.json'),
 link('初始授权',P/'authorization.json')+'；'+link('开机确认',D/'authorization-confirmation.json')+'；'+link('云端预检',P/'evidence/remote-preflight.json'),'','## A/B/C 汇总','',
 '| 组 | completed | resolved | 未评分 | 空补丁 | 首次编辑中位数 | 输入token | 输出token | 总token | API计量估算/元 | 保守上界/元 | 累计耗时/秒 |','|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|']
 for arm in ['A','B','C']:
  a=s['arms'][arm];t=a['totals'];empty=f"{a['empty_patch_count']}/{a['empty_patch_observed']}（{a['empty_patch_rate']:.2%}）" if a['empty_patch_rate'] is not None else '未运行'
  report.append(f"| {arm} | {a['completed']}/24 | {a['resolved']}/{a['tasks']-a['unscored']}已评分 | {a['unscored']} | {empty} | {val(a['first_edit_median_among_edited'])} | {t['input_tokens']:,} | {t['output_tokens']:,} | {t['total_tokens']:,} | {f(t['metered_cny'],6)} | {f(t['upper_cny'],6)} | {a['wall_seconds_excluding_images_including_locator_harness']:.2f} |")
 report+=['',
 'B/C token、请求、费用及耗时均含定位；A不含定位。耗时列为各题定位+编码+harness之和，不含镜像下载。第14题控制器交接时的评测结束时间取原 evaluation.json 写入时间；交接等待仅计入整轮自然耗时。首次编辑从1计数，只在发生过源码编辑的题中取中位数；未编辑不填0或40。空补丁依据最终diff，分母仅为实际有编码记录的题，未运行不冒充空补丁。未评分不计作resolved=False，配对检验仅用评分齐全的题。','',
 f"C整轮自然耗时（含镜像与编排）{s['C_run_wall_seconds']:.2f}秒。费用是usage/cache/请求时间推算，未核对账户账单、不含云计算/云盘/网络费用；A/B历史计量值原样保留。C晚间适用空闲价，不能把低费用直接解释为token效率提升。价格来源：[DeepSeek官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。",'',
 '## 配对不一致与 McNemar','']
 for pair,v in s['pairs'].items():
  report += [f"### {pair}",'',f"完整配对 {v['complete_pairs']}；双方resolved {len(v['both_resolved'])}；双方未resolved {len(v['both_unresolved'])}。",'',f"- C resolved、对方未resolved（{len(v['C_resolved_other_not'])}）：{ids(v['C_resolved_other_not'])}",f"- C未resolved、对方resolved（{len(v['C_not_other_resolved'])}）：{ids(v['C_not_other_resolved'])}",f"- 未评分排除：{ids(v['unscored_excluded'])}",f"- McNemar精确双侧 p = {v['McNemar_exact_two_sided_p']:.10g}",'']
 report+=['按不一致对上的 Binomial(n,0.5) 精确双侧尾概率计算；没有连续性校正或渐近近似。','','## 披露分组','',
 '| 分组 | 题数 | 已评分 | resolved | 已评分中resolved率 |','|---|---:|---:|---:|---:|']
 for group,v in s['disclosure_groups'].items():report.append(f"| {group} | {v['tasks']} | {v['scored']} | {v['resolved']} | {v['resolved_rate_among_scored']:.2%} |" if v['resolved_rate_among_scored'] is not None else f"| {group} | {v['tasks']} | {v['scored']} | {v['resolved']} | 无此类题 |")
 report += ['',f"定位全回退{s['C_full_fallback']}题；validator_error {s['C_validator_errors']}；残留规则条数：{s['C_rule_counts']}。分组是观察性描述，题目难度与证据缺口可能共同影响结果。",'',
 '## 重点题逐题 A/B/C','', '| 题目 | A resolved | B resolved | C resolved | C首次编辑 | C编码请求 | C披露 |','|---|---|---|---|---:|---:|---:|']
 for ident,v in s['focus'].items():
  c=v['C'];report.append(f"| {ident} | {val(v['A']['resolved'])} | {val(v['B']['resolved'])} | {val(c['resolved'])} | {edit_value(c)} | {val(c['coding_requests'])} | {val(c.get('disclosure_count'))} |")
 observations=read(D/'focus-observations.json') if (D/'focus-observations.json').exists() else {}
 report+=['']+[f"- {i}：{observations[i]['reason']}" for i in s['focus'] if i in observations]
 report+=['','## read_file 报错','',f"C总计{s['C_read_file_error_count']}次；B历史总计{s['B_read_file_error_count']}次，原日志也存在此问题。",'', '| 题目 | C次数 | C类型 | B次数 | B类型 |','|---|---:|---|---:|---|']
 for r in errors:
  if not (r['C_count'] or r['B_count']):continue
  typ=lambda es:', '.join(sorted({e.get('error_type') or e.get('error','未知') for e in es})) or '无'
  report.append(f"| {r['instance_id']} | {val(r['C_count'])} | {typ(r['C_errors'])} | {r['B_count']} | {typ(r['B_errors'])} |")
 report += ['',link('B/C逐条错误与请求参数',D/'read-file-errors-BC.json'),'','## C未resolved题的离线轨迹判断','',
 '只审阅已评分且未resolved的C题。判断来自原定位包、编码工具轨迹、最终补丁与原harness日志；不重新调用模型/运行代码。使用40次本身不等于循环；重复同一无进展操作才据轨迹标记。沿用错误假设只记录具体诊断与后续操作的对应，不宣称证明因果效应；证据不足明确写不确定或未见明确证据。','',
 '| 题目 | 沿用定位错误假设 | 用满40次 | 循环 | 依据 |','|---|---|---|---|---|']
 for r in rows:
  if r.get('resolved') is not False:continue
  j=jmap[r['instance_id']];report.append(f"| {link(r['instance_id'],D/j['evidence'])} | {j['wrong_locator_hypothesis_adopted']} | {val(j['used_all_40'])} | {j['loop']} | {j['reason']} {j['loop_reason']} |")
 report += ['',link('离线判断结构化明细',D/'failure-judgments.json'),'','## 逐题记录及边界','',
 link('C逐题CSV',D/'C-per-task.csv')+'；'+link('A/B/C逐题JSON',D/'ABC-per-task.json')+'；'+link('完整汇总及配对JSON',D/'summary.json')+'。','',
 'requests-2317保持原harness评分，证书错误单独列在'+link('环境观察文件',D/'environment-observations.json')+'；不补跑、不重评、不修改证书。C还引入 method=None 转换的额外回归，不能将全部失败归因于证书。',
 'sphinx-8595存在测试补丁同名文件冲突；sphinx-8721原测试总览与harness逐项评分不一致。均保留原resolved=False，详见'+link('额外评测观察',D/'additional-harness-observations.json')+'。未触碰holdout50。A/B未重跑；没有额外重复C。',
 '云端临时API密钥已删除，运行/全部容器均为0，24个任务镜像缓存保留。控制台已核验“已关机”“关机不计费模式”，公网IPv4为“-”，计费栏为“按量计费-部分停止计费”。',
 link('清理和关机状态',D/'final-cloud-audit.json')+'；'+link('关机凭据',D/'shutdown-receipt.json')+'；'+link('云端最终哈希与缓存核验',D/'final-remote-verification.json')+'；'+link('结果一致性检查',D/'result-validation.json')+'。']
 unscored=[r for r in rows if type(r.get('resolved')) is not bool]
 if unscored:
  report += ['','### 未评分/未运行项目','', '以下项目不按未resolved处理；单题状态和中止原因保留原记录。']
  for r in unscored:report.append(f"- {r['instance_id']}：{'未运行' if r['status']=='not_run' else '已尝试但未评分'}；{r.get('reason') or r.get('errors')}")
 (D/'REPORT_ZH.md').write_text('\n'.join(report)+'\n')
 print('Report generated with all unresolved-case judgments.')
if __name__=='__main__':main()
