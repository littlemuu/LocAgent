import json,socket,ssl,unittest
from unittest.mock import patch
from locagent_service import public_repo as repo

class DownloadDiagnosticsTests(unittest.TestCase):
    def test_timeout_chain_has_no_exception_text(self):
        with patch.object(repo,'PinnedHTTPS') as cls:
            conn=cls.return_value
            def fail():
                try:raise OSError(5,'Authorization: secret-token')
                except OSError as exc:raise TimeoutError('secret URL') from exc
            conn.getresponse.side_effect=fail
            with self.assertRaises(repo.PipelineError) as caught:repo.fetch('api.github.com','/repos/a/b')
            d=caught.exception.diagnostic
            self.assertEqual(d['transport_stage'],'response_headers')
            self.assertEqual(d['exception_chain'],[{'category':'timeout'},{'category':'os','errno':5}])
            self.assertNotIn('secret',json.dumps(d));conn.close.assert_called_once()
    def test_rate_limit_status_and_numeric_headers_only(self):
        for status in (403,429):
            with self.subTest(status=status),patch.object(repo,'PinnedHTTPS') as cls:
                response=cls.return_value.getresponse.return_value;response.status=status
                response.getheader.side_effect=lambda h,*args: {'Retry-After':'30','X-RateLimit-Remaining':'0','X-RateLimit-Reset':'1792038000'}.get(h,'secret')
                with self.assertRaises(repo.PipelineError) as caught:repo.fetch('api.github.com','/repos/a/b')
                self.assertEqual(caught.exception.code,'github_http_'+str(status))
                self.assertEqual(caught.exception.diagnostic,{'host':'api.github.com','transport_stage':'response_headers','http_status':status,'retry_after_seconds':30,'rate_remaining':0,'rate_reset_epoch':1792038000})
                cls.return_value.request.assert_called_once()
    def test_non_numeric_header_not_saved(self):
        with patch.object(repo,'PinnedHTTPS') as cls:
            response=cls.return_value.getresponse.return_value;response.status=302
            response.getheader.return_value='secret-header'
            with self.assertRaises(repo.PipelineError) as caught:repo.fetch('api.github.com','/repos/a/b')
            self.assertNotIn('secret',json.dumps(caught.exception.diagnostic))
    def test_tls_failure_stage_and_closed_socket(self):
        with patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1',443))]),patch.object(socket,'socket') as sock,patch.object(ssl,'create_default_context') as ctx:
            ctx.return_value.wrap_socket.side_effect=ssl.SSLError('secret TLS detail')
            with self.assertRaises(repo.PipelineError) as caught:repo.fetch('api.github.com','/repos/a/b')
            self.assertEqual(caught.exception.diagnostic['transport_stage'],'tls')
            self.assertEqual(caught.exception.diagnostic['exception_chain'][0]['category'],'tls')
            self.assertNotIn('secret',json.dumps(caught.exception.diagnostic))
            sock.return_value.close.assert_called_once()
