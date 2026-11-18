"""Read only same-task historical B locator logs to corroborate source boundaries.
Never credits historical B reads as C evidence; never reads coding/harness outputs."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
cs=json.loads((OUT/'cases.json').read_text());wanted={c['instance_id'] for c in cs if c['fallback']};provenance=[]
for filename in ['first8-evidence-v4.tar.gz','remaining16-evidence-v5.tar.gz']:
 archive=ROOT/'dev24-completion-20261117-v5/delivery'/filename
 with tarfile.open(archive) as tar:
  members={m.name:m for m in tar.getmembers() if m.isfile()}
  for name,member in members.items():
   if not name.endswith('/locator/result.json'):continue
   identifier=name.split('/')[-3]
   if identifier not in wanted:continue
   parent=name[:-len('locator/result.json')];lp=parent+'localization.json'
   old=json.loads(tar.extractfile(members[lp]).read());current=json.loads((ROOT/'dev24-locator-v81-20261117/evidence/run/trial'/identifier/'localization.json').read_text())
   assert old['instance_id']==current['instance_id'] and old['base_commit']==current['base_commit']
   data=tar.extractfile(member).read();r=json.loads(data);dest=OUT/'reference-v5'/identifier;dest.mkdir(parents=True,exist_ok=True)
   (dest/'locator-result.json').write_bytes(data)
   blocks=[]
   for i,t in enumerate(r['tool_audit'],1):blocks.append(f"B TOOL {i}: {t['tool']}\nARGS: {json.dumps(t['arguments'],ensure_ascii=False)}\n{t['result'].get('text','')}\n")
   (dest/'tool-output.txt').write_text('\n'.join(blocks))
   provenance.append(dict(instance_id=identifier,base_commit=current['base_commit'],source_archive=str(archive),member=name,sha256=hashlib.sha256(data).hexdigest(),purpose='source-boundary reference only; NOT C read evidence'))
(OUT/'reference-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n');print('Read same-base historical B locator logs:',len(provenance))
