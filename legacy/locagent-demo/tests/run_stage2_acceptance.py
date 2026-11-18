"""Fail if real PostgreSQL is unavailable; never substitute a mock/SQLite DB."""
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pattern', default='stage2_postgres_acceptance.py')
    args = parser.parse_args()
    attempts = []
    local = {'localhost', '127.0.0.1', '::1'}

    def guard(original):
        def wrapped(*args, **kwargs):
            address = args[0]
            host = address[0] if isinstance(address, tuple) else address
            if host not in local:
                attempts.append('non-local network attempt')
                raise RuntimeError('Acceptance permits only local PostgreSQL/HTTP')
            return original(*args, **kwargs)
        return wrapped

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket, 'getaddrinfo', guard(socket.getaddrinfo)))
        stack.enter_context(patch.object(socket, 'create_connection', guard(socket.create_connection)))
        for name in ('connect', 'connect_ex', 'sendto'):
            original = getattr(socket.socket, name)

            def method(sock, *args, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    return guard(lambda *a, **kw: _original(sock, *a, **kw))(*args, **kwargs)
                return _original(sock, *args, **kwargs)

            stack.enter_context(patch.object(socket.socket, name, method))
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent),
                                                   pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    if attempts:
        print('FAIL: forbidden non-local network attempts', file=sys.stderr)
    return 0 if result.wasSuccessful() and not attempts else 1


if __name__ == '__main__':
    raise SystemExit(main())
