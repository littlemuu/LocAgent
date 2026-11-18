"""Exactly one explicitly approved recovery, sharing the original CNY 1 cap."""
from decimal import Decimal
import fcntl
import json
import os
import sqlite3

from locagent_service import bailian_contract as c
from locagent_service.bailian_live import (ROOT,AUTHORITY,Journal,engine_hashes,validate_manifest,
                                         sha,exchange,ORIGIN,WORKSPACE)
from locagent_service.bailian_config import load_env_file

RECOVERY_APPROVAL='Sentinel_f333a77eb8808191b7258386500ac2d3'
PARENT_HASH='0f7a528612306d2fa6d3047520b6c279ebdcca0e1edb6f615530dbf3c5fdd36b'
RECOVERY=ROOT/'outputs/bailian-recovery-once-20261015'
PLAN=ROOT/'outputs/bailian-recovery-once-manifest.json'
LOCK=ROOT/'outputs/bailian-recovery-once-20261015.lock'


def combined_cost(old_reserved, new_inputs):
    old=Decimal(str(old_reserved))
    if not old.is_finite() or old!=Decimal('0.262144'):
        raise ValueError('Parent unknown reservation must remain held')
    total=old+(c.reservation(new_inputs) if new_inputs else Decimal(0))
    if total>c.CAP:raise ValueError('Combined original and recovery budget exceeded')
    return total


def parent_snapshot():
    paths=[ROOT/'outputs/bailian-frozen-manifest.json',ROOT/'outputs/bailian-live-20261015.lock',
           AUTHORITY/'manifest.json',AUTHORITY/'authority.json',AUTHORITY/'ledger.sqlite']
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('Parent evidence unavailable')
    hashes={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in paths}
    raw=paths[0].read_bytes()
    if sha(raw)!=PARENT_HASH:raise ValueError('Wrong parent experiment')
    # Read-only, no WAL/journal writes or migration of the old ledger.
    with sqlite3.connect('file:'+str(AUTHORITY/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
        calls=db.execute('SELECT id,n,state,http_status,response_hash,tokens FROM calls').fetchall()
        run=db.execute('SELECT manifest_hash,state FROM run').fetchall()
    if calls!=[(0,16,'unknown',200,'56031aa97ee99715dc57f0e1092b829843b14fab5223f7faf2b23288e3becd2e',None)] or run!=[(PARENT_HASH,'halted')]:
        raise ValueError('Parent unresolved state changed; requires review')
    return json.loads(raw),hashes


def recovery_manifest(old, hashes):
    result=json.loads(c.canonical(old))
    result['engine_files']=engine_hashes()
    result['recovery']={'approval':RECOVERY_APPROVAL,'parent_manifest_sha256':PARENT_HASH,
                        'parent_file_hashes':hashes,'parent_unknown_reserved_cny':'0.262144',
                        'full_recovery_reserved_cny':'0.688128','combined_cap_cny':'1',
                        'combined_full_reservation_cny':str(combined_cost('0.262144',42)),
                        'first_16_documents_explicitly_repeat_once':True}
    return result


def prepare_recovery():
    old,hashes=parent_snapshot()
    m=recovery_manifest(old,hashes);requests=validate_manifest(m)
    if sum(x['count'] for x in requests)!=42:raise ValueError('Fixed membership changed')
    with PLAN.open('xb') as f:
        f.write(c.canonical(m));f.flush();os.fsync(f.fileno())
    return {'manifest_sha256':sha(c.canonical(m)),**m['recovery']}


def validate_recovery():
    old,hashes=parent_snapshot()
    m=json.loads(PLAN.read_bytes())
    if m!=recovery_manifest(old,hashes):raise ValueError('Recovery content or parent binding changed')
    from importlib.metadata import version
    if m['package_versions']!={name:version(name) for name in ('bm25s','PyStemmer','psycopg')}:
        raise ValueError('Dependency version changed')
    return m,validate_manifest(m)


def run_recovery(*,first_only=False):
    if ROOT.is_symlink() or (ROOT/'outputs').is_symlink() or RECOVERY.is_symlink():
        raise ValueError('Unsafe authority path')
    m,requests=validate_recovery()
    fd=os.open(LOCK,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'r+') as held:
        fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
        binding=c.canonical({'approval':RECOVERY_APPROVAL,'manifest_sha256':sha(c.canonical(m))}).decode()
        previous=held.read()
        if (previous and previous!=binding) or bool(previous)!=RECOVERY.exists():
            raise ValueError('Recovery authority missing or changed; no new round permitted')
        config=load_env_file(ROOT/'.env.bailian.local')
        if c.endpoint(config.get('DASHSCOPE_WORKSPACE_ID'),config.get('DASHSCOPE_API_HOST'))!=ORIGIN+c.PATH:
            raise ValueError('Configured host differs from approved workspace')
        journal=Journal(RECOVERY,m,requests,create=not RECOVERY.exists())
        if not previous:held.write(binding);held.flush();os.fsync(held.fileno())
        for index in range(len(requests)):
            # Parent unchanged + cumulative new reservations checked before every
            # step, including cached results. Unknown child rows block all steps.
            validate_recovery()
            with journal.db() as db:rows=journal.audit(db)
            inputs=sum(row[2] for row in rows)
            if index>=len(rows):inputs+=requests[index]['count']
            total=combined_cost('0.262144',inputs)
            journal.step(index,lambda body:exchange(body,config))
            print(json.dumps({'recovery':journal.report(),'combined_retained_cny':str(total)}),flush=True)
            if first_only:return journal.report()
        if not (RECOVERY/'completed.json').exists():journal.write_once('completed.json',c.canonical(journal.report()))
        return journal.report()
