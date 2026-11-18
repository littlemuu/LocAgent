import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from calibration.policy import EvidenceLedger, HEADINGS, calibrate, sections, violations
from readonly_agent.read_lines import LineReader


def ledger(source='def f():\n    return 1\n', path='a.py'):
    return EvidenceLedger(SimpleNamespace(files={path: source}))


def read(e, start, end, *, cursor=None, next_cursor=None, path='a.py'):
    text = ''.join(f'{n}: {e.lines[path][n-1]}\n' for n in range(start, end+1))
    e.observe(dict(tool='read_file', arguments=dict(path=path, start_line=start, end_line=end, cursor=cursor),
                   result=dict(text=text, start_line=start, end_line=end, start_column=0,
                               end_column=len(e.lines[path][end-1]), next_cursor=next_cursor)))


def packet(answer=None):
    return dict(files=['a.py'], entities=['a.py:f'], answer=answer or '\n'.join([
        HEADINGS[0], 'a.py:1-2 函数返回常量。', HEADINGS[1],
        '待验证假设：a.py:f 的常量返回可能与问题有关。', HEADINGS[2],
        '调用链和运行行为未核验。最小验证：`assert f() == 1`']))


class CoverageTests(unittest.TestCase):
    def test_requested_end_is_not_delivered_end_and_strong_claim_is_removed(self):
        e = ledger('def f():\n    x = 1\n    return x\n')
        read(e, 1, 2, next_cursor='page2')
        e.audit[0]['arguments']['end_line'] = 3
        p, a = calibrate(packet('已确认根因在 a.py:1-3，不是 bug，无需修改。'), e)
        self.assertTrue(a['fallback']); self.assertFalse(e.complete_entity('a.py:f'))
        self.assertIn('R3_unverified_strong_claim', a['violations'])
        self.assertIn('a.py:f：未读完', p['answer']); self.assertIn('分页未读完', p['answer'])
        self.assertNotIn('已确认根因', p['answer']); self.assertNotIn('a.py:1-3', p['answer'])

    def test_real_cursor_fragments_unicode_join_without_crediting_missing_bytes(self):
        source = 'def f():\n    return ' + repr('界'*500) + '\n'
        snap = SimpleNamespace(files={'a.py':source}, identity='fixture')
        e = EvidenceLedger(snap); reader = LineReader(snap)
        args = {'path':'a.py', 'start_line':1, 'end_line':2}
        pages = 0
        while True:
            result = reader.read(args, 450)
            e.observe({'tool':'read_file','arguments':dict(args),'result':result}); pages += 1
            if not result['next_cursor']: break
            self.assertFalse(e.complete_entity('a.py:f'))
            args = {'path':'a.py','cursor':result['next_cursor']}
        self.assertGreater(pages, 2); self.assertTrue(e.complete_entity('a.py:f')); self.assertFalse(e.pending)

    def test_end_of_requested_range_does_not_mean_end_of_function(self):
        e = ledger('def f():\n    x = 1\n    return x\n'); read(e,1,2)
        self.assertFalse(e.pending); self.assertFalse(e.complete_entity('a.py:f'))
        self.assertTrue(any(v.startswith('R1_body') for v in violations(packet(),e)))

    def test_preview_omission_and_search_hit_never_count_as_body(self):
        e=ledger('def f():\n    """doc"""\n    return 1\n')
        e.observe({'tool':'locagent_retrieve','arguments':{'query':'f','offset':0},'result':{
            'text':'path=a.py; lines=1-3;\n1: def f():\n... lines 2-2 omitted ...\n3:     return 1\n','next_offset':None}})
        e.observe({'tool':'search_text','arguments':{'query':'doc'},'result':{'text':'a.py:2:     """doc"""','next_offset':None}})
        self.assertFalse(e.complete_entity('a.py:f')); self.assertFalse(e.covers('a.py',1,3))
        read(e,2,2); self.assertTrue(e.complete_entity('a.py:f'))

    def test_preview_split_header_reassembled_only_with_contiguous_pages(self):
        e=ledger(); text='path=a.py; lines=1-2;\n1: def f():\n2:     return 1\n'
        for offset,chunk in [(10,text[10:]),(0,text[:10])]:
            e.observe({'tool':'locagent_retrieve','arguments':{'query':'f','offset':offset},'result':{'text':chunk,'next_offset':None}})
            if offset: self.assertFalse(e.complete_entity('a.py:f'))
        self.assertTrue(e.complete_entity('a.py:f'))

    def test_missing_decorator_and_duplicate_definitions_are_not_complete(self):
        e=ledger('@decorator\ndef f():\n    return 1\ndef f():\n    return 2\n')
        read(e,2,3); self.assertFalse(e.complete_entity('a.py:f'))
        read(e,1,1); self.assertFalse(e.complete_entity('a.py:f'))
        read(e,4,5); self.assertTrue(e.complete_entity('a.py:f'))

    def test_invalid_snippet_and_wrong_path_are_not_credited(self):
        e=ledger(); e.credit('a.py',2,'    return 2'); e.credit('missing.py',1,'abc')
        self.assertFalse(e.fragments)

    def test_physical_unicode_line_separator_is_not_a_source_line(self):
        e=ledger('def f():\r\n    return "a\u2028b"\r\n'); read(e,1,2)
        self.assertEqual(len(e.lines['a.py']),2); self.assertTrue(e.complete_entity('a.py:f'))

    def test_body_priority_releases_after_candidate_is_fully_read(self):
        e=ledger();e.candidates.add('a.py:f')
        self.assertFalse(e.read_priority('search_text',1,4))
        self.assertTrue(e.read_priority('search_text',2,4))
        self.assertFalse(e.read_priority('read_file',2,4))
        read(e,1,2);self.assertFalse(e.read_priority('search_text',2,4))


class DiagnosticTests(unittest.TestCase):
    def test_three_sections_and_valid_hypothesis_survive(self):
        e=ledger(); read(e,1,2); p=packet(); result,a=calibrate(p,e)
        self.assertFalse(a['fallback']); self.assertEqual(set(sections(result['answer'])),set(HEADINGS))
        self.assertIn('常量返回可能',result['answer']); self.assertEqual(result['files'],p['files'])
        self.assertEqual(result['entities'],p['entities']); self.assertFalse(a['quality_measured'])

    def test_sections_missing_duplicate_reordered_and_preamble_rejected(self):
        e=ledger();read(e,1,2)
        for text in ['freeform',packet()['answer']+'\n推断\nextra','preamble\n'+packet()['answer'],packet()['answer'].replace(HEADINGS[0],HEADINGS[2])]:
            with self.subTest(text=text):self.assertIn('R2_three_sections',violations(packet(text),e))

    def test_citation_range_hole_and_missing_path_rejected(self):
        e=ledger('def f():\n    x = 1\n    return x\n');read(e,1,1);read(e,3,3)
        for citation in ['a.py:1-3','a.py:4','other.py:1','a.py:3-1']:
            self.assertTrue(any(v.startswith('R4_citation') for v in violations(packet(packet()['answer'].replace('a.py:1-2',citation)),e)))

    def test_unread_entity_mentioned_only_in_answer_is_checked(self):
        e=ledger();read(e,1,2);p=packet();p['answer']=p['answer'].replace('a.py:f 的','b.py:g 的')
        self.assertIn('R1_body_incomplete_unmarked:b.py:g',violations(p,e))

    def test_no_minimal_validation_and_unmarked_inference_are_rejected(self):
        e=ledger();read(e,1,2)
        self.assertIn('R3_missing_minimal_validation',violations(packet(packet()['answer'].replace('最小验证：','验证：')),e))
        self.assertIn('R3_inference_not_hypothesis',violations(packet(packet()['answer'].replace('待验证假设：','确定：')),e))

    def test_full_function_does_not_prove_chain_or_authorize_strong_claim(self):
        e=ledger();read(e,1,2)
        for claim in ['The root cause is f.', 'This is not a bug.', 'no code change is warranted', '无需修改', '已确认根因']:
            p,a=calibrate(packet(packet()['answer'].replace('待验证假设：a.py:f 的常量返回可能与问题有关。','待验证假设：'+claim)),e)
            self.assertTrue(a['fallback']);self.assertFalse(a['call_chain_complete']);self.assertNotIn(claim,p['answer'])

    def test_no_evidence_fallback_preserves_unknown_candidates(self):
        e=ledger();p=packet();p['entities']=['unknown.py:g'];p['files']=['unknown.py']
        result,a=calibrate(p,e);self.assertEqual(result['entities'],p['entities']);self.assertFalse(violations(result,e))
        self.assertIn('尚无可引用的完整源码行',result['answer']);self.assertIn('unknown.py:g：未读完',result['answer'])


class SDKTests(unittest.TestCase):
    def setup_case(self, root):
        from readonly_agent.core import Snapshot
        from locagent_e2e.baseline import CurrentRetriever
        (root/'a.py').write_text('def f():\n    return 1\n')
        snap=Snapshot(root,['a.py']);snap.e2e_source_root=root
        return CurrentRetriever(snap)

    def test_four_requests_schema_parity_and_calibrated_sdk_finish(self):
        from calibration.locator import run
        from locagent_e2e.agent import run as b_run
        from locagent_e2e.transport import ScriptedTransport
        from test_preparation import response
        class Capture(ScriptedTransport):
            def __init__(self,responses):super().__init__(responses);self.payloads=[]
            def exchange(self,payload):self.payloads.append(copy.deepcopy(payload));return super().exchange(payload)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); retriever=self.setup_case(root)
            responses=[response('read_file',{'path':'a.py','start_line':1,'end_line':2},i) for i in range(1,4)] + [response('finish',{'message':packet('The root cause is f; no code change is warranted.')},4)]
            c=Capture(copy.deepcopy(responses));b=Capture(copy.deepcopy(responses))
            r=run(issue='fixture',output=root/'C',transport=c,locator=retriever,scripted=True)
            old=b_run(issue='fixture',output=root/'B',transport=b,locator=retriever,scripted=True)
            self.assertEqual(r['status'],'completed',r);self.assertEqual(r['requests'],4)
            self.assertEqual(r['budget'],old['budget']);self.assertEqual(r['tool_schema_sha256'],old['tool_schema_sha256'])
            for cb,bb in zip(c.payloads,b.payloads):
                for key in ['tools','model','temperature','max_tokens','thinking','stream','tool_choice']:
                    self.assertEqual(cb[key],bb[key],key)
            self.assertEqual([t['function']['name'] for t in c.payloads[-1]['tools']],['finish'])
            self.assertNotIn('root cause',r['finished']['answer']);self.assertIn('root cause',old['finished']['answer'])
            audit=json.loads((root/'C/diagnostic-audit.json').read_text());self.assertTrue(audit['fallback'])
            event_text='\n'.join(p.read_text() for p in (root/'C/events').rglob('*.json'))
            self.assertIn('待验证假设',event_text)
            from locagent_e2e.common import digest
            proof=dict(mode='synthetic SDK protocol test; NOT real v8 quality',requests_B=old['requests'],requests_C=r['requests'],
                SDK_tool_schema_B=old['tool_schema_sha256'],SDK_tool_schema_C=r['tool_schema_sha256'],
                wire_tool_schemas_B=[digest(x['tools']) for x in b.payloads],wire_tool_schemas_C=[digest(x['tools']) for x in c.payloads],
                budget_B=old['budget'],budget_C=r['budget'],model=c.payloads[0]['model'],raw_rejected_answer_retained=audit['fallback'])
            (Path(__file__).resolve().parents[1]/'delivery/locator-contract-evidence.json').write_text(json.dumps(proof,indent=2)+'\n')

    def test_coding_request_contract_unchanged_except_packet_content(self):
        from calibration.locator import build_packet
        from locagent_e2e.agent import run
        from locagent_e2e.transport import ScriptedTransport
        from test_preparation import response,LocalFixture
        class Capture(ScriptedTransport):
            def exchange(self,payload):self.payload=copy.deepcopy(payload);return super().exchange(payload)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e=ledger();calibrated,_=calibrate(packet('old assertion'),e);payloads=[];results=[]
            for arm,p in [('B',packet('old assertion')),('C',calibrated)]:
                p=build_packet({'status':'completed','finished':p},instance_id='fixture__repo-1',base_commit='fixture')
                t=Capture([response('finish',{'message':'fixture complete'},1)])
                results.append(run(issue='fixture',output=root/arm,transport=t,sandbox=LocalFixture(root),packet=p,scripted=True))
                user=next(m for m in t.payload['messages'] if m['role']=='user')
                body=json.loads(user['content']);self.assertEqual(set(body),{'issue','localization_packet'})
                self.assertEqual(set(body['localization_packet']),{'version','instance_id','base_commit','result'})
                self.assertEqual(set(body['localization_packet']['result']),{'files','entities','answer'})
                body['localization_packet']=None;user['content']=json.dumps(body);payloads.append(t.payload)
            self.assertEqual(payloads[0],payloads[1])
            for key in ['system_prompt_sha256','tool_schema_sha256','budget']:
                self.assertEqual(results[0][key],results[1][key])
            from locagent_e2e.common import digest
            proof=dict(mode='synthetic coding first-request parity; NOT real C run',
                packet_envelope=['version','instance_id','base_commit','result'],result_keys=['files','entities','answer'],
                request_hash_with_only_packet_removed_B=digest(payloads[0]),request_hash_with_only_packet_removed_C=digest(payloads[1]),
                contracts=[{key:r[key] for key in ['system_prompt_sha256','tool_schema_sha256','budget']} for r in results])
            (Path(__file__).resolve().parents[1]/'delivery/coding-contract-evidence.json').write_text(json.dumps(proof,indent=2)+'\n')

    def test_plain_text_and_malformed_finish_fail_without_retry(self):
        from calibration.locator import run
        from locagent_e2e.transport import ScriptedTransport
        from test_preparation import response
        from test_completion_and_edits import text_response
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); retriever=self.setup_case(root)
            for i,raw in enumerate([text_response(),response('finish',{'message':{'answer':'x'}},1)]):
                t=ScriptedTransport([raw]);r=run(issue='fixture',output=root/str(i),transport=t,locator=retriever,scripted=True)
                self.assertEqual(r['status'],'failed');self.assertEqual(len(t.records),1);self.assertIsNone(r['finished'])

    def test_packet_envelope_refuses_failure_and_oversize(self):
        from calibration.locator import build_packet
        with self.assertRaises(ValueError):build_packet({'status':'failed'},instance_id='fixture',base_commit='fixture')
        with self.assertRaises(RuntimeError):build_packet({'status':'completed','finished':packet('界'*15000)},instance_id='fixture',base_commit='fixture')

    def test_sdk_cannot_expand_search_while_candidate_body_is_incomplete(self):
        from calibration.locator import run
        from locagent_e2e.transport import ScriptedTransport
        from locagent_e2e.baseline import CurrentRetriever
        from readonly_agent.core import Snapshot
        from test_preparation import response
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'a.py').write_text('def f():\n    """docstring omitted in preview"""\n    return 1\n')
            snap=Snapshot(root,['a.py']);snap.e2e_source_root=root
            t=ScriptedTransport([response('locagent_retrieve',{'query':'f','offset':0},1),
                response('search_text',{'query':'unrelated','offset':0},2),
                response('read_file',{'path':'a.py','start_line':1,'end_line':3},3),
                response('finish',{'message':packet('root cause is f')},4)])
            r=run(issue='fixture',output=root/'out',transport=t,locator=CurrentRetriever(snap),scripted=True)
            self.assertEqual(r['status'],'completed',r);self.assertEqual(r['requests'],4)
            self.assertEqual(r['tool_audit'][1]['result']['error'],'candidate_body_read_priority')
            self.assertEqual(r['tool_calls'],3);self.assertLessEqual(r['source_bytes'],14336)

    def test_bare_function_inference_cannot_hide_an_unread_helper(self):
        e=ledger('def f():\n    return helper()\ndef helper():\n    return 1\n');read(e,1,2)
        p=packet();p['answer']=p['answer'].replace('常量返回可能','helper() 可能')
        self.assertIn('R1_body_incomplete_unmarked:a.py:helper',violations(p,e))
