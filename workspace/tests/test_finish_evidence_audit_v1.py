import unittest
from copy import deepcopy
from experiments.finish_evidence_audit_v1.check import observed_lines,entity_metadata,audit_finish,inspect_entity,mention_tokens

FILES={'a.py':'class C:\n    def root(self):\n        return self.helper()\n    def helper(self):\n        """doc"""\n        return 7\n'}
GRAPH={'a.py:C.root':{'type':'function','start_line':2,'end_line':3,'code':'def root(self):\n        return self.helper()'},
       'a.py:C.helper':{'type':'function','start_line':4,'end_line':6,'code':'def helper(self):\n        """doc"""\n        return 7'}}

def evidence(text,tool='read_file',args=None):
    args=args or {'path':'a.py','start_line':1,'end_line':6}
    result={'text':text,'next_cursor':'unseen-page'}
    return {'tool_call_id':'fixture','tool':tool,'arguments':args,'result':result,
            'lines':observed_lines(tool,args,result,FILES)}

class Tests(unittest.TestCase):
    def test_called_function_is_not_misreported_as_body_seen(self):
        e=evidence('2:     def root(self):\n3:         return self.helper()')
        c=inspect_entity('a.py:C.helper',entity_metadata(GRAPH),[e])
        self.assertTrue(c['observations'][0]['reference_lines']);self.assertFalse(c['definition_line_visible']);self.assertFalse(c['body_lines_all_visible'])

    def test_requested_range_does_not_count_as_visible(self):
        e=evidence('4:     def helper(self):\n5:         """doc"""')
        c=inspect_entity('a.py:C.helper',entity_metadata(GRAPH),[e])
        self.assertTrue(c['definition_line_visible']);self.assertFalse(c['body_start_visible'])

    def test_full_body_requires_source_line_match(self):
        meta=entity_metadata(GRAPH)
        self.assertTrue(inspect_entity('a.py:C.helper',meta,[evidence('6:         return 7')])['body_lines_all_visible'])
        self.assertFalse(inspect_entity('a.py:C.helper',meta,[evidence('6:         return … [line excerpt]')])['body_lines_all_visible'])

    def test_mentions_never_modify_finish_even_when_negated(self):
        answer={'files':['a.py'],'entities':['a.py:C.root'],'answer':'I did not inspect `helper`; it may be unrelated.'}
        before=deepcopy(answer);r=audit_finish(answer,entity_metadata(GRAPH),[evidence('3:         return self.helper()')])
        self.assertEqual(answer,before);self.assertEqual(r['mentions'][0]['omitted_observed_candidates'],['a.py:C.helper'])
        self.assertTrue(r['mentions'][0]['review_only_not_required_additions'])

    def test_same_leaf_ambiguity_is_retained(self):
        g=deepcopy(GRAPH);g['a.py:Other.helper']=dict(g['a.py:C.helper'])
        r=audit_finish({'files':[],'entities':[],'answer':'Inspect `helper`.'},entity_metadata(g),[evidence('4:     def helper(self):')])
        self.assertEqual(r['mentions'][0]['repository_match_count'],2);self.assertTrue(r['mentions'][0]['ambiguous_repository_symbol'])

    def test_missing_owner_not_automatically_corrected(self):
        c=inspect_entity('a.py:Other.helper',entity_metadata(GRAPH),[])
        self.assertFalse(c['exists_as_definition_id']);self.assertEqual(c['same_leaf_definitions'],['a.py:C.helper'])

    def test_both_renderer_formats_and_unicode_physical_lines(self):
        for text in ('##Searching for entity `a.py:C.helper`...\n4 | def helper(self):',
                     '#1 a.py:C.helper [exact_id]\n4:     def helper(self):'):
            rows=observed_lines('locagent_retrieve',{}, {'text':text},FILES)
            self.assertEqual(rows[0]['line'],4);self.assertTrue(rows[0]['full_line'])
        files={'字.py':'def f():\r\n    return "甲\u2028乙"\r\n'}
        rows=observed_lines('read_file',{'path':'字.py'},{'text':'2:     return "甲\u2028乙"'},files)
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]['full_line'])

    def test_search_snippet_reference_is_not_full_body(self):
        e=evidence('a.py:3: return self.helper()',tool='search_text',args={'query':'helper'})
        c=inspect_entity('a.py:C.helper',entity_metadata(GRAPH),[e])
        self.assertTrue(c['observations'][0]['reference_lines']);self.assertFalse(c['body_start_visible'])

    def test_source_not_seen_and_ordinary_words_not_mined(self):
        self.assertNotIn('copy',mention_tokens('Copy or copy the file, then run it.'))
        r=audit_finish({'files':[],'entities':[],'answer':'`helper` is a hypothesis.'},entity_metadata(GRAPH),[])
        self.assertFalse(r['mentions'][0]['observed_candidates'])

    def test_symbol_boundary_prevents_substring_support(self):
        c=inspect_entity('a.py:C.helper',entity_metadata(GRAPH),[evidence('3:         return self.helper_extra()')])
        self.assertEqual(c['observations'],[])

    def test_exact_entity_id_not_a_prefix_match(self):
        e=evidence('a.py:C.helper_extra',tool='locagent_retrieve',args={'query':'fixture'})
        c=inspect_entity('a.py:C.helper',entity_metadata(GRAPH),[e])
        self.assertFalse(c['exact_id_visible'])

if __name__=='__main__':unittest.main()
