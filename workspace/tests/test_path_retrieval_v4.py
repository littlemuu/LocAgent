import unittest
from experiments.path_retrieval_v4.retriever import path_candidates, one_edit, PathAwareRetriever


class Tests(unittest.TestCase):
    def test_confusables_are_distinct_candidates_not_rewritten(self):
        paths = ['src/training_lm_model.py', 'other/training_1m_model.py']
        rows = path_candidates('src/training_1m_model.py', paths)
        self.assertEqual([r['path'] for r in rows], list(reversed(paths)))
        self.assertEqual(rows[0]['match'], 'exact_basename')
        self.assertEqual(rows[1]['match'], 'approximate_basename_one_edit')

    def test_directory_noise_does_not_rank(self):
        rows = path_candidates('examples/training_1m_model.py', [
            'examples/other.py', 'examples/inference', 'examples', 'src/training_lm_model.py'])
        self.assertEqual([r['path'] for r in rows], ['src/training_lm_model.py'])

    def test_same_basename_candidates_are_retained(self):
        rows = path_candidates('c/config.py', ['b/config.py', 'a/config.py', 'c/config.py'])
        self.assertEqual([r['path'] for r in rows], ['c/config.py', 'a/config.py', 'b/config.py'])

    def test_no_match_short_names_prose_and_traversal(self):
        for query in ['cat.py', '../training_1m_model.py', '/src/training_1m_model.py',
                      'fix training_1m_model.py please', 'missing_unknown.py', '.env.py',
                      'x//training_lm_model.py', 'training_lm_model.py:main']:
            self.assertEqual(path_candidates(query, ['bat.py', 'training_lm_model.py']), [])

    def test_unicode_exact_and_case_not_silently_normalized(self):
        self.assertEqual(path_candidates('src/模块.py', ['模块.py'])[0]['path'], '模块.py')
        self.assertEqual(path_candidates('Cat.py', ['cat.py']), [])

    def test_one_edit_variants_and_multiple_edits(self):
        for a, b in [('training', 'trainings'), ('training', 'trainin'), ('training', 'traxning')]:
            self.assertTrue(one_edit(a,b)); self.assertTrue(one_edit(b,a))
        for a, b in [('training','training'), ('training','traxnixg'), ('abc','acb')]:
            self.assertFalse(one_edit(a,b))

    def test_bounded_deterministic_results(self):
        files = [str(i) + '/config.py' for i in range(20)]
        self.assertEqual(path_candidates('config.py', files), path_candidates('config.py', reversed(files)))
        self.assertEqual(len(path_candidates('config.py', files)), 5)

    def test_unmatched_filename_does_not_fall_back_to_directory_noise(self):
        from types import SimpleNamespace
        class Graph:
            def nodes(self, data=False): return [('examples/other.py', {'type':'file'})]
            def __contains__(self, query): return False
        calls = []
        base = SimpleNamespace(_graph=Graph(), snapshot_id='fixture',
                               retrieve=lambda q: calls.append(q) or 'legacy')
        wrapper = PathAwareRetriever(base)
        self.assertIn('No matching source paths', wrapper.retrieve('examples/not_existing.py'))
        self.assertEqual(calls, [])
        self.assertEqual(wrapper.retrieve('read state from config'), 'legacy')
        self.assertEqual(calls, ['read state from config'])

    def test_saved_actual_replay_first_page_and_budget(self):
        import json
        from pathlib import Path
        from types import SimpleNamespace
        from readonly_agent.core import FileTools, encoded
        root=Path('verification/dev37-preparation-v4/checks/huggingface__accelerate-3261.json')
        if not root.exists(): self.skipTest('real static replay unavailable')
        result=json.loads(root.read_text())
        r=result['queries'][0]
        target=r['candidates'][0]['path']
        fake=SimpleNamespace(snapshot_id=result['snapshot'], retrieve=lambda query:r['new_text'])
        tools=FileTools(SimpleNamespace(identity=result['snapshot'],files={}), fake)
        page=tools.respond('locagent_retrieve',{'query':r['query'],'offset':0},4096)
        self.assertLessEqual(len(encoded(page)),4096)
        self.assertIn(target, page['text'])
        self.assertNotIn(target,r['old_text'])
        self.assertIn('approximate_basename_one_edit',page['text'])
        self.assertIsNotNone(page['next_offset'])
        again=tools.respond('locagent_retrieve',{'query':r['query'],'offset':0},4096)
        self.assertEqual(page,again)


if __name__ == '__main__':
    unittest.main()
