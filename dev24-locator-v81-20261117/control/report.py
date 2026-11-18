import collections,csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];E=ROOT/'evidence';D=ROOT/'delivery'
auth=json.loads((ROOT/'authorization.json').read_text());state=json.loads((E/'run/state.json').read_text());ledger=json.loads((E/'run/ledger.json').read_text())
rows=state['rows'];by={r['instance_id']:r for r in rows};delivered=[r for r in rows if r['delivery_success']];audited=[r for r in rows if r['fallback'] is not None]
assert [r['instance_id'] for r in rows]==auth['trial_ids'][:len(rows)]
assert len(by)==len(rows) and ledger['limit_microcny']==5000000
assert all(c['context'].startswith('locator:') for c in ledger['calls'])
assert all(r['coding_agent']=='未运行' and r['harness']=='未运行' for r in rows)
rules={rule:sum(rule in r['violation_rules'] for r in rows) for rule in ['R1','R2','R3','R4']}
details=collections.Counter(v.split('_')[0] for r in rows for v in r['violation_details'])
costs=[r['metered_cny'] for r in rows]
summary=dict(status=state['status'],binding=auth['v81_binding'],planned=24,attempted=len(rows),unrun=24-len(rows),delivered=len(delivered),delivery_success_rate=len(delivered)/24,
 raw_compliant=sum(r['raw_compliant'] is True for r in rows),fallback=sum(r['fallback'] is True for r in rows),fallback_denominator=len(delivered),fallback_rate=sum(r['fallback'] is True for r in rows)/len(delivered) if delivered else None,
 validator_error_count=sum(bool(r['validator_error']) for r in rows),rule_case_counts=rules,rule_detail_counts={k:details[k] for k in rules},
 delivered_unread_mark_count=sum(r['delivered_marks_unread'] is True for r in rows),requests=len(ledger['calls']),received_requests=sum(c['status']=='received' for c in ledger['calls']),
 prompt_tokens=sum(r['prompt_tokens'] for r in rows),completion_tokens=sum(r['completion_tokens'] for r in rows),metered_cny=sum(costs) if all(c is not None for c in costs) else None,cost_upper_cny=sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in ledger['calls'])/1e6,
 wall_seconds=state['finished_at']-state['started_at'],locator_seconds=sum(r['locator_seconds'] or 0 for r in rows),coding_agent='未运行',harness='未运行',resolved='未运行',holdout='未运行',global_stop_reason=state.get('global_stop_reason'),further_runs_authorized=False,
 pricing_note='Provider usage with frozen 2026-11-17 cache/peak schedule, not reconciled provider invoice; peak no-cache upper bound enforces 5 CNY cap')
assert summary['cost_upper_cny']<=5
cols=['instance_id','status','delivery_success','raw_compliant','fallback','violation_rules','violation_details','validator_error','raw_marks_unread','delivered_marks_unread','requests','received_requests','prompt_tokens','completion_tokens','metered_cny','cost_upper_cny','locator_seconds','wall_seconds','error']
with (D/'precheck-per-task.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for i in auth['trial_ids']:
  if i not in by:w.writerow(dict(instance_id=i,**{c:'未运行' for c in cols[1:]}));continue
  r=by[i];out={c:r.get(c) for c in cols};out['violation_rules']=';'.join(out['violation_rules']);out['violation_details']=';'.join(out['violation_details']);w.writerow(out)
images=[json.loads((E/'run/images'/r['instance_id']/'image.json').read_text()) for r in rows if (E/'run/images'/r['instance_id']/'image.json').exists()]
summary['image_pull_seconds']=sum(x['pull_elapsed_seconds'] for x in images if not x['preexisting'])
summary['new_image_count']=sum(not x['preexisting'] for x in images)
cache=json.loads((E/'cache-retention.json').read_text())
summary['cached_for_reuse']=sum(x['canonical_restored'] for x in cache['images'])
summary['images_removed_before_retention']=cache['already_removed']
(D/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(D/'precheck-status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
lines=['# dev24 C(v8.1) 仅定位预检', '',f"冻结 binding：`{summary['binding']}`。",'',
 f"执行 {len(rows)}/24 题；成功交付 {len(delivered)}/24（{summary['delivery_success_rate']:.1%}）。",
 f"原回答合规 {summary['raw_compliant']} 题；回退 {summary['fallback']}/{len(delivered)}；validator_error {summary['validator_error_count']}。",
 f"R1/R2/R3/R4 触发题数：{rules}；逐条违规计数：{summary['rule_detail_counts']}（同一题可能触发多个规则）。",
 f"请求 {summary['requests']} 次；输入/输出 token：{summary['prompt_tokens']:,}/{summary['completion_tokens']:,}。",
 f"API 计量费用 {summary['metered_cny']} 元；保守费用上界 {summary['cost_upper_cny']:.6f} 元，低于 5 元。费用依据冻结单价和 provider usage，未核对账单。",
 f"运行总耗时 {summary['wall_seconds']:.1f} 秒（含镜像/源码准备），定位阶段累计 {summary['locator_seconds']:.1f} 秒。",'',
 '本轮只运行定位器；Coding Agent、harness、resolved、空补丁率、首次编辑：**未运行**。A/B 未重跑，holdout 50 未接触。失败无自动重试。保守回退按固定模板交付，不再二次调用 violations()。',
 '本轮保留原 v8 提示词和配置；改动仅在校准策略及测试。候选预测不自动纠错；成功交付不代表定位正确或任务 resolved。dev24 仅作开发参考，不下最终效果结论。','',
 '## 逐题结果','','| 题目 | 交付 | 原回答合规 | 回退 | 规则 | validator_error | 未读完（交付） | 请求 | token 入/出 | 计量元 | 定位秒 |','|---|---|---|---|---|---|---|---:|---:|---:|---:|']
for i in auth['trial_ids']:
 if i not in by:lines.append(f'| {i} | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 |');continue
 r=by[i];yes=lambda x:'是' if x is True else ('否' if x is False else '未产出')
 cost=f"{r['metered_cny']:.6f}" if r['metered_cny'] is not None else '未知'
 secs=f"{r['locator_seconds']:.1f}" if r['locator_seconds'] is not None else '未运行'
 lines.append(f"| {i} | {yes(r['delivery_success'])} | {yes(r['raw_compliant'])} | {yes(r['fallback'])} | {','.join(r['violation_rules']) or '无'} | {r['validator_error'] or '无'} | {yes(r['delivered_marks_unread'])} | {r['requests']} | {r['prompt_tokens']}/{r['completion_tokens']} | {cost} | {secs} |")
lines += ['',f"镜像新下载 {summary['new_image_count']} 个，累计下载/解包 {summary['image_pull_seconds']:.1f} 秒；已保留并恢复原标签、供下次复用 {summary['cached_for_reuse']} 个。用户要求保留缓存前已清理的镜像：{', '.join(cache['already_removed'])}。没有为缓存而重新下载这些镜像。"]
lines+=['','requests-2317：本轮未跑 harness，证书问题没有重新评分，历史原评分保持不变。','', '云端密钥删除与关机不计费状态见 final-cloud-audit.json、shutdown-receipt.json 和关机截图。']
(D/'REPORT_ZH.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
