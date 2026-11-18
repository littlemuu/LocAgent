"""Python-level network denial for reviewed offline dependencies, not an OS sandbox."""
from contextlib import contextmanager, ExitStack
import os
import socket
from unittest.mock import patch


@contextmanager
def no_network(persistence_dir):
    attempts = []
    def deny(*args, **kwargs):
        attempts.append('network_attempt')
        raise RuntimeError('offline_network_denied')
    def guarded(method):
        def wrapped(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                return deny()
            return method(sock, *args, **kwargs)
        return wrapped
    with ExitStack() as stack:
        # Exclude credentials, observability exporters and user profile config.
        stack.enter_context(patch.dict(os.environ, {
            'PATH': os.defpath, 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
            'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
            'OH_PERSISTENCE_DIR': str(persistence_dir), 'DO_NOT_TRACK': '1',
            'TOKENIZERS_PARALLELISM': 'false'}, clear=True))
        for name in ('create_connection', 'getaddrinfo'):
            stack.enter_context(patch.object(socket, name, deny))
        for name in ('connect', 'connect_ex', 'sendto'):
            stack.enter_context(patch.object(socket.socket, name, guarded(getattr(socket.socket, name))))
        try:
            yield attempts
        finally:
            if attempts:
                raise RuntimeError('offline_guard_observed_network_attempt')
