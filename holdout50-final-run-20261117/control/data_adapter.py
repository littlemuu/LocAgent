"""Explicitly authorized dataset boundary; no monkeypatch of frozen modules.
Evaluator data is loaded only by evaluator/contract processes. Public projection
reads only four public columns; reference patches never enter agent inputs.
"""
import os
from pathlib import Path
from support import P,F,IDS,PARQUET,sha,load,durable

class Dataset:
 def __init__(self,scope):
  if scope not in ('dev24','holdout50'):raise PermissionError('unknown_dataset_scope')
  self.scope=scope
  if scope=='dev24':
   self.manifest=load(F/'baseline/data/dev24/manifest.json')
   self.ids=[r['instance_id'] for r in self.manifest['instances']]
  else:
   assert sha(P/'data/ids.txt')==IDS,'holdout_id_hash_mismatch'
   self.manifest=load(P/'data/manifest.json')
   self.ids=(P/'data/ids.txt').read_text().splitlines()
   assert self.ids==[r['instance_id'] for r in self.manifest['instances']]
   assert self.manifest['ids_sha256']==IDS and len(self.ids)==50 and len(set(self.ids))==50
  self._rows=None
 def allow(self,identifier,smoke=False):
  allowed=self.manifest['smoke_ids'] if self.scope=='dev24' and smoke else self.ids
  if identifier not in allowed:raise PermissionError('outside_selected_dataset_scope')
 def evaluator_rows(self):
  if self._rows is None:
   if self.scope=='dev24':
    source=F/'baseline/data/dev24/content/evaluator.json';receipt=load(source.parent/'receipt.json')
    assert sha(source)==receipt['files']['evaluator.json'],'evaluator_content_changed'
    rows=load(source)
   else:
    source=P/'data/sealed-verified-test.parquet'
    assert sha(source)==PARQUET,'sealed_dataset_changed'
    import pyarrow.parquet as pq
    # Only evaluator loads scoring columns; output and model payloads never include them.
    rows=pq.read_table(source,filters=[('instance_id','in',self.ids)]).to_pylist()
   assert len(rows)==len(self.ids) and {r['instance_id'] for r in rows}==set(self.ids),'evaluator_membership_changed'
   metadata={r['instance_id']:r for r in self.manifest['instances']}
   for r in rows:
    m=metadata[r['instance_id']]
    assert r['repo']==m['repo'] and r['base_commit']==m['base_commit'],'evaluator_metadata_changed'
   self._rows=rows
  return self._rows
 def row(self,identifier):
  self.allow(identifier)
  return next(r for r in self.evaluator_rows() if r['instance_id']==identifier)

def active():
 scope=os.environ.get('LOCAGENT_EVAL_SCOPE')
 if scope not in ('dev24','holdout50'):raise PermissionError('explicit_dataset_scope_required')
 return Dataset(scope)

def prepare_public():
 d=Dataset('holdout50');source=P/'data/sealed-verified-test.parquet';assert sha(source)==PARQUET
 import pyarrow.parquet as pq
 columns=['instance_id','repo','base_commit','problem_statement']
 rows=pq.read_table(source,columns=columns,filters=[('instance_id','in',d.ids)]).to_pylist()
 assert len(rows)==50 and {r['instance_id'] for r in rows}==set(d.ids)
 mm={r['instance_id']:r for r in d.manifest['instances']}
 for r in rows:
  assert set(r)==set(columns) and r['base_commit']==mm[r['instance_id']]['base_commit'] and r['repo']==mm[r['instance_id']]['repo']
 by={r['instance_id']:r for r in rows};rows=[by[i] for i in d.ids]
 durable(P/'data/public.json',rows)
 durable(P/'public-data-receipt.json',{'ids_sha256':IDS,'source_sha256':PARQUET,'public_sha256':sha(P/'data/public.json'),'columns':columns,'rows':50,'scoring_columns_read':False})

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--prepare-public',action='store_true');a=p.parse_args()
 if a.prepare_public:prepare_public();print('Public projection ready: 50 rows; no scoring fields.')
