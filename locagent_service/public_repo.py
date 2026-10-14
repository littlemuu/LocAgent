"""Bounded, unauthenticated GitHub HTTPS acquisition. No git or project commands."""
import ast
import gzip
import hashlib
import http.client
import io
import ipaddress
import json
from pathlib import PurePosixPath
import re
import socket
import ssl
import tarfile
import time
from urllib.parse import quote

MAX_DOWNLOAD = 8 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024
MAX_FILE = 1024 * 1024
MAX_FILES = 3000
POLICY = 'public-python-v1'


class PipelineError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def normalize_url(value):
    if not isinstance(value, str):
        raise ValueError('GitHub HTTPS URL required')
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9_.-]{1,100})/?', value)
    if not match:
        raise ValueError('GitHub HTTPS repository URL required')
    owner, name = match.groups()
    name = name.removesuffix('.git')
    if name in ('', '.', '..') or name.startswith('.'):
        raise ValueError('Invalid repository name')
    return f'https://github.com/{owner.lower()}/{name.lower()}'


def validate_ref(value):
    if value is not None and (not isinstance(value, str) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', value)
            or '..' in value or '//' in value or value.endswith(('/', '.'))):
        raise ValueError('Invalid Git reference')
    return value


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Resolve once, reject every non-public answer, connect to the checked IP,
        # then validate TLS with the original hostname. No proxy or second DNS lookup.
        answers = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        addresses = [ipaddress.ip_address(a[4][0]) for a in answers]
        if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
            raise PipelineError('network_address_rejected')
        family, kind, proto, _, address = answers[0]
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(address)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch(host, path, *, limit=MAX_DOWNLOAD):
    if host not in ('api.github.com', 'codeload.github.com') or not path.startswith('/'):
        raise PipelineError('network_target_rejected')
    end = time.monotonic() + 60
    connection = PinnedHTTPS(host, timeout=10, context=ssl.create_default_context())
    try:
        connection.request('GET', path, headers={'User-Agent': 'LocAgent-static-preview',
            'Accept': 'application/vnd.github+json', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        # Including redirects: never follow a Location header.
        if response.status != 200:
            raise PipelineError('github_http_' + str(response.status))
        if int(response.getheader('Content-Length', '0')) > limit:
            raise PipelineError('download_limit')
        chunks, total = [], 0
        while True:
            if time.monotonic() > end:
                raise PipelineError('download_timeout')
            chunk = response.read(min(65536, limit + 1 - total))
            if not chunk:
                return b''.join(chunks)
            total += len(chunk)
            if total > limit:
                raise PipelineError('download_limit')
            chunks.append(chunk)
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('download_failed') from None
    finally:
        connection.close()


def resolve(url, ref):
    repo = normalize_url(url).removeprefix('https://github.com/')
    metadata = json.loads(fetch('api.github.com', '/repos/' + repo, limit=1024 * 1024))
    if metadata.get('private') is not False or metadata.get('full_name', '').lower() != repo:
        raise PipelineError('repository_not_public')
    ref = validate_ref(ref or metadata.get('default_branch'))
    if not ref:
        raise PipelineError('invalid_ref')
    commit = json.loads(fetch('api.github.com', '/repos/' + repo + '/commits/' + quote(ref, safe=''), limit=MAX_DOWNLOAD))['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise PipelineError('invalid_commit')
    return commit


def download(url, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise PipelineError('invalid_commit')
    repo = normalize_url(url).removeprefix('https://github.com/')
    tree = json.loads(fetch('api.github.com', '/repos/' + repo + '/git/trees/' + commit + '?recursive=1'))
    if tree.get('truncated') is not False or len(tree.get('tree', [])) > MAX_FILES:
        raise PipelineError('tree_limit')
    blobs = {}
    for entry in tree['tree']:
        if entry['type'] == 'tree' and entry['mode'] == '040000':
            continue
        if entry['type'] != 'blob' or entry['mode'] not in ('100644', '100755'):
            raise PipelineError('links_or_submodules_unsupported')
        if entry.get('size', MAX_FILE + 1) > MAX_FILE:
            raise PipelineError('file_limit')
        blobs[entry['path']] = entry['sha']
    return fetch('codeload.github.com', '/' + repo + '/tar.gz/' + commit), blobs


def extract(archive, destination, expected):
    if destination.is_symlink() or any(destination.iterdir()):
        raise PipelineError('unsafe_destination')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive)) as stream:
            raw = stream.read(MAX_EXPANDED + 1)
        if len(raw) > MAX_EXPANDED:
            raise PipelineError('expanded_limit')
        seen, files, roots, python_count = set(), {}, set(), 0
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
            for number, member in enumerate(tar):
                if number >= MAX_FILES:
                    raise PipelineError('file_count_limit')
                name = member.name
                path = PurePosixPath(name)
                if (not name or name.startswith('/') or '\\' in name or '\0' in name
                        or '..' in path.parts or len(name) > 512 or len(path.parts) > 30
                        or any(ord(c) < 32 for c in name)):
                    raise PipelineError('unsafe_archive_path')
                roots.add(path.parts[0])
                if len(roots) > 1 or name in seen:
                    raise PipelineError('invalid_archive_layout')
                seen.add(name)
                if not (member.isdir() or member.isfile()):
                    raise PipelineError('links_or_submodules_unsupported')
                if member.isdir():
                    continue
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                if relative == '.' or '.git' in path.parts or relative.endswith('.gitmodules'):
                    raise PipelineError('unsupported_repository')
                if member.size > MAX_FILE:
                    raise PipelineError('file_limit')
                data = tar.extractfile(member).read(MAX_FILE + 1)
                if (data.startswith(b'version https://git-lfs.github.com/spec/v1') or
                        (relative.endswith('.gitattributes') and b'filter=lfs' in data)):
                    raise PipelineError('lfs_unsupported')
                oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                if expected.get(relative) != oid:
                    raise PipelineError('tree_content_mismatch')
                files[relative] = data
            if set(files) != set(expected):
                raise PipelineError('tree_content_mismatch')
        # Write only Python: no configs, hooks, data readers or executable installs.
        for name, data in files.items():
            if name.endswith('.py'):
                try:
                    tree = ast.parse(data, filename=name)
                    if sum(1 for _ in ast.walk(tree)) > 100000:
                        raise PipelineError('parser_limit')
                except (SyntaxError, ValueError, RecursionError):
                    raise PipelineError('unsupported_python') from None
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                python_count += 1
        if not python_count:
            raise PipelineError('no_python_files')
        return {'python_files': python_count, 'archive_sha256': hashlib.sha256(archive).hexdigest(),
                'tree_verified': True, 'policy': POLICY}
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('archive_rejected') from None
