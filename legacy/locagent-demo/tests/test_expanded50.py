import importlib.util,io,tarfile,gzip,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/prepare_expanded50.py'
s=importlib.util.spec_from_file_location('expanded50',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def archive(self,entries):
  b=io.BytesIO()
  with tarfile.open(fileobj=b,mode='w') as t:
   for name,content,kind in entries:
    h=tarfile.TarInfo(name);h.size=len(content);h.type=kind;t.addfile(h,io.BytesIO(content))
  return gzip.compress(b.getvalue())
 def test_all_python_including_tests(self):
  b=self.archive([('r/a.py',b'def a(): pass\n',tarfile.REGTYPE),('r/tests/test_b.py',b'def b(): pass\n',tarfile.REGTYPE),('r/readme',b'x',tarfile.REGTYPE)])
  files,inv=m.archive_files(b);self.assertEqual(set(files),{'a.py','tests/test_b.py'});self.assertEqual(len(inv),3)
 def test_path_escape(self):
  with self.assertRaises(ValueError):m.archive_files(self.archive([('r/../bad.py',b'',tarfile.REGTYPE)]))
 def test_wrong_commit_root(self):
  with self.assertRaises(ValueError):m.archive_files(self.archive([('wrong/a.py',b'x=1',tarfile.REGTYPE)]),'expected-sha')
 def test_symlink(self):
  with self.assertRaises(ValueError):m.archive_files(self.archive([('r/a.py',b'',tarfile.SYMTYPE)]))
 def test_lfs(self):
  with self.assertRaises(ValueError):m.archive_files(self.archive([('r/a.py',b'version https://git-lfs.github.com/spec/v1',tarfile.REGTYPE)]))
 def test_base_context(self):
  m.verify_patch_context('@@ -1,2 +1,2 @@\n def a():\n-    return 1\n+    return 2',b'def a():\n    return 1\n')
  with self.assertRaises(ValueError):m.verify_patch_context('@@ -1 +1 @@\n-old\n+new',b'wrong\n')
 def test_incomplete_hunk(self):
  with self.assertRaises(ValueError):m.verify_patch_context('@@ -1,2 +1,2 @@\n one',b'one\ntwo\n')
 def test_parent_child_overlap(self):
  self.assertTrue(m.target_overlap({('r','a.py:f.child')},{('r','a.py:f')}));self.assertFalse(m.target_overlap({('r','a.py:foo')},{('r','a.py:f')}))
 def test_title_before_fix(self):
  title,meta=m.title_before_fix({'title':'fix-specific','created_at':'1','updated_at':'9'},[{'event':'renamed','created_at':'8','rename':{'from':'original problem','to':'fix-specific'}}],{'created_at':'5','merged_at':'7'})
  self.assertEqual(title,'original problem')
 def test_no_test_gold(self):
  self.assertFalse(m.production('tests/test_a.py'));self.assertFalse(m.production('docs/conf.py'));self.assertTrue(m.production('src/a.py'))
 def test_docstring_only_is_not_behavior_change(self):
  self.assertEqual(m.semantic_ast('def f():\n "old docs"\n return 1'),m.semantic_ast('def f():\n "new docs"\n return 1'))
  self.assertNotEqual(m.semantic_ast('def f():\n return 1'),m.semantic_ast('def f():\n return 2'))
 def test_apply_patch_is_static_and_context_verified(self):
  self.assertEqual(m.apply_public_patch('@@ -1,2 +1,2 @@\n def f():\n- return 1\n+ return 2',b'def f():\n return 1\n'),'def f():\n return 2')
if __name__=='__main__':unittest.main()
