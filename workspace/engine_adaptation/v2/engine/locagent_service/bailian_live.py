"""Single approved embedding experiment; fixed origin, durable no-replay ledger."""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import ssl
import time

from locagent_service import bailian_contract as c
from locagent_service.bailian_config import load_env_file
from locagent_service.bailian_experiment import COMMIT, REPO
from locagent_service.public_repo import PinnedHTTPS

WORKSPACE = 'ws-8t0i3jte6m9op4ad'
HOST = WORKSPACE + '.cn-beijing.maas.aliyuncs.com'
ORIGIN = 'https://' + HOST
APPROVAL = 'Sentinel_62cda48fe0ac8191bcb8d6cf83249e5e'
ROOT = Path('/home/lenovo/projects/LocAgent-rag-preview')
AUTHORITY = ROOT / 'outputs/bailian-live-20261015'
ENGINE_FILES = ['locagent_service/bailian_transport_diagnostics.py', 'locagent_service/bailian_raw_artifact.py', 'locagent_service/bailian_recovery.py', 'locagent_service/bailian_response.py', 'locagent_service/bailian_live.py', 'locagent_service/bailian_contract.py',
                'locagent_service/bailian_config.py', 'locagent_service/bailian_experiment.py',
                'locagent_service/bailian_dataset.py', 'locagent_service/bailian_evaluate.py',
                'locagent_service/public_repo.py', 'locagent_service/rag_offline.py',
                'locagent_service/rag_postgres.py', 'locagent_service/config.py',
                'locagent_service/migrations/004_vector_preview.sql']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def engine_hashes(root=ROOT):
    return {name: sha((root / name).read_bytes()) for name in ENGINE_FILES}


def batches(manifest):
    result = []
    for role, field in [('document', 'documents'), ('query', 'questions')]:
        rows = manifest[field]
        for offset in range(0, len(rows), 16):
            selected = rows[offset:offset+16]
            body = c.canonical(c.request([row['text'] for row in selected], role))
            result.append({'role': role, 'ids': [row['id'] for row in selected],
                           'sha256': sha(body), 'body': body, 'count': len(selected)})
    return result


def validate_manifest(manifest, *, root=ROOT):
    from locagent_service.bailian_dataset import validate_dataset
    validate_dataset(manifest)
    if manifest['engine_files'] != engine_hashes(root):
        raise ValueError('Engine hash mismatch')
    if manifest['endpoint'] != c.endpoint(WORKSPACE, ORIGIN):
        raise ValueError('Endpoint differs from user supplied origin')
    if manifest['approval'] != APPROVAL or manifest['model'] != c.MODEL or manifest['dimensions'] != 1024:
        raise ValueError('Live authorization scope mismatch')
    if manifest['parameters'] != c.request(['x'], 'query')['parameters'] or manifest['document_parameters'] != c.request(['x'], 'document')['parameters']:
        raise ValueError('Model parameters changed')
    if manifest['budget_cny'] != '1' or manifest['reservation_cny'] != str(c.planned_cost(len(manifest['documents']), len(manifest['questions']))):
        raise ValueError('Budget mismatch')
    return batches(manifest)


def exchange(body, config, *, connection_factory=PinnedHTTPS):
    """One POST; preserve only fixed transport diagnostics on failure."""
    from locagent_service.bailian_transport_diagnostics import exchange_once
    return exchange_once(body,config,connection_factory=connection_factory,host=HOST,
                         origin=ORIGIN,path=c.PATH,workspace=WORKSPACE,endpoint=c.endpoint)


class Journal:
    """Trusted local filesystem, SQLite FULL transactions, global halt on uncertainty.

    This generic class is testable in a temporary directory. Only run_live exposes
    the real transport and it fixes the authority path; no output-dir override.
    """
    def __init__(self, folder, manifest, requests, *, create=False, approval=APPROVAL):
        self.folder = Path(folder)
        self.manifest = manifest
        self.identity = sha(c.canonical(manifest))
        self.requests = requests
        self.dbpath = self.folder / 'ledger.sqlite'
        if create:
            self.folder.mkdir(mode=0o700)  # exclusive; existing/partial runs never reset
            self.write_once('manifest.json', c.canonical(manifest))
            with self.db() as db:
                db.execute('CREATE TABLE calls (id INTEGER PRIMARY KEY, request_hash TEXT NOT NULL, n INTEGER NOT NULL, state TEXT NOT NULL, http_status INTEGER, response_hash TEXT, tokens INTEGER, vectors TEXT, diagnostic TEXT, elapsed REAL)')
                db.execute('CREATE TABLE run (singleton INTEGER PRIMARY KEY, manifest_hash TEXT NOT NULL, state TEXT NOT NULL)')
                db.execute("INSERT INTO run VALUES (1,?,'active')", (self.identity,))
            self.dbpath.chmod(0o600)
            stat = self.dbpath.stat()
            self.write_once('authority.json', c.canonical({'approval': approval,
                'manifest_sha256': self.identity, 'database_device': stat.st_dev, 'database_inode': stat.st_ino}))
        if self.folder.is_symlink() or self.dbpath.is_symlink():
            raise ValueError('Authority symlink rejected')
        marker = json.loads((self.folder / 'authority.json').read_bytes())
        stat = self.dbpath.stat()
        if marker != {'approval': approval, 'manifest_sha256': self.identity,
                      'database_device': stat.st_dev, 'database_inode': stat.st_ino}:
            raise ValueError('Authority binding mismatch')
        if (self.folder / 'manifest.json').read_bytes() != c.canonical(manifest):
            raise ValueError('Frozen manifest changed')

    def write_once(self, name, raw):
        with (self.folder / name).open('xb') as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        fd = os.open(self.folder, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.dbpath, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db: yield db
        finally: db.close()

    def audit(self, db):
        if db.execute('SELECT manifest_hash FROM run WHERE singleton=1').fetchone() != (self.identity,):
            raise ValueError('Ledger manifest mismatch')
        rows = db.execute('SELECT id,request_hash,n,state,tokens,vectors,response_hash FROM calls ORDER BY id').fetchall()
        if [row[0] for row in rows] != list(range(len(rows))) or len(rows) > len(self.requests):
            raise ValueError('Ledger sequence mismatch')
        for index, request_hash, n, state, tokens, vectors, response_hash in rows:
            expected = self.requests[index]
            if request_hash != expected['sha256'] or n != expected['count'] or state not in ('reserved','settled','unknown'):
                raise ValueError('Ledger request mismatch')
            if state == 'settled':
                if not isinstance(response_hash, str) or len(response_hash) != 64:
                    raise ValueError('Response audit hash missing')
                values = json.loads(vectors)
                synthetic = {'usage': {'prompt_tokens': tokens, 'total_tokens': tokens},
                             'output': {'embeddings': [{'text_index': i, 'embedding': v} for i, v in enumerate(values)]}}
                c.response(c.canonical(synthetic), n)
        return rows

    def step(self, index, transport):
        if type(index) is not int or not 0 <= index < len(self.requests):
            raise ValueError('Request outside plan')
        req = self.requests[index]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = self.audit(db)
            if db.execute('SELECT state FROM run').fetchone()[0] == 'halted' or any(row[3] != 'settled' for row in rows):
                raise ValueError('Run halted or uncertain; no further requests allowed')
            if index < len(rows):
                return json.loads(rows[index][5])
            if index != len(rows):
                raise ValueError('Requests must follow frozen order')
            if c.reservation(sum(row[2] for row in rows) + req['count']) > c.CAP:
                raise ValueError('Budget exceeded')
            db.execute("INSERT INTO calls(id,request_hash,n,state) VALUES (?,?,?,'reserved')",
                       (index, req['sha256'], req['count']))
        started = time.monotonic(); status = None; response_hash = None
        diagnostic = 'raw_capture_unavailable:transport_failure'
        try:
            from locagent_service.bailian_transport_diagnostics import TransportFailure
            transport_failure=None
            try:
                status, raw = transport(req['body'])
            except TransportFailure as exc:
                if exc.body is None:raise
                status,raw=exc.diagnostic['http_status'],exc.body
                transport_failure=exc
            response_hash = sha(raw) if isinstance(raw, bytes) else None
            diagnostic = 'raw_capture_unavailable:persistence_failure'
            from locagent_service.bailian_raw_artifact import persist_response
            persist_response(self.folder,index,raw,manifest_sha256=self.identity,
                             request_sha256=req['sha256'],http_status=status)
            with self.db() as db:
                db.execute('UPDATE calls SET response_hash=?,http_status=? WHERE id=? AND state=\'reserved\'',
                           (response_hash,status if type(status) is int else None,index))
            if transport_failure is not None:raise transport_failure
            from locagent_service.bailian_response import safe_response_json
            self.write_once(f'response-{index:03d}.safe.json', c.canonical(safe_response_json(raw)))
            diagnostic = 'response_invalid' if type(status) is int and status == 200 else 'http_error'
            from locagent_service.bailian_response import validate_response, ResponseValidationError
            try:
                values, tokens, audit = validate_response(raw, req['count'], status)
            except ResponseValidationError as exc:
                self.write_once(f'response-{index:03d}.audit.json', c.canonical(exc.audit))
                raise
            # Only allowlisted metadata plus validated numeric vectors and usage.
            # No raw provider error text or response/request headers are retained.
            audit['vectors'] = values
            self.write_once(f'response-{index:03d}.audit.json', c.canonical(audit))
            with self.db() as db:
                db.execute("UPDATE calls SET state='settled',http_status=?,response_hash=?,tokens=?,vectors=?,diagnostic='ok',elapsed=? WHERE id=? AND state='reserved'",
                           (status,response_hash,tokens,c.canonical(values).decode(),time.monotonic()-started,index))
            return values
        except BaseException as exc:
            from locagent_service.bailian_raw_artifact import CaptureUnavailable
            from locagent_service.bailian_transport_diagnostics import TransportFailure
            if isinstance(exc,TransportFailure):
                status=exc.diagnostic['http_status']
                diagnostic='transport_failure:'+exc.diagnostic['stage']+':'+exc.diagnostic['category']
                record={'manifest_sha256':self.identity,'request_sha256':req['sha256'],**exc.diagnostic}
                try:self.write_once(f'transport-{index:03d}.json',c.canonical(record))
                except BaseException:diagnostic+=':diagnostic_persistence_failure'
            elif isinstance(exc,CaptureUnavailable):
                diagnostic = 'raw_capture_unavailable:' + exc.code
            with self.db() as db:
                db.execute("UPDATE calls SET state='unknown',http_status=?,response_hash=?,diagnostic=?,elapsed=? WHERE id=? AND state='reserved'",
                           (status if type(status) is int else None,response_hash,diagnostic,time.monotonic()-started,index))
                db.execute("UPDATE run SET state='halted'")
            raise ValueError('Run halted; request outcome requires reconciliation, never automatic replay') from None

    def report(self):
        with self.db() as db:
            rows = self.audit(db)
            details = db.execute('SELECT id,state,http_status,response_hash,tokens,diagnostic,elapsed FROM calls ORDER BY id').fetchall()
        retained = c.reservation(sum(row[2] for row in rows)) if rows else Decimal(0)
        actual = sum((Decimal(row[4]) * c.RATE / 1000000 for row in rows if row[3]=='settled'), Decimal(0))
        return {'manifest_sha256':self.identity,'retained_full_reservation_cny':str(retained),
                'settled_usage_cost_cny':str(actual),'calls':[dict(zip(['id','state','http_status','response_sha256','tokens','diagnostic','elapsed_seconds'],row)) for row in details]}


def run_live(*, first_only=False):
    if Path(__file__).resolve().parents[1] != ROOT or ROOT.is_symlink():
        raise ValueError('Live worktree must match fixed authorized location')
    if any(p.is_symlink() for p in [ROOT/'outputs', AUTHORITY]):
        raise ValueError('Authority location rejected')
    manifest = json.loads((ROOT/'outputs/bailian-frozen-manifest.json').read_bytes())
    requests = validate_manifest(manifest)
    from importlib.metadata import version
    if manifest['package_versions'] != {name:version(name) for name in ('bm25s','PyStemmer','psycopg')}:
        raise ValueError('Retrieval dependency versions changed')
    # This fixed lock and authority directory cannot be redirected by CLI/env.
    lock = ROOT/'outputs/bailian-live-20261015.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'r+') as held:
        fcntl.flock(held,fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding = c.canonical({'approval':APPROVAL,'manifest_sha256':sha(c.canonical(manifest))}).decode()
        previous = held.read()
        if (previous and previous != binding) or (bool(previous) != AUTHORITY.exists()):
            raise ValueError('Single-use authority marker mismatch; no reset permitted')
        config = load_env_file(ROOT/'.env.bailian.local')
        if c.endpoint(config.get('DASHSCOPE_WORKSPACE_ID'),config.get('DASHSCOPE_API_HOST')) != ORIGIN+c.PATH or not config.get('DASHSCOPE_API_KEY'):
            raise ValueError('Explicit local configuration required')
        journal = Journal(AUTHORITY, manifest, requests, create=not AUTHORITY.exists())
        if not previous:
            held.write(binding);held.flush();os.fsync(held.fileno())
        for i in range(len(requests)):
            journal.step(i, lambda body: exchange(body, config))
            print(json.dumps(journal.report()), flush=True)
            if first_only:
                return journal.report()
        journal.write_once('completed.json', c.canonical(journal.report()))
        return journal.report()
