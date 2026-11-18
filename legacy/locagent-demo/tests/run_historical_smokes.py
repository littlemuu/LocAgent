"""Run the existing Day4-6 smoke scripts with network and live models blocked.

Requires the locally saved outputs/day1 fixtures. Day5 writes a new outputs/day5
run directory, as it did before; no existing artifacts are replaced.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import runpy
import socket
import sys
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    for name in ('outputs/day1/graphs/psf__requests-3362.pkl', 'outputs/day1/task.json'):
        if not Path(name).is_file():
            raise SystemExit('Missing historical fixture: ' + name)
    attempts = []

    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Historical smokes forbid network access')

    def local_only(original):
        def guarded(sock, address, *args, **kwargs):
            # multiprocessing.Manager uses AF_UNIX locally; this is IPC, not a
            # route to model APIs. TCP/UDP/DNS are always rejected.
            if sock.family == socket.AF_UNIX:
                return original(sock, address, *args, **kwargs)
            return deny()
        return guarded

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
            'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
        }))
        stack.enter_context(patch('socket.create_connection', side_effect=deny))
        stack.enter_context(patch('socket.getaddrinfo', side_effect=deny))
        for name in ('connect', 'connect_ex', 'sendto'):
            stack.enter_context(patch.object(socket.socket, name,
                                             local_only(getattr(socket.socket, name))))
        import litellm
        stack.enter_context(patch.object(litellm, 'completion', side_effect=deny))
        for name in ('day4_return_trace_smoke.py', 'day5_main_trace_smoke.py',
                     'day6_repeat_output_smoke.py'):
            print('RUN', name, flush=True)
            runpy.run_path(name, run_name='__main__')
    if attempts:
        raise AssertionError(f'{len(attempts)} forbidden network/model attempts')
    print('PASS: 3 historical smoke scripts; no network or live model attempts')


if __name__ == '__main__':
    main()
