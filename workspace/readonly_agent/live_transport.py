"""Explicitly admitted real transport; locked by default and bounded to one POST."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from .authority import Admission
from .deepseek_wire import RawHTTP
from .core import encoded


def exchange_live(data, key, *, admission=None, ledger=None, reservation=None, enabled=False):
    if enabled is not True or type(admission) is not Admission or ledger is None or type(reservation) is not int:
        raise PermissionError('explicit_live_admission_required')
    if not isinstance(key, str) or not 12 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError('invalid_key_shape')
    # Checking and consuming the ticket is atomic, and occurs before helper start.
    ledger.start_transport(reservation, data, admission)
    worker = Path(__file__).with_name('transport_worker.py')
    try:
        completed = subprocess.run([sys.executable, '-I', '-B', str(worker)],
            input=encoded({'body': data.decode(), 'key': key}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            env={'PATH': os.defpath}, check=False)
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for the helper; no second request.
        raise TimeoutError('provider_wall_clock_deadline') from None
    if completed.returncode != 0 or len(completed.stdout) > 100000:
        raise RuntimeError('provider_exchange_failed')
    raw = json.loads(completed.stdout)
    if set(raw) != {'status', 'body', 'complete'} or type(raw['status']) is not int or type(raw['complete']) is not bool:
        raise ValueError('invalid_transport_result')
    body = base64.b64decode(raw['body'], validate=True)
    if len(body) > 65536 or key.encode() in body:
        raise ValueError('invalid_or_sensitive_response')
    return RawHTTP(raw['status'], body, raw['complete'])
