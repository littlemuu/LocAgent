import json,re,sys,collections
from pathlib import Path
P=Path(__file__).resolve().parents[1];lo,hi=map(int,sys.argv[1:3]);mode=sys.argv[3] if len(sys.argv)>3 else 'loop'
for x in json.loads((P/'delivery/review-packets.json').read_text()):
 if not lo<=x['number']<=hi:continue
 if mode=='C' and x['arm']!='C':continue
 print('\nEP',x['number'],x['instance_id'],x['arm'],'n',x['coding_requests'],'edits',[e['request'] for e in x['source_edit_events']])
 if mode=='C':
  print('LOC',json.dumps(x['localization'],ensure_ascii=False));print('PATCH',str(x['patch']));print('FIN',x['finished']);continue
 groups=collections.defaultdict(list)
 for t in x['sequence']:
  k=re.sub(r'0x[0-9a-fA-F]+','<addr>',t['result_tail']);k=re.sub(r'\b\d+\.\d+(?=s| seconds)','<time>',k);groups[k].append(t)
 if mode!='brief':print('SEQUENCE','; '.join(str(t['r'])+':'+str(t['args'].get('command',t['args'].get('path',t['tool']))).replace('\n',' ')[:90] for t in x['sequence']))
 for k,g in groups.items():
  if len(g)>=3:print('REPEAT_RESULT', [t['r'] for t in g],'EDIT',[t['r'] for t in g if t['edit']], 'OUT',k[-180:],'LAST_COMMAND',str(g[-1]['args'])[-120:])
 print('FIN',str(x['finished'])[:180])
