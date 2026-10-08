"""Fresh isolated Compose volume; real HTTP loop and SIGKILL recovery; retain volume."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    project='locagent-acceptance-'+uuid4().hex[:10]
    out=ROOT/'outputs/stage5'/project
    out.mkdir(parents=True)
    base=['docker','compose','-p',project,'-f',str(ROOT/'compose.yaml')]
    events=[]
    def command(*args,check=True):
        result=subprocess.run([*base,*args],cwd=ROOT,text=True,capture_output=True)
        with (out/'compose.log').open('a') as log:
            log.write(' '.join(args)+'\n'+result.stdout+result.stderr+'\n')
        if check and result.returncode:
            raise RuntimeError('Compose action failed; see isolated run log')
        return result
    def wait(client,task_id,state='completed',timeout=90):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            row=client.get('/tasks/'+task_id).json()
            if row['status']==state:return row
            if row['status'] in ('failed','cancelled','needs_review') and row['status']!=state:
                raise AssertionError(row.get('error'))
            time.sleep(0.1)
        raise AssertionError('Task state timeout')
    volume=project+'_pgdata'
    assert subprocess.run(['docker','volume','inspect',volume],capture_output=True).returncode!=0
    evidence={'project':project,'volume':volume,'empty_volume_before_start':True,'events':events}
    try:
        command('up','-d','--no-build','--wait','--wait-timeout','90')
        with httpx.Client(base_url='http://127.0.0.1:18080',trust_env=False,timeout=5) as client:
            assert client.get('/health').json()=={'status':'ok','schema_version':2}
            count=command('exec','-T','postgres','psql','-U','locagent','-d','locagent','-Atc',
                          'SELECT count(*) FROM locagent.tasks').stdout.strip()
            assert count=='0',count
            events.append({'clean_task_count':0})
            body={'problem_statement':'Compose task closure'}
            first=client.post('/tasks',json=body,headers={'Idempotency-Key':'compose-success'})
            assert first.status_code==202
            success=wait(client,first.json()['id'])
            assert success['result']['found_files']==['demo.py']
            again=client.post('/tasks',json=body,headers={'Idempotency-Key':'compose-success'})
            assert again.json()['id']==success['id']
            assert client.post('/tasks',json={'problem_statement':'different'},
                               headers={'Idempotency-Key':'compose-success'}).status_code==409
            events.append({'success_task':success['id'],'attempt':success['attempt'],'idempotency':True})
            failed=client.post('/tasks',json={'problem_statement':'failure',
                                            'demo_scenario':'provider_error'}).json()
            failure=wait(client,failed['id'],'failed')
            assert failure['error']['code']=='model_error'
            events.append({'failure_task':failure['id'],'error':'model_error'})
            # Stop the idle worker first; then create a task, restart, and kill after claim.
            command('stop','worker')
            crash=client.post('/tasks',json={'problem_statement':'Crash recovery','max_attempts':2}).json()
            command('start','worker')
            running=wait(client,crash['id'],'running')
            command('kill','-s','SIGKILL','worker')
            time.sleep(5.2)
            command('start','worker')
            recovered=wait(client,crash['id'])
            assert recovered['attempt']==2
            attempts=client.get('/tasks/'+crash['id']+'/attempts').json()
            assert [a['outcome'] for a in attempts]==['lease_expired','completed'],attempts
            events.append({'recovered_task':crash['id'],'attempts':attempts})
            # Actual database restart; history must survive; worker must reconnect.
            command('restart','postgres')
            until=time.monotonic()+30
            while time.monotonic()<until:
                try:
                    if client.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(0.25)
            assert client.get('/tasks/'+success['id']).json()==success
            newer=client.post('/tasks',json={'problem_statement':'After database restart'}).json()
            assert wait(client,newer['id'])['status']=='completed'
            events.append({'postgres_restart_preserved_history':True,'new_task':newer['id']})
        evidence['image']=subprocess.check_output(
            ['docker','image','inspect','locagent-service:local','--format','{{.Id}}'],text=True).strip()
        evidence['python']=command('exec','-T','worker','python','--version').stdout.strip()
        evidence['passed']=True
    finally:
        command('logs','--no-color',check=False)
        command('down','--timeout','10',check=False)  # Deliberately never --volumes.
        evidence['retained_volume']=subprocess.run(
            ['docker','volume','inspect',volume],capture_output=True).returncode==0
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
