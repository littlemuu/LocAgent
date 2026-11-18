"""Private, immutable, byte-exact response artifacts. Never accepts headers."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


class CaptureUnavailable(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__('Raw response capture unavailable')


def atomic_once(path, data):
    path = Path(path)
    parent = path.parent
    info = parent.stat()
    if parent.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise CaptureUnavailable('unsafe_artifact_directory')
    fd, temporary = tempfile.mkstemp(prefix='.response-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        # Same-filesystem hard link publishes a complete inode atomically and
        # refuses any existing destination, including a symlink. Never replace.
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        os.unlink(temporary)


def persist_response(folder, index, body, *, manifest_sha256, request_sha256, http_status):
    if type(index) is not int or not 0 <= index < 100:
        raise CaptureUnavailable('invalid_request_index')
    if not isinstance(body, bytes) or len(body) > 4 * 1024 * 1024:
        raise CaptureUnavailable('invalid_body_or_limit')
    if any(not isinstance(x,str) or not re.fullmatch(r'[0-9a-f]{64}',x) for x in (manifest_sha256,request_sha256)):
        raise CaptureUnavailable('invalid_binding')
    folder = Path(folder)
    name = f'response-{index:03d}.body.bin'
    digest = hashlib.sha256(body).hexdigest()
    # This must precede every JSON parse, validation or lossy projection.
    atomic_once(folder / name, body)
    metadata = {'version':1,'request_index':index,'manifest_sha256':manifest_sha256,
                'request_sha256':request_sha256,'response_sha256':digest,
                'body_file':name,'body_bytes':len(body),'http_status':http_status if type(http_status) is int else None,
                'request_id':None,'request_id_sha256':None,'json_parse':'invalid'}
    try:
        parsed = json.loads(body)
        metadata['json_parse'] = 'parsed'
        ident = parsed.get('request_id') if isinstance(parsed,dict) else None
        if isinstance(ident,str):
            metadata['request_id_sha256'] = hashlib.sha256(ident.encode('utf-8',errors='replace')).hexdigest()
            if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',ident):metadata['request_id']=ident
    except (ValueError,UnicodeError,RecursionError):
        pass
    atomic_once(folder / f'response-{index:03d}.binding.json',
                json.dumps(metadata,sort_keys=True,separators=(',',':')).encode())
    return metadata
