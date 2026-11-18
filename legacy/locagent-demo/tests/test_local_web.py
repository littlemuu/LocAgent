"""Offline local-web acceptance. Only loopback HTTP and synthetic provider calls."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from locagent_service import local, local_web as web
from test_local_cli import CONFIG


class OfflineController(web.Controller):
    unknown = False
    def _command(self, folder, kind):
        return [sys.executable, '-B', str(Path(__file__).with_name('local_web_offline_job.py')),
                str(folder), kind, str(self.timeout)] + (['unknown'] if self.unknown else [])


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='locagent-web-test-')
        self.root = Path(self.tmp.name).resolve() / 'jobs'
        self.env = patch.dict(os.environ, {'LOCAL_TEST_KEY':'synthetic-not-a-real-key', 'LOCAGENT_ALLOW_PAID':'0'})
        self.env.start()
        self.controller = OfflineController(self.root, CONFIG, enable_paid=True, timeout=90)
        self.server = web.Server(self.controller, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = self.server.host
        self.token = self.server.token

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.controller.close()
        self.env.stop();self.tmp.cleanup()

    def request(self, method, path, value=None, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(value, ensure_ascii=False).encode() if value is not None else None
        h = {'Host':self.host, 'Origin':'http://' + self.host, 'X-LocAgent-Session':self.token}
        if body is not None: h['Content-Type']='application/json'
        h.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=15)
        connection.request(method,path,body=body,headers=h)
        response = connection.getresponse();data=response.read();status=response.status;returned=dict(response.getheaders());connection.close()
        return status, data, returned

    def post(self, path, value):
        status,data,_=self.request('POST',path,value)
        return status,json.loads(data)

    def create(self):
        identity=uuid4().hex
        status,data=self.post('/api/prepare',{'id':identity,'repository_url':'https://github.com/example/demo','question':'Find sign_payload.','ref':'v1'})
        self.assertEqual(status,202,data)
        return identity

    def wait(self, identity):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            status,data,_=self.request('GET','/api/jobs/'+identity)
            value=json.loads(data)
            self.assertEqual(status,200,value)
            if value['state'] not in web.ACTIVE:return value
            time.sleep(.15)
        self.fail('job deadline')

    def test_free_http_e2e_real_graph_synthetic_provider_and_duplicate_block(self):
        identity=self.create();prepared=self.wait(identity)
        self.assertEqual(prepared['state'],'prepared',prepared)
        self.assertEqual(prepared['paid_calls'],0)
        self.assertTrue(prepared['can_run'])
        consent={'plan_sha256':prepared['preview']['plan_sha256'],'consent':True}
        status,_=self.post('/api/jobs/'+identity+'/run',consent);self.assertEqual(status,202)
        status,_=self.post('/api/jobs/'+identity+'/run',consent);self.assertEqual(status,409)
        result=self.wait(identity)
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['result']['found_entities'],['pkg.py:sign_payload'])
        self.assertEqual(result['evidence']['items'][1]['start_line'],1)
        self.assertEqual(result['paid_calls'],3) # Three synthetic HTTP responses, not paid traffic.
        self.assertTrue(result['result']['return_records'])
        self.assertFalse(result['can_run'])
        self.assertEqual(result['accounting']['reserved'],'0')
        self.assertNotIn('synthetic-not-a-real-key',json.dumps(result))
        status,_=self.post('/api/jobs/'+identity+'/run',consent);self.assertEqual(status,409)

    def test_unknown_transport_keeps_reservation_and_blocks_replay(self):
        self.controller.unknown=True
        identity=self.create();prepared=self.wait(identity)
        consent={'plan_sha256':prepared['preview']['plan_sha256'],'consent':True}
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',consent)[0],202)
        result=self.wait(identity)
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(result['paid_calls'],1)
        self.assertEqual(result['accounting']['reserved'],'0.0012')
        self.assertEqual(result['accounting']['calls'][0]['status'],'outcome_unknown')
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',json.dumps(result))
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',consent)[0],409)

    def test_host_origin_fetch_site_session_and_content_type_guards(self):
        for headers in [{'Host':'evil.example'},{'Origin':'https://evil.example'}, {'Origin':'null'},
                        {'Sec-Fetch-Site':'cross-site'},{'X-LocAgent-Session':'wrong'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('POST','/api/demo',{'id':uuid4().hex},headers)[0],403)
        self.assertEqual(self.request('POST','/api/demo',{'id':uuid4().hex},{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('POST','/api/demo',raw=b'x'*65537)[0],413)
        self.assertEqual(self.request('GET','/api/session',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/session',headers={'Sec-Fetch-Site':'cross-site'})[0],403)

    def test_cross_site_navigation_only_serves_public_html_not_session(self):
        headers={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Dest':'document','Sec-Fetch-Mode':'navigate'}
        self.assertEqual(self.request('GET','/',headers=headers)[0],200)
        self.assertEqual(self.request('GET','/api/session',headers=headers)[0],403)
        self.assertEqual(self.request('GET','/api/jobs/'+uuid4().hex,headers=headers)[0],403)

    def test_static_assets_csp_no_cors_no_secrets_and_traversal(self):
        for path in ['/', '/app.js','/style.css','/?job='+uuid4().hex]:
            status,data,headers=self.request('GET',path);self.assertEqual(status,200)
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
            self.assertNotIn('Access-Control-Allow-Origin',headers)
            self.assertNotIn(b'synthetic-not-a-real-key',data)
        for path in ['/../local.py','/api/jobs/../../provider.json','/provider.json','/.env']:
            self.assertIn(self.request('GET',path)[0],(400,404))
        status,data,_=self.request('GET','/api/session')
        self.assertNotIn(b'synthetic-not-a-real-key',data)

    def test_default_paid_off_and_exact_consent_required(self):
        identity=self.create();prepared=self.wait(identity)
        sha=prepared['preview']['plan_sha256']
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',{'plan_sha256':sha,'consent':False})[0],400)
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',{'plan_sha256':'0'*64,'consent':True})[0],409)
        self.controller.enable_paid=False
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',{'plan_sha256':sha,'consent':True})[0],403)
        self.assertFalse((self.root/identity/'paid-request.json').exists())

    def test_modified_preview_cannot_lie_about_price_or_question(self):
        identity=self.create();prepared=self.wait(identity)
        path=self.root/identity/'run'/'preview.json'
        old=web.read(path)
        web.replace(path,old|{'budget':'999999','endpoint':'https://evil.example/api'})
        result=self.controller.get(identity)
        self.assertEqual(result['preview']['budget'],CONFIG['budget'])
        self.assertEqual(result['preview']['endpoint'],CONFIG['endpoint'])
        web.replace(path,old|{'problem_statement':'different question'})
        self.assertEqual(self.request('GET','/api/jobs/'+identity)[0],409)
        self.assertEqual(self.post('/api/jobs/'+identity+'/run',{'plan_sha256':prepared['preview']['plan_sha256'],'consent':True})[0],409)

    def test_reused_id_large_chinese_question_and_single_active(self):
        identity=uuid4().hex
        with patch.object(self.controller,'_start'):
            data={'id':identity,'repository_url':'https://github.com/example/demo','question':'中'*8000,'ref':None}
            self.assertEqual(self.post('/api/prepare',data)[0],202)
            self.assertEqual(self.post('/api/prepare',data)[0],409)
            self.controller.active=identity
            self.assertEqual(self.post('/api/demo',{'id':uuid4().hex})[0],409)
            self.controller.active=None

    def test_restart_interrupted_jobs_are_read_only_fenced(self):
        identity=uuid4().hex;folder=self.root/identity;folder.mkdir(mode=0o700)
        local.save_new(folder/'job.json',{'id':identity,'kind':'prepare','state':'running'})
        # Close only controller while HTTP is idle; recreate on same private root.
        self.controller.close()
        self.controller=OfflineController(self.root,CONFIG,enable_paid=True)
        self.server.controller=self.controller
        self.assertTrue(self.controller.interrupted_fence)
        self.assertEqual(self.controller.get(identity)['state'],'needs_review')
        self.assertEqual(self.post('/api/demo',{'id':uuid4().hex})[0],409)
        self.controller.close()
        self.controller=OfflineController(self.root,CONFIG,enable_paid=True)
        self.server.controller=self.controller
        self.assertTrue(self.controller.interrupted_fence)

    def test_second_server_cannot_share_storage(self):
        with self.assertRaisesRegex(web.WebError,'storage_already_in_use'):
            web.Controller(self.root,CONFIG)

    def test_demo_uses_production_subprocess_without_key(self):
        with patch.object(self.controller,'_command', lambda folder,kind:web.Controller._command(self.controller,folder,kind)):
            identity=uuid4().hex
            self.assertEqual(self.post('/api/demo',{'id':identity})[0],202)
            value=self.wait(identity)
        self.assertEqual(value['state'],'demo_completed',value)
        self.assertEqual(value['demo']['mode'],'synthetic-demo')
        self.assertEqual(value['demo']['paid_calls'],0)


if __name__=='__main__':unittest.main()
