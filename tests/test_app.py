import unittest
from unittest.mock import patch
import app

class WorkbenchTests(unittest.TestCase):
    def test_valid_inputs(self):
        self.assertEqual(app.target('example.com'), ('example.com', 'https://example.com/', 'site'))
        self.assertEqual(app.target('8.8.8.8')[2], 'ip')
        self.assertEqual(app.target('2606:4700:4700::1111')[2], 'ip')
    def test_unsafe_inputs(self):
        for value in ['127.0.0.1', 'http://169.254.169.254/', 'http://[::1]', 'file:///etc/passwd', 'https://user:pass@example.com', 'https://example.com:8080', 'localhost', '']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.target(value)
    @patch('app.socket.getaddrinfo', return_value=[(None,None,None,None,('10.0.0.1',443))])
    def test_private_dns_is_rejected(self, _):
        with self.assertRaises(ValueError):
            app.public_addresses('example.com')
    @patch('app.ip_info', return_value={'country':'US','source':'fixture'})
    @patch('app.public_addresses', return_value=['8.8.8.8'])
    def test_ip_report_runs_providers(self, dns, ip):
        report=app.investigate('8.8.8.8')
        self.assertEqual(report['results']['ip']['data']['country'], 'US')
        self.assertEqual(report['results']['network']['status'], 'ok')
        ip.assert_called_once_with('8.8.8.8')
    @patch('app.public_addresses', return_value=['93.184.216.34'])
    @patch('app.ip_info', side_effect=RuntimeError('provider unavailable'))
    @patch('app.dns_info', return_value={'records':{'A':[]}})
    @patch('app.site_info', return_value={'status':200,'title':'Example'})
    @patch('app.certificate', return_value={'protocol':'TLSv1.3'})
    def test_partial_failure_retains_other_results(self, *mocks):
        result=app.investigate('example.com')['results']
        self.assertEqual(result['ip']['status'],'error')
        self.assertEqual(result['website']['data']['title'],'Example')
        self.assertEqual(result['tls']['status'],'ok')
    def test_links_are_resolved_and_filtered(self):
        parser=app.Links('https://example.com/path')
        parser.feed('<title>Example</title><a href="/about">About</a><a href="javascript:alert(1)">x</a>')
        self.assertEqual(parser.links,{'https://example.com/about'})
        self.assertEqual(parser.title,'Example')

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
    def request(self, target, origin=None):
        import urllib.request,json
        headers={'Content-Type':'application/json'}
        if origin: headers['Origin']=origin
        return urllib.request.urlopen(urllib.request.Request(self.base+'/api/investigate',data=json.dumps({'target':target}).encode(),headers=headers))
    def test_private_target_returns_400(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('127.0.0.1')
        self.assertEqual(ctx.exception.code,400)
    def test_foreign_origin_is_rejected(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('example.com','https://other.example')
        self.assertEqual(ctx.exception.code,403)
    @patch('app.ip_info',return_value={'country':'US'})
    @patch('app.public_addresses',return_value=['8.8.8.8'])
    def test_report_over_http(self,*mocks):
        import json
        with self.request('8.8.8.8') as response:
            self.assertEqual(response.status,200)
            data=json.load(response)
        self.assertEqual(data['results']['ip']['data']['country'],'US')
        self.assertIn('created_at',data)

if __name__=='__main__':
    unittest.main()
