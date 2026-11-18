"""Durable, path-bound SQLite budget ledger for the unapproved offline pilot.

SQLite FULL transactions commit reservations and raw receipts before a response
can reach the SDK. An interrupted reservation blocks every later request.
No live authority is created here. Existing project authorization is never read.
"""
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .core import digest, encoded
from .deepseek_wire import RESERVATION, usage


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Ledger:
    @classmethod
    def create(cls, path, plan, *, admission=None):
        mode = 'simulation'
        if admission is not None:
            from .authority import Admission
            if type(admission) is not Admission or admission.plan_hash != digest(plan):
                raise PermissionError('valid_live_admission_required')
            admission.validate(path)
            mode = 'live'
        if plan.get('authorization') != 'not_granted' or plan.get('mode') != 'offline_preparation':
            raise ValueError('offline_unapproved_plan_required')
        if (plan.get('max_requests_per_arm') != 4 or plan.get('max_requests_total') != 8
                or plan.get('budget_micro_cny') != 17000000
                or plan.get('reservation_micro_cny') != RESERVATION):
            raise ValueError('pilot_limits_mismatch')
        path = Path(path).absolute()
        if path != path.resolve() or path.exists():
            raise ValueError('fresh_canonical_ledger_required')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE run(plan TEXT NOT NULL, hash TEXT NOT NULL, owner TEXT NOT NULL, mode TEXT NOT NULL,
                                 halted INTEGER NOT NULL DEFAULT 0, reason TEXT);
                CREATE TABLE arms(name TEXT PRIMARY KEY, token TEXT NOT NULL, finished INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE calls(id INTEGER PRIMARY KEY, arm TEXT NOT NULL, turn INTEGER NOT NULL,
                    request BLOB NOT NULL, request_hash TEXT NOT NULL, status TEXT NOT NULL,
                    reservation INTEGER NOT NULL, response BLOB, response_hash TEXT,
                    http_status INTEGER, complete INTEGER, cost INTEGER,
                    transport_started INTEGER NOT NULL DEFAULT 0, UNIQUE(arm,turn));
            ''')
            db.execute('INSERT INTO run(plan,hash,owner,mode) VALUES(?,?,?,?)',
                       (encoded(plan).decode(), digest(plan), str(path), mode))
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return cls(path, digest(plan))

    def __init__(self, path, plan_hash):
        self.path = Path(path).absolute()
        self.plan_hash = plan_hash
        if self.path != self.path.resolve() or not self.path.is_file():
            raise ValueError('canonical_existing_ledger_required')
        with self.transaction() as db:
            self.validate(db)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def validate(self, db):
        rows = db.execute('SELECT * FROM run').fetchall()
        if len(rows) != 1:
            raise ValueError('invalid_run_record')
        row = rows[0]
        if 'mode' in row.keys() and row['mode'] not in ('simulation', 'live'):
            raise ValueError('invalid_ledger_mode')
        plan = json.loads(row['plan'])
        if row['owner'] != str(self.path) or row['hash'] != self.plan_hash or digest(plan) != self.plan_hash:
            raise ValueError('ledger_binding_changed')
        calls = db.execute('SELECT * FROM calls ORDER BY id').fetchall()
        if len(calls) > plan['max_requests_total']:
            raise ValueError('call_limit_corruption')
        spent = reserved = 0
        counts = {'baseline': 0, 'retrieval': 0}
        for index, call in enumerate(calls, 1):
            if (call['id'] != index or call['arm'] not in counts or call['reservation'] != RESERVATION
                    or call['request_hash'] != sha(bytes(call['request']))
                    or call['status'] not in ('reserved', 'raw_received', 'settled', 'unknown')):
                raise ValueError('call_record_corruption')
            counts[call['arm']] += 1
            if call['turn'] != counts[call['arm']] or counts[call['arm']] > plan['max_requests_per_arm']:
                raise ValueError('arm_quota_corruption')
            if call['response'] is not None and call['response_hash'] != sha(bytes(call['response'])):
                raise ValueError('receipt_corruption')
            if call['status'] == 'settled':
                _, expected = usage(bytes(call['response']))
                if call['cost'] != expected or expected > RESERVATION or call['http_status'] != 200 or call['complete'] != 1:
                    raise ValueError('settlement_corruption')
                spent += expected
            else:
                reserved += RESERVATION
        if spent + reserved > plan['budget_micro_cny']:
            raise ValueError('budget_corruption')
        return plan, row, calls, spent, reserved

    def claim(self, arm):
        if arm not in ('baseline', 'retrieval'):
            raise ValueError('invalid_arm')
        with self.transaction() as db:
            _, state, calls, _, _ = self.validate(db)
            if state['halted'] or any(c['status'] != 'settled' for c in calls):
                raise RuntimeError('outcome_review_required')
            token = uuid4().hex
            db.execute('INSERT INTO arms(name,token) VALUES(?,?)', (arm, token))
            return token

    def reserve(self, arm, token, request):
        if not isinstance(request, bytes) or not 0 < len(request) <= 65536:
            raise ValueError('invalid_request_bytes')
        with self.transaction() as db:
            plan, state, calls, spent, pending = self.validate(db)
            owner = db.execute('SELECT * FROM arms WHERE name=?', (arm,)).fetchone()
            if owner is None or owner['token'] != token or owner['finished']:
                raise RuntimeError('arm_claim_not_available')
            if state['halted'] or any(c['status'] != 'settled' for c in calls):
                raise RuntimeError('outcome_review_required')
            turn = sum(c['arm'] == arm for c in calls) + 1
            if turn > plan['max_requests_per_arm'] or len(calls) >= plan['max_requests_total']:
                raise RuntimeError('request_quota_exhausted')
            if spent + pending + RESERVATION > plan['budget_micro_cny']:
                raise RuntimeError('budget_exhausted')
            identifier = len(calls) + 1
            db.execute('INSERT INTO calls(id,arm,turn,request,request_hash,status,reservation) VALUES(?,?,?,?,?,?,?)',
                       (identifier, arm, turn, request, sha(request), 'reserved', RESERVATION))
            return identifier

    def received(self, identifier, response):
        if not isinstance(response.body, bytes) or len(response.body) > 65536:
            raise ValueError('invalid_receipt_size')
        with self.transaction() as db:
            self.validate(db)
            cursor = db.execute("UPDATE calls SET response=?,response_hash=?,http_status=?,complete=?,status='raw_received' WHERE id=? AND status='reserved'",
                (response.body, sha(response.body), response.status, int(response.complete), identifier))
            if cursor.rowcount != 1:
                raise RuntimeError('receipt_already_consumed')

    def start_transport(self, identifier, data, admission):
        """Consume one specific durable reservation exactly once before network."""
        admission.validate(self.path)
        with self.transaction() as db:
            _, state, calls, _, _ = self.validate(db)
            if 'mode' not in state.keys() or state['mode'] != 'live' or state['halted']:
                raise PermissionError('live_ledger_required')
            if admission.plan_hash != self.plan_hash:
                raise PermissionError('admission_plan_mismatch')
            call = next((c for c in calls if c['id'] == identifier), None)
            if call is None or call['request_hash'] != sha(data) or bytes(call['request']) != data:
                raise PermissionError('reservation_payload_mismatch')
            cursor = db.execute("UPDATE calls SET transport_started=1 WHERE id=? AND status='reserved' AND transport_started=0", (identifier,))
            if cursor.rowcount != 1:
                raise PermissionError('transport_already_consumed')

    def settle(self, identifier):
        with self.transaction() as db:
            self.validate(db)
            call = db.execute('SELECT * FROM calls WHERE id=?', (identifier,)).fetchone()
            if call is None or call['status'] != 'raw_received' or call['http_status'] != 200 or call['complete'] != 1:
                raise RuntimeError('receipt_not_settleable')
            raw, cost = usage(bytes(call['response']))
            db.execute("UPDATE calls SET status='settled',cost=? WHERE id=?", (cost, identifier))
            return raw

    def halt(self, identifier, reason):
        with self.transaction() as db:
            self.validate(db)
            # A valid usage receipt stays settled even when tool parsing fails.
            db.execute("UPDATE calls SET status='unknown' WHERE id=? AND status!='settled'", (identifier,))
            db.execute('UPDATE run SET reason=CASE WHEN halted=0 THEN ? ELSE reason END,halted=1', (reason,))

    def finish(self, arm, token):
        with self.transaction() as db:
            _, state, calls, _, _ = self.validate(db)
            if state['halted'] or any(c['status'] != 'settled' for c in calls):
                raise RuntimeError('outcome_review_required')
            cursor = db.execute('UPDATE arms SET finished=1 WHERE name=? AND token=? AND finished=0', (arm, token))
            if cursor.rowcount != 1:
                raise RuntimeError('arm_already_consumed')

    def summary(self):
        with self.transaction() as db:
            plan, state, calls, spent, reserved = self.validate(db)
            live = 'mode' in state.keys() and state['mode'] == 'live'
            return {'mode': 'live' if live else plan['mode'],
                    'authorization': 'one_use_claimed' if live else plan['authorization'], 'currency': 'CNY',
                    'simulation': 'mode' not in state.keys() or state['mode'] == 'simulation',
                    'spent_upper_micro_cny': spent, 'reserved_micro_cny': reserved,
                    'limit_micro_cny': plan['budget_micro_cny'], 'halted': bool(state['halted']),
                    'reason': state['reason'],
                    'needs_review': bool(state['halted'] or any(c['status'] != 'settled' for c in calls)),
                    'calls': [{k: c[k] for k in ('id','arm','turn','status','reservation','cost','http_status')}
                              for c in calls]}
