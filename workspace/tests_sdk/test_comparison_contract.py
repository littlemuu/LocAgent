import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from copy import deepcopy

from readonly_agent.core import Snapshot, encoded, digest
from readonly_agent.journal import Ledger
from readonly_agent.preparation import make_plan, PreparationSession
from readonly_agent.offline import no_network
from experiments.eval_preflight.common_contract import (
    SharedWire, FINISH, raw_payload, validate_response, check_messages, ContractError)
from experiments.eval_preflight.native_adapter import CommonPages
from experiments.eval_preflight.body_index import chunks


def reply(name='finish', args=None, count=1):
    if args is None: args={'message':{'files':[],'entities':[],'answer':'unknown'}}
    return {'id':'offline-only','model':'deepseek-flash','usage':{
        'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100},
        'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
            'tool_calls':[{'id':f'call-{i}','type':'function','function':{'name':name,'arguments':json.dumps(args)}} for i in range(count)]}}]}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        (self.root/'a.py').write_bytes(b'\xef\xbb\xbfdef f():\r\n    return "ok"\r\n')
        self.snap=Snapshot(self.root,['a.py']);self.plan=make_plan(self.snap,'offline synthetic')
        self.ledger=Ledger.create(self.root/'ledger.sqlite',self.plan)
        self.wire=SharedWire(self.ledger,'baseline',self.snap)
        self.messages=[{'role':'user','content':'offline fixture'}]
        self.tools=[FINISH,{'type':'function','function':{'name':'read_file','parameters':{'type':'object'}}}]
        self.guard=no_network(self.root/'profiles');self.guard.__enter__()
        self.addCleanup(self.guard.__exit__,None,None,None)
        import httpx
        self.httpx=httpx

    def transport(self,raw=None,status=200):
        return self.httpx.MockTransport(lambda request:self.httpx.Response(status,json=raw or reply()))

    def test_model_fields_and_finish_schema(self):
        data=json.loads(raw_payload(self.messages,self.tools,closing=True))
        self.assertEqual((data['model'],data['max_tokens'],data['temperature']),('deepseek-flash',2048,0))
        self.assertEqual(data['tools'],[FINISH]);self.assertEqual(data['thinking'],{'type':'disabled'})

    def test_committed_before_io_both_arms(self):
        def handler(request):
            reopened=Ledger(self.ledger.path,digest(self.plan))
            self.assertEqual(reopened.summary()['calls'][-1]['status'],'reserved')
            return self.httpx.Response(200,json=reply())
        for wire in [self.wire,SharedWire(self.ledger,'retrieval',self.snap)]:
            wire.exchange(self.messages,self.tools,False,self.httpx.MockTransport(handler));wire.finish()
        self.assertEqual(len(self.ledger.summary()['calls']),2)

    def test_live_transport_rejected_before_reservation(self):
        with self.assertRaises(PermissionError):self.wire.exchange(self.messages,self.tools,False,object())
        with self.assertRaises(PermissionError):self.wire.live()
        self.assertEqual(self.ledger.summary()['calls'],[])

    def test_truncated_receipt_preserved_and_halts(self):
        raw=reply();raw['choices'][0]['finish_reason']='length'
        with self.assertRaisesRegex(ContractError,'output_truncated'):
            self.wire.exchange(self.messages,self.tools,False,self.transport(raw))
        self.assertTrue(self.ledger.summary()['halted'])
        self.assertEqual(self.ledger.summary()['calls'][0]['status'],'settled')
        with self.assertRaises(RuntimeError):self.wire.exchange(self.messages,self.tools,False,self.transport())

    def test_timeout_unknown_no_retry_or_other_arm(self):
        seen=[]
        def handler(request):seen.append(1);raise self.httpx.ReadTimeout('fixture')
        transport=self.httpx.MockTransport(handler)
        with self.assertRaises(self.httpx.ReadTimeout):self.wire.exchange(self.messages,self.tools,False,transport)
        with self.assertRaises(RuntimeError):self.wire.exchange(self.messages,self.tools,False,transport)
        with self.assertRaises(RuntimeError):SharedWire(self.ledger,'retrieval',self.snap)
        self.assertEqual(seen,[1]);self.assertEqual(self.ledger.summary()['calls'][0]['status'],'unknown')

    def test_http_failure_stops(self):
        with self.assertRaises(RuntimeError):self.wire.exchange(self.messages,self.tools,False,self.transport(status=503))
        self.assertTrue(self.ledger.summary()['halted'])

    def test_cumulative_cap_rejects_entire_batch(self):
        raw=reply('read_file',{'path':'a.py'},count=2)
        self.wire.calls=15
        with self.assertRaisesRegex(ContractError,'cumulative_tool_budget'):
            self.wire.exchange(self.messages,self.tools,False,self.transport(raw))
        self.assertEqual(self.wire.calls,15)

    def test_exhausted_tools_force_finish(self):
        self.wire.calls=16
        raw,available,closed=self.wire.exchange(self.messages,self.tools,False,self.transport())
        self.assertTrue(closed);self.assertEqual(available,{'finish'})

    def test_fourth_request_is_finish_only(self):
        for _ in range(3):self.wire.exchange(self.messages,self.tools,False,self.transport(reply('read_file',{'path':'a.py'})))
        _,names,closed=self.wire.exchange(self.messages,self.tools,False,self.transport())
        self.assertTrue(closed);self.assertEqual(names,{'finish'})
        with self.assertRaises(RuntimeError):self.wire.exchange(self.messages,self.tools,True,self.transport())

    def test_closing_violation(self):
        with self.assertRaises(ContractError):self.wire.exchange(self.messages,self.tools,True,self.transport(reply('read_file',{})))

    def test_duplicates_and_mixed_finish(self):
        for raw in [reply(count=2),reply('read_file',{},count=2)]:
            raw['choices'][0]['message']['tool_calls'][1]['id']='call-0'
            with self.assertRaises(ContractError):validate_response(raw,{'finish','read_file'},False,16,self.snap)

    def test_cross_turn_duplicate_id_rejected_before_execution(self):
        with self.assertRaises(ContractError):
            validate_response(reply('read_file',{}),{'read_file'},False,16,self.snap,{'call-0'})

    def test_exact_request_byte_boundary(self):
        messages=[{'role':'user','content':''}]
        overhead=len(raw_payload(messages,[FINISH],closing=False))
        messages[0]['content']='x'*(65536-overhead)
        self.assertEqual(len(raw_payload(messages,[FINISH],closing=False)),65536)
        messages[0]['content']+='x'
        with self.assertRaisesRegex(ContractError,'request_bytes_exhausted'):
            raw_payload(messages,[FINISH],closing=False)

    def test_null_compatibility_and_unknown_extension(self):
        args={'message':{'files':[],'entities':[],'answer':'ok','entities_note':None}}
        self.assertEqual(validate_response(reply(args=args),{'finish'},True,16,self.snap),0)
        args['message']['secret_extra']='not discardable'
        with self.assertRaises(ValueError):validate_response(reply(args=args),{'finish'},True,16,self.snap)

    def test_unknown_symbol_is_valid_localization_prediction(self):
        args={'message':{'files':['a.py'],'entities':['a.py:WrongButValid'],'answer':'uncertain'}}
        self.assertEqual(validate_response(reply(args=args),{'finish'},True,16,self.snap),0)
        args['message']['files']=['outside.py']
        with self.assertRaises(ValueError):validate_response(reply(args=args),{'finish'},True,16,self.snap)

    def test_top_six_rejected(self):
        args={'message':{'files':['a.py'],'entities':[f'a.py:f{i}' for i in range(6)],'answer':'ok'}}
        with self.assertRaises(ValueError):validate_response(reply(args=args),{'finish'},True,16,self.snap)

    def test_raw_unicode_pages_reassemble_and_repeated_pages_charge(self):
        pages=CommonPages();raw=('中文\r\n\\"'*600)
        out=pages.add(raw,'read',{});offset=0;text=''
        while True:
            message=pages.page(out,offset,'call','read');body=json.loads(message['content'])
            self.assertLessEqual(len(message['content'].encode()),4096)
            text+=body['text'];offset=body['next_offset']
            if offset is None:break
        self.assertEqual(text,raw)
        before=pages.delivered_bytes
        if before<10240:
            pages.page(out,0,'repeated','read');self.assertGreater(pages.delivered_bytes,before)

    def test_pagination_invalid_cursor_empty_and_total_cap(self):
        pages=CommonPages();out=pages.add('','read',{})
        self.assertEqual(json.loads(pages.page(out,0,'call','read')['content'])['text'],'')
        for offset in [-1,1,True]:
            with self.assertRaises(ValueError):pages.page(out,offset,'call','read')
        pages.delivered_bytes=14330
        with self.assertRaises(BufferError):pages.page(out,0,'call','read')

    def test_orphan_and_source_byte_gate(self):
        with self.assertRaises(ContractError):check_messages([{'role':'tool','tool_call_id':'x','content':'a'}])
        messages=deepcopy(self.messages)
        for i in range(4):
            messages.extend([{'role':'assistant','content':None,'tool_calls':[{'id':str(i)}]},
                {'role':'tool','tool_call_id':str(i),'content':'x'*4000}])
        with self.assertRaisesRegex(ContractError,'source_or_control'):check_messages(messages)

    def test_chunk_fidelity_bom_crlf(self):
        rows=chunks(self.snap,1)
        self.assertEqual(''.join(r['text'] for r in rows),self.snap.files['a.py'])
        self.assertEqual([(r['metadata']['start_line'],r['metadata']['end_line']) for r in rows],[(1,1),(2,2)])

    def test_duplicate_launch_and_finish(self):
        with self.assertRaises(Exception):SharedWire(self.ledger,'baseline',self.snap)
        self.wire.exchange(self.messages,self.tools,True,self.transport());self.wire.finish()
        with self.assertRaises(RuntimeError):self.wire.finish()

if __name__=='__main__':unittest.main()
