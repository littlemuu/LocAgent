"""Fail closed on Python network/model attempts in the deterministic demo run.

Database calls happen before/after this scope. This guard is test/demo defense,
not an OS sandbox for untrusted Python or native extensions.
"""
from contextlib import contextmanager, ExitStack
import os
import socket
from unittest.mock import patch


@contextmanager
def offline_engine():
    attempts = []

    def deny(*args, **kwargs):
        attempts.append('network or live model attempt')
        raise RuntimeError('Demo localization must stay offline')

    def socket_method(original):
        def guarded(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                return deny()
            return original(sock, *args, **kwargs)
        return guarded

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
            'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
        }))
        for name in ('create_connection', 'getaddrinfo'):
            stack.enter_context(patch.object(socket, name, deny))
        for name in ('connect', 'connect_ex', 'sendto'):
            stack.enter_context(patch.object(socket.socket, name,
                                             socket_method(getattr(socket.socket, name))))
        import litellm
        stack.enter_context(patch.object(litellm, 'completion', deny))
        try:
            yield
        finally:
            if attempts:
                raise RuntimeError('Offline guard observed a forbidden attempt')
