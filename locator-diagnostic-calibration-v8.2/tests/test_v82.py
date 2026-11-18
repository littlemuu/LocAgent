"""Soft-gate unit regressions and stored-answer replay; no live transports."""
import ast
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from calibration.policy import (EvidenceLedger, HEADINGS, INSTRUCTION, DISCLOSURE_HEADING,
                                calibrate, violations, referenced_entities)
from test_calibration import ledger, read, packet

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent/'fixtures'

def search(e, text, **kwargs):
    e.observe({'tool':'search_text','arguments':{'query':kwargs.pop('query','x'),'offset':kwargs.pop('offset',0)},
               'result':{'text':text,'next_offset':kwargs.pop('next_offset',None)}})

class V82Tests(unittest.TestCase):
    def test_soft_gate_preserves_every_original_character(self):
        e=ledger();p=packet();p['answer']=p['answer'].replace('待验证假设：','已确认：')+'\n  '
        original=copy.deepcopy(p);r,a=calibrate(p,e)
        self.assertFalse(a['fallback']);self.assertEqual(p,original)
        self.assertTrue(r['answer'].startswith(p['answer']+'\n\n'+DISCLOSURE_HEADING+'\n'))
        self.assertEqual(a['rule_counts'],{'R1':1,'R2':0,'R3':2,'R4':1})
        self.assertEqual(a['disclosure_count'],4)
        self.assertEqual(r['files'],p['files']);self.assertEqual(r['entities'],p['entities'])
        self.assertEqual([d['violation'] for d in a['disclosures']],a['violations'])

    def test_clean_answer_has_no_injected_or_rewritten_body(self):
        e=ledger();read(e,1,2);p=packet();r,a=calibrate(p,e)
        self.assertEqual(r,p);self.assertFalse(a['disclosure_attached']);self.assertEqual(a['violation_count'],0)

    def test_only_structure_failure_is_hard_gate(self):
        for answer in ['freeform',packet()['answer']+'\n推断\nextra',packet()['answer'].replace('推断\n','推断\n未核验点\n')]:
            r,a=calibrate(packet(answer),ledger())
            self.assertTrue(a['fallback']);self.assertIn('R2_three_sections',a['violations'])
            self.assertFalse(a['disclosure_attached']);self.assertIn('候选实体：',r['answer'])

    def test_error_in_disclosure_also_uses_fixed_fallback_once(self):
        p=packet()
        with patch('calibration.policy.disclosure_items',side_effect=ValueError('bad disclosure')):
            r,a=calibrate(p,ledger())
        self.assertTrue(a['fallback']);self.assertEqual(a['validator_error'],'ValueError')
        self.assertIn('python -m pytest -q',r['answer'])

    def test_def_start_accepted_but_investigation_still_strict(self):
        e=ledger('@decorate\ndef f():\n    """doc"""\n    return 1\n');e.candidates.add('a.py:f')
        read(e,2,4)
        self.assertTrue(e.validation_complete_entity('a.py:f'))
        self.assertFalse(e.complete_entity('a.py:f'));self.assertTrue(e.read_priority('search_text',2,4))
        self.assertNotIn('R1_body_incomplete_unmarked:a.py:f',violations(packet(),e))
        read(e,1,1);self.assertTrue(e.complete_entity('a.py:f'))

    def test_def_body_docstring_gap_remains_unverified(self):
        e=ledger('@decorate\ndef f():\n    """doc"""\n    return 1\n');read(e,2,2);read(e,4,4)
        self.assertFalse(e.validation_complete_entity('a.py:f'))
        self.assertIn('R1_body_incomplete_unmarked:a.py:f',violations(packet(),e))

    def test_duplicate_defs_need_all_bodies(self):
        e=ledger('@decorate\ndef f():\n    return 1\ndef f():\n    return 2\n');read(e,2,3)
        self.assertFalse(e.validation_complete_entity('a.py:f'));read(e,4,5)
        self.assertTrue(e.validation_complete_entity('a.py:f'))

    def test_unique_filename_citation_and_entity(self):
        e=EvidenceLedger(SimpleNamespace(files={'pkg/a.py':'def f():\n    return 1\n'}));read(e,1,2,path='pkg/a.py')
        p=packet();p['files']=['pkg/a.py'];p['entities']=['pkg/a.py:f']
        self.assertEqual(violations(p,e),[])

    def test_ambiguous_filename_is_not_guessed(self):
        e=EvidenceLedger(SimpleNamespace(files={'one/a.py':'def f():\n    return 1\n','two/a.py':'def f():\n    return 2\n'}))
        read(e,1,2,path='one/a.py');read(e,1,2,path='two/a.py')
        p=packet();p['files']=['one/a.py','two/a.py'];p['entities']=[]
        self.assertIn('R4_citation_not_delivered:a.py:1-2',violations(p,e))

    def test_search_supports_literal_narrow_fact_without_body_credit(self):
        e=ledger('def f():\n    x = 1\n    return x\n');search(e,'a.py:2:     x = 1\n')
        p=packet();p['answer']=p['answer'].replace('a.py:1-2 函数返回常量。','a.py:2 搜索命中：`x = 1`。')
        self.assertNotIn('R4_citation_not_delivered:a.py:2',violations(p,e))
        self.assertFalse(e.covers('a.py',2,2));self.assertFalse(e.validation_complete_entity('a.py:f'))
        self.assertIn('R1_body_incomplete_unmarked:a.py:f',violations(p,e))

    def test_search_never_supports_contiguous_range_even_adjacent(self):
        e=ledger('def f():\n    return 1\n');search(e,'a.py:1: def f():\na.py:2:     return 1\n')
        self.assertIn('R4_citation_not_delivered:a.py:1-2',violations(packet(),e))
        self.assertFalse(e.validation_complete_entity('a.py:f'))

    def test_search_does_not_support_unshown_assignment_or_default_or_global_claim(self):
        e=ledger('x = 1\n');search(e,'a.py:1: x = 1\n')
        for claim in ['a.py:1 `x = 2`。','a.py:1 x 默认 False。','a.py:1 所有分支中 x 均为1。']:
            p=packet();p['answer']=p['answer'].replace('a.py:1-2 函数返回常量。',claim)
            self.assertIn('R4_citation_not_delivered:a.py:1',violations(p,e))

    def test_search_page_cut_is_not_complete_row(self):
        e=ledger();search(e,'a.py:2:     ret',next_offset=17)
        self.assertFalse(e.search_hits)
        text='a.py:2:     return 1\n';e=ledger();cut=14
        search(e,text[cut:],offset=cut);self.assertFalse(e.search_hits)
        search(e,text[:cut],next_offset=cut);self.assertIn(('a.py',2),e.search_hits)

    def test_search_clause_assignment_not_applied_to_other_file(self):
        e=ledger();search(e,'a.py:1: alias = str\nb.py:2: isinstance(x, alias)\n')
        p=packet();p['answer']=p['answer'].replace('a.py:1-2 函数返回常量。','搜索命中：a.py:1 `alias = str`；b.py:2 使用 `isinstance(x, alias)`。')
        self.assertFalse(any(v.startswith('R4_citation') for v in violations(p,e)))

    def test_unread_ranges_and_validation_targets_are_not_read_assertions(self):
        e=ledger();read(e,1,2);p=packet();p['answer']+='\n- 未读 b.py:10-100。\n最小验证：`python -m pytest b.py`，观察 b.py:200。'
        self.assertEqual(violations(p,e),[])

    def test_hypothesis_root_cause_allowed_certainty_disclosed(self):
        e=ledger();read(e,1,2)
        for claim in ['根因在 a.py:f','根因是 a.py:f','The root cause is a.py:f']:
            p=packet();p['answer']=p['answer'].replace('a.py:f 的常量返回可能与问题有关。',claim)
            self.assertEqual(violations(p,e),[])
        p=packet();p['answer']=p['answer'].replace('a.py:f 的常量返回可能与问题有关。','已确认根因在 a.py:f')
        r,a=calibrate(p,e);self.assertFalse(a['fallback']);self.assertIn('R3_unverified_strong_claim',a['violations'])
        self.assertIn('- [R3] a.py:f',r['answer'])

    def test_short_unique_unread_and_synonyms(self):
        for phrase in ['`f` 函数体未读','未读 `f` 函数头','`f` 正文未核验','`f` 函数体被截断']:
            p=packet();p['answer']+='\n'+phrase
            self.assertNotIn('R1_body_incomplete_unmarked:a.py:f',violations(p,ledger()))

    def test_short_unread_ambiguous_requires_file(self):
        e=EvidenceLedger(SimpleNamespace(files={'a.py':'def f():\n    pass\n','b.py':'def f():\n    pass\n'}))
        p=packet();p['files'].append('b.py');p['entities'].append('b.py:f');p['answer']+='\n`f` 函数体未读完。'
        for entity in p['entities']:self.assertIn('R1_body_incomplete_unmarked:'+entity,violations(p,e))
        p['answer']+='\na.py 的 `f` 函数体未读完。'
        self.assertNotIn('R1_body_incomplete_unmarked:a.py:f',violations(p,e))
        self.assertIn('R1_body_incomplete_unmarked:b.py:f',violations(p,e))

    def test_other_callsite_unread_is_not_containing_function_unread(self):
        e=ledger('class C:\n    def __init__(self):\n        self._init()\n    def _init(self):\n        pass\n')
        p=packet();p['entities']=['a.py:C.__init__'];p['answer']=p['answer'].replace('a.py:f','a.py:C.__init__')
        p['answer']=p['answer'].replace('常量返回可能与问题有关。','分配可能有关（该分配处未读，属未核验）。')
        p['answer']+='\n未读 C._init（分配处）。'
        self.assertIn('R1_body_incomplete_unmarked:a.py:C.__init__',violations(p,e))

    def test_alias_is_not_a_function_body(self):
        e=ledger('builtin_str = str\n');p=packet();p['entities']=['a.py:builtin_str'];p['answer']=p['answer'].replace('a.py:f','a.py:builtin_str')
        self.assertFalse(any(v.startswith('R1_body') for v in violations(p,e)))

    def test_commands_and_directory_words_do_not_create_entities(self):
        e=ledger('def f():\n    return 1\ndef helper():\n    pass\n');read(e,1,2);p=packet()
        p['answer']+='\n最小验证：`python a.py:helper`；目录 helper/。'
        self.assertNotIn('a.py:helper',referenced_entities(p,e));self.assertEqual(violations(p,e),[])

    def test_pending_synonyms_exact_cursors(self):
        e=ledger();e.pending={'cursor-one':'a.py','cursor-two':'a.py'}
        for label in ['两处分页未续读：cursor-one 与 cursor-two','未读完：cursor-one、cursor-two 未续读']:
            p=packet();p['answer']+='\n'+label
            self.assertNotIn('R1_cursor_unfinished_unmarked',violations(p,e))
        p=packet();p['answer']+='\n未续读 cursor-one'
        self.assertIn('R1_cursor_unfinished_unmarked',violations(p,e))

    def test_missing_validation_has_targeted_soft_disclosure(self):
        e=ledger();read(e,1,2);p=packet();p['answer']=p['answer'].replace('最小验证：','验证：')
        r,a=calibrate(p,e);self.assertFalse(a['fallback']);self.assertEqual(a['rule_counts']['R3'],1)
        self.assertIn('- [R3] a.py:f',r['answer'])

    def test_recorded_unknown_spans_not_invented_and_search_not_body(self):
        p=packet();audit={'raw_packet':p,'violations':['R1_body_incomplete_unmarked:a.py:f'],'entity_body_complete':{'a.py:f':False},'pending_read_pages':{},'delivered_full_line_ranges':[]}
        e=EvidenceLedger.from_recorded(audit,[{'tool':'search_text','arguments':{'query':'f'},'result':{'text':'a.py:1: def f():\na.py:2:     return 1\n','next_offset':None}}])
        self.assertEqual(e.def_spans,{});self.assertFalse(e.validation_complete_entity('a.py:f'))
        self.assertFalse(e.lines);self.assertFalse(e.covers('a.py',1,2))

    def test_prompt_notice_and_investigation_methods_unchanged(self):
        old=ROOT.parent/'locator-diagnostic-calibration-v8.1/calibration/policy.py'
        def nodes(path):
            tree=ast.parse(path.read_text());out={}
            for node in tree.body:
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INSTRUCTION' for t in node.targets):out['INSTRUCTION']=ast.literal_eval(node.value)
                if isinstance(node,ast.ClassDef) and node.name=='EvidenceLedger':
                    for child in node.body:
                        if isinstance(child,ast.FunctionDef) and child.name in ['complete_entity','notice','incomplete_candidates','read_priority']:out[child.name]=ast.dump(child,include_attributes=False)
            return out
        self.assertEqual(nodes(old),nodes(ROOT/'calibration/policy.py'))

class RecordedReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((FIXTURES/'v81-recorded24.json').read_text())
        cls.review=json.loads((FIXTURES/'v81-reviewed55.json').read_text())
        cls.results={c['instance_id']:calibrate(c['audit']['raw_packet'],EvidenceLedger.from_recorded(c['audit'],c['tool_audit'])) for c in cls.cases}

    def test_all_24_original_bodies_preserved_and_deliverable(self):
        self.assertEqual(len(self.cases),24)
        for c in self.cases:
            with self.subTest(case=c['instance_id']):
                r,a=self.results[c['instance_id']];raw=c['audit']['raw_packet']
                self.assertFalse(a['fallback']);self.assertIsNone(a['validator_error'])
                self.assertEqual(r['files'],raw['files']);self.assertEqual(r['entities'],raw['entities'])
                suffix=('\n\n'+DISCLOSURE_HEADING+'\n'+'\n'.join('- ['+d['rule']+'] '+'；'.join(d['targets']) for d in a['disclosures'])) if a['disclosure_count'] else ''
                self.assertEqual(r['answer'],raw['answer']+suffix)
                envelope={'version':1,'instance_id':c['instance_id'],'base_commit':'x'*40,'result':r}
                self.assertLessEqual(len(json.dumps(envelope,ensure_ascii=False).encode()),14336)

    def test_seven_true_findings_all_disclosed(self):
        rows=[v for v in self.review if v['classification']=='真违规'];self.assertEqual(len(rows),7)
        for v in rows:
            with self.subTest(id=v['id']):
                r,a=self.results[v['instance_id']]
                self.assertIn(v['recorded_violation'],[d['violation'] for d in a['disclosures']])
                d=next(d for d in a['disclosures'] if d['violation']==v['recorded_violation'])
                for target in d['targets']:self.assertIn(target,r['answer'].split(DISCLOSURE_HEADING)[-1])

    def test_thirty_one_false_positives_all_removed(self):
        rows=[v for v in self.review if v['classification']=='误判'];self.assertEqual(len(rows),31)
        for v in rows:
            with self.subTest(id=v['id']):self.assertNotIn(v['recorded_violation'],self.results[v['instance_id']][1]['violations'])

    def test_reference_labels_not_needed_for_replay(self):
        # No expectations/classifications/instance IDs enter calibrate/ledger.
        for c in self.cases:
            audit=copy.deepcopy(c['audit']);audit.pop('policy',None)
            result=calibrate(audit['raw_packet'],EvidenceLedger.from_recorded(audit,c['tool_audit']))
            self.assertEqual(result,self.results[c['instance_id']])
