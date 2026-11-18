"""Server-side exact filtering only: never download/read the full Verified parquet."""
import json,urllib.request,urllib.parse,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REV='c104f840cc67f8b6eec6f759ebc8b2693d585d4a'
def get(url):
 with urllib.request.urlopen(url,timeout=60) as r:return json.load(r)
def main():
 m=json.loads((ROOT/'data/dev24/manifest.json').read_text());ids={r['instance_id'] for r in m['instances']}
 before=get('https://huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified');assert before['sha']==REV,'dataset_revision_changed'
 # The filter service returned a public authentication timeout. Use exact pinned row offsets,
 # never ranges spanning unselected rows and never the full parquet.
 metadata_rows=json.loads((ROOT/'data/selection-metadata.json').read_text())
 offsets={r['instance_id']:i for i,r in enumerate(metadata_rows)}
 rows=[]
 for identifier in sorted(ids):
  url='https://datasets-server.huggingface.co/rows?'+urllib.parse.urlencode({'dataset':'princeton-nlp/SWE-bench_Verified','config':'default','split':'test','offset':offsets[identifier],'length':1})
  response=get(url)
  assert len(response['rows'])==1 and response['rows'][0]['row']['instance_id']==identifier,'unexpected_row_refuse'
  assert not response['rows'][0].get('truncated_cells')
  rows.append(response['rows'][0]['row'])
 after=get('https://huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified');assert after['sha']==REV
 metadata={r['instance_id']:r for r in m['instances']}
 for r in rows:assert all(r[k]==metadata[r['instance_id']][k] for k in ('repo','base_commit','created_at'))
 public=[{k:r[k] for k in ('instance_id','repo','base_commit','problem_statement')} for r in rows]
 target=ROOT/'data/dev24/content';target.mkdir(exist_ok=False)
 for name,value in [('public.json',public),('evaluator.json',rows)]:
  p=target/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
 receipt={'method':'HF exact single-row offsets from pinned metadata; revision checked before/after; expected ID checked; no full dataset download','revision':REV,'ids':sorted(ids),'fetched_rows':len(rows),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.glob('*.json')},'response_revision_header':'not supplied; moving viewer revision is checked against pinned repository before/after, row repo/base_commit/created_at cross-checked'}
 (target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Fetched exactly',len(rows),'exposed development rows; holdout rows requested: 0')
if __name__=='__main__':main()
