"""One-response description pair, exact immutable payloads, no tool execution or retry."""
import argparse,hashlib,json,os,sqlite3,sys
from datetime import timedelta
from pathlib import Path
from readonly_agent.authority import Authority,Admission,now,private,save_new
from readonly_agent.core import digest,encoded,runtime_identity
from readonly_agent.journal import Ledger
from readonly_agent.deepseek_wire import RESERVATION,MODEL,normalize,WireProtocolError
from readonly_agent.live_transport import exchange_live
ROOT=Path(__file__).resolve().parents[2]
STORE=ROOT/'authority-choice-pair'
FROZEN=ROOT/'choice_pair/v2/manifest.json'
DRAFT=ROOT/'verification/retrieval-choice-state-v1'
INPUTS={'baseline':'control','retrieval':'candidate'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def request(arm):return encoded(json.loads((DRAFT/f'diagnostic-{INPUTS[arm]}-request.json').read_text()))
def candidate():
 inputs={a:request(a) for a in INPUTS}
 c=json.loads(inputs['baseline']);t=json.loads(inputs['retrieval']);t['tools'][3]['function']['description']=c['tools'][3]['function']['description'];assert t==c
 for body in inputs.values():
  q=json.loads(body)
  assert len(body)<=65536 and q['model']==MODEL and q['max_tokens']==2048 and q['tool_choice']=='auto'
  assert q['temperature']==0 and q['thinking']=={'type':'disabled'}
 return {'version':2,'mode':'offline_preparation','authorization':'not_granted','kind':'one_response_description_pair',
  'model':MODEL,'endpoint':'https://api.deepseek.com/chat/completions','arms':['baseline','retrieval'],'arm_meanings':INPUTS,
  'max_requests_per_arm':1,'max_requests_total':2,'budget_micro_cny':5_000_000,'reservation_micro_cny':RESERVATION,
  'full_reservations_micro_cny':2*RESERVATION,'currency':'CNY','input_ceiling':2,'output_ceiling':8,
  'runtime_hash':runtime_identity(),'driver_sha256':sha(Path(__file__)),'dependency_lock_sha256':sha(ROOT/'requirements-openhands.lock'),
  'payload_sha256':{a:hashlib.sha256(b).hexdigest() for a,b in inputs.items()},
  'source_draft_sha256':sha(DRAFT/'draft-experiment.json'),'tool_execution':False,'retry':False,'resume':False,
  'interpretation':'Constructed historical checkpoint; one response per wording, fixed control-first order; not natural trajectory, not causal estimate.'}
def frozen():
 p=json.loads(FROZEN.read_text())
 if p!=candidate():raise PermissionError('pair_inputs_or_code_changed')
 return p

class PairAuthority(Authority):
 def __init__(self,root=STORE):super().__init__(root)
 def approve(self,plan,h,*,consent,currency,input_ceiling,output_ceiling,all_charges_included):
  if plan!=frozen() or digest(plan)!=h or consent!=f'APPROVE CHOICE {h} CNY 5' or (currency,input_ceiling,output_ceiling,all_charges_included)!=('CNY','2','8',True):raise PermissionError('pair_scope_price_confirmation_required')
  self.root.mkdir(mode=0o700,parents=True,exist_ok=True);private(self.root,True)
  folder=self.folder(h);folder.mkdir(mode=0o700,exist_ok=False);start=now()
  save_new(folder/'grant.json',{'kind':'choice_pair','plan':plan,'plan_hash':h,'consent':consent,'currency':currency,'input_ceiling':input_ceiling,'output_ceiling':output_ceiling,'all_charges_included':True,'approved_at':start.isoformat(),'expires_at':(start+timedelta(hours=24)).isoformat(),'authority_root':str(self.root),'run_dir':str(folder/'run')})
 def read(self,h,*,fresh=True):
  from datetime import datetime
  folder=self.folder(h);private(self.root,True);private(folder,True);private(folder/'grant.json');r=json.loads((folder/'grant.json').read_text())
  if r['kind']!='choice_pair' or r['plan_hash']!=h or digest(r['plan'])!=h or r['consent']!=f'APPROVE CHOICE {h} CNY 5' or r['authority_root']!=str(self.root) or r['run_dir']!=str(folder/'run') or (r['currency'],r['input_ceiling'],r['output_ceiling'],r['all_charges_included'])!=('CNY','2','8',True):raise PermissionError('pair_grant_changed')
  if fresh:
   start,end=map(datetime.fromisoformat,(r['approved_at'],r['expires_at']))
   if not start<=now()<end or end-start>timedelta(hours=24) or r['plan']!=frozen():raise PermissionError('pair_expired_or_changed')
  return r

class PairLedger(Ledger):
 @classmethod
 def create(cls,path,plan,*,admission):
  if type(admission) is not Admission or admission.plan_hash!=digest(plan) or plan!=frozen():raise PermissionError('exact_pair_admission_required')
  path=Path(path).absolute();admission.validate(path)
  if path!=path.resolve() or path.exists():raise PermissionError('fresh_pair_ledger_required')
  path.parent.mkdir(mode=0o700,parents=True,exist_ok=False)
  fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
  with sqlite3.connect(path) as db:
   db.execute('PRAGMA synchronous=FULL')
   db.executescript('''CREATE TABLE run(plan TEXT NOT NULL,hash TEXT NOT NULL,owner TEXT NOT NULL,mode TEXT NOT NULL,halted INTEGER NOT NULL DEFAULT 0,reason TEXT);
CREATE TABLE arms(name TEXT PRIMARY KEY,token TEXT NOT NULL,finished INTEGER NOT NULL DEFAULT 0);
CREATE TABLE calls(id INTEGER PRIMARY KEY,arm TEXT NOT NULL,turn INTEGER NOT NULL,request BLOB NOT NULL,request_hash TEXT NOT NULL,status TEXT NOT NULL,reservation INTEGER NOT NULL,response BLOB,response_hash TEXT,http_status INTEGER,complete INTEGER,cost INTEGER,transport_started INTEGER NOT NULL DEFAULT 0,UNIQUE(arm,turn));''')
   db.execute('INSERT INTO run(plan,hash,owner,mode) VALUES(?,?,?,?)',(encoded(plan).decode(),digest(plan),str(path),'live'))
  fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
  return cls(path,digest(plan))
 def validate(self,db):
  plan,state,calls,spent,pending=super().validate(db)
  if plan!=frozen():raise PermissionError('pair_ledger_plan_changed')
  if [r['arm'] for r in calls]!=['baseline','retrieval'][:len(calls)]:raise PermissionError('pair_arm_order')
  if any(r['request_hash']!=plan['payload_sha256'][r['arm']] for r in calls):raise PermissionError('pair_payload_changed')
  return plan,state,calls,spent,pending
 def reserve(self,arm,token,data):
  if data!=request(arm):raise PermissionError('exact_pair_payload_required')
  # Transport order is additionally validated transactionally before helper launch.
  return super().reserve(arm,token,data)

def selected_tools(raw, offered):
 """Extract advertised SDK summary before strict Action validation; execute nothing.

 Unlike the SDK's fallback for invalid summaries, require the advertised string
 type. Unadvertised security_risk and all other extras stay strict errors.
 Preserve original wire arguments separately from adapted Action arguments.
 """
 from readonly_agent.openhands_tools import QueryAction,ReadAction,CursorAction
 from readonly_agent.deepseek_wire import strict_json
 schemas={t['function']['name']:t['function']['parameters'] for t in offered}
 native=normalize(raw,set(schemas))
 originals=raw['choices'][0]['message']['tool_calls']
 chosen=[]
 for call,original in zip(native.message.tool_calls,originals,strict=True):
  args=strict_json(call.arguments)
  metadata={}
  if 'summary' in args:
   if schemas[call.name]['properties'].get('summary',{}).get('type')!='string' or not isinstance(args['summary'],str):
    raise ValueError('invalid_or_unadvertised_summary')
   metadata['summary']=args.pop('summary')
  if call.name in ('locagent_retrieve','search_text'):QueryAction.model_validate(args)
  elif call.name=='read_file':ReadAction.model_validate(args)
  elif call.name=='list_files':CursorAction.model_validate(args)
  elif call.name!='finish':raise ValueError('unsupported_action')
  chosen.append({'id':call.id,'name':call.name,'arguments':args,
   'sdk_metadata':metadata,'wire_arguments':strict_json(original['function']['arguments'])})
 return chosen

def execute(admission,key,transport=exchange_live):
 record=admission.validate();root=Path(record['run_dir']);ledger=PairLedger.create(root/'ledger.sqlite',record['plan'],admission=admission)
 save_new(root/'execution.json',{'mode':'live' if transport is exchange_live else 'mocked_transport','tool_execution':False})
 rows=[];ticket=None
 try:
  for arm in INPUTS:
   token=ledger.claim(arm);body=request(arm);ticket=ledger.reserve(arm,token,body)
   receipt=transport(body,key,admission=admission,ledger=ledger,reservation=ticket,enabled=True)
   ledger.received(ticket,receipt);raw=ledger.settle(ticket)
   chosen=selected_tools(raw,json.loads(body)['tools'])
   rows.append({'variant':INPUTS[arm],'chosen_tools':chosen,'retrieval_selected':any(c['name']=='locagent_retrieve' for c in chosen),'request_bytes':len(body),'usage':raw['usage'],'tool_execution':False})
   ledger.finish(arm,token);ticket=None
  result={'status':'completed','rows':rows,'budget':ledger.summary(),'tool_execution':False,'quality_measured':False,'causal_effect_estimated':False}
  save_new(root/'result.json',result);return result
 except BaseException as error:
  ledger.halt(ticket,error.code if isinstance(error,WireProtocolError) else type(error).__name__)
  result={'status':'halted','reason':ledger.summary()['reason'],'rows':rows,'budget':ledger.summary(),'tool_execution':False,'retry':False}
  save_new(root/'stopped.json',result);return result
 finally:key=None

def run(h,authority=None):
 a=authority or PairAuthority();a.read(h)
 if (a.folder(h)/'claim.json').exists():raise PermissionError('pair_already_consumed')
 if not sys.stdin.isatty():raise PermissionError('interactive_terminal_required')
 from readonly_agent.local_env import load_selected_key
 key=load_selected_key()
 try:return execute(a.claim(h),key)
 finally:key=None

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','authorize','run','status']);p.add_argument('--hash');p.add_argument('--consent');p.add_argument('--currency');p.add_argument('--input-ceiling');p.add_argument('--output-ceiling');p.add_argument('--all-charges-included',action='store_true');args=p.parse_args();a=PairAuthority()
 if args.action=='freeze':
  plan=candidate();FROZEN.parent.mkdir(mode=0o700,parents=True,exist_ok=False);save_new(FROZEN,plan);print(digest(plan))
 elif args.action=='authorize':a.approve(frozen(),args.hash,consent=args.consent,currency=args.currency,input_ceiling=args.input_ceiling,output_ceiling=args.output_ceiling,all_charges_included=args.all_charges_included);print('Pair grant recorded; no key or model request.')
 elif args.action=='run':
  result=run(args.hash);print(json.dumps(result,ensure_ascii=False,indent=2))
  if result['status']!='completed':raise SystemExit(1)
 else:
  r=a.read(args.hash,fresh=False);path=Path(r['run_dir'])/'ledger.sqlite';print(json.dumps(PairLedger(path,args.hash).summary() if path.exists() else {'claimed':(a.folder(args.hash)/'claim.json').exists(),'started':False},indent=2))
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('Stopped: '+type(error).__name__+'. No automatic retry.',file=sys.stderr);raise SystemExit(1) from None
