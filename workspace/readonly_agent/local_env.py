"""Explicit local credential setup/loading. No model, grant or transport imports.

Never source a shell file, interpolate variables, export values, log content, or
change an existing file. The setup/check CLI is for the user's local terminal.
"""
import argparse
import getpass
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import warnings

PROJECT = Path(__file__).resolve().parent.parent
LEGACY = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
MAX_BYTES = 65536


def validate_key(key):
    if (not isinstance(key, str) or not 12 <= len(key) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in key)
            or '$' in key or '`' in key):
        raise ValueError('invalid_local_key')
    return key


def select_path(project=PROJECT, legacy=LEGACY):
    # Local override is explicit by presence; an unsafe/invalid local file must
    # fail, never silently fall through to a different account.
    for root in (Path(project), Path(legacy)):
        candidate = root / '.env'
        if os.path.lexists(candidate):
            return candidate
    return Path(project) / '.env'


def check_ignored(path):
    """Reject tracked files; ignore rules are not retroactive for tracked keys."""
    path = Path(path)
    root = path.parent
    # A durable project rule is required even before this project has Git metadata.
    ignore = root / '.gitignore'
    if ignore.is_symlink() or not ignore.is_file():
        raise PermissionError('local_ignore_rules_required')
    rules = ignore.read_text().splitlines()
    if '.env' not in rules or '.env.*' not in rules:
        raise PermissionError('local_ignore_rules_required')
    env = {'PATH': os.defpath, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], env=env,
                              capture_output=True, timeout=10, check=False)
    if git('rev-parse', '--show-toplevel').returncode == 0:
        if git('ls-files', '--error-unmatch', '--', path.name).returncode == 0:
            raise PermissionError('credential_file_is_tracked')
        if git('check-ignore', '--no-index', '-q', '--', path.name).returncode != 0:
            raise PermissionError('credential_file_not_ignored')


def check_metadata(path):
    path = Path(path).absolute()
    if path != path.resolve():
        raise PermissionError('canonical_regular_env_required')
    info = path.lstat()
    check_stat(info)
    check_ignored(path)
    return path


def check_stat(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or info.st_size > MAX_BYTES):
        raise PermissionError('owned_single_link_mode_0600_env_required')


def parse_key(text):
    # Low-level parser has no interpolation and emits no malformed-line warnings.
    from dotenv.parser import parse_stream
    values = {}
    for binding in parse_stream(io.StringIO(text)):
        if binding.error or (binding.key is not None and binding.key in values):
            raise ValueError('invalid_or_duplicate_env_entry')
        if binding.key is not None:
            values[binding.key] = binding.value
    # Other settings, including legacy paid switches, are never applied.
    return validate_key(values.get('DEEPSEEK_API_KEY'))


def load_key(path):
    path = check_metadata(path)
    # Refuse links/races to FIFOs or broad-permission files before reading bytes.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        check_stat(os.fstat(stream.fileno()))
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('oversized_local_env')
    return parse_key(raw.decode('utf-8'))


def load_selected_key():
    return load_key(select_path())


def write_new(path, key):
    key = validate_key(key)
    path = Path(path).absolute()
    if path.parent != path.parent.resolve():
        raise PermissionError('canonical_env_parent_required')
    check_ignored(path)
    # Exclusive creation: never overwrite, append, copy, back up or chmod old secrets.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        escaped = key.replace('\\', '\\\\').replace("'", "\\'")
        stream.write("DEEPSEEK_API_KEY='" + escaped + "'\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path


def setup(*, new_local=False, project=PROJECT, legacy=LEGACY):
    path = Path(project)/'.env' if new_local else select_path(project, legacy)
    if os.path.lexists(path):
        # Run by the user locally; checks readiness without revealing the value.
        key = load_key(path)
        key = None
        return 'Existing private .env is ready; contents unchanged: ' + str(path)
    check_ignored(path)
    if not sys.stdin.isatty():
        raise PermissionError('local_interactive_terminal_required')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('DeepSeek API key (hidden; saved locally as plaintext, mode 0600): ')
    try:
        write_new(path, key)
    finally:
        key = None
    return 'Saved private plaintext .env (0600); no request or authorization created: ' + str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'check', 'status'])
    parser.add_argument('--new-local', action='store_true',
                        help='Use a project-local .env instead of the legacy file; never overwrite.')
    args = parser.parse_args()
    if args.new_local and args.action != 'setup':
        parser.error('--new-local is for setup only')
    if args.action == 'setup':
        print(setup(new_local=args.new_local))
    elif args.action == 'check':
        key = load_selected_key()
        key = None
        print('Local key format and file permissions passed; provider validity not checked.')
    else:
        path = check_metadata(select_path())
        print('Private .env available; contents NOT read: ' + str(path))


def cli():
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Local configuration stopped: ' + type(error).__name__ +
              '. Existing files preserved; no model request sent.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    cli()
