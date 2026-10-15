import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from intelligence import compare, graph
from workspace import Store, InstanceLock


def report(ip="8.8.8.8"):
    return {
        "version": 3,
        "target": "example.com",
        "type": "site",
        "mode": "deep",
        "created_at": "2026-10-15T15:00:00+00:00",
        "results": {
            "network": {"status": "ok", "data": {"addresses": [ip], "source": "DNS"}},
            "dns": {
                "status": "ok",
                "data": {"records": {"A": [{"value": ip, "ttl": 300}]}},
            },
        },
        "summary": {"completed": 2, "total": 2, "findings": []},
    }


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "atlas.sqlite3"
        self.store = Store(self.path)
        self.project = self.store.create("Investigação")

    def tearDown(self):
        self.temp.cleanup()

    def test_reports_notes_evidence_survive_reopen(self):
        saved = self.store.save_report(self.project["id"], report())
        self.store.annotate(saved["saved_id"], "Hipótese a confirmar", ["network"])
        self.store.edit(self.project["id"], "Contexto do projeto")
        reopened = Store(self.path)
        self.assertEqual(
            reopened.project(self.project["id"])["notes"], "Contexto do projeto"
        )
        restored = reopened.report(saved["saved_id"])
        self.assertEqual(restored["analyst_notes"], "Hipótese a confirmar")
        self.assertEqual(restored["bookmarks"], ["network"])

    def test_instance_lock_prevents_duplicate_schedulers(self):
        with InstanceLock(Path(self.temp.name)):
            with self.assertRaises(RuntimeError):
                with InstanceLock(Path(self.temp.name)):
                    pass
        with InstanceLock(Path(self.temp.name)):
            pass

    def test_project_deletion_cascades(self):
        saved = self.store.save_report(self.project["id"], report())
        mid = self.store.monitor(self.project["id"], "example.com", True, 24)
        self.store.delete(self.project["id"])
        with self.assertRaises(KeyError):
            self.store.report(saved["saved_id"])
        with self.assertRaises(KeyError):
            self.store.get_monitor(mid)

    def test_scheduler_runs_due_monitor(self):
        mid = self.store.monitor(self.project["id"], "example.com", True, 1)
        with self.store.connect() as db:
            db.execute("UPDATE monitors SET next_run=0 WHERE id=?", (mid,))

        class Stop:
            calls = 0

            def wait(self, seconds):
                self.calls += 1
                return self.calls > 1

            def is_set(self):
                return False

        with patch.object(app, "STORE", self.store), patch.object(
            app, "run_monitor"
        ) as run:
            app.monitor_loop(Stop())
            run.assert_called_once_with(mid)

    def test_monitors_reschedule_and_pause(self):
        mid = self.store.monitor(self.project["id"], "example.com", True, 1)
        with self.store.connect() as db:
            db.execute("UPDATE monitors SET next_run=0 WHERE id=?", (mid,))
        self.assertEqual(len(self.store.due()), 1)
        self.store.finish_monitor(mid, None, "Provider unavailable")
        self.assertEqual(self.store.due(), [])
        self.assertGreater(self.store.get_monitor(mid)["next_run"], time.time())
        self.store.set_monitor(mid, False)
        self.assertEqual(self.store.get_monitor(mid)["enabled"], 0)

    def test_bad_bookmarks_and_intervals_rejected(self):
        saved = self.store.save_report(self.project["id"], report())
        with self.assertRaises(ValueError):
            self.store.annotate(saved["saved_id"], "", ["not-a-module"])
        with self.assertRaises(ValueError):
            self.store.monitor(self.project["id"], "example.com", True, 0)

    def test_monitor_saves_comparison(self):
        self.store.save_report(self.project["id"], report())
        mid = self.store.monitor(self.project["id"], "example.com", True, 1)
        with patch.object(app, "STORE", self.store), patch.object(
            app, "investigate", return_value=report("1.1.1.1")
        ) as investigate:
            result = app.run_monitor(mid)
        self.assertEqual(len(result["comparison"]["changes"]), 2)
        self.assertIn("saved_id", result)
        self.assertEqual(
            self.store.get_monitor(mid)["last_report_id"], result["saved_id"]
        )
        self.assertTrue(investigate.call_args.kwargs["refresh"])


class AnalysisTests(unittest.TestCase):
    def test_comparison_ignores_ttl_order_and_failure_removal(self):
        old, new = report(), report()
        old["results"]["network"]["data"]["addresses"] = ["8.8.8.8", "1.1.1.1"]
        new["results"]["network"]["data"]["addresses"] = ["1.1.1.1", "8.8.8.8"]
        new["results"]["dns"]["data"]["records"]["A"][0]["ttl"] = 100
        self.assertEqual(compare(old, new)["changes"], [])
        new["results"]["network"] = {"status": "error", "error": "offline"}
        comparison = compare(old, new)
        self.assertEqual(comparison["changes"], [])
        self.assertEqual(comparison["coverage"][0]["after"], "error")

    def test_comparison_rejects_different_targets(self):
        other = report()
        other["target"] = "other.com"
        with self.assertRaises(ValueError):
            compare(report(), other)

    def test_graph_relationships_have_sources(self):
        r = report()
        r["results"]["subdomains"] = {
            "status": "ok",
            "data": {"hosts": [{"host": "www.example.com", "addresses": ["8.8.8.8"]}]},
        }
        model = graph(r)
        self.assertTrue(any(e["label"] == "resolve para" for e in model["edges"]))
        self.assertTrue(all(e["source"] for e in model["edges"]))
        self.assertEqual(len([n for n in model["nodes"] if n["id"] == "ip:8.8.8.8"]), 1)

    def test_company_name_match_is_hypothesis(self):
        r = report()
        r["results"] = {
            "company": {
                "status": "ok",
                "data": {
                    "candidates": [
                        {
                            "id": "Q1",
                            "name": "Example",
                            "websites": ["https://example.com"],
                        }
                    ]
                },
            }
        }
        self.assertEqual(graph(r)["edges"][0]["confidence"], "hypothesis")


class ResearchTests(unittest.TestCase):
    def setUp(self):
        app.CACHE.clear()

    def tearDown(self):
        app.CACHE.clear()

    @patch("app.fetch", return_value=(200, {}, b'{"value":1}', False))
    def test_success_cache_and_refresh(self, fetch):
        url = "https://provider.example/data"
        app.CONTEXT.refresh = False
        app.json_source(url)
        app.json_source(url)
        self.assertEqual(fetch.call_count, 1)
        app.CONTEXT.refresh = True
        try:
            app.json_source(url)
        finally:
            app.CONTEXT.refresh = False
        self.assertEqual(fetch.call_count, 2)

    @patch("app.fetch", return_value=(429, {}, b"{}", False))
    def test_provider_error_is_not_cached(self, fetch):
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                app.json_source("https://provider.example/429")
        self.assertEqual(fetch.call_count, 2)

    @patch("app.site_info", return_value={"status": 200, "title": "Public page"})
    @patch("app.public_addresses", return_value=["8.8.8.8"])
    @patch(
        "app.fetch",
        return_value=(200, {}, b"api.example.com,8.8.8.8\nevil.test,1.1.1.1\n", False),
    )
    def test_subdomains_merge_scope_and_verify(self, fetch, dns, website):
        results = {
            "transparency": {
                "status": "ok",
                "data": {"domains": ["api.example.com", "www.example.com"]},
            },
            "tls": {
                "status": "ok",
                "data": {"names": ["*.example.com", "www.example.com"]},
            },
        }
        result = app.subdomains("example.com", results)
        self.assertEqual(result["total_candidates"], 2)
        api = next(h for h in result["hosts"] if h["host"] == "api.example.com")
        self.assertEqual(api["sources"], ["HackerTarget", "crt.sh"])
        self.assertEqual(api["dns_state"], "resolved")
        self.assertEqual(api["http_state"], "responded")
        self.assertEqual(website.call_count, 2)

    @patch("app.site_info", side_effect=OSError("TLS unavailable"))
    @patch("app.public_addresses", return_value=["8.8.8.8"])
    @patch("app.fetch", return_value=(200, {}, b"api.example.com,8.8.8.8", False))
    def test_dns_resolution_is_not_http_success(self, *mocks):
        result = app.subdomains("example.com", {})
        self.assertEqual(result["hosts"][0]["dns_state"], "resolved")
        self.assertEqual(result["hosts"][0]["http_state"], "unverified")

    @patch("app.json_source")
    def test_company_results_filter_people_and_keep_lei_records(self, source):
        def response(url, *args, **kwargs):
            if "gleif.org" in url:
                return {
                    "data": [
                        {
                            "id": "LEI123",
                            "attributes": {
                                "entity": {
                                    "legalName": {"name": "Example SA"},
                                    "jurisdiction": "PT",
                                    "status": "ACTIVE",
                                },
                                "registration": {"status": "ISSUED"},
                            },
                        }
                    ]
                }
            if "wbsearchentities" in url:
                return {
                    "search": [
                        {"id": "Q1", "label": "Example SA"},
                        {"id": "Q2", "label": "A Person"},
                    ]
                }
            return {
                "entities": {
                    "Q1": {
                        "claims": {
                            "P31": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": {"id": "Q4830453"}}
                                    }
                                }
                            ],
                            "P856": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": "https://example.com"}
                                    }
                                }
                            ],
                        }
                    },
                    "Q2": {
                        "claims": {
                            "P31": [
                                {"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}
                            ],
                            "P856": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": "https://person.example"}
                                    }
                                }
                            ],
                        }
                    },
                }
            }

        source.side_effect = response
        result = app.company_search("Example")
        self.assertEqual(
            result["results"]["company"]["data"]["candidates"][0]["id"], "Q1"
        )
        self.assertEqual(len(result["results"]["company"]["data"]["candidates"]), 1)
        self.assertEqual(
            result["results"]["business_registry"]["data"]["records"][0]["name"],
            "Example SA",
        )


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(
            app, "STORE", Store(Path(self.temp.name) / "test.sqlite3")
        )
        self.patch.start()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        import urllib.request

        return urllib.request.urlopen(
            urllib.request.Request(
                self.base + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": "application/json"} | (headers or {}),
            )
        )

    def test_project_report_and_comparison_over_http(self):
        p = json.load(self.request("/api/projects", {"name": "HTTP Project"}))
        saved = json.load(
            self.request(
                "/api/reports/save", {"project_id": p["id"], "report": report()}
            )
        )
        next_report = json.load(
            self.request(
                "/api/reports/save",
                {"project_id": p["id"], "report": report("1.1.1.1")},
            )
        )
        diff = json.load(
            self.request(
                "/api/compare?before="
                + saved["saved_id"]
                + "&after="
                + next_report["saved_id"]
            )
        )
        self.assertEqual(len(diff["changes"]), 2)
        backup = json.load(self.request("/api/projects/" + p["id"] + "/export"))
        self.assertEqual(len(backup["reports"]), 2)

    def test_foreign_host_cannot_read_projects(self):
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/projects", headers={"Host": "attacker.example"})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
