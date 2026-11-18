import tempfile
import unittest
from pathlib import Path
from readonly_agent.core import Snapshot


class HiddenSources(unittest.TestCase):
    def test_opt_in_preserves_bytes_and_default_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'.ci').mkdir()
            p=root/'.ci/tool.py'; p.write_bytes(b'def f():\r\n    return "\xe4\xb8\xad"\r\n')
            with self.assertRaisesRegex(ValueError, 'hidden_source_path'):
                Snapshot(root, ['.ci/tool.py'])
            s=Snapshot(root, ['.ci/tool.py'], hidden_python_paths=['.ci/tool.py'])
            self.assertEqual(s.files['.ci/tool.py'].encode(),p.read_bytes())

    def test_forbidden_and_unlisted_names(self):
        for name in ['.git/a.py','.aws/a.py','.env/a.py','.ssh/a.py','.codex/a.py','.agents/a.py',
                     '.ci/a.txt','../a.py','/tmp/a.py']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    Snapshot(tmp,[name],hidden_python_paths=[name])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                Snapshot(tmp,['normal.py'],hidden_python_paths=['.ci/a.py'])

    def test_symlink_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source.py').write_text('x=1\n');(root/'.ci').mkdir()
            (root/'.ci/a.py').symlink_to(root/'source.py')
            with self.assertRaisesRegex(ValueError,'linked_source_path'):
                Snapshot(root,['.ci/a.py'],hidden_python_paths=['.ci/a.py'])
