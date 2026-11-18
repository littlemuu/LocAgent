"""Offline manifest/cache/ledger harness. No live HTTP implementation.

execute_fake accepts a caller-supplied test transport. Do not connect a real
transport until source/endpoint/authorization verification is implemented.
"""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from locagent_service import bailian_contract as c

REPO = 'pallets/itsdangerous'
COMMIT = '096c8d42545d3b68ea21a4f890fb2b2d8979c0bd'


def freeze(documents, questions, *, workspace, api_host, chunker, engine_hash):
    """Freeze ordered public-source input/labels before any retrieval output.

    Caller must verify source provenance; a repo name in JSON is not proof.
    """
    url = c.endpoint(workspace, api_host)
    if not isinstance(engine_hash, str) or len(engine_hash) != 64 or any(x not in '0123456789abcdef' for x in engine_hash):
        raise ValueError('Engine SHA256 required')
    if not isinstance(chunker, dict) or set(chunker) != {'name', 'max_chars'}:
        raise ValueError('Explicit chunker configuration required')
    if chunker['name'] != 'python-ast-lines-v2' or type(chunker['max_chars']) is not int or not 32 <= chunker['max_chars'] <= 16000:
        raise ValueError('Unsupported chunker configuration')
    cost = c.planned_cost(len(documents), len(questions))
    ids, entities = set(), set()
    for doc in documents:
        if set(doc) != {'id', 'entity', 'path', 'text'} or not all(isinstance(x, str) and x for x in doc.values()):
            raise ValueError('Invalid document')
        if doc['id'] in ids:
            raise ValueError('Duplicate document')
        from locagent_service.rag_offline import allowed
        if not allowed(doc['path']):
            raise ValueError('Invalid source path')
        c.request([doc['text']], 'document')
        ids.add(doc['id']); entities.add(doc['entity'])
    qids = set()
    for q in questions:
        if set(q) != {'id', 'text', 'relevant_entities'} or not isinstance(q['id'], str) or not q['id'] or q['id'] in qids:
            raise ValueError('Invalid question identity')
        labels = q['relevant_entities']
        if not isinstance(labels, list) or not labels or any(not isinstance(x, str) for x in labels) or len(set(labels)) != len(labels) or not set(labels) <= entities:
            raise ValueError('Invalid relevance labels')
        c.request([q['text']], 'query')
        if any(label.split('.')[-1].lower() in q['text'].lower() for label in labels):
            raise ValueError('Target symbol name leaked into question')
        qids.add(q['id'])
    data = {'version': 1, 'mode': 'offline-only', 'repo': REPO, 'commit': COMMIT,
            'endpoint': url, 'model': c.MODEL, 'dimensions': c.DIMENSIONS,
            'instruction': c.INSTRUCTION, 'preprocessing': c.PREPROCESSING,
            'chunker': chunker, 'engine_sha256': engine_hash,
            'documents': documents, 'questions': questions,
            'budget_cny': '1', 'full_reservation_cny': str(cost),
            'evaluation': 'manually-constructed-development-set-not-blind'}
    return c.canonical(data)


class Ledger:
    """One SQLite file binds one frozen plan, never resets or releases budget.

    Each distinct input is reserved once, even after settlement; this stricter
    rule keeps aggregate worst-case cost within the frozen <=CNY1 plan.
    A crash leaves reserved rows that block replay. No takeover/retry API.
    """
    def __init__(self, path, manifest):
        self.path = Path(path)
        self.manifest = json.loads(manifest)
        m = self.manifest
        expected = freeze(m['documents'], m['questions'], workspace=m['endpoint'].split('//')[1].split('.')[0],
                          api_host=m['endpoint'].removesuffix(c.PATH), chunker=m['chunker'], engine_hash=m['engine_sha256'])
        if manifest != expected:
            raise ValueError('Manifest differs from frozen contract')
        self.identity = hashlib.sha256(manifest).hexdigest()
        self.inputs = {}
        for role, rows in [('document', m['documents']), ('query', m['questions'])]:
            for row in rows:
                key = c.cache_key(row['text'], role, m['endpoint'], c.digest(m['chunker']))
                self.inputs[key] = c.request([row['text']], role)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS plan (singleton INTEGER PRIMARY KEY CHECK(singleton=1), hash TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN (\'reserved\',\'settled\',\'unknown\')), response_hash TEXT, tokens INTEGER, vectors TEXT)')
            db.execute('INSERT OR IGNORE INTO plan VALUES (1,?)', (self.identity,))
            if db.execute('SELECT hash FROM plan WHERE singleton=1').fetchone()[0] != self.identity:
                raise ValueError('Existing ledger belongs to another manifest')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def execute_fake(self, key, transport):
        if key not in self.inputs:
            raise ValueError('Input is not in frozen manifest')
        body = c.canonical(self.inputs[key])
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT hash FROM plan WHERE singleton=1').fetchone() != (self.identity,):
                raise ValueError('Ledger plan identity changed')
            existing = db.execute('SELECT state,vectors FROM calls WHERE key=?', (key,)).fetchone()
            if existing:
                if existing[0] == 'settled':
                    return json.loads(existing[1])
                raise ValueError('Unknown or in-flight call cannot be replayed')
            if c.reservation(db.execute('SELECT count(*) FROM calls').fetchone()[0] + 1) > c.CAP:
                raise ValueError('Budget exhausted')
            db.execute('INSERT INTO calls(key,request_hash,state) VALUES (?,?,\'reserved\')',
                       (key, hashlib.sha256(body).hexdigest()))
        response_hash = None
        try:
            status, raw = transport(body)  # one invocation only; no retry loop
            if isinstance(raw, bytes):
                response_hash = hashlib.sha256(raw).hexdigest()
            if type(status) is not int or status != 200:
                raise ValueError()
            vectors, tokens = c.response(raw, 1)
            with self.connection() as db:
                db.execute('UPDATE calls SET state=\'settled\',response_hash=?,tokens=?,vectors=? WHERE key=? AND state=\'reserved\'',
                           (response_hash, tokens, c.canonical(vectors).decode(), key))
            return json.loads(c.canonical(vectors))
        except Exception:
            with self.connection() as db:
                db.execute('UPDATE calls SET state=\'unknown\',response_hash=? WHERE key=? AND state=\'reserved\'', (response_hash, key))
            raise ValueError('Embedding outcome unknown; automatic replay prohibited') from None

    def accounting(self):
        with self.connection() as db:
            rows = db.execute('SELECT state,tokens FROM calls').fetchall()
        return {'manifest_sha256': self.identity, 'call_count': len(rows),
                'retained_full_reservation_cny': str(c.reservation(len(rows))) if rows else '0',
                'settled_usage_cny': str(sum((Decimal(tokens) * c.RATE / 1000000
                                             for state, tokens in rows if state == 'settled'), Decimal(0))),
                'unresolved_count': sum(state != 'settled' for state, _ in rows)}


def metrics(questions, rankings, k):
    """Macro entity recall and hit rate; missing/failed questions count as zero."""
    if type(k) is not int or k < 1 or not questions:
        raise ValueError('Positive k and nonempty questions required')
    hits, recall = 0, 0.0
    for q in questions:
        labels = set(q['relevant_entities'])
        if not labels:
            raise ValueError('Nonempty relevance labels required')
        ordered = list(dict.fromkeys(rankings.get(q['id'], [])))[:k]
        found = len(labels.intersection(ordered))
        hits += bool(found)
        recall += found / len(labels)
    return {'question_count': len(questions), 'hit_at_k': hits / len(questions),
            'macro_recall_at_k': recall / len(questions)}
