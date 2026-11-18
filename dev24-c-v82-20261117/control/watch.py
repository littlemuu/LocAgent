"""Read-only progress monitor; never launches/retries a paid run."""
import argparse,json,subprocess,sys,time
from pathlib import Path
P=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();last=None
while True:
 start=time.monotonic()
 r=subprocess.run([sys.executable,str(P/'control/cloud_io.py'),'status','--host',a.host],capture_output=True,text=True,timeout=45)
 if r.returncode:
  print(json.dumps({'monitor_error':r.stderr[-700:],'at':time.time()}),flush=True);break
 line=r.stdout.strip();data=json.loads(line)
 with (P/'delivery/progress.jsonl').open('a') as f:f.write(json.dumps(dict(data,observed_at=time.time()),ensure_ascii=False)+'\n')
 (P/'delivery/latest-progress.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 signature=(data['rows'],data['stage'],data['requests'],data['exit'])
 if signature!=last:print(line,flush=True);last=signature
 if data['exit'] is not None:break
 time.sleep(max(1,45-(time.monotonic()-start)))
