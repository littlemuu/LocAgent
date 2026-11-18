"""Oversized generated output exclusion must not weaken source/archive integrity."""
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from locagent_service import public_repo as repo
from test_public_pipeline import archive

OUTPUT = 'evaluation/loc_output/locagent/claude_3-5/loc_outputs.jsonl'
LARGE = b'x' * (repo.MAX_FILE + 1)


class LargeOutputTests(unittest.TestCase):
    def extract(self, entries, expected=None):
        packed, blobs = archive(entries)
        with tempfile.TemporaryDirectory() as directory:
            audit = repo.extract(packed, Path(directory), blobs if expected is None else expected)
            self.assertEqual(sorted(p.relative_to(directory).as_posix()
                                    for p in Path(directory).rglob('*') if p.is_file()), ['a.py'])
            return audit

    def test_exact_output_verified_but_not_written(self):
        audit = self.extract([('a.py', b'x=1', tarfile.REGTYPE),
                              (OUTPUT, LARGE, tarfile.REGTYPE)])
        self.assertEqual(audit['python_files'], 1)
        self.assertEqual(audit['verified_files'], 2)
        self.assertTrue(audit['tree_verified'])
        self.assertEqual(audit['analysis_scope'], 'python_only')
        self.assertEqual(audit['policy'], 'public-python-v2')
        self.assertEqual(audit['omitted_large_outputs'][0]['path'], OUTPUT)
        self.assertEqual(audit['omitted_large_outputs'][0]['size_bytes'], len(LARGE))

    def test_small_output_needs_no_size_exception(self):
        audit = self.extract([('a.py', b'x=1', tarfile.REGTYPE),
                              (OUTPUT, b'{}\n', tarfile.REGTYPE)])
        self.assertEqual(audit['omitted_large_outputs'], [])

    def test_no_suffix_directory_or_source_exemption(self):
        for path in ['large.py', OUTPUT + '.py', OUTPUT.replace('.jsonl', '.py'),
                     OUTPUT.replace('claude_3-5', 'other'), 'data.jsonl']:
            with self.subTest(path=path), self.assertRaises(repo.PipelineError) as caught:
                self.extract([('a.py', b'x=1', tarfile.REGTYPE), (path, LARGE, tarfile.REGTYPE)])
            self.assertEqual(caught.exception.code, 'file_limit')
            self.assertEqual(caught.exception.diagnostic['path'], path)
            self.assertEqual(caught.exception.diagnostic['limit_bytes'], repo.MAX_FILE)

    def test_omitted_blob_still_required_and_hash_checked(self):
        entries = [('a.py', b'x=1', tarfile.REGTYPE), (OUTPUT, LARGE, tarfile.REGTYPE)]
        _, blobs = archive(entries)
        for expected in [dict(blobs, **{OUTPUT: '0' * 40}), {'a.py': blobs['a.py']}]:
            with self.assertRaisesRegex(repo.PipelineError, 'tree_content_mismatch'):
                self.extract(entries, expected)
        with self.assertRaisesRegex(repo.PipelineError, 'tree_content_mismatch'):
            self.extract(entries[:1], blobs)

    def test_omission_preserves_archive_safety(self):
        for name, data, kind, error in [
            (OUTPUT, LARGE, tarfile.SYMTYPE, 'links_or_submodules'),
            ('../' + OUTPUT, LARGE, tarfile.REGTYPE, 'unsafe_archive_path'),
            (OUTPUT, b'version https://git-lfs.github.com/spec/v1\n' + LARGE,
             tarfile.REGTYPE, 'lfs_unsupported')]:
            with self.subTest(error=error), self.assertRaisesRegex(repo.PipelineError, error):
                self.extract([('a.py', b'x=1', tarfile.REGTYPE), (name, data, kind)])
        entries = [('a.py', b'x=1', tarfile.REGTYPE), (OUTPUT, LARGE, tarfile.REGTYPE)]
        with patch.object(repo, 'MAX_EXPANDED', repo.MAX_FILE), self.assertRaisesRegex(
                repo.PipelineError, 'expanded_limit'):
            self.extract(entries)
        with patch.object(repo, 'MAX_FILES', 1), self.assertRaisesRegex(
                repo.PipelineError, 'file_count_limit'):
            self.extract(entries)
        with self.assertRaisesRegex(repo.PipelineError, 'invalid_archive_layout'):
            self.extract(entries + entries[1:])

    def test_sparse_declared_size_cannot_bypass_expansion_limit(self):
        packed, blobs = archive([('a.py', b'x=1', tarfile.REGTYPE),
                                  (OUTPUT, b'{}', tarfile.REGTYPE)])
        original = tarfile.TarFile.next
        def oversized_member(tar):
            member = original(tar)
            if member and member.name.endswith(OUTPUT):
                member.size = repo.MAX_EXPANDED + 1
            return member
        with tempfile.TemporaryDirectory() as directory, patch.object(
                tarfile.TarFile, 'next', oversized_member), self.assertRaisesRegex(
                    repo.PipelineError, 'expanded_limit'):
            repo.extract(packed, Path(directory), blobs)

    def test_download_tree_only_accepts_known_output_and_valid_size(self):
        for path, size, error in [(OUTPUT, len(LARGE), None),
                ('large.py', len(LARGE), 'file_limit'), (OUTPUT, None, 'invalid_tree_size'),
                (OUTPUT, -1, 'invalid_tree_size'), (OUTPUT, True, 'invalid_tree_size')]:
            tree = {'truncated': False, 'tree': [{'type': 'blob', 'mode': '100644',
                    'path': path, 'sha': 'a' * 40, 'size': size}]}
            with self.subTest(path=path, size=size), patch.object(repo, 'fetch',
                    side_effect=[json.dumps(tree).encode(), b'archive']) as fetch:
                if error:
                    with self.assertRaisesRegex(repo.PipelineError, error):
                        repo.download('https://github.com/a/b', 'a' * 40)
                    self.assertEqual(fetch.call_count, 1)
                else:
                    self.assertEqual(repo.download('https://github.com/a/b', 'a' * 40),
                                     (b'archive', {OUTPUT: 'a' * 40}))


if __name__ == '__main__':
    unittest.main()
