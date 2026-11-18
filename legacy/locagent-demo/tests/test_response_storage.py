from phased_test_support import install_synthetic_cohorts
"""Large original responses stay out of the small, readable execution ledger."""
from decimal import Decimal
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from locagent_service import phased as p, response_store as store, deepseek_http as h
from locagent_service.offline import offline_engine
from locagent_service.sources import digest

MiB=1024*1024


def padded_body(size,ordinal=0):
    raw=p.scripted_raw(ordinal)
    return raw+b' '*(size-len(raw))


class ResponseStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'ledger.json'
        self.addCleanup(patch.stopall)
        install_synthetic_cohorts(self)
        patch.object(p,'OWNERSHIP_ROOT',self.root/'owners').start()
        patch.object(p,'verify_sources').start();patch.object(p,'check_labels').start()
        self.guard=offline_engine();self.guard.__enter__();self.addCleanup(self.guard.__exit__,None,None,None)

    def claim(self,name='body-storage'):
        self.plan=p.expected_plan('new20',name)
        p.initialize(self.path,self.plan)
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path)
            state.update(status='running',active_run={'token':'run','arm_index':0,'phase':'initial-five'})
            state['arms'][0]['status']='running';p.commit(self.path,state)
        return p.Provider(self.path,0,'run')

    def send(self,provider,body,status=200,ordinal=0):
        def raw(number,**kw):
            return h.exchange(h.payload(**kw),'synthetic-only',
                transport=httpx.MockTransport(lambda request:httpx.Response(status,content=body,request=request)),
                max_response_bytes=store.capacity(self.path))
        provider.raw=raw
        return provider(messages=[{'role':'user','content':str(ordinal)}])

    def readable(self):
        self.assertLess(self.path.stat().st_size,128*1024)
        state,_,_=p.load_state(self.path)
        self.assertNotIn('raw_body_b64',self.path.read_text())
        return state

    def test_six_mib_http_error_preserved_and_auditable(self):
        provider=self.claim();body=b'E'*(6*MiB)
        with self.assertRaises(ValueError):self.send(provider,body,503)
        state=self.readable();call=state['calls'][0]
        self.assertEqual(p.response_body(self.path,call),body)
        self.assertEqual(call['raw_body_sha256'],digest(body))
        self.assertEqual(store.usage(self.path),len(body))
        self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(self.readable()['status'],'halted')

    def test_multiple_three_mib_valid_bodies_do_not_grow_ledger(self):
        provider=self.claim()
        sizes=[]
        for i in range(2):
            self.send(provider,padded_body(3*MiB,i),ordinal=i);sizes.append(self.path.stat().st_size)
        state=self.readable()
        self.assertTrue(all(c['status']=='settled' for c in state['calls']))
        self.assertLess(sizes[1]-sizes[0],4096)
        self.assertEqual(store.usage(self.path),6*MiB)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(self.readable()['status'],'halted')

    def test_single_body_limit_keeps_prefix_explicitly_incomplete_and_reserved(self):
        provider=self.claim();body=padded_body(9*MiB)
        with self.assertRaises(ValueError):self.send(provider,body)
        state=self.readable();call=state['calls'][0]
        prefix=p.response_body(self.path,call)
        self.assertEqual(len(prefix),8*MiB)
        self.assertIsInstance(json.loads(prefix),dict,'Even a valid JSON prefix must not settle')
        self.assertIs(call['response_complete'],False)
        self.assertEqual(call['transport_error_type'],'ResponseTooLarge')
        self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_aggregate_limit_stops_second_response_without_false_settlement(self):
        with patch.object(store,'MAX_TOTAL_BYTES',5*MiB):
            provider=self.claim()
            self.send(provider,padded_body(3*MiB))
            with self.assertRaises(ValueError):self.send(provider,padded_body(3*MiB,1),ordinal=1)
            state=self.readable()
            self.assertEqual(store.usage(self.path),5*MiB)
            self.assertEqual(state['calls'][0]['status'],'settled')
            self.assertEqual(state['calls'][1]['status'],'outcome_unknown')
            self.assertIs(state['calls'][1]['response_complete'],False)
            self.assertEqual(state['calls'][1]['raw_body_ref']['bytes'],2*MiB)
            self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
            self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_exactly_full_store_rejects_before_any_next_transport(self):
        with patch.object(store,'MAX_TOTAL_BYTES',3*MiB):
            provider=self.claim();self.send(provider,padded_body(3*MiB))
            provider.raw=lambda *a,**k:self.fail('No next transport after storage cap')
            with self.assertRaises(RuntimeError):provider(messages=[])
            state=self.readable();self.assertEqual(len(state['calls']),1)
            self.assertEqual(Decimal(state['reserved_cny']),0)
            self.assertEqual(state['stop_reason'],'response_storage_exhausted')
            self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_missing_or_changed_reference_is_blocked_but_audit_remains_readable(self):
        for fault in ['missing','hash']:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'l.json';provider=self.claim(fault)
                provider.hook=lambda point:(_ for _ in ()).throw(RuntimeError('raw saved')) if point=='raw_saved' else None
                with self.assertRaises(RuntimeError):self.send(provider,padded_body(MiB))
                state=p.read_json(self.path);ref=state['calls'][0]['raw_body_ref']
                target=store.directory(self.path)/ref['file']
                if fault=='missing':target.unlink()
                else:
                    body=target.read_bytes();target.write_bytes(b'X'+body[1:])
                with self.assertRaises(RuntimeError):p.load_state(self.path)
                audit=p.audit_recovery(self.path)
                self.assertFalse(audit['recoverable']);self.assertEqual(audit['body_evidence_errors'][0]['call_index'],0)
                state=p.load_state(self.path,allow_body_errors=True)[0]
                self.assertEqual(state['status'],'halted')
                self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                self.assertLess(self.path.stat().st_size,128*1024)

    def test_failed_publication_retains_temp_evidence_and_unknown_reserve(self):
        provider=self.claim();body=padded_body(MiB)
        with patch.object(store.os,'link',side_effect=OSError('synthetic disk publication error')):
            with self.assertRaises(OSError):self.send(provider,body)
        state=self.readable()
        self.assertEqual(state['calls'][0]['status'],'outcome_unknown')
        self.assertNotIn('raw_body_ref',state['calls'][0])
        self.assertEqual(store.usage(self.path),MiB)
        self.assertEqual(len(list(store.directory(self.path).glob('*.tmp'))),1)
        self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_actual_crash_after_body_publication_cannot_resend_or_adopt_unreferenced_body(self):
        provider=self.claim();ctx=mp.get_context('fork');counter=ctx.Value('i',0)
        def run():
            def raw(*a,**kw):
                with counter.get_lock():counter.value+=1
                return padded_body(MiB)
            provider.raw=raw
            provider.hook=lambda point:os._exit(91) if point=='body_saved' else None
            provider(messages=[])
        child=ctx.Process(target=run);child.start();child.join(20)
        if child.is_alive():child.kill();child.join();self.fail('Body crash probe timed out')
        self.assertEqual(child.exitcode,91);self.assertEqual(counter.value,1)
        state=self.readable()
        self.assertEqual(state['calls'][0]['status'],'reserved')
        self.assertNotIn('raw_body_ref',state['calls'][0])
        self.assertEqual(store.usage(self.path),MiB)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(Decimal(self.readable()['reserved_cny']),p.followup.RESERVE)
        with self.assertRaises(RuntimeError):provider(messages=[])
        self.assertEqual(counter.value,1)

    def test_reference_paths_links_and_overwrites_are_rejected(self):
        body=b'original';ref=store.persist(self.path,0,body)
        with self.assertRaises(FileExistsError):store.persist(self.path,0,b'changed')
        with self.assertRaises(ValueError):store.read(self.path,0,{**ref,'file':'../outside'})
        target=store.directory(self.path)/ref['file'];target.unlink()
        outside=self.root/'outside';outside.write_bytes(body);target.symlink_to(outside)
        with self.assertRaises(ValueError):store.read(self.path,0,ref)
        with self.assertRaises(ValueError):store.capacity(self.path)

    def test_oversized_metadata_write_leaves_previous_json_readable(self):
        store.save_json(self.path,{'version':'previous'})
        original=self.path.read_bytes()
        with self.assertRaises(ValueError):store.save_json(self.path,{'padding':'X'*(8*MiB)})
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(p.read_json(self.path),{'version':'previous'})

    def test_halted_ledger_with_missing_settled_body_still_returns_blocked_audit(self):
        provider=self.claim();self.send(provider,p.scripted_raw(0))
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        state=self.readable();before_spent=state['spent_cny']
        ref=state['calls'][0]['raw_body_ref']
        (store.directory(self.path)/ref['file']).unlink()
        audit=p.audit_recovery(self.path)
        self.assertFalse(audit['recoverable'])
        state=p.load_state(self.path,allow_body_errors=True)[0]
        self.assertEqual(state['status'],'halted')
        self.assertEqual(state['spent_cny'],before_spent)
        self.assertEqual(len(state['calls']),1)
