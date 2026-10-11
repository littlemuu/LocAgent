"""Bounded immutable raw-body files; ledgers contain references, never body text."""
import json
import os
from pathlib import Path
import re
import stat

from locagent_service import budget
from locagent_service.sources import digest

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024


def limits():
    return {'max_body_bytes':MAX_BODY_BYTES,'max_total_bytes':MAX_TOTAL_BYTES,
            'max_json_bytes':MAX_JSON_BYTES,'policy':'immutable-response-files-v1'}


def directory(ledger):
    folder=Path(ledger).parent/(Path(ledger).name+'.responses')
    if folder.is_symlink():
        raise ValueError('Response directory cannot be a symlink')
    return folder


def usage(ledger):
    folder=directory(ledger)
    if not folder.exists():return 0
    seen=set();total=0
    for path in folder.iterdir():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Response store must contain only regular files')
        inode=(info.st_dev,info.st_ino)
        # Publication briefly has two links to the same immutable body.
        if inode not in seen:
            total+=info.st_size;seen.add(inode)
    return total


def capacity(ledger):
    return max(0,min(MAX_BODY_BYTES,MAX_TOTAL_BYTES-usage(ledger)))


def filename(index):
    if type(index) is not int or not 0<=index<120:
        raise ValueError('Bounded call index required')
    return 'call-%06d.body' % index


def persist(ledger,index,body):
    """Publish once after body fsync; leave any failed temp file as evidence."""
    if not isinstance(body,bytes) or len(body)>capacity(ledger):
        raise ValueError('Body exceeds remaining immutable storage capacity')
    folder=directory(ledger);folder.mkdir(exist_ok=True)
    target=folder/filename(index);temporary=folder/('.'+filename(index)+'.tmp')
    if target.exists() or target.is_symlink():
        raise FileExistsError('Response body already exists; never overwrite')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    os.link(temporary,target)  # Atomic exclusive publication, no replacement.
    temporary.unlink()
    fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'file':target.name,'bytes':len(body),'sha256':digest(body)}


def validate_reference(index,reference):
    if (not isinstance(reference,dict) or set(reference)!={'file','bytes','sha256'}
        or reference['file']!=filename(index)
        or type(reference['bytes']) is not int or not 0<=reference['bytes']<=MAX_BODY_BYTES
        or not isinstance(reference['sha256'],str)
        or not re.fullmatch('[0-9a-f]{64}',reference['sha256'])):
        raise ValueError('Invalid immutable body reference')


def read(ledger,index,reference):
    validate_reference(index,reference)
    path=directory(ledger)/reference['file']
    if path.is_symlink():raise ValueError('Response body cannot be a symlink')
    with path.open('rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size!=reference['bytes']:
            raise ValueError('Response body size mismatch')
        body=stream.read(MAX_BODY_BYTES+1)
    if len(body)!=reference['bytes'] or digest(body)!=reference['sha256']:
        raise ValueError('Response body hash mismatch')
    return body


def save_json(path,value):
    # Match budget.save serialization exactly; a rejected write leaves readable
    # previous state. The shared strict JSON reader has the same 8 MiB ceiling.
    if len(json.dumps(value,sort_keys=True).encode())>MAX_JSON_BYTES:
        raise ValueError('Metadata exceeds bounded JSON reader limit')
    budget.save(path,value)
