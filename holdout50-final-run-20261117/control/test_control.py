"""Offline invariants for paid-run safety; no calls to frozen agent or cloud."""
import tempfile,time
from pathlib import Path
from support import P,load,claim
from run_once import Runner
from analyze import exact,holm,pairs

def main():
 tasks=load(P/'execution-order.json')['tasks'];assert len(tasks)==50
 for n,t in enumerate(tasks):assert t['number']==n+1 and t['arm_order']==[['A','B','C'],['B','C','A'],['C','A','B']][n%3]
 with tempfile.TemporaryDirectory() as td:
  r=Runner.__new__(Runner);r.out=Path(td);r.state={'steps':{}};r.save=lambda:None;count=[]
  r.once('stage',lambda:count.append(1) or {'status':'completed'})
  try:r.once('stage',lambda:count.append(2) or {'status':'completed'})
  except FileExistsError:pass
  else:raise AssertionError('duplicate_stage_executed')
  assert count==[1]
  claim(r.out/'once/uncertain',{'status':'started'})
  try:r.once('uncertain',lambda:count.append(3))
  except FileExistsError:pass
  else:raise AssertionError('uncertain_stage_reexecuted')
  def failed():raise RuntimeError('fixture_failure')
  assert r.once('failed',failed)['status']=='failed'
  assert r.once('independent-next',lambda:{'status':'completed'})['status']=='completed'
 assert exact(0,0)==1 and exact(5,0)==.0625 and exact(5,1)==.21875
 assert holm({'x':.01,'y':.02,'z':.8})=={'x':.03,'y':.04,'z':.8}
 rows=[{'instance_id':'i','arm':a,'resolved':v} for a,v in [('A',None),('B',False),('C',True)]]
 assert pairs(rows,['i'])['C_vs_A']['first_resolved_other_not']==['i']
 assert pairs(rows,['i'],True)['C_vs_A']['excluded_unscored']==['i']
 print('PASS: rotation, durable once, uncertain-stage prohibition, independent failure continuation, exact McNemar, Holm, missing-score policy. 0 API calls.')
if __name__=='__main__':main()
