import unittest
from unittest.mock import patch
import app


class WorkbenchTests(unittest.TestCase):
    def test_valid_inputs(self):
        self.assertEqual(
            app.target("example.com"), ("example.com", "https://example.com/", "site")
        )
        self.assertEqual(app.target("8.8.8.8")[2], "ip")
        self.assertEqual(app.target("2606:4700:4700::1111")[2], "ip")

    def test_unsafe_inputs(self):
        for value in [
            "127.0.0.1",
            "http://169.254.169.254/",
            "http://[::1]",
            "file:///etc/passwd",
            "https://user:pass@example.com",
            "https://example.com:8080",
            "localhost",
            "",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.target(value)

    @patch(
        "app.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("10.0.0.1", 443))],
    )
    def test_private_dns_is_rejected(self, _):
        with self.assertRaises(ValueError):
            app.public_addresses("example.com")

    @patch("app.ip_info", return_value={"country": "US", "source": "fixture"})
    @patch("app.public_addresses", return_value=["8.8.8.8"])
    def test_ip_report_runs_providers(self, dns, ip):
        report = app.investigate("8.8.8.8")
        self.assertEqual(report["results"]["ip"]["data"]["country"], "US")
        self.assertEqual(report["results"]["network"]["status"], "ok")
        ip.assert_called_once_with("8.8.8.8")

    @patch("app.public_addresses", return_value=["93.184.216.34"])
    @patch("app.ip_info", side_effect=RuntimeError("provider unavailable"))
    @patch("app.dns_info", return_value={"records": {"A": []}})
    @patch("app.site_info", return_value={"status": 200, "title": "Example"})
    @patch("app.certificate", return_value={"protocol": "TLSv1.3"})
    def test_partial_failure_retains_other_results(self, *mocks):
        result = app.investigate("example.com")["results"]
        self.assertEqual(result["ip"]["status"], "error")
        self.assertEqual(result["website"]["data"]["title"], "Example")
        self.assertEqual(result["tls"]["status"], "ok")

    def test_links_are_resolved_and_filtered(self):
        parser = app.Links("https://example.com/path")
        parser.feed(
            '<title>Example</title><a href="/about">About</a><a href="javascript:alert(1)">x</a>'
        )
        self.assertEqual(parser.links, {"https://example.com/about"})
        self.assertEqual(parser.title, "Example")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading

        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, target, origin=None):
        import urllib.request, json

        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        return urllib.request.urlopen(
            urllib.request.Request(
                self.base + "/api/investigate",
                data=json.dumps({"target": target}).encode(),
                headers=headers,
            )
        )

    def test_private_target_returns_400(self):
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("127.0.0.1")
        self.assertEqual(ctx.exception.code, 400)

    def test_foreign_origin_is_rejected(self):
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("example.com", "https://other.example")
        self.assertEqual(ctx.exception.code, 403)

    @patch("app.ip_info", return_value={"country": "US"})
    @patch("app.public_addresses", return_value=["8.8.8.8"])
    def test_report_over_http(self, *mocks):
        import json

        with self.request("8.8.8.8") as response:
            self.assertEqual(response.status, 200)
            data = json.load(response)
        self.assertEqual(data["results"]["ip"]["data"]["country"], "US")
        self.assertIn("created_at", data)


class DeepResearchTests(unittest.TestCase):
    def setUp(self):
        app.CACHE.clear()

    def tearDown(self):
        app.CACHE.clear()

    @patch("app.fetch")
    def test_dns_queries_dmarc_and_separates_record_types(self, fetch):
        import json, urllib.parse

        def response(url, maximum=2097152):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if query["name"] == ["_dmarc.example.com"]:
                self.assertEqual(query["type"], ["TXT"])
                answers = [{"type": 16, "data": '"v=DMARC1; p=reject"', "TTL": 300}]
            else:
                answers = [
                    {"type": 5, "data": "alias.example.com.", "TTL": 300},
                    {"type": 1, "data": "8.8.8.8", "TTL": 300},
                ]
            return 200, {}, json.dumps({"Status": 0, "Answer": answers}).encode(), False

        fetch.side_effect = response
        records = app.dns_info("example.com")["records"]
        self.assertEqual(records["A"], [{"value": "8.8.8.8", "ttl": 300}])
        self.assertEqual(
            records["CNAME"], [{"value": "alias.example.com.", "ttl": 300}]
        )
        self.assertIn("v=DMARC1", records["DMARC"][0]["value"])
        self.assertEqual(fetch.call_count, 9)

    def test_header_assessment_is_case_insensitive(self):
        result = app.header_analysis(
            {
                "content-security-policy": "frame-ancestors 'none'",
                "X-Content-Type-Options": "nosniff",
            },
            "https://example.com",
        )
        self.assertTrue(result["checks"]["Proteção contra framing"])
        self.assertTrue(result["checks"]["X-Content-Type-Options"])
        self.assertFalse(result["checks"]["Strict-Transport-Security"])

    def test_technology_detection_has_evidence(self):
        parser = app.Links("https://example.com")
        parser.feed(
            '<meta name><meta name="description" content><meta name="generator" content="Example CMS"><script src="/_next/static/app.js"></script>'
        )
        result = app.technologies({"Server": "nginx"}, parser)
        self.assertEqual(
            {r["technology"] for r in result}, {"nginx", "Example CMS", "Next.js"}
        )
        self.assertTrue(all(r["evidence"] for r in result))

    @patch(
        "app.json_source",
        return_value=[
            {
                "name_value": "*.example.com\napi.example.com\nnotexample.com\napi.example.com"
            }
        ],
    )
    def test_certificate_names_are_scoped_and_deduplicated(self, _):
        result = app.transparency("example.com")
        self.assertEqual(result["domains"], ["api.example.com", "example.com"])
        self.assertEqual(result["total_discovered"], 2)

    @patch(
        "app.json_source",
        side_effect=[
            {
                "services": [
                    [["com"], ["http://unsafe.example/", "https://registry.example/"]]
                ]
            },
            {
                "ldhName": "example.com",
                "events": [{"eventAction": "registration", "eventDate": "2000-01-01"}],
                "entities": [
                    {
                        "roles": ["registrant"],
                        "vcardArray": [
                            "vcard",
                            [
                                ["fn", {}, "text", "Private Person"],
                                ["org", {}, "text", "Example Ltd"],
                            ],
                        ],
                    }
                ],
            },
        ],
    )
    def test_rdap_uses_bootstrap_and_omits_personal_name(self, mock):
        result = app.registration("example.com", "site")
        self.assertEqual(
            mock.call_args.args[0], "https://registry.example/domain/example.com"
        )
        self.assertEqual(result["entities"][0]["organizations"], ["Example Ltd"])
        self.assertNotIn("Private Person", str(result))

    @patch("app.fetch", return_value=(200, {}, b"[]", True))
    def test_truncated_provider_response_is_not_complete(self, _):
        with self.assertRaisesRegex(RuntimeError, "limite"):
            app.json_source("https://crt.sh/")

    @patch(
        "app.site_info",
        return_value={
            "status": 200,
            "url": "https://example.com/robots.txt",
            "text": "User-agent: *",
            "truncated": False,
        },
    )
    def test_public_documents_have_same_origin_guard(self, mock):
        result = app.discovery("https://example.com/path")
        self.assertEqual(len(result["documents"]), 3)
        self.assertEqual(mock.call_count, 3)
        for call in mock.call_args_list:
            self.assertEqual(call.args[2], "example.com")

    @patch("app.public_addresses")
    def test_discovery_redirect_cannot_escape_site(self, dns):
        with self.assertRaisesRegex(ValueError, "fora do site"):
            app.site_info("https://other.example/", True, "example.com")
        dns.assert_not_called()

    def test_unavailable_sources_do_not_create_findings(self):
        self.assertEqual(
            app.summarize(
                {
                    "dns": {"status": "error", "error": "offline"},
                    "website": {"status": "error"},
                }
            ),
            [],
        )

    @patch("app.discovery", return_value={"documents": {}})
    @patch("app.archives", return_value={"snapshots": []})
    @patch("app.transparency", return_value={"domains": []})
    @patch("app.reverse_dns", return_value={"records": []})
    @patch("app.registration", return_value={"name": "example.com"})
    @patch("app.certificate", return_value={})
    @patch("app.site_info", return_value={"status": 200})
    @patch(
        "app.dns_info",
        return_value={
            "records": {
                "TXT": [{"value": '"v=spf1 -all"'}],
                "DMARC": [{"value": '"v=DMARC1; p=reject"'}],
            }
        },
    )
    @patch("app.ip_info", return_value={"ip": "8.8.8.8"})
    @patch("app.public_addresses", return_value=["8.8.8.8"])
    def test_deep_mode_runs_ten_modules(self, *mocks):
        result = app.investigate("example.com", True)
        self.assertEqual(result["mode"], "deep")
        self.assertEqual(result["summary"]["total"], 10)
        self.assertEqual(result["summary"]["completed"], 10)
        self.assertEqual(result["summary"]["findings"], [])
        self.assertTrue(all("checked_at" in r for r in result["results"].values()))


if __name__ == "__main__":
    unittest.main()
