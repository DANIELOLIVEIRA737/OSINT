"""Optional Chromium smoke test. Install playwright separately; isolated DB, no real provider queries."""

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intelligence import graph
from playwright.sync_api import sync_playwright, expect
import os, subprocess, tempfile, socket, time, urllib.request, shutil

OUTPUT = Path(
    os.environ.get(
        "ATLAS_BROWSER_OUTPUT", tempfile.mkdtemp(prefix="atlas-browser-output-")
    )
)
OUTPUT.mkdir(parents=True, exist_ok=True)
fixture = {
    "version": 3,
    "target": "example.com",
    "input": "example.com",
    "type": "site",
    "mode": "deep",
    "created_at": "2026-10-15T15:00:00+00:00",
    "duration_ms": 1200,
    "summary": {"completed": 3, "total": 3, "findings": []},
    "results": {
        "network": {
            "status": "ok",
            "data": {"addresses": ["8.8.8.8"], "source": "DNS"},
        },
        "subdomains": {
            "status": "ok",
            "data": {
                "hosts": [
                    {
                        "host": "api.example.com",
                        "addresses": ["8.8.8.8"],
                        "dns_state": "resolved",
                        "http_state": "responded",
                        "http_status": 200,
                        "sources": ["crt.sh", "HackerTarget"],
                    }
                ],
                "total_candidates": 2,
                "checked": 1,
                "unverified": ["old.example.com"],
                "source": "https://crt.sh/",
            },
        },
        "ip": {
            "status": "ok",
            "data": {
                "ip": "8.8.8.8",
                "connection": {"asn": 15169, "org": "Example Network"},
                "source": "https://ipwho.is/",
            },
        },
    },
}
fixture["graph"] = graph(fixture)
company = {
    "version": 3,
    "target": "Example",
    "type": "company",
    "mode": "company",
    "created_at": fixture["created_at"],
    "summary": {"completed": 1, "total": 1, "findings": []},
    "results": {
        "company": {
            "status": "ok",
            "data": {
                "candidates": [
                    {
                        "id": "Q1",
                        "name": "Example Ltd",
                        "description": "Empresa candidata",
                        "websites": ["https://example.com"],
                        "source": "https://www.wikidata.org/wiki/Q1",
                    }
                ],
                "source": "https://www.wikidata.org/",
            },
        }
    },
}
company["graph"] = graph(company)
with tempfile.TemporaryDirectory(prefix="atlas-browser-data-") as data_dir:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        env=os.environ | {"PORT": str(port), "ATLAS_DATA_DIR": data_dir},
        stdout=subprocess.DEVNULL,
    )
    try:
        for attempt in range(100):
            try:
                urllib.request.urlopen(base + "/health", timeout=0.5).close()
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("Test server failed to start")
                time.sleep(0.05)
        else:
            raise RuntimeError("Test server startup timeout")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                headless=True,
                args=["--no-sandbox"],
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base)
            page.wait_for_function(
                "() => document.getElementById('storage-status').textContent.includes('Avulso')"
            )
            page.route(
                "**/api/investigate",
                lambda r: r.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(fixture),
                ),
            )
            page.route(
                "**/api/company",
                lambda r: r.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(company),
                ),
            )
            page.locator("#show-projects").click()
            page.locator("#project-name").fill("Teste de GUI")
            page.locator("#project-create button").click()
            page.wait_for_selector("#project-detail:not([hidden])")
            pid = page.locator("#active-project").input_value()
            assert pid
            page.locator("#project-notes").fill("Contexto persistente")
            page.locator("#save-project-notes").click()
            page.locator("#close-projects").click()
            page.locator("#target").fill("example.com")
            page.locator("#submit").click()
            page.wait_for_selector("#results:not([hidden])")
            assert "Guardado em" in page.locator("#saved-state").inner_text()
            assert page.locator(".graph-node").count() == 5
            page.locator(".graph-node.type-ip").click()
            assert "8.8.8.8" in page.locator("#graph-detail").inner_text()
            page.locator("#graph-in").click()
            assert "scale(1.2)" in page.locator("#relation-graph > g").get_attribute(
                "transform"
            )
            page.locator("#graph-filter").select_option("ip")
            assert page.locator(".graph-node").count() == 2
            page.locator("#graph-filter").select_option("all")
            assert page.locator("#subdomain-rows tr").count() == 1
            page.locator("#report-notes").fill("Hipótese <script>alert(1)</script>")
            page.locator("#save-notes").click()
            page.wait_for_function(
                "() => document.getElementById('message').textContent==='Notas do relatório guardadas.'"
            )
            page.locator('[data-name="network"] .pin-evidence').click()
            page.wait_for_function(
                "() => document.getElementById('bookmarked-list').textContent.includes('Resolução')"
            )
            page.screenshot(path=str(OUTPUT / "report.png"), full_page=True)
            page.locator("#subdomain-rows button").click()
            assert page.locator("#target").input_value() == "api.example.com"
            # A second report with a changed IP, still using the real persistence API.
            changed = json.loads(json.dumps(fixture))
            changed["created_at"] = "2026-10-16T15:00:00+00:00"
            changed["results"]["network"]["data"]["addresses"] = ["1.1.1.1"]
            changed["graph"] = graph(changed)
            page.unroute("**/api/investigate")
            page.route(
                "**/api/investigate",
                lambda r: r.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(changed),
                ),
            )
            page.locator("#target").fill("example.com")
            page.locator("#submit").click()
            page.wait_for_function(
                "() => document.getElementById('report-date').textContent.includes('16/10/2026')"
            )
            page.locator("#show-projects").click()
            assert (
                "Contexto persistente" == page.locator("#project-notes").input_value()
            )
            expect(page.locator("#project-reports .saved-report-row")).to_have_count(2)
            page.locator("#compare-reports").click()
            page.wait_for_selector("#comparison-panel:not([hidden])")
            assert "1 alteração" in page.locator("#comparison-count").inner_text()
            # Schedule creation and pause hit the real API. No network calls are needed until execution is due.
            page.locator("#show-projects").click()
            page.locator("#monitor-target").fill("example.com")
            page.locator("#monitor-create button").click()
            page.wait_for_selector(".monitor-row")
            page.locator(".monitor-row button", has_text="Pausar").click()
            page.wait_for_selector('.monitor-row button:has-text("Retomar")')
            page.locator("#close-projects").click()
            page.locator("#show-company").click()
            page.locator("#company-query").fill("Example")
            page.locator("#company-submit").click()
            page.wait_for_selector("#company-candidates:not([hidden])")
            assert "Example Ltd" in page.locator("#candidate-list").inner_text()
            assert page.locator(".graph-edge.hypothesis").count() == 1
            page.locator("#candidate-list button").click()
            assert page.locator("#target").input_value() == "https://example.com"
            with page.expect_download() as download:
                page.locator("#export").click()
            assert (
                json.loads(Path(download.value.path()).read_text())["type"] == "company"
            )
            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            assert page.locator("#cover-summary").inner_text()
            page.emulate_media(media="print")
            page.pdf(
                path=str(OUTPUT / "report.pdf"), format="A4", print_background=True
            )
            page.emulate_media(media="screen")
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate(
                "document.documentElement.scrollWidth<=innerWidth"
            ), "Mobile overflow"
            page.screenshot(path=str(OUTPUT / "mobile.png"), full_page=True)
            page.reload()
            page.wait_for_function(
                "() => document.getElementById('active-project').options.length>1"
            )
            page.locator("#show-projects").click()
            page.locator(f'.project-choice[data-project-id="{pid}"]').click()
            expect(page.locator("#project-reports .saved-report-row")).to_have_count(3)
            # Persistent notes and marked evidence survive a reload.
            page.locator("#project-reports .saved-report-row").last.locator(
                "button"
            ).click()
            expect(page.locator("#report-notes")).to_have_value(
                "Hipótese <script>alert(1)</script>"
            )
            assert "Resolução" in page.locator("#bookmarked-list").inner_text()

            # Exercise every domain module with an explicit full-report fixture.
            full = json.loads(json.dumps(fixture))

            def ok(data):
                return {
                    "status": "ok",
                    "duration_ms": 10,
                    "data": data,
                    "provenance": [
                        {
                            "url": "https://source.example/",
                            "cached": True,
                            "fetched_at": fixture["created_at"],
                            "ttl_seconds": 300,
                        }
                    ],
                }

            full["results"].update(
                {
                    "dns": ok(
                        {
                            "records": {
                                "MX": [{"value": "10 mail.example.com.", "ttl": 300}],
                                "DMARC": [{"value": "v=DMARC1; p=reject", "ttl": 300}],
                            },
                            "source": "https://dns.google/",
                        }
                    ),
                    "tls": ok(
                        {
                            "issuer": {"commonName": "Example CA"},
                            "valid_until": "Nov 15 23:59:59 2026 GMT",
                            "names": ["example.com"],
                            "source": "example.com:443",
                        }
                    ),
                    "website": ok(
                        {
                            "title": "Proof <img src=x onerror=alert(1)>",
                            "security": {
                                "checks": {
                                    "HTTPS": True,
                                    "Content-Security-Policy": False,
                                }
                            },
                            "metadata": {"description": "Evidence description"},
                            "scripts": ["https://example.com/app.js"],
                            "headers": {"Server": "Example"},
                            "links": ["https://example.com/about"],
                            "source": "https://example.com/",
                        }
                    ),
                    "transparency": ok(
                        {
                            "domains": ["api.example.com"],
                            "total_discovered": 1,
                            "source": "https://crt.sh/",
                        }
                    ),
                    "registration": ok(
                        {
                            "name": "EXAMPLE.COM",
                            "events": [{"event": "registration", "date": "2000-01-01"}],
                            "source": "https://rdap.example/",
                        }
                    ),
                    "reverse": ok(
                        {
                            "records": [
                                {"ip": "8.8.8.8", "hostname": "dns.example.com"}
                            ],
                            "source": "System DNS",
                        }
                    ),
                    "discovery": ok(
                        {
                            "documents": {
                                "robots.txt": {
                                    "status": 200,
                                    "excerpt": "User-agent: *",
                                }
                            },
                            "source": "https://example.com/",
                        }
                    ),
                    "archives": ok(
                        {
                            "snapshots": [
                                {
                                    "timestamp": "20000101000000",
                                    "url": "https://example.com/",
                                    "archive": "https://web.archive.org/web/20000101000000/https://example.com/",
                                }
                            ],
                            "source": "https://web.archive.org/",
                        }
                    ),
                }
            )
            full["graph"] = graph(full)
            full["summary"] = {"completed": 11, "total": 11, "findings": []}
            page.unroute("**/api/investigate")
            page.route(
                "**/api/investigate",
                lambda r: r.fulfill(
                    status=200, content_type="application/json", body=json.dumps(full)
                ),
            )
            page.locator("#target").fill("example.com")
            page.locator("#submit").click()
            expect(page.locator("#metric-sources")).to_have_text("11/11")
            expect(page.locator(".result-card")).to_have_count(11)
            assert page.locator("#cards img").count() == 0
            assert "Proof <img" in page.locator('[data-name="website"]').inner_text()
            page.locator('[data-tab="web"]').click()
            expect(page.locator(".result-card:visible")).to_have_count(3)
            page.locator('[data-tab="all"]').click()
            page.locator("#filter").fill("Example CA")
            expect(page.locator(".result-card:visible")).to_have_count(1)
            page.locator("#filter").fill("")
            page.locator("#show-projects").click()
            page.wait_for_selector("#project-detail:not([hidden])")
            with page.expect_download() as backup:
                page.locator("#project-backup").click()
            assert (
                len(json.loads(Path(backup.value.path()).read_text())["reports"]) == 4
            )
            page.locator("#close-projects").click()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            page.emulate_media(media="print")
            page.pdf(path=str(OUTPUT / "all-modules.pdf"), format="A4")
            page.emulate_media(media="screen")
            page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            page.set_viewport_size({"width": 1440, "height": 1100})
            page.reload()
            page.wait_for_selector("#storage-status")
            page.screenshot(path=str(OUTPUT / "workspace.png"), full_page=True)

            assert not errors, errors
            browser.close()
            print(
                "V3 GUI passed: real project/report persistence, project notes, evidence bookmarks, 2-report comparison, schedule+pause, graph filter/selection/zoom, subdomain actions, company candidates, JSON, PDF, reload and mobile layout. External investigation responses used explicit fixtures."
            )

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
print("Browser artifacts: " + str(OUTPUT))
