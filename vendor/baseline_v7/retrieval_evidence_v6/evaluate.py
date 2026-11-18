"""Post-retrieval label audit only; never supplies gold to queries or ranking."""
import re
from experiments.cohort_preflight.entry import ROOT,read,save,sha

out=ROOT/'verification/retrieval-evidence-v6';result=read(out/'results.json')
binding={x['id']:x for x in read(ROOT/'verification/dev37-preparation-v4/scoring-only/gold-binding.json')}
rows=[]
for case in result['cases']:
    b=binding[case['id']];assert sha(b['original_label_path'])==b['original_label_hash']
    gold=b['gold']
    for q in case['rows']:
        nodes=[c['id'] for c in q['new_audit']['candidates']]
        first=q['new_first_page']['text']
        visible={int(n) for n in re.findall(r'^(\d+): ',first,re.M)}
        primary=q['new_audit']['candidates'][0] if nodes else None
        row={'id':case['id'],'batch':q['batch'],'query':q['query'],
             'old_first_gold_rank':next((i for i,n in enumerate(q['old_candidates'],1) if n in gold),None),
             'new_first_gold_rank':next((i for i,n in enumerate(nodes,1) if n in gold),None),
             'old_bytes':q['old_bytes'],'new_bytes':q['new_bytes'],'new_pages':len(q['new_pages']),
             'new_candidates':nodes,'new_primary':primary,
             'primary_implementation_in_first_page':q['primary_implementation_in_first_page'],
             'primary_body_lines_all_in_first_page':bool(primary and primary['implementation_start'] is not None and
                 all(n in visible for n in range(primary['implementation_start'],primary['end_line']+1))),
             'gold_read_only_after_retrieval':True}
        rows.append(row)
save(out/'evaluation.json',{'rows':rows,'selection':'exposed development queries; not independent tests',
                          'gold_never_supplied_to_retriever':True,'real_requests':0})
for row in rows:
    print(row['id'],row['query'],'gold rank',row['old_first_gold_rank'],'->',row['new_first_gold_rank'],
          'bytes',row['old_bytes'],'->',row['new_bytes'])
