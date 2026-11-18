import ast
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever, rank_candidates, prune_containers, ast_entities
from readonly_agent.core import FileTools, encoded


def fixture(files):
    nodes = {}
    for path, source in files.items():
        nodes[path] = {'type': 'file', 'code': source}
        _, entries = ast_entities(source)
        for (name, start, end), node in entries.items():
            nodes[path + ':' + name] = {'type': 'class' if isinstance(node, ast.ClassDef) else 'function',
                                      'start_line': start, 'end_line': end}
    class Graph:
        def nodes(self, data=False): return list(nodes.items())
    base = SimpleNamespace(snapshot_id='fixture', _graph=Graph(), _lexical=SimpleNamespace(
        corpus=[{'_node_content': json.dumps({'text': n})} for n in nodes], similarity_top_k=5))
    snapshot = SimpleNamespace(identity='fixture', files=files)
    retriever = EvidenceRetriever(base, snapshot)
    return retriever, snapshot


class RankingTests(unittest.TestCase):
    def test_qualified_name_over_module_leaf(self):
        r, _ = fixture({'one.py': 'def emit(): pass\nclass Stream:\n    def emit(self): pass\n'})
        rows, _ = rank_candidates('Stream.emit', r.nodes, ['one.py:emit'], r.searchable)
        self.assertEqual([x['id'] for x in rows], ['one.py:Stream.emit'])

    def test_qualified_ambiguity_is_not_hidden(self):
        r, _ = fixture({p: 'class Stream:\n    def emit(self): pass\n' for p in ('a.py', 'b.py')})
        rows, _ = rank_candidates('Stream.emit', r.nodes, [], r.searchable)
        self.assertEqual([x['id'] for x in rows], ['a.py:Stream.emit', 'b.py:Stream.emit'])

    def test_context_and_private_alias_recover_outside_lexical_top5(self):
        r, _ = fixture({'backends/snow.py': 'def _render_pair(): return 1\n', 'base.py': 'class Writer:\n    def render_pair(self): return 2\n'})
        rows, _ = rank_candidates('snow Render_pair', r.nodes, ['base.py:Writer.render_pair'], r.searchable)
        self.assertEqual([x['id'] for x in rows], ['backends/snow.py:_render_pair'])
        self.assertEqual(rows[0]['alias_rule'], 'casefold_and_edge_underscores_only')

    def test_digit_letter_names_not_equated(self):
        r, _ = fixture({'a.py': 'def label_l(): pass\ndef label_1(): pass\n'})
        rows, _ = rank_candidates('label_1', r.nodes, [], r.searchable)
        self.assertEqual(rows[0]['id'], 'a.py:label_1')
        self.assertEqual(len(rows), 1)

    def test_empty_positive_pool_stays_empty(self):
        r, _ = fixture({'a.py': 'def good(): pass\n'})
        rows, _ = rank_candidates('_missing_api', r.nodes, [], r.searchable)
        self.assertEqual(rows, [])

    def test_corpus_scope_is_preserved_except_explicit_fetch(self):
        r, _ = fixture({'tests/a.py': 'def hidden(): pass\n', 'a.py': 'def other(): pass\n'})
        rows, _ = rank_candidates('hidden', r.nodes, [], ['a.py:other'])
        self.assertEqual(rows, [])
        rows, _ = rank_candidates('tests/a.py:hidden', r.nodes, [], [])
        self.assertEqual(rows[0]['id'], 'tests/a.py:hidden')

    def test_parent_containers_removed_but_siblings_preserved(self):
        r, _ = fixture({'a.py': 'class C:\n    def one(self): pass\n    def two(self): pass\n'})
        ids = ['a.py', 'a.py:C', 'a.py:C.one', 'a.py:C.two']
        rows, omitted = prune_containers([{'id': n} for n in ids], r.nodes)
        self.assertEqual([x['id'] for x in rows], ids[2:])
        self.assertEqual(len(omitted), 2)

    def test_explicit_file_or_class_not_replaced_by_child(self):
        r, _ = fixture({'a.py': 'class C:\n    def one(self): pass\n'})
        for query in ('a.py', 'a.py:C'):
            rows, _ = rank_candidates(query, r.nodes, ['a.py:C.one'], r.searchable)
            self.assertEqual(rows, [{'id': query, 'match': 'exact_id'}])

    def test_paths_keep_v4_near_match_label(self):
        r, _ = fixture({'src/training_lm_model.py': 'value = 1\n'})
        text = r.retrieve('src/training_1m_model.py')
        self.assertIn('src/training_lm_model.py', text)
        self.assertIn('not a verified correction', text)

    def test_fallback_top5_is_deterministic(self):
        r, _ = fixture({'a.py': '\n'.join(f'def f{i}(): pass' for i in range(10))})
        ids = [f'a.py:f{i}' for i in range(10)]
        rows, _ = rank_candidates('unmatched prose query', r.nodes, ids, reversed(r.searchable))
        self.assertEqual([x['id'] for x in rows], ids[:5])


class PreviewTests(unittest.TestCase):
    def test_long_docstring_impl_in_first_page_and_no_execution(self):
        source = 'raise RuntimeError("must never execute")\ndef compute(x):\n    """' + ('docs\n' * 240) + '    """\n    return x + 1\n'
        r, snapshot = fixture({'a.py': source})
        tools = FileTools(snapshot, r);page = tools.respond('locagent_retrieve', {'query':'compute', 'offset':0},4096)
        impl = r.last_audit['candidates'][0]['implementation_start']
        self.assertIn(f'{impl}:     return x + 1',page['text'])
        self.assertLessEqual(len(encoded(page)),4096)
        self.assertIn('read_file',page['text'])
        self.assertTrue(r.last_audit['candidates'][0]['docstring_omitted'])

    def test_bom_crlf_unicode_and_physical_line_numbers(self):
        r, snapshot = fixture({'模块.py': '\ufeffclass 容器:\r\n    async def 计算(self):\r\n        """文档\u2028同一行"""\r\n        return "值"\r\n'})
        text = r.retrieve('容器.计算')
        self.assertIn('4:         return "值"', text)
        self.assertEqual(r.last_audit['candidates'][0]['implementation_start'],4)

    def test_multiline_signature_and_decorator(self):
        r, _ = fixture({'a.py':'@decorator\ndef f(\n    a,\n    b,\n):\n    """docs"""\n    return a + b\n'})
        text=r.retrieve('f')
        self.assertIn('2: def f(',text)
        self.assertIn('7:     return a + b',text)
        self.assertIn('omitted',text)

    def test_docstring_only_and_empty_file(self):
        r, _ = fixture({'a.py':'def f():\n    """only doc"""\n','empty.py':''})
        self.assertIn('No non-docstring body',r.retrieve('f'))
        self.assertIn('lines=1-0',r.retrieve('empty.py'))

    def test_single_line_doc_and_implementation_not_erased(self):
        r, _ = fixture({'a.py':'def f(): "doc"; return 7\n'})
        self.assertIn('return 7',r.retrieve('f'))
        self.assertFalse(r.last_audit['candidates'][0]['docstring_omitted'])

    def test_long_line_is_labeled_excerpt_and_pages_are_repeatable(self):
        r,snapshot=fixture({'a.py':'def f():\n    return "'+ '界'*1800 +'"\n'})
        tools=FileTools(snapshot,r);args={'query':'f','offset':0}
        page=tools.respond('locagent_retrieve',args,4096)
        self.assertIn('[line excerpt]',page['text']);self.assertIn('Preview incomplete',page['text'])
        self.assertEqual(page,tools.respond('locagent_retrieve',args,4096))
        self.assertLessEqual(len(encoded(page)),4096)
        with self.assertRaises(ValueError):tools.respond('locagent_retrieve',{'query':'f','offset':999999},4096)
        self.assertIsNone(tools.respond('locagent_retrieve',args,5))

    def test_long_function_has_explicit_gaps_and_valid_source_lines(self):
        r,_=fixture({'a.py':'def f():\n'+''.join(f'    value = {i}\n' for i in range(80))+'    return value\n'})
        text=r.retrieve('f');meta=r.last_audit['candidates'][0]
        self.assertIn('omitted',text);self.assertIn('82:     return value',text)
        self.assertFalse(meta['complete']);self.assertLessEqual(len(meta['shown_lines']),24)

    def test_preview_line_dedup_across_overlapping_records(self):
        r,_=fixture({'a.py':'class C:\n    def f(self):\n        return 1\n'})
        seen=set();r.preview({'id':'a.py:C','match':'fixture'},1,seen)
        _,meta=r.preview({'id':'a.py:C.f','match':'fixture'},2,seen)
        self.assertEqual(meta['shown_lines'],[])

    def test_snapshot_mismatch_rejected(self):
        r,s=fixture({'a.py':''});s.identity='different'
        with self.assertRaisesRegex(ValueError,'snapshot_mismatch'):EvidenceRetriever(r.base,s)

    def test_backend_failure_is_not_converted_to_empty_result(self):
        r,_=fixture({'a.py':'def f(): pass\n'})
        with patch.object(r,'lexical',side_effect=RuntimeError('broken_index')):
            with self.assertRaisesRegex(RuntimeError,'broken_index'):r.retrieve('nonsymbol prose')

    def test_bad_query_and_mutated_entity_span_fail(self):
        r,_=fixture({'a.py':'def f(): pass\n'})
        for query in ('',None,'x'*257):
            with self.assertRaises(ValueError):r.retrieve(query)
        r.nodes['a.py:f']['end_line']=999
        with self.assertRaisesRegex(ValueError,'ast_span'):r.retrieve('f')

    def test_multi_candidate_pagination_reassembles_bounded_previews(self):
        source='class Worker:\n    def go(self):\n'+''.join('        value = "'+ '字'*70 +'"\n' for _ in range(35))+'        return value\n'
        r,snapshot=fixture({f'{i}.py':source for i in range(5)})
        tools=FileTools(snapshot,r);args={'query':'Worker.go','offset':0}
        raw,_=tools.render('locagent_retrieve',args);offset=0;parts=[]
        while True:
            page=tools.respond('locagent_retrieve',dict(args,offset=offset),4096)
            self.assertLessEqual(len(encoded(page)),4096);parts.append(page['text'])
            if page['next_offset'] is None:break
            self.assertGreater(page['next_offset'],offset);offset=page['next_offset']
        self.assertGreater(len(parts),1);self.assertEqual(''.join(parts),raw)
        self.assertEqual([c['id'] for c in r.last_audit['candidates']],[f'{i}.py:Worker.go' for i in range(5)])

    def test_cumulative_source_budget_and_closing_fence(self):
        from readonly_agent.openhands_tools import ToolSession
        from readonly_agent.core import Limits
        r,snapshot=fixture({'a.py':'def f():\n'+''.join('    x = "'+ 'x'*90 +'"\n' for _ in range(50))})
        session=ToolSession(snapshot,retriever=r,limits=Limits(source_bytes=900,page_bytes=500,max_tool_calls=16))
        for _ in range(16):session.execute('locagent_retrieve',{'query':'f','offset':0})
        self.assertTrue(session.closed);self.assertLessEqual(session.used,900)
        before=session.calls;session.execute('locagent_retrieve',{'query':'f','offset':0})
        self.assertEqual(session.calls,before);self.assertEqual(session.audit[-1]['result']['error'],'investigation_closed')


if __name__ == '__main__':
    unittest.main()
