"""Explicit private env-file loading for the isolated embedding experiment."""
import argparse
import json
import os
from pathlib import Path
import stat

from locagent_service.bailian_contract import endpoint

NAMES = {'DASHSCOPE_API_KEY', 'DASHSCOPE_WORKSPACE_ID', 'DASHSCOPE_API_HOST'}


def load_env_file(path):
    # Same opt-in, mode-0600, allowlisted, no-interpolation policy as configure.py.
    # Return a private mapping instead of changing global environment variables.
    # O_NOFOLLOW plus fstat avoids the existing loader's stat/open race.
    from dotenv.parser import parse_stream
    import io
    fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('Private ordinary file owned by current user required')
        if info.st_size > 8192:
            raise ValueError('Configuration too large')
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            fd = None
            text = stream.read(8193)
        if len(text.encode('utf-8')) > 8192:
            raise ValueError('Configuration too large')
        values = {}
        for binding in parse_stream(io.StringIO(text)):
            if binding.error:
                raise ValueError('Malformed configuration')
            if binding.key is None:
                continue
            if binding.key not in NAMES or binding.key in values:
                raise ValueError('Unexpected or duplicate configuration name')
            value = binding.value or ''
            if any(ord(c) < 32 for c in value):
                raise ValueError('Control characters in configuration')
            values[binding.key] = value
        return values
    finally:
        if fd is not None:
            os.close(fd)


def presence(values):
    result = {name + '_present': bool(values.get(name)) for name in sorted(NAMES)}
    try:
        endpoint(values.get('DASHSCOPE_WORKSPACE_ID'), values.get('DASHSCOPE_API_HOST'))
        result['beijing_host_matches_workspace'] = True
    except ValueError:
        result['beijing_host_matches_workspace'] = False
    # Matching syntax is not verification of console ownership/API entitlement.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(presence(load_env_file(args.env_file))))
    except (OSError, ValueError, UnicodeError):
        raise SystemExit('Configuration rejected; check mode 0600, owner, syntax and allowed names') from None


if __name__ == '__main__':
    main()
