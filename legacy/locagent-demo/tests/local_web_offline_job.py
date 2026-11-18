"""TEST ONLY: fake GitHub archive and fake HTTP, real local engine + subprocess.

There is no production option to select this helper or its provider responses.
"""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from locagent_service import local, local_web, public_repo, public_authorization as auth
from test_local_cli import archive, offline_model_child
from locagent_service.offline import offline_engine


def prepare(url, question, config, root, *, ref=None, timeout_seconds=300):
    with offline_engine(), patch.object(public_repo, 'resolve', return_value='a' * 40), \
         patch.object(public_repo, 'download', return_value=archive()):
        return {'state':'prepared', **local.prepare_source(url, question, config, root, ref=ref)}


def timeout_child(root, identity, connection):
    with patch.object(auth, 'exchange', side_effect=TimeoutError('SYNTHETIC_PRIVATE_ERROR_MUST_NOT_LEAK')):
        local.child(root, identity, connection)


if __name__ == '__main__':
    folder, kind, timeout = sys.argv[1:4]
    unknown = len(sys.argv) > 4 and sys.argv[4] == 'unknown'
    with patch.object(local, 'prepare', prepare), patch.object(local, 'child', timeout_child if unknown else offline_model_child):
        local_web.job_main(Path(folder), kind, int(timeout))
