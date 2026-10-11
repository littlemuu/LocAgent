"""Extract a Git archive without following links; audit narrow image omissions."""
import io
import hashlib
from pathlib import Path, PurePosixPath
import posixpath
import re
import tarfile

from locagent_service.sources import canonical, digest

IMAGE_SUFFIXES = {'.png', '.svg', '.jpg', '.jpeg', '.gif', '.ico', '.webp'}


def _path(name):
    if not name or name.startswith('/') or '\\' in name or '\0' in name:
        raise ValueError('Unsafe archive path')
    path = PurePosixPath(name)
    if '..' in path.parts or str(path) == '.':
        raise ValueError('Unsafe archive path')
    return str(path)


def _image(data, suffix):
    if suffix == '.png':
        return data.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix in ('.jpg', '.jpeg'):
        return data.startswith(b'\xff\xd8\xff')
    if suffix == '.gif':
        return data.startswith((b'GIF87a', b'GIF89a'))
    if suffix == '.ico':
        return data.startswith(b'\x00\x00\x01\x00')
    if suffix == '.webp':
        return data.startswith(b'RIFF') and data[8:12] == b'WEBP'
    if suffix == '.svg':
        # Inspect only; never parse XML, resolve a DTD, render or execute SVG.
        return bool(re.search(rb'<svg(?:\s|>)', data[:8192])) and b'</svg>' in data
    return False


def inspect_git_tree(data):
    """Git archive can omit submodules; reject them before archive extraction."""
    python_blobs = {}
    for entry in data.split(b'\0'):
        if not entry:
            continue
        meta, raw_path = entry.split(b'\t', 1)
        mode, kind, oid = meta.decode('ascii').split()
        name = _path(raw_path.decode('utf-8'))
        if mode not in ('100644', '100755', '120000') or kind != 'blob':
            raise ValueError('Git submodules and other special tree entries are unsupported')
        if mode != '120000' and name.endswith('.py'):
            python_blobs[name] = oid
    return python_blobs


def extract_snapshot(archive, destination, *, exclude_verified_image_links=False,
                     expected_python_blobs=None):
    destination = Path(destination)
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        raise ValueError('Snapshot destination must be a new empty directory')
    destination.mkdir(parents=True, exist_ok=True)
    excluded, python_before, archive_python_blobs = [], {}, {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = {}
        for member in tar.getmembers():
            name = _path(member.name)
            if name in members:
                raise ValueError('Duplicate archive path')
            members[name] = member
        for name in members:
            for parent in PurePosixPath(name).parents:
                if str(parent) in members and not members[str(parent)].isdir():
                    raise ValueError('Non-directory archive ancestor')
        for name, member in members.items():
            if member.isfile():
                if name.endswith('.py'):
                    data = tar.extractfile(member).read()
                    python_before[name] = digest(data)
                    oid = (expected_python_blobs or {}).get(name, '')
                    algorithm = hashlib.sha256 if len(oid) == 64 else hashlib.sha1
                    archive_python_blobs[name] = algorithm(
                        b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                continue
            if member.isdir():
                continue
            if not exclude_verified_image_links or not member.issym():
                raise ValueError('Unsupported special archive member')
            target = member.linkname
            if (PurePosixPath(name).suffix.lower() not in IMAGE_SUFFIXES or not target
                    or target.startswith('/') or '\\' in target or '\0' in target):
                raise ValueError('Only verified in-repository image links may be excluded')
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved == '..' or resolved.startswith('../') or resolved.startswith('/'):
                raise ValueError('Image link escapes repository')
            target_member = members.get(resolved)
            suffix = PurePosixPath(resolved).suffix.lower()
            if (target_member is None or not target_member.isfile()
                    or suffix not in IMAGE_SUFFIXES or target_member.mode & 0o111):
                raise ValueError('Image link must target an ordinary non-executable image directly')
            data = tar.extractfile(target_member).read()
            if not _image(data, suffix):
                raise ValueError('Image target signature is not recognized')
            excluded.append({'path': name, 'git_mode': '120000',
                             'archive_mode': oct(member.mode), 'target': target,
                             'resolved_path': resolved, 'target_git_mode': '100644',
                             'target_sha256': digest(data),
                             'reason': 'verified in-repository non-code image link; omitted without following'})
        if expected_python_blobs is not None and archive_python_blobs != expected_python_blobs:
            raise ValueError('Git archive changed or omitted ordinary Python files')
        tar.extractall(destination, members=[m for m in members.values()
                       if m.isfile() or m.isdir()], filter='data')
    python_after = {p.relative_to(destination).as_posix(): digest(p.read_bytes())
                    for p in destination.rglob('*.py') if p.is_file()}
    if python_before != python_after or any(p.is_symlink() for p in destination.rglob('*')):
        raise ValueError('Ordinary Python files changed during extraction')
    return {'version': 1, 'archive_sha256': digest(archive),
            'policy': 'exclude-verified-image-links-v1' if exclude_verified_image_links else 'ordinary-only',
            'excluded_links': excluded, 'ordinary_python_files': python_before,
            'ordinary_python_inventory_sha256': digest(canonical(python_before)),
            'python_inventory_preserved': True,
            'git_python_blobs': expected_python_blobs}
