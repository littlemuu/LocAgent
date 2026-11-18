from .parts import record_part
from .finalize import complete_upload

def receive(session, number, data):
    record_part(session, number, data)

def finish(session, expected_hash, storage):
    return complete_upload(session, expected_hash, storage)
