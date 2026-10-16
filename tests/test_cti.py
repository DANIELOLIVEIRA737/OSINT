import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import app
from cti import (
    CTIService,
    Geography,
    FEEDS,
    NEWS,
    parse_kev,
    parse_urlhaus,
    parse_dshield,
    parse_feodo,
    parse_news,
    passive_identifier,
)

FIX = Path(__file__).resolve().parents[1] / "integrations" / "cti" / "fixtures"


def fixture_fetch(url, maximum):
    mapping = {
        FEEDS["kev"]: "kev.json",
        FEEDS["urlhaus"]: "urlhaus.csv",
        FEEDS["dshield"]: "dshield-sources.json",
        FEEDS["feodo"]: "feodo.csv",
    }
    if url in mapping:
        return 200, {}, (FIX / mapping[url]).read_bytes(), False
    if url in NEWS.values():
        return 200, {}, (FIX / "news.xml").read_bytes(), False
    if url.startswith("https://isc.sans.edu/api/ip/"):
        import urllib.parse

        ip = urllib.parse.unquote(url.split("/api/ip/")[1].split("?")[0])
        return (
            200,
            {},
            json.dumps(
                json.loads((FIX / "dshield-ips.json").read_text()).get(ip, {})
            ).encode(),
            False,
        )
    raise AssertionError("Unexpected network destination: " + url)


class CTITests(unittest.TestCase):
    def setUp(self):
        self.service = CTIService(fixture_fetch)

    def test_all_feeds_geo_news_and_no_hostname_resolution(self):
        with patch(
            "socket.getaddrinfo", side_effect=AssertionError("No IOC DNS queries")
        ):
            feed = self.service.feed()
        self.assertTrue(all(feed[k]["ok"] for k in (*FEEDS, "news")))
        item = next(
            i
            for i in feed["urlhaus"]["items"]
            if i["ioc"].startswith("http://193.136.")
        )
        self.assertEqual(item["geo"]["cc"], "PT")
        host = next(i for i in feed["urlhaus"]["items"] if ".invalid" in i["ioc"])
        self.assertIsNone(host["geo"])
        self.assertTrue(feed["mapDshield"]["withGeo"] > 0)
        self.assertTrue(feed["mapFeodo"]["withGeo"] > 0)

    def test_correlation_is_exact_and_not_a_clean_verdict(self):
        result = self.service.correlate("193.136.2.10")
        self.assertTrue(any(i["source"] == "urlhaus" for i in result["matches"]))
        self.assertEqual(self.service.correlate("other.example.invalid")["matches"], [])
        self.assertIn(
            "não confirma",
            self.service.correlate("other.example.invalid")["assessment"],
        )
        self.assertTrue(self.service.correlate("CVE-2024-0001")["matches"])

    def test_unavailable_sources_are_not_zero_matches(self):
        service = CTIService(lambda u, m: (403, {}, b"Forbidden", False))
        with self.assertRaisesRegex(ValueError, "indisponíveis"):
            service.correlate("example.com")
        self.assertFalse(service.feed()["news"]["ok"])

    def test_refresh_cache_and_cooldown(self):
        from unittest.mock import Mock

        fetch = Mock(side_effect=fixture_fetch)
        service = CTIService(fetch)
        service.feed()
        calls = fetch.call_count
        service.feed(True)
        self.assertEqual(calls, fetch.call_count)
        service.at -= 31
        service.feed(True)
        self.assertGreater(fetch.call_count, calls)

    def test_private_indicator_is_passive_metadata_only(self):
        self.assertEqual(passive_identifier("http://127.0.0.1/a"), ("127.0.0.1", "ip"))
        for bad in (
            "file:///etc/passwd",
            "https://user:pass@example.com",
            "not an indicator",
        ):
            with self.assertRaises(ValueError):
                passive_identifier(bad)

    def test_source_redirect_cannot_escape_allowlist(self):
        service = CTIService(
            lambda u, m: (302, {"Location": "http://127.0.0.1/"}, b"", False)
        )
        with self.assertRaisesRegex(ValueError, "não autorizado"):
            service.text(FEEDS["kev"])

    def test_dshield_429_stops_unclaimed_enrichment(self):
        calls = []

        def limited(url, maxsize):
            if "/api/ip/" in url:
                calls.append(url)
                return 429, {}, b"", False
            return fixture_fetch(url, maxsize)

        feed = CTIService(limited).feed()
        self.assertTrue(feed["dshield"]["enrich"]["stopped429"])
        self.assertTrue(all(not i.get("geo") for i in feed["dshield"]["items"]))
        self.assertLessEqual(len(calls), 5)

    def test_cti_report_never_visits_or_resolves_indicator(self):
        with patch.object(app, "CTI", self.service), patch.object(
            app, "public_addresses", side_effect=AssertionError("No target request")
        ):
            report = app.cti_report("http://193.136.2.10/ioc")
        self.assertEqual(report["mode"], "cti")
        self.assertEqual(report["results"]["threat_intelligence"]["status"], "ok")
        self.assertTrue(any(n["type"] == "indicator" for n in report["graph"]["nodes"]))

    def test_optional_correlation_integrates_technical_report(self):
        with patch.object(app, "CTI", self.service), patch.object(
            app, "public_addresses", return_value=["193.136.2.10"]
        ), patch.object(app, "ip_info", return_value={"ip": "193.136.2.10"}):
            report = app.investigate("193.136.2.10", with_cti=True)
        self.assertEqual(report["results"]["threat_intelligence"]["status"], "ok")
        self.assertTrue(
            any(
                f["source"] == "threat_intelligence"
                for f in report["summary"]["findings"]
            )
        )

    def test_comparison_does_not_turn_failed_feed_into_removed_ioc(self):
        from intelligence import compare

        old_data = self.service.correlate("193.136.2.10")
        new_data = copy.deepcopy(old_data)
        new_data["matches"] = []
        new_data["observed_at"] = "2027-01-01T00:00:00Z"
        new_data["assessment"] = "Sem correspondências na amostra disponível"
        for source in new_data["sources_checked"]:
            if source["source"] == "urlhaus":
                source["available"] = False
                source["error"] = "HTTP 403"

        def report(d):
            return {
                "target": "193.136.2.10",
                "mode": "cti",
                "created_at": "2026-10-16T00:00:00Z",
                "results": {"threat_intelligence": {"status": "ok", "data": d}},
            }

        result = compare(report(old_data), report(new_data))
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["coverage"][0]["module"], "threat_intelligence/urlhaus")

    @unittest.skipUnless(
        shutil.which("node"), "Node only required for upstream parity tests"
    )
    def test_python_parsers_match_original_javascript(self):
        root = FIX.parent
        script = "const p=require('./parse.js'),fs=require('fs');console.log(JSON.stringify({kev:p.parseKev(JSON.parse(fs.readFileSync('fixtures/kev.json'))),urlhaus:p.parseUrlhausCsv(fs.readFileSync('fixtures/urlhaus.csv','utf8')),dshield:p.parseDshieldSources(JSON.parse(fs.readFileSync('fixtures/dshield-sources.json'))),feodo:p.parseFeodoCsv(fs.readFileSync('fixtures/feodo.csv','utf8'))}));"
        original = json.loads(subprocess.check_output(["node", "-e", script], cwd=root))
        parsed = {
            "kev": parse_kev(json.loads((FIX / "kev.json").read_text())),
            "urlhaus": parse_urlhaus((FIX / "urlhaus.csv").read_text()),
            "dshield": parse_dshield(
                json.loads((FIX / "dshield-sources.json").read_text())
            ),
            "feodo": parse_feodo((FIX / "feodo.csv").read_text()),
        }
        for name in parsed:
            self.assertEqual(parsed[name]["items"], original[name]["items"], name)
            self.assertEqual(parsed[name]["total"], original[name]["total"], name)


if __name__ == "__main__":
    unittest.main()
