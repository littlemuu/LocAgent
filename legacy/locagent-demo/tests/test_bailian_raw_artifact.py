import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

from locagent_service.bailian_raw_artifact import atomic_once,persist_response,CaptureUnavailable
from locagent_service.bailian_live import Journal,batches,exchange,ORIGIN,WORKSPACE


class RawArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)

    def save(self,body):
        return persist_response(self.root,0,body,manifest_sha256='a'*64,request_sha256='b'*64,http_status=200)

    def test_extra_index_and_unknown_fields_byte_exact(self):
        body=b'{ "request_id":"1ba94ac8-e058-99bc-9cc1-7fdb37940a46", "output":{"embeddings":[{"index":0,"embedding":[1.0],"extra_field":42}]}, "unknown": [2,3] }\n'
        binding=self.save(body)
        self.assertEqual((self.root/'response-000.body.bin').read_bytes(),body)
        self.assertEqual(hashlib.sha256((self.root/binding['body_file']).read_bytes()).hexdigest(),binding['response_sha256'])
        self.assertEqual(binding['manifest_sha256'],'a'*64)
        self.assertEqual(binding['request_sha256'],'b'*64)
        self.assertEqual(binding['request_id'],'1ba94ac8-e058-99bc-9cc1-7fdb37940a46')
        for path in self.root.iterdir():self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_non_json_still_retained(self):
        body=b'not JSON\x00\xff'
        binding=self.save(body)
        self.assertEqual(binding['json_parse'],'invalid')
        self.assertEqual((self.root/'response-000.body.bin').read_bytes(),body)

    def test_duplicate_never_overwritten(self):
        self.save(b'first')
        with self.assertRaises(FileExistsError):self.save(b'second')
        self.assertEqual((self.root/'response-000.body.bin').read_bytes(),b'first')

    def test_interruption_before_publish_has_no_partial_final(self):
        with patch('locagent_service.bailian_raw_artifact.os.fsync',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.save(b'body')
        self.assertFalse((self.root/'response-000.body.bin').exists())
        self.assertEqual(list(self.root.iterdir()),[])

    def test_parse_happens_after_raw_publish(self):
        def interrupted(*args,**kwargs):
            self.assertEqual((self.root/'response-000.body.bin').read_bytes(),b'{}')
            raise KeyboardInterrupt()
        with patch('locagent_service.bailian_raw_artifact.json.loads',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):self.save(b'{}')
        self.assertFalse((self.root/'response-000.binding.json').exists())

    def journal(self):
        manifest={'documents':[{'id':'d','text':'public'}],'questions':[]}
        return Journal(self.root/'journal',manifest,batches(manifest),create=True)

    def test_invalid_response_retained_and_ledger_hash_bound(self):
        j=self.journal()
        body=json.dumps({'usage':{'prompt_tokens':2,'total_tokens':2},'output':{'embeddings':[{'index':0,'text_index':1,'embedding':[1.]+[0.]*1023}]}}).encode()
        with self.assertRaises(ValueError):j.step(0,lambda _: (200,body))
        self.assertEqual((j.folder/'response-000.body.bin').read_bytes(),body)
        self.assertEqual(j.report()['calls'][0]['response_sha256'],hashlib.sha256(body).hexdigest())
        self.assertEqual(j.report()['calls'][0]['state'],'unknown')
        self.assertIn('index',json.loads((j.folder/'response-000.body.bin').read_bytes())['output']['embeddings'][0])

    def test_save_failure_closed_with_explicit_diagnostic(self):
        j=self.journal()
        with patch('locagent_service.bailian_raw_artifact.atomic_once',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(ValueError):j.step(0,lambda _: (200,b'{}'))
        self.assertEqual(j.report()['calls'][0]['diagnostic'],'raw_capture_unavailable:persistence_failure')
        with self.assertRaises(ValueError):j.step(0,lambda _:self.fail('No retry'))

    def test_transport_interrupt_explicitly_no_body(self):
        j=self.journal()
        def interrupted(body):raise KeyboardInterrupt()
        with self.assertRaises(ValueError):j.step(0,interrupted)
        self.assertEqual(j.report()['calls'][0]['diagnostic'],'raw_capture_unavailable:transport_failure')

    def test_unsafe_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(CaptureUnavailable):self.save(b'{}')

    def test_echoed_credential_never_reaches_artifact_layer(self):
        conn=Mock();reply=conn.getresponse.return_value
        reply.status=200;reply.getheader.return_value='0';reply.read.return_value=b'{"echo":"synthetic-only-credential"}'
        with self.assertRaises(CaptureUnavailable) as caught:
            exchange(b'{}',{'DASHSCOPE_API_KEY':'synthetic-only-credential','DASHSCOPE_WORKSPACE_ID':WORKSPACE,'DASHSCOPE_API_HOST':ORIGIN},connection_factory=lambda *a,**k:conn)
        self.assertEqual(caught.exception.code,'credential_echo')
        self.assertNotIn('synthetic-only-credential',str(caught.exception))


if __name__=='__main__':unittest.main()
