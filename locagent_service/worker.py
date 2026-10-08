"""One supervised, fresh engine process per attempt; no shared graph globals."""
import argparse
import ctypes
import multiprocessing as mp
import os
import json
from pathlib import Path
import tempfile
import signal
import time
from threading import Event
from uuid import uuid4

from locagent_service.config import Settings
from locagent_service.store import StateConflict, TaskStore



class ResultMailbox:
    """Child writes privately, fsyncs, then atomically publishes a bounded JSON result."""
    MAX_BYTES=16*1024*1024

    def __init__(self,directory):
        self.directory=Path(directory)
        self.ready=self.directory/'ready.json'

    def send(self,value):
        payload=json.dumps(value).encode()
        if len(payload)>self.MAX_BYTES:
            raise ValueError('Result exceeds local handoff limit')
        partial=self.directory/'partial.json'
        with partial.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        partial.replace(self.ready)

    def receive(self):
        if self.ready.stat().st_size>self.MAX_BYTES:
            raise ValueError('Invalid result size')
        return json.loads(self.ready.read_bytes())

    def close(self):
        pass


def execute(request, channel, parent_pid):
    # Linux PDEATHSIG prevents an orphan engine from continuing after supervisor SIGKILL.
    if os.name == 'posix':
        libc = ctypes.CDLL(None)
        if libc.prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent_pid:
            os._exit(70)
    try:
        from locagent_service.models import CreateTask
        from locagent_service.sources import localize
        from util.localization_contract import LocalizationError
        request = CreateTask.model_validate(request)
        result = localize(request)
        channel.send(('completed',result.to_dict()))
    except Exception as exc:
        from util.localization_contract import LocalizationError
        error = exc.to_dict() if isinstance(exc,LocalizationError) else {
            'code':'execution_error','message':'Localization execution failed'}
        channel.send(('failed',error))
    finally:
        channel.close()


def stop_child(child):
    if child.is_alive():
        child.terminate()
        child.join(2)
    if child.is_alive():
        child.kill()
    child.join(5)


def run_one(store, worker_id, *, lease_seconds=15, stopping=None, executor=execute):
    claim = store.claim_next(worker_id,lease_seconds)
    if claim is None:
        return False
    context = mp.get_context('spawn')
    directory=tempfile.TemporaryDirectory(prefix='locagent-attempt-')
    mailbox=ResultMailbox(directory.name)
    child = context.Process(target=executor,args=(claim.request,mailbox,os.getpid()),daemon=True)
    try:
        child.start()
        tick = min(1.0,lease_seconds/3)
        while True:
            # Renewal also detects cancellation; expiration cannot be resurrected.
            store.heartbeat(claim,lease_seconds)
            if stopping is not None and stopping.is_set():
                stop_child(child)
                store.interrupt(claim,'worker_stopped')
                break
            if mailbox.ready.exists():
                status, payload = mailbox.receive()
                if status == 'completed':
                    store._finish(claim,status,payload,None)
                else:
                    # A real provider error can mean the remote operation completed.
                    if claim.request.get('source_id','demo-v1') != 'demo-v1':
                        store.interrupt(claim,'outcome_unknown')
                    else:
                        store._finish(claim,'failed',None,payload)
                break
            if not child.is_alive():
                # Recheck after observing exit: the child may have just published its result.
                if mailbox.ready.exists():
                    continue
                store.interrupt(claim,'worker_crashed')
                break
            time.sleep(tick)
    except StateConflict:
        # Deadline, cancellation or another claim won. Never write over its decision.
        stop_child(child)
        store.recover()
    finally:
        # Includes DB disconnect and failures between provider return and persistence.
        if child.pid is not None:
            stop_child(child)
        directory.cleanup()
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-interval',type=float,default=0.5)
    parser.add_argument('--lease-seconds',type=float,default=15)
    parser.add_argument('--worker-id',default=f'worker-{os.getpid()}-{uuid4().hex[:8]}')
    args=parser.parse_args()
    if not 0.05 <= args.poll_interval <= 60 or not 0.2 <= args.lease_seconds <= 300:
        parser.error('Invalid poll or lease interval')
    stopping=Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda signum,frame:stopping.set())
    store=TaskStore(Settings.from_env())
    store.check_ready()
    while not stopping.is_set():
        try:
            found=run_one(store,args.worker_id,lease_seconds=args.lease_seconds,stopping=stopping)
        except Exception:
            # No replay here: recovery requires lease expiry and a safe source policy.
            if args.once:
                raise SystemExit('Worker storage unavailable; inspect persisted task state') from None
            stopping.wait(args.poll_interval)
            continue
        if args.once:
            break
        if not found:
            stopping.wait(args.poll_interval)


if __name__ == '__main__':
    main()
