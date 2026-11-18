import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from locagent_service.models import TaskRequest
from locagent_service import public_repo as repo
from locagent_service import public_pipeline as pipeline


def archive(entries):
    stream = io.BytesIO()
    blobs = {}
    with tarfile.open(fileobj=stream, mode='w') as tar:
        for name, data, kind in entries:
            item = tarfile.TarInfo('repo-commit/' + name)
            item.type = kind
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            tar.addfile(item, io.BytesIO(data) if item.isfile() else None)
            blobs[name] = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    return gzip.compress(stream.getvalue()), blobs


class AcquisitionTests(unittest.TestCase):
    def test_url_and_ref_boundary(self):
        self.assertEqual(repo.normalize_url('https://github.com/Pallets/Click.git/'),
                         'https://github.com/pallets/click')
        for value in ('http://github.com/a/b', 'https://github.com.evil/a/b',
            'https://u:p@github.com/a/b', 'https://github.com:443/a/b', '/tmp/repo',
            'file:///a', 'git@github.com:a/b', 'https://127.0.0.1/a/b',
            'https://github.com/a/b?x=1', 'https://github.com/a/b#main',
            'https://github.com/a/../b', 'https://github.com/a/%2e%2e',
            'https://github.com/a/b\n', 'https://github.com/a/b --upload-pack=x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repo.normalize_url(value)
        for value in ('-x', '../a', 'a..b', 'a//b', 'a@{x}', 'a;id', 'a\n'):
            with self.assertRaises(ValueError):
                repo.validate_ref(value)
        self.assertEqual(repo.validate_ref('feature/python-3.12'), 'feature/python-3.12')

    def test_request_rejects_unknown_provider_and_incompatible_fields(self):
        base = {'source_id': 'github-v1', 'repository_url': 'https://github.com/a/b',
                'problem_statement': 'find x'}
        self.assertEqual(TaskRequest(**base).repository_url, base['repository_url'])
        for extra in ({'provider': 'paid'}, {'ref': '--upload-pack=evil'},
                      {'repository_url': 'file:///tmp/x'}, {'demo_scenario': 'empty'}):
            with self.assertRaises(ValidationError):
                TaskRequest(**(base | extra))
        with self.assertRaises(ValidationError):
            TaskRequest(problem_statement='x', repository_url=base['repository_url'])

    def test_public_preview_requires_explicit_isolation(self):
        from locagent_service.config import Settings
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'LOCAGENT_PUBLIC_PREVIEW': '1', 'LOCAGENT_PUBLIC_ROOT': directory,
                'LOCAGENT_SOURCE_ROOT': directory}):
            pipeline.enabled(Settings('postgresql://localhost/unit', 'public_preview_test'))
            with self.assertRaises(ValueError):
                pipeline.enabled(Settings('postgresql://localhost/unit', 'locagent'))
            with patch.dict(os.environ, {'LOCAGENT_PUBLIC_PREVIEW': '0'}):
                with self.assertRaises(ValueError):
                    pipeline.enabled()

    def test_git_tree_submodules_and_truncation_fail_closed(self):
        for tree in ({'truncated': True, 'tree': []}, {'truncated': False, 'tree': [
                {'type': 'commit', 'mode': '160000', 'path': 'submodule'}]},
                {'truncated': False, 'tree': [
                {'type': 'blob', 'mode': '120000', 'path': 'link'}]}):
            with patch.object(repo, 'fetch', return_value=json.dumps(tree).encode()) as fetch:
                with self.assertRaises(repo.PipelineError):
                    repo.download('https://github.com/a/b', 'a' * 40)
                self.assertEqual(fetch.call_count, 1)
        with self.assertRaisesRegex(repo.PipelineError, 'invalid_commit'):
            repo.download('https://github.com/a/b', 'main')

    def test_fixed_commit_and_public_metadata(self):
        sha = 'a' * 40
        calls = []
        def fetch(host, path, **kwargs):
            calls.append(path)
            return json.dumps({'sha': sha} if '/commits/' in path else {
                'private': False, 'full_name': 'A/B', 'default_branch': 'main'}).encode()
        with patch.object(repo, 'fetch', fetch):
            self.assertEqual(repo.resolve('https://github.com/a/b', 'feature/x'), sha)
        self.assertTrue(calls[-1].endswith('feature%2Fx'))
        with patch.object(repo, 'fetch', return_value=b'{"private":true}'):
            with self.assertRaises(repo.PipelineError):
                repo.resolve('https://github.com/a/b', None)

    def test_internal_addresses_rejected_before_connect(self):
        for ip in ('127.0.0.1', '10.1.2.3', '169.254.169.254', '::1', '224.0.0.1', 'ff0e::1'):
            with patch.object(socket, 'getaddrinfo', return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]), \
                 patch.object(socket, 'socket') as connect:
                with self.assertRaises(repo.PipelineError):
                    repo.PinnedHTTPS('api.github.com').connect()
                connect.assert_not_called()

    def test_redirect_and_length_rejected(self):
        for status, length, code in ((302, '0', 'github_http_302'),
                                      (200, str(repo.MAX_DOWNLOAD + 1), 'download_limit')):
            with patch.object(repo, 'PinnedHTTPS') as cls:
                response = cls.return_value.getresponse.return_value
                response.status = status
                response.getheader.return_value = length
                with self.assertRaisesRegex(repo.PipelineError, code):
                    repo.fetch('api.github.com', '/repos/a/b')

    def test_archive_limits_and_special_paths(self):
        cases = [('ok.py', b'def f():\n return 1\n', tarfile.REGTYPE, None),
            ('../evil.py', b'x=1', tarfile.REGTYPE, 'unsafe_archive_path'),
            ('link.py', b'', tarfile.SYMTYPE, 'links_or_submodules'),
            ('.gitmodules', b'', tarfile.REGTYPE, 'unsupported_repository'),
            ('data', b'version https://git-lfs.github.com/spec/v1\n', tarfile.REGTYPE, 'lfs_unsupported'),
            ('bad.py', b'def syntax error', tarfile.REGTYPE, 'unsupported_python'),
            ('readme.md', b'hello', tarfile.REGTYPE, 'no_python_files'),
            ('large.py', b'x' * (repo.MAX_FILE + 1), tarfile.REGTYPE, 'file_limit')]
        for name, data, kind, error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                packed, blobs = archive([(name, data, kind)])
                if error:
                    with self.assertRaisesRegex(repo.PipelineError, error):
                        repo.extract(packed, Path(directory), blobs)
                else:
                    self.assertEqual(repo.extract(packed, Path(directory), blobs)['python_files'], 1)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(repo, 'MAX_EXPANDED', 10):
                with self.assertRaisesRegex(repo.PipelineError, 'expanded_limit'):
                    repo.extract(packed, Path(directory), blobs)

    def test_count_hash_and_duplicates(self):
        packed, blobs = archive([('a.py', b'x=1', tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(repo.PipelineError, 'tree_content_mismatch'):
                repo.extract(packed, Path(directory), {'a.py': '0' * 40})
            with patch.object(repo, 'MAX_FILES', 0):
                with self.assertRaisesRegex(repo.PipelineError, 'file_count_limit'):
                    repo.extract(packed, Path(directory), blobs)
        packed, blobs = archive([('a.py', b'x=1', tarfile.REGTYPE)] * 2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(repo.PipelineError, 'invalid_archive_layout'):
                repo.extract(packed, Path(directory), blobs)


class FakeProviderContractTests(unittest.TestCase):
    def test_http_rejects_live_configuration_fields(self):
        from fastapi.testclient import TestClient
        from locagent_service.api import create_app
        from locagent_service.config import Settings
        with patch('locagent_service.api.TaskStore') as store:
            with TestClient(create_app(Settings('postgresql://localhost/unit', 'public_preview_unit'))) as client:
                body = {'source_id': 'github-v1', 'repository_url': 'https://github.com/a/b',
                        'problem_statement': 'Find serialize'}
                for extra in ({'provider': 'live'}, {'model': 'paid-model'}, {'allow_paid': True},
                              {'api_key': 'synthetic-not-a-key'}, {'api_base': 'https://example.invalid'},
                              {'options': {'provider': 'live'}}):
                    with self.subTest(extra=extra):
                        response = client.post('/tasks', json=body | extra)
                        self.assertEqual(response.status_code, 422)
                        self.assertEqual(response.json()['error']['code'], 'invalid_request')
                store.return_value.create.assert_not_called()

    def test_fake_finish_is_fixed_and_paid_environment_cannot_select_live(self):
        from locagent_service import sources
        from locagent_service.budget import BudgetProvider
        from locagent_service.models import CreateTask
        request = CreateTask(source_id='github-v1', repository_url='https://github.com/a/b',
                             problem_statement='Find a real bug')
        recorded = []
        def localize(prepared, provider):
            for feedback in ('no matches', 'candidate module found', 'different candidate'):
                response = provider(messages=[{'role': 'tool', 'content': feedback}])
                call = response.choices[0].message.tool_calls[0].function
                recorded.append((call.name, json.loads(call.arguments)))
            return 'offline-sentinel'
        with patch.dict(os.environ, {'LOCAGENT_ALLOW_PAID': '1'}), \
             patch.object(BudgetProvider, 'from_env', side_effect=AssertionError('live path selected')) as paid, \
             patch.object(sources, 'localize_prepared', side_effect=localize):
            self.assertEqual(pipeline.fake_localize(request, 'prepared-' + 'a' * 64), 'offline-sentinel')
            paid.assert_not_called()
        self.assertEqual([name for name, _ in recorded],
                         ['search_code_snippets', 'explore_tree_structure', 'finish'])
        self.assertEqual(recorded[-1][1], {'files': [], 'entities': []})


class CacheTests(unittest.TestCase):
    def test_duplicate_build_cache_hit_and_incomplete_recovery(self):
        from locagent_service import prepare
        packed, blobs = archive([('a.py', b'def f():\n return 1\n', tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'LOCAGENT_SOURCE_ROOT': directory}), \
             patch.object(repo, 'download', return_value=(packed, blobs)) as download, \
             patch.object(prepare, 'build_indexes') as build:
            def create(snapshot, bundle, instance, **kwargs):
                (bundle / 'graph.pkl').write_bytes(b'unit-only-artifact')
            build.side_effect = create
            def run():
                return pipeline.index('https://github.com/a/b', 'a' * 40, lambda **v: None)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: run(), range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(build.call_count, 1)
            self.assertEqual(download.call_count, 1)
            ready = next(Path(directory).glob('*.ready'))
            ready.unlink()  # model a crash before pointer publication
            run()
            self.assertEqual(build.call_count, 2)
            (Path(directory) / results[0]['bundle'] / 'graph.pkl').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                run()

    def test_cache_pointer_cannot_alias_another_repository_at_same_commit(self):
        from locagent_service import prepare
        packed, blobs = archive([('a.py', b'x=1', tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'LOCAGENT_SOURCE_ROOT': directory}), \
             patch.object(repo, 'download', return_value=(packed, blobs)), \
             patch.object(prepare, 'build_indexes'):
            first = pipeline.index('https://github.com/a/b', 'a' * 40, lambda **v: None)
            second = pipeline.index('https://github.com/c/d', 'a' * 40, lambda **v: None)
            root = Path(directory)
            first_pointer = root / (first['task']['instance_id'] + '.ready')
            second_pointer = root / (second['task']['instance_id'] + '.ready')
            first_pointer.write_bytes(second_pointer.read_bytes())
            with self.assertRaisesRegex(repo.PipelineError, 'cache_integrity_error'):
                pipeline.index('https://github.com/a/b', 'a' * 40, lambda **v: None)

    def test_download_and_build_failure_never_publish_ready(self):
        from locagent_service import prepare
        packed, blobs = archive([('a.py', b'x=1', tarfile.REGTYPE)])
        for error in ('download', 'build'):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                    'LOCAGENT_SOURCE_ROOT': directory}), \
                 patch.object(repo, 'download', return_value=(packed, blobs)) as fetch, \
                 patch.object(prepare, 'build_indexes') as build:
                if error == 'download':
                    fetch.side_effect = repo.PipelineError('download_failed')
                else:
                    build.side_effect = RuntimeError('secret-detail')
                with self.assertRaises(repo.PipelineError):
                    pipeline.index('https://github.com/a/b', 'a' * 40, lambda **v: None)
                self.assertEqual(list(Path(directory).glob('*.ready')), [])


if __name__ == '__main__':
    unittest.main()
