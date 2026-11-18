"""Offline shard builder; fresh source/index objects per task, no target imports."""
import contextlib,gc,json,signal,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from experiments.cohort_preflight.entry import read,sha,load_entry,save
from experiments.cohort_preflight import body
from locagent_service.offline import offline_engine

def main():
    job=read(sys.argv[1]);out=Path(job['output'])
    if any(sha(ROOT/n)!=h for n,h in job['code'].items()):raise ValueError('builder_code_changed')
    def expired(*args):raise TimeoutError('offline_case_deadline')
    signal.signal(signal.SIGALRM,expired)
    with contextlib.redirect_stdout(sys.stderr),offline_engine():
        for i,row in enumerate(job['cases']):
            start=time.monotonic();signal.alarm(120)
            try:
                value,snapshot=load_entry(row['entry'],row['entry_sha256'],check_engine=i==0)
                directory=out/'body'/row['id']
                att=body.build(snapshot,directory)
                loaded,_=body.load(snapshot,directory,sha(directory/'attestation.json'))
                result={'id':row['id'],'status':'ready','snapshot':snapshot.identity,
                    'entry_sha256':row['entry_sha256'],'body_directory':str(directory),
                    'body_attestation_sha256':sha(directory/'attestation.json'),'chunks':att['chunks'],
                    'body_version':body.VERSION,'model_calls':0,'seconds':round(time.monotonic()-start,3)}
                del loaded,snapshot,att
            except Exception as e:
                result={'id':row['id'],'status':'failed','error_type':type(e).__name__,
                    'error':str(e)[:160],'model_calls':0,'seconds':round(time.monotonic()-start,3)}
            finally:signal.alarm(0)
            save(out/'body-status'/(row['id']+'.json'),result)
            print(f"{job['shard']}: {i+1}/{len(job['cases'])} {result['status']}",file=sys.stderr,flush=True)
            gc.collect()
            if result['status']!='ready':break  # no retry, preserve partial shard
    print('Offline shard completed',flush=True)

if __name__=='__main__':main()
