"""Fixed, explicitly authorized single-document diagnostic. No resume or retries."""
from decimal import Decimal
from importlib.metadata import version
import json
import os
import sqlite3
from pathlib import Path

from locagent_service import bailian_contract as c
from locagent_service.bailian_live import ROOT, Journal, batches, engine_hashes, sha, exchange, ORIGIN, WORKSPACE
from locagent_service.bailian_config import load_env_file
from locagent_service.bailian_dataset import validate_dataset

APPROVAL='Sentinel_abb0aace377c81919fa44bb0aaac6c70'
FOLDER=ROOT/'outputs/bailian-single-diagnostic-20261015'
PLAN=ROOT/'outputs/bailian-single-diagnostic-manifest.json'
LOCK=ROOT/'outputs/bailian-single-diagnostic-20261015.lock'
OLD=Decimal('0.524288')
NEW=Decimal('0.016384')
TOTAL=Decimal('0.540672')


def parents():
    expected=json.loads((ROOT/'outputs/bailian-raw-capture-offline/after.json').read_bytes())
    current={}
    for path,digest in expected.items():
        p=Path(path)
        if p.is_symlink() or not p.is_file() or not p.is_relative_to(ROOT/'outputs'):
            raise ValueError('Historical evidence path changed')
        actual=sha(p.read_bytes())
        if actual!=digest:raise ValueError('Historical evidence changed')
        current[str(p.relative_to(ROOT))]=actual
    for folder,identity in [
        ('bailian-live-20261015','0f7a528612306d2fa6d3047520b6c279ebdcca0e1edb6f615530dbf3c5fdd36b'),
        ('bailian-recovery-once-20261015','34c3c005ea86d08aaff7bb8e4c48218fea062c86c2704ad63bc83e7edcea902c')]:
        p=ROOT/'outputs'/folder
        if sha((p/'manifest.json').read_bytes())!=identity:raise ValueError('Wrong historical manifest')
        with sqlite3.connect('file:'+str(p/'ledger.sqlite')+'?mode=ro&immutable=1',uri=True) as db:
            if db.execute('SELECT id,n,state FROM calls').fetchall()!=[(0,16,'unknown')]:raise ValueError('Historical reservation changed')
            if db.execute('SELECT manifest_hash,state FROM run').fetchall()!=[(identity,'halted')]:raise ValueError('Historical run changed')
    if c.reservation(32)!=OLD or c.reservation(1)!=NEW or OLD+NEW!=TOTAL or TOTAL>c.CAP:
        raise ValueError('Approved cumulative budget mismatch')
    return current


def expected_manifest():
    bindings=parents()
    original=json.loads((ROOT/'outputs/bailian-frozen-manifest.json').read_bytes())
    validate_dataset(original)
    if original['package_versions']!={name:version(name) for name in ('bm25s','PyStemmer','psycopg')}:
        raise ValueError('Dependency version changed')
    engines=engine_hashes()
    engines['locagent_service/bailian_single_diagnostic.py']=sha(Path(__file__).read_bytes())
    return {'version':1,'approval':APPROVAL,'purpose':'single-input-response-schema-diagnostic',
            'repo':original['repo'],'commit':original['commit'],
            'endpoint':c.endpoint(WORKSPACE,ORIGIN),'model':c.MODEL,'dimensions':1024,
            'document_parameters':c.request(['x'],'document')['parameters'],
            'documents':[original['documents'][0]],'questions':[],
            'parent_file_hashes':bindings,'engine_files':engines,
            'parent_unknown_reserved_cny':str(OLD),'reservation_cny':str(NEW),
            'combined_retained_cap_cny':str(TOTAL),'original_cap_cny':'1',
            'max_http_requests':1,'automatic_retries':0}


def prepare():
    if LOCK.exists() or FOLDER.exists():raise ValueError('Diagnostic already started; never repeat')
    m=expected_manifest()
    with PLAN.open('xb') as stream:
        stream.write(c.canonical(m));stream.flush();os.fsync(stream.fileno())
    return {'manifest_sha256':sha(c.canonical(m)),'input_count':1,'combined_cap_cny':str(TOTAL)}


def validate():
    if ROOT.is_symlink() or (ROOT/'outputs').is_symlink() or PLAN.is_symlink():raise ValueError('Unsafe path')
    m=json.loads(PLAN.read_bytes())
    if m!=expected_manifest():raise ValueError('Diagnostic manifest or code changed')
    requests=batches(m)
    if len(requests)!=1 or requests[0]['count']!=1 or requests[0]['role']!='document':raise ValueError('Single document required')
    return m,requests


def run():
    m,requests=validate()
    if LOCK.exists() or FOLDER.exists():raise ValueError('Diagnostic consumed or interrupted; never repeat')
    config=load_env_file(ROOT/'.env.bailian.local')
    if c.endpoint(config.get('DASHSCOPE_WORKSPACE_ID'),config.get('DASHSCOPE_API_HOST'))!=m['endpoint']:
        raise ValueError('Endpoint mismatch')
    fd=os.open(LOCK,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(c.canonical({'approval':APPROVAL,'manifest_sha256':sha(c.canonical(m))}));stream.flush();os.fsync(stream.fileno())
    directory=os.open(LOCK.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    journal=Journal(FOLDER,m,requests,create=True,approval=APPROVAL)
    validate()
    invoked=False
    def once(body):
        nonlocal invoked
        if invoked or body!=requests[0]['body']:raise ValueError('Transport replay or payload change refused')
        invoked=True
        return exchange(body,config)
    try:
        journal.step(0,once)
    except ValueError:
        pass  # Journal persists fixed diagnostic; never print provider exception text.
    finally:
        config.clear()
    # No transport is reachable after this single step. Inspect separately offline.
    parents()
    result={'approval':APPROVAL,'transport_invocations':int(invoked),
            'parent_unknown_reserved_cny':str(OLD),'combined_retained_cny':str(TOTAL),
            'journal':journal.report()}
    journal.write_once('completion.json',c.canonical(result))
    return result


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['prepare']:print(json.dumps(prepare()))
    elif sys.argv[1:]==['validate']:print(json.dumps({'valid':bool(validate())}))
    elif sys.argv[1:]==['run']:print(json.dumps(run()))
    else:raise SystemExit('Use prepare, validate, or run')
