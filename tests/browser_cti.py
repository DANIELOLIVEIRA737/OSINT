"""Optional end-to-end CTI/Atlas integration test. Providers use upstream fixtures."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(
    os.environ.get("ATLAS_BROWSER_OUTPUT", tempfile.mkdtemp(prefix="atlas-cti-output-"))
)
OUTPUT.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="atlas-cti-db-") as data:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    code = "import sys;sys.path.insert(0,'tests');import app;from cti import CTIService;from test_cti import fixture_fetch;app.CTI=CTIService(fixture_fetch);app.ip_info=lambda ip:{'ip':ip,'source':'fixture IP metadata'};app.serve()"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=os.environ | {"PORT": str(port), "ATLAS_DATA_DIR": data},
        stdout=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/health", timeout=0.5).close()
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("Server failed to start")
                time.sleep(0.05)
        else:
            raise RuntimeError("Startup timeout")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                headless=True,
                args=["--no-sandbox"],
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            destinations = []
            violations = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda r: destinations.append(urllib.parse.urlsplit(r.url).hostname),
            )
            page.route("https://tile.openstreetmap.org/**", lambda r: r.abort())
            project = page.request.post(
                base + "/api/projects", data={"name": "Atlas CTI Integration"}
            ).json()
            page.add_init_script(
                'localStorage.setItem("atlas.activeProject",'
                + json.dumps(project["id"])
                + ");"
            )
            page.goto(base + "/cti/")
            page.evaluate(
                "() => window.addEventListener('securitypolicyviolation',e=>console.error('CSP: '+e.violatedDirective))"
            )
            expect(page.locator("#uh-list .card")).to_have_count(2)
            expect(page.locator("#ds-list .card")).to_have_count(3)
            expect(page.locator("#feodo-list .card")).to_have_count(3)
            expect(page.locator("#kev-list .card")).to_have_count(2)
            expect(
                page.locator("#world-map .leaflet-overlay-pane path").first
            ).to_be_visible()
            expect(page.locator("#cti-project")).to_have_value(project["id"])
            page.locator("#open-atlas-projects").click()
            expect(page.locator("#projects-dialog")).to_be_visible()
            page.locator("#close-projects").click()
            page.locator('a[href="/cti/"]').click()
            expect(page.locator("#uh-list .card")).to_have_count(2)

            expect(page.locator("#feed-health")).to_have_text("5 / 5")
            page.screenshot(
                path=str(OUTPUT / "observatory-desktop.png"), full_page=True
            )
            expect(page.locator("#world-map")).to_have_attribute(
                "data-basemap", "vector"
            )
            page.locator("#map-expand").click()
            expect(page.locator(".map-stage")).to_have_class("map-stage is-expanded")
            page.keyboard.press("Escape")
            expect(page.locator("#map-expand")).to_have_attribute(
                "aria-pressed", "false"
            )
            page.locator("#map-tiles").click()
            expect(page.locator("#world-map")).to_have_attribute("data-basemap", "osm")
            page.locator("#map-tiles").click()
            expect(page.locator("#world-map")).to_have_attribute(
                "data-basemap", "vector"
            )
            page.locator('[data-map-layer="dshield"][role="tab"]').click()
            expect(page.locator("body")).to_have_attribute("data-map-layer", "dshield")
            page.locator('[data-map-layer="feodo"][role="tab"]').click()
            expect(page.locator("body")).to_have_attribute("data-map-layer", "feodo")
            page.locator("#settings-btn").click()
            page.locator('[data-theme="forest"]').click()
            expect(page.locator("html")).to_have_attribute("data-theme", "forest")
            page.locator('[data-theme="night"]').click()
            page.locator("#settings-close").click()
            page.locator('[data-map-layer="urlhaus"][role="tab"]').click()
            expect(
                page.locator('.country-count-marker[data-cc="PT"]')
            ).to_have_attribute("data-count", "1")
            page.locator('.country-count-marker[data-cc="PT"]').focus()
            page.keyboard.press("Enter")
            expect(page.locator("#country-card")).to_have_attribute("data-open", "1")
            page.locator("#map-home").click()
            expect(page.locator("#country-card")).to_be_hidden()
            page.locator("#q").fill("PT")
            expect(page.locator("#country-card")).to_be_visible()
            with page.expect_download() as csv:
                page.locator("#country-export").click()
            assert "193.136.2.10" in Path(csv.value.path()).read_text(
                encoding="utf-8-sig"
            )
            page.locator("#country-clear").click()
            page.locator("#q").fill("")
            target = page.locator("#uh-list .card", has_text="193.136.2.10")
            target.locator(".atlas-save").click()
            expect(page.locator("#cti-save-status")).to_contain_text(
                "Evidência guardada"
            )
            saved = page.request.get(base + "/api/projects/" + project["id"]).json()
            assert len(saved["reports"]) == 1
            restored = page.request.get(
                base + "/api/reports/" + saved["reports"][0]["id"]
            ).json()
            assert restored["bookmarks"] == ["threat_intelligence"]
            # No raw malicious destination is an anchor in the map or Atlas report.
            for href in page.locator("a[href]").evaluate_all(
                "(nodes)=>nodes.map(n=>n.href)"
            ):
                assert urllib.parse.urlsplit(href).hostname not in (
                    "193.136.2.10",
                    "malware.example.invalid",
                )
            page.screenshot(path=str(OUTPUT / "cti-desktop.png"), full_page=True)
            target.locator(".atlas-analyse").click()
            expect(page.locator("#results")).to_be_visible()
            expect(page.locator("#report-title")).to_have_text("193.136.2.10")
            expect(page.locator("#saved-state")).to_contain_text("Guardado em")
            expect(page.locator('[data-name="threat_intelligence"]')).to_contain_text(
                "URLhaus"
            )
            assert page.locator('a[href="http://193.136.2.10/ioc"]').count() == 0
            assert (
                "193.136.2.10" not in destinations
                and "malware.example.invalid" not in destinations
            )
            assert page.locator(".graph-node.type-indicator").count() >= 1
            page.emulate_media(media="print")
            page.pdf(path=str(OUTPUT / "cti-evidence.pdf"), format="A4")
            page.emulate_media(media="screen")
            # Optional correlation in an ordinary technical IP report uses the same feed cache.
            page.locator("#mode-standard").click()
            page.locator("#cti-check").check()
            page.locator("#target").fill("193.136.2.10")
            page.locator("#submit").click()
            expect(page.locator("#metric-sources")).to_have_text("3/3")
            expect(page.locator('[data-name="threat_intelligence"]')).to_contain_text(
                "URLhaus"
            )
            page.locator('a[href="/cti/"]').click()
            expect(page.locator("#kev-list .card")).to_have_count(2)
            page.locator('[data-feed-tab="kev"]').click()
            page.locator("#kev-list .card").first.locator(".atlas-analyse").click()
            expect(page.locator("#report-title")).to_have_text("CVE-2024-0001")
            expect(page.locator('[data-name="threat_intelligence"]')).to_contain_text(
                "CISA KEV"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.goto(base + "/cti/")
            expect(page.locator("#uh-list .card")).to_have_count(2)
            page.screenshot(path=str(OUTPUT / "cti-mobile.png"), full_page=True)
            assert page.evaluate(
                "document.documentElement.scrollWidth<=innerWidth"
            ), "CTI mobile overflow"
            page.locator('[data-feed-tab="news"]').click()
            expect(page.locator("#panel-news")).to_be_visible()
            expect(page.locator("#panel-urlhaus")).to_be_hidden()
            page.set_viewport_size({"width": 320, "height": 740})
            assert page.evaluate(
                "document.documentElement.scrollWidth<=innerWidth"
            ), "320px overflow"
            # Source failures have an explicit empty state, not fabricated map activity.
            unavailable = {
                key: {
                    "ok": False,
                    "error": "Fixture: source unavailable",
                    "total": 0,
                    "items": [],
                }
                for key in ["kev", "urlhaus", "dshield", "feodo", "news"]
            }
            unavailable.update(
                fetchedAt="2026-10-16T10:00:00Z",
                map={"pins": [], "withGeo": 0, "withoutGeo": 0},
                mapDshield={"pins": []},
                mapFeodo={"pins": []},
            )
            page.route(
                "**/api/cti/feed*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(unavailable),
                ),
            )
            page.locator("#refresh-btn").click()
            expect(page.locator("#feed-health")).to_have_text("0 / 5")
            expect(page.locator("#map-empty")).to_be_visible()
            expect(page.locator("#map-empty-message")).to_contain_text("indisponível")
            expect(page.locator("#world-map")).to_have_attribute("data-pin-count", "0")
            page.locator("#map-expand").click()
            expect(page.locator("#map-expand")).to_have_attribute(
                "aria-pressed", "true"
            )
            page.keyboard.press("Escape")
            page.set_viewport_size({"width": 1366, "height": 650})
            page.locator(".map-footer").scroll_into_view_if_needed()
            expect(page.locator(".map-footer")).to_be_in_viewport()
            assert page.evaluate(
                "document.documentElement.scrollWidth<=innerWidth"
            ), "Short desktop overflow"
            assert not errors, errors
            for path in [
                "/cti/../cti.py",
                "/cti/data/ranges.bin",
                "/integrations/cti/data/ranges.bin",
                "/cti/parse.js",
                "/data/atlas.sqlite3",
            ]:
                assert page.request.get(base + path).status == 404, path
            browser.close()
        print(
            "CTI integration GUI passed: real parsers/API, 3 map layers, geo shapes, filters/settings, CSV, project evidence, passive IOC/CVE navigation, no IOC requests/links, graph, PDF, mobile and static-file isolation. Sources: explicit upstream fixtures."
        )
        print("Artifacts: " + str(OUTPUT))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
