"""Python adapter for DANIELOLIVEIRA737/cti: identical feed shapes, no Node runtime."""

import bisect
import concurrent.futures
import copy
import csv
import ipaddress
import json
import re
import struct
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DATA = Path(__file__).parent / "integrations" / "cti" / "data"
FEEDS = {
    "kev": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "urlhaus": "https://urlhaus.abuse.ch/downloads/csv_recent/",
    "dshield": "https://isc.sans.edu/api/sources/attacks/40?json",
    "feodo": "https://feodotracker.abuse.ch/downloads/ipblocklist.csv",
}
NEWS = {
    "CISA": "https://www.cisa.gov/ncas/alerts.xml",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
}
ALLOWED = {urllib.parse.urlsplit(u).hostname for u in [*FEEDS.values(), *NEWS.values()]}


def now():
    return datetime.now(timezone.utc).isoformat()


def empty(error):
    return {"ok": False, "error": str(error)[:400], "total": 0, "items": []}


def base(source, ident, ioc, date, **values):
    labels = {
        "kev": "CISA KEV",
        "urlhaus": "URLhaus",
        "dshield": "SANS DShield",
        "feodo": "Feodo Tracker",
    }
    return {
        "source": source,
        "sourceLabel": labels[source],
        "id": ident,
        "ioc": ioc,
        "date": date,
        "vendor": "",
        "product": "",
        "family": "",
    } | values


def parse_kev(data):
    if not isinstance(data, dict) or not isinstance(data.get("vulnerabilities"), list):
        raise ValueError("KEV: resposta sem lista de vulnerabilidades.")
    items = []
    for row in data["vulnerabilities"]:
        cve = str(row.get("cveID", ""))
        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve):
            continue
        items.append(
            base(
                "kev",
                cve,
                cve,
                str(row.get("dateAdded", "")),
                vendor=str(row.get("vendorProject", "")).strip(),
                product=str(row.get("product", "")).strip(),
                sourceUrl="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                detailUrl="https://nvd.nist.gov/vuln/detail/" + cve,
            )
        )
    items.sort(key=lambda r: r["date"], reverse=True)
    return {
        "ok": True,
        "error": None,
        "catalogVersion": data.get("catalogVersion", ""),
        "dateReleased": data.get("dateReleased", ""),
        "total": len(items),
        "items": items[:300],
    }


def csv_rows(text):
    return csv.reader(
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def parse_urlhaus(text):
    items = []
    for row in csv_rows(text):
        if len(row) < 8 or row[0] == "id":
            continue
        detail = (
            "https://urlhaus.abuse.ch/url/" + row[0] + "/"
            if row[0].isdigit()
            else "https://urlhaus.abuse.ch/"
        )
        items.append(
            base(
                "urlhaus",
                row[0],
                row[2],
                row[1],
                family=row[6] if row[6] != "None" else "",
                status=row[3],
                sourceUrl=detail,
                detailUrl=detail,
            )
        )
    if not items and "#" not in text and "id,dateadded,url" not in text:
        raise ValueError("URLhaus: CSV sem linhas reconhecíveis.")
    items.sort(key=lambda r: r["date"], reverse=True)
    return {"ok": True, "error": None, "total": len(items), "items": items[:300]}


def parse_dshield(data):
    if not isinstance(data, list):
        raise ValueError("DShield: esperado array de sources.")
    items = []
    for row in data:
        ip = str(row.get("ip", "")).strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue

        def number(value):
            try:
                return float(value or 0)
            except (ValueError, TypeError):
                return 0

        items.append(
            base(
                "dshield",
                ip,
                ip,
                str(row.get("lastseen") or row.get("firstseen") or ""),
                attacks=number(row.get("attacks")),
                count=number(row.get("count")),
                firstseen=str(row.get("firstseen", "")),
                lastseen=str(row.get("lastseen", "")),
                asnCountry=None,
                geo=None,
                sourceUrl="https://isc.sans.edu/",
                detailUrl="https://isc.sans.edu/ipinfo.html?ip="
                + urllib.parse.quote(ip),
            )
        )
    items.sort(key=lambda r: r["attacks"], reverse=True)
    return {"ok": True, "error": None, "total": len(items), "items": items[:40]}


def parse_feodo(text):
    items = []
    for row in csv_rows(text):
        if len(row) < 6 or row[0].startswith("first_seen"):
            continue
        ip = row[1].strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        items.append(
            base(
                "feodo",
                ip + ":" + row[2],
                ip,
                row[0],
                port=row[2],
                status=row[3],
                malware=row[5],
                family=row[5],
                lastOnline=row[4],
                geo=None,
                sourceUrl="https://feodotracker.abuse.ch/",
                detailUrl="https://feodotracker.abuse.ch/",
            )
        )
    if not items and "#" not in text and "dst_ip" not in text:
        raise ValueError("Feodo: CSV sem linhas reconhecíveis.")
    items.sort(key=lambda r: r["date"], reverse=True)
    return {"ok": True, "error": None, "total": len(items), "items": items[:300]}


def parse_news(text, label):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("RSS com entidades não suportado.")
    root = ET.fromstring(text)
    items = []
    for item in root.iter("item"):
        title = " ".join((item.findtext("title") or "").split())[:240]
        link = item.findtext("link") or ""
        url = urllib.parse.urlsplit(link)
        if (
            not title
            or url.scheme not in ("http", "https")
            or url.username
            or url.password
        ):
            continue
        date = (
            item.findtext("pubDate")
            or item.findtext("{http://purl.org/dc/elements/1.1/}date")
            or item.findtext("updated")
            or ""
        )
        try:
            ts = parsedate_to_datetime(date).timestamp() * 1000
        except (ValueError, TypeError, OverflowError):
            try:
                ts = (
                    datetime.fromisoformat(date.replace("Z", "+00:00")).timestamp()
                    * 1000
                )
            except (ValueError, OverflowError):
                ts = 0
        items.append(
            {"source": label, "title": title, "url": link, "date": date, "ts": ts}
        )
    if not items:
        raise ValueError("RSS sem itens reconhecíveis (" + label + ").")
    return items


class Geography:
    def __init__(self, directory=DATA):
        raw = (directory / "ranges.bin").read_bytes()
        magic, count = struct.unpack_from(">II", raw)
        if magic != 0x43544952 or len(raw) != 8 + count * 10:
            raise ValueError("Dataset RIR inválido.")
        self.ranges = [
            (a, b, c.decode("ascii"))
            for a, b, c in struct.iter_unpack(">II2s", raw[8:])
        ]
        self.starts = [r[0] for r in self.ranges]
        self.centroids = json.loads((directory / "centroids.json").read_text())

    def geo(self, ioc):
        try:
            host = urllib.parse.urlsplit(ioc).hostname if "://" in ioc else ioc
            address = ipaddress.ip_address(host)
            if address.version != 4:
                return None
            number = int(address)
            index = bisect.bisect_right(self.starts, number) - 1
            if index < 0 or number > self.ranges[index][1]:
                return None
            cc = self.ranges[index][2]
            point = self.centroids.get(cc)
            return (
                {"cc": cc, "lat": point[0], "lng": point[1], "ip": host}
                if point
                else None
            )
        except (ValueError, TypeError):
            return None

    def attach(self, source):
        if source["ok"]:
            for item in source["items"]:
                item["geo"] = self.geo(item["ioc"])


def build_map(source, kind):
    note = {
        "rir": "País de alocação RIR; não GPS nem ataques em direto. Hostnames não são resolvidos.",
        "asn": "País do ASN (ascountry); ASN ≠ GPS. Scanners reportados ao DShield.",
        "c2": "País RIR dos IPs destino C2; não origem do atacante.",
    }[kind]
    pins = {}
    without = 0
    skipped = 0
    for item in source.get("items", []):
        g = item.get("geo")
        if not g:
            without += 1
            if "://" in item["ioc"]:
                try:
                    ipaddress.IPv4Address(urllib.parse.urlsplit(item["ioc"]).hostname)
                except (ValueError, TypeError):
                    skipped += 1
            continue
        cc = g["cc"]
        pins.setdefault(
            cc, {"cc": cc, "lat": g.get("lat"), "lng": g.get("lng"), "count": 0}
        )["count"] += 1
    return {
        "pins": sorted(pins.values(), key=lambda r: -r["count"]),
        "withGeo": sum(p["count"] for p in pins.values()),
        "withoutGeo": without,
        "skippedNoIp": skipped,
        "note": (source.get("error") or "") + " " + note,
    }


class CTIService:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.cached = None
        self.at = 0
        self.lock = threading.Lock()
        self.geo = Geography()

    def text(self, url):
        for _ in range(4):
            status, headers, body, truncated = self.fetcher(url, 10485760)
            if status in (301, 302, 303, 307, 308):
                location = next(
                    (v for k, v in headers.items() if k.lower() == "location"), None
                )
                new = urllib.parse.urljoin(url, location or "")
                parsed = urllib.parse.urlsplit(new)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname not in ALLOWED
                    or parsed.username
                    or parsed.port not in (None, 443)
                ):
                    raise ValueError("Redirecionamento da fonte CTI não autorizado.")
                url = new
                continue
            if status != 200:
                raise ValueError(
                    "HTTP "
                    + str(status)
                    + " na fonte "
                    + urllib.parse.urlsplit(url).hostname
                )
            if truncated:
                raise ValueError("Fonte excede o limite de leitura de 10 MiB.")
            return body.decode("utf-8-sig", errors="replace")
        raise ValueError("Demasiados redirecionamentos na fonte CTI.")

    def source(self, name):
        try:
            text = self.text(FEEDS[name])
            result = {
                "kev": lambda: parse_kev(json.loads(text)),
                "urlhaus": lambda: parse_urlhaus(text),
                "dshield": lambda: parse_dshield(json.loads(text)),
                "feodo": lambda: parse_feodo(text),
            }[name]()
            result["observedAt"] = now()
            return result
        except Exception as exc:
            return empty(exc) | {"observedAt": now()}

    def enrich(self, source):
        items = source["items"]
        stats = {
            "attempted": len(items),
            "fetched": 0,
            "failed": 0,
            "skipped": 0,
            "stopped429": False,
        }
        stop = threading.Event()
        lock = threading.Lock()

        def worker(item):
            if stop.is_set():
                return
            try:
                ip = ipaddress.ip_address(item["ioc"])
                if not ip.is_global:
                    raise ValueError("Endereço não público; enriquecimento ignorado.")
                data = json.loads(
                    self.text(
                        "https://isc.sans.edu/api/ip/"
                        + urllib.parse.quote(str(ip), safe="")
                        + "?json"
                    )
                )
                data = data.get("ip", data)
                cc = str(data.get("ascountry") or "").upper()
                point = self.geo.centroids.get(cc)
                if re.fullmatch("[A-Z]{2}", cc):
                    item["asnCountry"] = cc
                    item["geo"] = {"cc": cc, "kind": "asn", "ip": item["ioc"]}
                    if point:
                        item["geo"].update(lat=point[0], lng=point[1])
                if data.get("asname"):
                    item["asname"] = str(data["asname"])
                if data.get("as") is not None:
                    item["asn"] = data["as"]
                with lock:
                    stats["fetched"] += 1
            except Exception as exc:
                with lock:
                    if re.search(r"\b429\b", str(exc)):
                        stats["stopped429"] = True
                        stop.set()
                    else:
                        stats["failed"] += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as workers:
            list(workers.map(worker, items))
        stats.update(
            withAsn=sum(bool(i.get("geo")) for i in items),
            withoutAsn=sum(not i.get("geo") for i in items),
        )
        stats["skipped"] = stats["attempted"] - stats["fetched"] - stats["failed"]
        stats["incomplete"] = bool(stats["failed"] or stats["skipped"])
        source.update(
            enrich=stats,
            enrichIncomplete=stats["incomplete"],
            enrichNote=(
                "Enriquecimento ASN parcial; países em falta não são inventados."
                if stats["incomplete"]
                else None
            ),
        )

    def news(self):
        items = []
        errors = []
        for label, url in NEWS.items():
            try:
                items.extend(parse_news(self.text(url), label))
            except Exception as exc:
                errors.append(label + ": " + str(exc))
        unique = {i["url"]: i for i in items}
        items = sorted(unique.values(), key=lambda r: r["ts"], reverse=True)
        recent = [i for i in items if 0 <= time.time() * 1000 - i["ts"] <= 3600000]
        return {
            "ok": bool(items),
            "error": " · ".join(errors) or None,
            "items": (recent or items)[:12],
            "total": len(items),
            "window": "hour" if recent else "latest" if items else "none",
        }

    def feed(self, force=False):
        with self.lock:
            if (
                self.cached
                and time.time() - self.at < 300
                and (not force or time.time() - self.at < 30)
            ):
                return copy.deepcopy(self.cached) | {
                    "cached": True,
                    "refreshRequested": force,
                }
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as workers:
                pending = {name: workers.submit(self.source, name) for name in FEEDS}
                news = workers.submit(self.news)
                result = {name: f.result() for name, f in pending.items()}
                result["news"] = news.result()
            if result["dshield"]["ok"]:
                self.enrich(result["dshield"])
            self.geo.attach(result["urlhaus"])
            self.geo.attach(result["feodo"])
            result.update(
                map=build_map(result["urlhaus"], "rir"),
                mapDshield=build_map(result["dshield"], "asn"),
                mapFeodo=build_map(result["feodo"], "c2"),
                fetchedAt=now(),
                cached=False,
            )
            self.cached = result
            self.at = time.time()
            return copy.deepcopy(result)

    def correlate(self, host, addresses=(), force=False):
        data = self.feed(force)
        matches = []
        sources = []
        targets = {str(v).lower().rstrip(".") for v in (host, *addresses)}
        for name in (
            ("kev",)
            if re.fullmatch(r"CVE-\d{4}-\d{4,}", host)
            else ("urlhaus", "dshield", "feodo")
        ):
            source = data[name]
            sources.append(
                {
                    "source": name,
                    "available": source["ok"],
                    "error": source.get("error"),
                    "sample_size": len(source["items"]),
                    "observed_at": source.get("observedAt", data["fetchedAt"]),
                }
            )
            if not source["ok"]:
                continue
            for item in source["items"]:
                try:
                    indicator = (
                        urllib.parse.urlsplit(item["ioc"]).hostname
                        if "://" in item["ioc"]
                        else item["ioc"]
                    )
                except ValueError:
                    continue
                if indicator and indicator.lower().rstrip(".") in targets:
                    matches.append(copy.deepcopy(item))
        if not any(s["available"] for s in sources):
            raise ValueError(
                "Fontes IOC indisponíveis; não é possível avaliar correspondências."
            )
        return {
            "matches": matches,
            "sources_checked": sources,
            "checked_targets": sorted(targets),
            "observed_at": data["fetchedAt"],
            "cached": data.get("cached", False),
            "source": "CTI local · URLhaus / SANS DShield / Feodo",
            "assessment": (
                "Correspondência(s) reportada(s) nas fontes públicas."
                if matches
                else "Sem correspondências na amostra disponível; não confirma que o alvo seja seguro."
            ),
            "note": "Comparação exata com IP/hostname observado, sobre amostras limitadas (300/40/300). Um IP partilhado não confirma comprometimento do domínio. Não foram visitados os destinos IOC. CISA KEV não permite inferir vulnerabilidade de um site por tecnologia ou nome.",
        }


def passive_identifier(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2048:
        raise ValueError("Indicador inválido.")
    value = value.strip()
    if re.fullmatch(r"CVE-\d{4}-\d{4,}", value.upper()):
        return value.upper(), "cve"
    if "://" in value:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            raise ValueError("URL IOC inválido.")
        host = parsed.hostname or ""
    else:
        host = value
    try:
        return str(ipaddress.ip_address(host)), "ip"
    except ValueError:
        pass
    host = host.rstrip(".").encode("idna").decode("ascii").lower()
    if not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
    ):
        raise ValueError("Indicador não reconhecido como IP, domínio, URL ou CVE.")
    return host, "site"
