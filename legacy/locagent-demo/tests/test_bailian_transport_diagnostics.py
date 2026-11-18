import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
from unittest.mock import Mock,patch
from contextlib import ExitStack
from locagent_service.bailian_live import exchange,Journal,batches,ORIGIN,WORKSPACE
from locagent_service.public_repo import PinnedHTTPS
from locagent_service.bailian_transport_diagnostics import TransportFailure,OverallTimeout

SECRET='synthetic-sensitive-https://private.invalid/token'
CONFIG={'DASHSCOPE_API_KEY':'synthetic-key','DASHSCOPE_API_HOST':ORIGIN,'DASHSCOPE_WORKSPACE_ID':WORKSPACE}
BODY=json.dumps({'usage':{'prompt_tokens':1,'total_tokens':1},'output':{'embeddings':[{'index':0,'embedding':[1.]+[0.]*1023}]}}).encode()


class TransportDiagnosticsTests(unittest.TestCase):
 def chain(self,stage,error,cleanup_error=None,socket_cleanup=False):
  sock=Mock();ctx=Mock();conn=Mock();conn.host='public.invalid';conn.timeout=15;conn._context=ctx
  conn.download_stage=None;conn.download_cleanup_failed=False
  reply=conn.getresponse.return_value;reply.status=200;reply.getheader.return_value='0';reply.read.return_value=BODY
  def send(*a,**k):
   PinnedHTTPS.connect(conn)
   if stage=='request_send':raise error
  conn.request.side_effect=send
  if stage=='tcp_connect':sock.connect.side_effect=error
  if stage=='tls':ctx.wrap_socket.side_effect=error
  if stage=='response_headers':conn.getresponse.side_effect=error
  if stage=='response_body':reply.read.side_effect=error
  if stage=='body_check':reply.read.return_value=b'x'*(4*1024*1024+1)
  if cleanup_error:conn.close.side_effect=cleanup_error
  if socket_cleanup:sock.close.side_effect=RuntimeError(SECRET)
  with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
   stack.enter_context(patch('locagent_service.public_repo.socket.socket',return_value=sock))
   dns=stack.enter_context(patch('locagent_service.public_repo.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]))
   if stage=='dns':dns.side_effect=error
   stack.enter_context(patch('locagent_service.bailian_transport_diagnostics.ssl.create_default_context',return_value=ctx))
   manifest={'documents':[{'id':'a','text':'public'}],'questions':[]}
   j=Journal(Path(tmp)/'j',manifest,batches(manifest),create=True)
   with self.assertRaises(ValueError):j.step(0,lambda body:exchange(body,CONFIG,connection_factory=lambda *a,**k:conn))
   record=json.loads((j.folder/'transport-000.json').read_bytes())
   report=j.report();raw=(j.folder/'response-000.body.bin')
   raw_saved=raw.exists()
   if raw_saved:self.assertEqual(raw.read_bytes(),BODY)
   self.assertNotIn(SECRET,json.dumps(record)+json.dumps(report))
   self.assertNotIn('synthetic-key',json.dumps(record)+json.dumps(report))
   self.assertEqual(report['calls'][0]['state'],'unknown')
   with self.assertRaises(ValueError):j.step(0,lambda _:self.fail('No retry'))
   conn.request.assert_called_once();conn.close.assert_called_once()
   return record,report,raw_saved

 def test_real_connect_chain_stages(self):
  for stage,exc,kind in [('dns',socket.gaierror(SECRET),'dns_error'),('tcp_connect',ConnectionRefusedError(SECRET),'connection_error'),
                         ('tls',ssl.SSLError(SECRET),'tls_error'),('request_send',BrokenPipeError(SECRET),'connection_error'),
                         ('response_headers',RuntimeError(SECRET),'unknown'),('response_body',RuntimeError(SECRET),'unknown')]:
   with self.subTest(stage=stage):
    d,_,_=self.chain(stage,exc);self.assertEqual((d['stage'],d['category']),(stage,kind))

 def test_operation_timeouts_do_not_claim_server_fault(self):
  for stage in ('dns','tcp_connect','tls','request_send','response_headers','response_body'):
   with self.subTest(stage=stage):
    d,_,_=self.chain(stage,TimeoutError(SECRET));self.assertEqual(d['category'],'operation_timeout');self.assertEqual(d['stage'],stage)

 def test_overall_timeout_distinct_from_operation_timeout(self):
  d,_,_=self.chain('response_body',OverallTimeout(SECRET));self.assertEqual(d['category'],'overall_timeout')

 def test_headers_status_preserved_when_body_fails(self):
  d,r,saved=self.chain('response_body',TimeoutError(SECRET))
  self.assertTrue(d['response_headers_received']);self.assertEqual(d['http_status'],200)
  self.assertEqual(r['calls'][0]['http_status'],200);self.assertFalse(saved)
  d,_,_=self.chain('response_headers',TimeoutError(SECRET));self.assertFalse(d['response_headers_received']);self.assertIsNone(d['http_status'])

 def test_primary_failure_survives_connection_cleanup_failure(self):
  d,_,_=self.chain('response_body',TimeoutError(SECRET),RuntimeError(SECRET))
  self.assertEqual(d['stage'],'response_body');self.assertEqual(d['category'],'operation_timeout');self.assertEqual(d['cleanup_categories'],['unknown'])

 def test_primary_connect_failure_survives_socket_cleanup_failure(self):
  d,_,_=self.chain('tls',ssl.SSLError(SECRET),socket_cleanup=True)
  self.assertEqual(d['category'],'tls_error');self.assertTrue(d['cleanup_failed'])

 def test_cleanup_only_failure_still_saves_complete_raw_body(self):
  d,r,saved=self.chain(None,None,RuntimeError(SECRET))
  self.assertEqual(d['stage'],'cleanup');self.assertTrue(d['complete_body_available']);self.assertTrue(saved)
  self.assertIsNotNone(r['calls'][0]['response_sha256'])

 def test_local_body_limit_failure_is_not_a_network_diagnosis(self):
  d,_,saved=self.chain('body_check',None)
  self.assertEqual((d['stage'],d['category']),('body_check','unknown'));self.assertFalse(saved)

 def test_actual_overall_alarm_handler_and_unchanged_limits(self):
  import signal
  conn=Mock();factory=Mock(return_value=conn);handlers=[]
  def set_handler(sig,handler):handlers.append(handler)
  def send(*a,**k):handlers[0](signal.SIGALRM,None)
  conn.request.side_effect=send
  with patch('signal.signal',side_effect=set_handler),patch('signal.setitimer') as timer:
   with self.assertRaises(TransportFailure) as caught:
    exchange(b'{}',CONFIG,connection_factory=factory)
  self.assertEqual(caught.exception.diagnostic['category'],'overall_timeout')
  self.assertEqual(factory.call_args.kwargs['timeout'],15)
  self.assertEqual([x.args[1] for x in timer.call_args_list],[60,0])
  self.assertEqual(len(handlers),2)

 def test_timer_cleanup_failure_does_not_replace_primary(self):
  conn=Mock();conn.request.side_effect=TimeoutError(SECRET)
  with patch('signal.signal'),patch('signal.setitimer',side_effect=[None,RuntimeError(SECRET)]):
   with self.assertRaises(TransportFailure) as caught:exchange(b'{}',CONFIG,connection_factory=lambda *a,**k:conn)
  d=caught.exception.diagnostic
  self.assertEqual(d['category'],'operation_timeout');self.assertEqual(d['cleanup_categories'],['unknown'])
  self.assertNotIn(SECRET,json.dumps(d)+str(caught.exception))

 def test_unknown_connection_stage_is_not_copied(self):
  conn=Mock();conn.download_stage=SECRET;conn.request.side_effect=RuntimeError(SECRET)
  with self.assertRaises(TransportFailure) as caught:exchange(b'{}',CONFIG,connection_factory=lambda *a,**k:conn)
  self.assertEqual(caught.exception.diagnostic['stage'],'request_send')
  self.assertNotIn(SECRET,json.dumps(caught.exception.diagnostic))


if __name__=='__main__':unittest.main()
