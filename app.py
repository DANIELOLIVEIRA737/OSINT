"""Public OSINT workbench. Python 3.12+, no third-party dependencies."""

import concurrent.futures
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import copy
from workspace import Store, InstanceLock
from intelligence import graph, compare
from cti import CTIService, passive_identifier

APP_BUILD = "atlas-cti-1"
ROOT = Path(__file__).parent
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8)
LIMIT = threading.BoundedSemaphore(4)
STORE = None
CTI = None
CTI_INIT_LOCK = threading.Lock()
CACHE = {}
CACHE_LOCK = threading.Lock()
CONTEXT = threading.local()


def store():
    global STORE
    if STORE is None:
        STORE = Store(
            Path(os.environ.get("ATLAS_DATA_DIR", str(ROOT / "data"))) / "atlas.sqlite3"
        )
    return STORE


def cti_service():
    global CTI
    if CTI is None:
        with CTI_INIT_LOCK:
            if CTI is None:
                CTI = CTIService(fetch)
    return CTI


def cti_report(value):
    started = time.monotonic()
    host, kind = passive_identifier(value)
    result = guarded(cti_service().correlate, host)
    report = {
        "version": 3,
        "target": host,
        "input": value,
        "type": kind,
        "mode": "cti",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": {"threat_intelligence": result},
        "summary": {
            "completed": int(result["status"] == "ok"),
            "total": 1,
            "findings": [],
        },
    }
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    report["summary"]["findings"] = summarize(report["results"])
    report["graph"] = graph(report)
    return report


def target(value):
    value = value.strip()
    if not value or len(value) > 2048:
        raise ValueError("Introduza um domínio, URL ou endereço IP válido.")
    try:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise ValueError("Apenas endereços IP públicos são permitidos.")
        return str(ip), None, "ip"
    except ValueError as exc:
        if "Apenas" in str(exc):
            raise
    parsed = urllib.parse.urlsplit(value if "://" in value else "https://" + value)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise ValueError("Use HTTP ou HTTPS, sem credenciais no URL.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Apenas as portas 80 e 443 são permitidas.")
    host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Apenas endereços IP públicos são permitidos.")
    except ValueError as exc:
        if "Apenas" in str(exc):
            raise
        if not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
        ):
            raise ValueError("O domínio não é válido.")
    authority = "[" + host + "]" if ":" in host else host
    return (
        host,
        urllib.parse.urlunsplit(
            (parsed.scheme, authority, parsed.path or "/", parsed.query, "")
        ),
        "site",
    )


def public_addresses(host):
    addresses = sorted(
        {r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    )
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("O destino resolve para uma rede privada ou reservada.")
    return addresses


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, maximum=524288):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PublicOSINT/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.5",
        },
    )
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=8)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(maximum + 1)
        return (
            response.status,
            dict(response.headers.items()),
            body[:maximum],
            len(body) > maximum,
        )


def dns_info(host):
    records = {}
    for kind in ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA", "SOA", "DMARC"):
        url = "https://dns.google/resolve?" + urllib.parse.urlencode(
            {
                "name": "_dmarc." + host if kind == "DMARC" else host,
                "type": "TXT" if kind == "DMARC" else kind,
            }
        )
        result = json_source(url)
        if result.get("Status") not in (0, 3):
            raise RuntimeError("Consulta DNS falhou: " + str(result.get("Status")))
        expected_type = {
            "A": 1,
            "AAAA": 28,
            "CNAME": 5,
            "MX": 15,
            "NS": 2,
            "TXT": 16,
            "CAA": 257,
            "SOA": 6,
            "DMARC": 16,
        }[kind]
        records[kind] = [
            {"value": a["data"], "ttl": a["TTL"]}
            for a in result.get("Answer", [])
            if a.get("type") == expected_type
        ]
    return {"records": records, "source": "https://dns.google/"}


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links, self.title, self.in_title = base, set(), "", False
        self.metadata, self.scripts = {}, set()

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        attributes = dict(attrs)
        if tag == "meta":
            name = (attributes.get("name") or attributes.get("property") or "").lower()
            if name in (
                "description",
                "generator",
                "robots",
                "og:title",
                "og:description",
                "og:site_name",
            ):
                self.metadata[name] = (attributes.get("content") or "")[:1000]
        if tag == "script" and attributes.get("src") and len(self.scripts) < 40:
            self.scripts.add(urllib.parse.urljoin(self.base, attributes["src"]))
        if tag == "a":
            href = dict(attrs).get("href", "")
            url = urllib.parse.urljoin(self.base, href)
            if (
                urllib.parse.urlsplit(url).scheme in ("http", "https")
                and len(self.links) < 100
            ):
                self.links.add(url)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title = (self.title + data)[:500]


def site_info(url, include_text=False, expected_origin=None):
    # Connect to a validated literal IP, preserving the original Host and TLS SNI.
    # This prevents DNS rebinding and never sends a supplied URL to an outbound proxy.
    import http.client

    redirects = []
    for _ in range(4):
        host, url, _ = target(url)
        if expected_origin and urllib.parse.urlsplit(url).netloc != expected_origin:
            raise ValueError("Redirecionamento para fora do site ignorado.")
        addresses = public_addresses(host)
        parsed = urllib.parse.urlsplit(url)
        port = 443 if parsed.scheme == "https" else 80
        connection = http.client.HTTPConnection(addresses[0], port, timeout=8)
        connection.connect()
        try:
            if port == 443:
                connection.sock = ssl.create_default_context().wrap_socket(
                    connection.sock, server_hostname=host
                )
            connection.request(
                "GET",
                urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, "")),
                headers={
                    "Host": parsed.netloc,
                    "User-Agent": "PublicOSINT/1.0",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            headers = dict(response.getheaders())
            location = response.getheader("Location")
            if response.status in (301, 302, 303, 307, 308) and location:
                redirects.append({"url": url, "status": response.status})
                url = urllib.parse.urljoin(url, location)
                continue
            body = response.read(524289)
            parser = Links(url)
            if "html" in response.getheader("Content-Type", ""):
                parser.feed(body[:524288].decode("utf-8", errors="replace"))
            # Cookies can contain session identifiers; omit them from reports.
            headers = {k: v for k, v in headers.items() if k.lower() != "set-cookie"}
            return {
                "url": url,
                "status": response.status,
                "headers": headers,
                "title": parser.title.strip(),
                "links": sorted(parser.links),
                "metadata": parser.metadata,
                "scripts": sorted(parser.scripts),
                "redirects": redirects,
                "security": header_analysis(headers, url),
                "technologies": technologies(headers, parser),
                **(
                    {"text": body[:524288].decode("utf-8", errors="replace")}
                    if include_text
                    else {}
                ),
                "truncated": len(body) > 524288,
                "source": url,
            }
        finally:
            connection.close()
    raise ValueError("Demasiados redirecionamentos.")


def certificate(host):
    address = public_addresses(host)[0]
    with socket.create_connection((address, 443), timeout=8) as raw:
        with ssl.create_default_context().wrap_socket(
            raw, server_hostname=host
        ) as conn:
            cert = conn.getpeercert()
            return {
                "subject": dict(x[0] for x in cert.get("subject", [])),
                "issuer": dict(x[0] for x in cert.get("issuer", [])),
                "valid_from": cert.get("notBefore"),
                "valid_until": cert.get("notAfter"),
                "names": [v for k, v in cert.get("subjectAltName", []) if k == "DNS"],
                "protocol": conn.version(),
                "source": host + ":443",
            }


def ip_info(ip):
    data = json_source("https://ipwho.is/" + urllib.parse.quote(ip, safe=":"))
    if not data.get("success"):
        raise RuntimeError(data.get("message", "Consulta IP indisponível."))
    return {
        k: data.get(k)
        for k in (
            "ip",
            "type",
            "country",
            "region",
            "city",
            "latitude",
            "longitude",
            "connection",
            "timezone",
        )
    } | {
        "source": "https://ipwho.is/" + ip,
        "note": "Localização aproximada da rede; não identifica uma pessoa ou morada.",
    }


def header_analysis(headers, url):
    normalized = {k.lower(): v for k, v in headers.items()}
    checks = {
        "HTTPS": urllib.parse.urlsplit(url).scheme == "https",
        "Strict-Transport-Security": "strict-transport-security" in normalized,
        "Content-Security-Policy": "content-security-policy" in normalized,
        "X-Content-Type-Options": normalized.get("x-content-type-options", "").lower()
        == "nosniff",
        "Proteção contra framing": (
            "x-frame-options" in normalized
            or "frame-ancestors"
            in normalized.get("content-security-policy", "").lower()
        ),
        "Referrer-Policy": "referrer-policy" in normalized,
        "Permissions-Policy": "permissions-policy" in normalized,
    }
    return {
        "checks": checks,
        "present": sum(checks.values()),
        "total": len(checks),
        "note": "Indicadores de configuração, não uma auditoria de vulnerabilidades. Presença não garante uma política eficaz.",
    }


def technologies(headers, parser):
    evidence = []
    for key, value in headers.items():
        if key.lower() in ("server", "x-powered-by"):
            evidence.append({"technology": value[:200], "evidence": "Cabeçalho " + key})
    if parser.metadata.get("generator"):
        evidence.append(
            {"technology": parser.metadata["generator"], "evidence": "Meta generator"}
        )
    patterns = {
        "WordPress": "/wp-content/",
        "Next.js": "/_next/",
        "Drupal": "/sites/default/",
        "Shopify": "cdn.shopify.com",
    }
    for technology, marker in patterns.items():
        if any(marker in script for script in parser.scripts):
            evidence.append(
                {
                    "technology": technology,
                    "evidence": "Referência pública a script: " + marker,
                }
            )
    return evidence


def json_source(url, maximum=2097152, ttl=300):
    with CACHE_LOCK:
        entry = CACHE.get(url)
    cached = bool(
        entry
        and time.time() < entry["expires"]
        and not getattr(CONTEXT, "refresh", False)
    )
    if cached:
        data = copy.deepcopy(entry["data"])
        fetched_at = entry["fetched_at"]
    else:
        status, _, body, truncated = fetch(url, maximum)
        if status != 200:
            raise RuntimeError(
                "Fonte respondeu HTTP "
                + str(status)
                + " (verifique limites ou permissões de rede)."
            )
        if truncated:
            raise RuntimeError(
                "A resposta excede o limite de leitura; os dados não foram tratados como completos."
            )
        data = json.loads(body)
        fetched_at = datetime.now(timezone.utc).isoformat()
        with CACHE_LOCK:
            for key in list(CACHE):
                if CACHE[key]["expires"] <= time.time():
                    del CACHE[key]
            while CACHE and (
                len(CACHE) >= 64
                or sum(e.get("size", 0) for e in CACHE.values()) + len(body) > 33554432
            ):
                CACHE.pop(next(iter(CACHE)))
            CACHE[url] = {
                "data": copy.deepcopy(data),
                "fetched_at": fetched_at,
                "expires": time.time() + ttl,
                "size": len(body),
            }
    if hasattr(CONTEXT, "sources"):
        CONTEXT.sources.append(
            {"url": url, "cached": cached, "fetched_at": fetched_at, "ttl_seconds": ttl}
        )
    return data


def registration(host, kind):
    # IANA bootstrap selects an authoritative RDAP service; user input never controls the endpoint host.
    ip = ipaddress.ip_address(host) if kind == "ip" else None
    family = ("ipv4" if ip.version == 4 else "ipv6") if ip else "dns"
    bootstrap = json_source("https://data.iana.org/rdap/" + family + ".json", ttl=86400)
    endpoint = None
    for keys, urls in bootstrap["services"]:
        match = (
            any(ip in ipaddress.ip_network(key) for key in keys)
            if ip
            else host.split(".")[-1] in keys
        )
        if match:
            endpoint = next((u for u in urls if u.startswith("https://")), None)
            break
    if not endpoint:
        raise RuntimeError(
            "Não existe um serviço RDAP HTTPS no registo IANA para este alvo."
        )
    query = (
        endpoint.rstrip("/")
        + ("/ip/" if ip else "/domain/")
        + urllib.parse.quote(host, safe=":")
    )
    data = json_source(query)
    # Domain services sometimes require the registrable parent domain. Do not guess public suffixes.
    nameservers = [n.get("ldhName", "") for n in data.get("nameservers", [])]
    events = [
        {"event": e.get("eventAction"), "date": e.get("eventDate")}
        for e in data.get("events", [])
    ]
    entities = []
    for entity in data.get("entities", []):
        # Keep organization / registrar names, excluding personal contact details.
        if any(role in entity.get("roles", []) for role in ("registrar", "registrant")):
            names = [
                v[3] for v in entity.get("vcardArray", [None, []])[1] if v[0] == "org"
            ]
            if "registrar" in entity.get("roles", []):
                names += [
                    v[3]
                    for v in entity.get("vcardArray", [None, []])[1]
                    if v[0] == "fn"
                ]
            entities.append(
                {
                    "roles": entity.get("roles", []),
                    "organizations": names,
                    "handle": entity.get("handle"),
                }
            )
    return {
        "name": data.get("ldhName", data.get("name")),
        "handle": data.get("handle"),
        "status": data.get("status", []),
        "events": events,
        "nameservers": nameservers,
        "entities": entities,
        "start_address": data.get("startAddress"),
        "end_address": data.get("endAddress"),
        "country": data.get("country"),
        "source": query,
        "note": "Dados do registo público. Alguns registos ocultam campos; subdomínios podem não ter um registo próprio.",
    }


def transparency(host):
    query = "https://crt.sh/?" + urllib.parse.urlencode(
        {"q": "%." + host, "output": "json"}
    )
    data = json_source(query, 4194304)
    names = set()
    for entry in data:
        for name in entry.get("name_value", "").lower().splitlines():
            name = name.removeprefix("*.").rstrip(".")
            if name == host or name.endswith("." + host):
                if len(name) <= 253:
                    names.add(name)
    return {
        "domains": sorted(names)[:200],
        "total_discovered": len(names),
        "shown_limit": 200,
        "certificate_entries": len(data),
        "source": query,
        "note": "Nomes observados em certificados públicos; não prova que estejam ativos nem que pertençam atualmente ao mesmo titular.",
    }


def archives(host):
    query = "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(
        {
            "url": host + "/*",
            "output": "json",
            "filter": "statuscode:200",
            "collapse": "urlkey",
            "limit": "40",
            "fl": "timestamp,original,mimetype",
        }
    )
    data = json_source(query)
    rows = data[1:] if data else []
    return {
        "snapshots": [
            {
                "timestamp": row[0],
                "url": row[1],
                "mime": row[2],
                "archive": "https://web.archive.org/web/" + row[0] + "/" + row[1],
            }
            for row in rows
        ],
        "limit": 40,
        "source": query,
        "note": "Amostra de URLs históricas, não um inventário completo nem uma lista necessariamente recente.",
    }


def reverse_dns(host):
    addresses = [host] if is_ip(host) else public_addresses(host)
    records = []
    for address in addresses[:4]:
        try:
            name, _, _ = socket.gethostbyaddr(address)
            records.append({"ip": address, "hostname": name})
        except (socket.herror, socket.gaierror):
            records.append({"ip": address, "hostname": None})
    return {
        "records": records,
        "source": "DNS reverso do sistema",
        "note": "Até quatro IPs. Um nome PTR não confirma a propriedade do endereço.",
    }


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def discovery(url):
    parsed = urllib.parse.urlsplit(url)
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
    documents = {}
    for path in ("robots.txt", "sitemap.xml", ".well-known/security.txt"):
        result = guarded(
            site_info, urllib.parse.urljoin(origin, path), True, parsed.netloc
        )
        if result["status"] == "ok":
            data = result["data"]
            documents[path] = {
                "status": data["status"],
                "url": data["url"],
                "excerpt": data.get("text", "")[:12000],
                "truncated": len(data.get("text", "")) > 12000 or data["truncated"],
            }
        else:
            documents[path] = {"error": result["error"]}
    if all("error" in document for document in documents.values()):
        raise RuntimeError(
            "Os três documentos públicos ficaram inacessíveis: "
            + next(iter(documents.values()))["error"]
        )
    return {
        "documents": documents,
        "source": origin,
        "note": "Apenas três caminhos públicos conhecidos. Regras do robots.txt não são percorridas e nenhum caminho descoberto é visitado.",
    }


def subdomains(host, results):
    candidates = {}

    def add(name, source):
        name = name.lower().removeprefix("*.").rstrip(".")
        if name != host and name.endswith("." + host):
            try:
                clean, _, _ = target(name)
                candidates.setdefault(clean, set()).add(source)
            except (ValueError, UnicodeError):
                pass

    ct = results.get("transparency", {})
    if ct.get("status") == "ok":
        for name in ct["data"].get("domains", []):
            add(name, "crt.sh")
    tls = results.get("tls", {})
    if tls.get("status") == "ok":
        for name in tls["data"].get("names", []):
            add(name, "Certificado TLS")
    source_url = "https://api.hackertarget.com/hostsearch/?" + urllib.parse.urlencode(
        {"q": host}
    )
    provider = guarded(fetch, source_url)
    source_status = {"crt.sh": ct.get("status", "unrun")}
    if provider["status"] == "ok":
        status, _, body, truncated = provider["data"]
        lines = body.decode("utf-8", errors="replace").splitlines()
        if (
            status == 200
            and not truncated
            and not any(
                "error" in line.lower() or "limit" in line.lower() for line in lines[:1]
            )
        ):
            source_status["HackerTarget"] = "ok"
            for line in lines[:500]:
                if "," in line:
                    add(line.split(",")[0], "HackerTarget")
        else:
            source_status["HackerTarget"] = (
                "error: HTTP " + str(status) + " / limite do fornecedor"
            )
    else:
        source_status["HackerTarget"] = "error: " + provider["error"]
    if not candidates and all(status != "ok" for status in source_status.values()):
        raise RuntimeError("Fontes de subdomínios indisponíveis. " + str(source_status))

    def probe(name):
        record = {
            "host": name,
            "sources": sorted(candidates[name]),
            "dns_state": "unknown",
            "http_state": "unverified",
            "addresses": [],
        }
        try:
            record["addresses"] = public_addresses(name)
            record["dns_state"] = "resolved"
        except socket.gaierror as exc:
            record["dns_state"] = (
                "not_found" if exc.errno == socket.EAI_NONAME else "unknown"
            )
            record["error"] = str(exc)
            return record
        except Exception as exc:
            record["error"] = str(exc)
            return record
        web = guarded(site_info, "https://" + name + "/", False, name)
        if web["status"] == "ok":
            record.update(
                http_state="responded",
                http_status=web["data"]["status"],
                title=web["data"]["title"],
            )
        else:
            record["http_error"] = web["error"]
        return record

    selected = sorted(candidates)[:12]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        hosts = list(workers.map(probe, selected))
    return {
        "hosts": hosts,
        "total_candidates": len(candidates),
        "checked": len(hosts),
        "limit": 12,
        "unverified": sorted(candidates)[12:200],
        "sources": source_status,
        "source": source_url,
        "note": "Até 12 nomes observados, sem brute force. DNS resolvido e resposta HTTPS são estados distintos. Uma falha não prova inatividade; IP partilhado não prova propriedade comum.",
    }


def company_search(query):
    started = time.monotonic()
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 160:
        raise ValueError("Introduza um nome de empresa entre 2 e 160 caracteres.")
    query = query.strip()

    def wikidata():
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "pt",
                "uselang": "pt",
                "limit": 8,
                "format": "json",
                "type": "item",
            }
        )
        data = json_source(url)
        hits = data.get("search", [])
        ids = [h["id"] for h in hits if re.fullmatch(r"Q[0-9]+", h.get("id", ""))]
        entities = {}
        if ids:
            detail_url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(ids),
                    "props": "claims|labels|descriptions",
                    "languages": "pt|en",
                    "format": "json",
                }
            )
            entities = json_source(detail_url).get("entities", {})

        def claims(entity, prop):
            return [
                c.get("mainsnak", {}).get("datavalue", {}).get("value")
                for c in entity.get("claims", {}).get(prop, [])
                if c.get("mainsnak", {}).get("datavalue")
            ]

        candidates = []
        for hit in hits:
            entity = entities.get(hit["id"], {})
            sites = [
                v
                for v in claims(entity, "P856")
                if isinstance(v, str)
                and urllib.parse.urlsplit(v).scheme in ("http", "https")
            ]
            # Require an official website or business identifiers to avoid presenting arbitrary people as companies.
            leis = claims(entity, "P1278")
            classes = [
                v.get("id") for v in claims(entity, "P31") if isinstance(v, dict)
            ]
            if not leis and not set(classes).intersection(
                {
                    "Q4830453",
                    "Q783794",
                    "Q6881511",
                    "Q43229",
                    "Q891723",
                    "Q167037",
                    "Q1664720",
                    "Q270791",
                    "Q484652",
                    "Q507619",
                    "Q891723",
                    "Q18127",
                }
            ):
                continue
            if not sites and not leis:
                continue
            candidates.append(
                {
                    "id": hit["id"],
                    "name": hit.get("label", hit["id"]),
                    "description": hit.get("description", ""),
                    "websites": sites[:8],
                    "lei": leis,
                    "classification": "Candidato por nome; confirmar identidade",
                    "source": "https://www.wikidata.org/wiki/" + hit["id"],
                }
            )
        return {
            "candidates": candidates,
            "source": url,
            "note": "Correspondências por nome, não confirmação de identidade ou propriedade. Wikidata é colaborativa; confirme no site e no registo oficial.",
        }

    def gleif():
        url = "https://api.gleif.org/api/v1/lei-records?" + urllib.parse.urlencode(
            {"filter[entity.legalName]": query, "page[size]": 8}
        )
        data = json_source(url)
        records = []
        for item in data.get("data", []):
            a = item.get("attributes", {})
            entity = a.get("entity", {})
            records.append(
                {
                    "lei": a.get("lei", item.get("id")),
                    "name": entity.get("legalName", {}).get("name"),
                    "jurisdiction": entity.get("jurisdiction"),
                    "status": entity.get("status"),
                    "registration_status": a.get("registration", {}).get("status"),
                    "source": "https://api.gleif.org/api/v1/lei-records/" + item["id"],
                }
            )
        return {
            "records": records,
            "source": url,
            "note": "Só entidades com LEI. Nomes semelhantes exigem confirmação; ausência não significa que a empresa não exista.",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        futures = {
            "company": workers.submit(guarded, wikidata),
            "business_registry": workers.submit(guarded, gleif),
        }
        results = {name: future.result() for name, future in futures.items()}
    report = {
        "version": 3,
        "target": query,
        "input": query,
        "type": "company",
        "mode": "company",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "summary": {
            "completed": sum(r["status"] == "ok" for r in results.values()),
            "total": 2,
            "findings": [],
        },
    }
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    report["graph"] = graph(report)
    return report


def guarded(fn, *args):
    started = time.monotonic()
    previous_sources = getattr(CONTEXT, "sources", None)
    CONTEXT.sources = []
    try:
        result = {"status": "ok", "data": fn(*args)}
    except Exception as exc:
        result = {"status": "error", "error": str(exc)[:300]}
    provenance = CONTEXT.sources
    CONTEXT.sources = previous_sources if previous_sources is not None else []
    return result | {
        "provenance": provenance,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize(results):
    findings = []
    website = results.get("website", {})
    if website.get("status") == "ok":
        data = website["data"]
        for name, present in data.get("security", {}).get("checks", {}).items():
            if not present:
                findings.append(
                    {
                        "level": "review",
                        "title": name + " não observado",
                        "source": "website",
                        "detail": "Verificar se esta configuração é adequada ao site. Não confirma uma vulnerabilidade.",
                    }
                )
        if data.get("status", 200) >= 400:
            findings.append(
                {
                    "level": "info",
                    "title": "A página respondeu HTTP " + str(data["status"]),
                    "source": "website",
                    "detail": data.get("url", ""),
                }
            )
    dns = results.get("dns", {})
    if dns.get("status") == "ok":
        records = dns["data"].get("records", {})
        for label, present in [
            (
                "SPF",
                any("v=spf1" in v["value"].lower() for v in records.get("TXT", [])),
            ),
            (
                "DMARC",
                any("v=dmarc1" in v["value"].lower() for v in records.get("DMARC", [])),
            ),
        ]:
            if not present:
                findings.append(
                    {
                        "level": "review",
                        "title": label + " não observado neste domínio",
                        "source": "dns",
                        "detail": "O domínio pode não enviar correio. DMARC pode ser herdado de um domínio organizacional.",
                    }
                )
    cti = results.get("threat_intelligence", {})
    if cti.get("status") == "ok" and cti["data"].get("matches"):
        matches = cti["data"]["matches"]
        findings.append(
            {
                "level": "review",
                "title": str(len(matches)) + " correspondência(s) em fontes CTI",
                "source": "threat_intelligence",
                "detail": "Consultar datas, fonte e indicador. A correspondência numa lista não confirma comprometimento do domínio; KEV descreve uma CVE, não uma vulnerabilidade verificada neste alvo.",
            }
        )
    tls = results.get("tls", {})
    if tls.get("status") == "ok" and tls["data"].get("valid_until"):
        try:
            days = int(
                (ssl.cert_time_to_seconds(tls["data"]["valid_until"]) - time.time())
                / 86400
            )
            if days < 30:
                findings.append(
                    {
                        "level": "review",
                        "title": "Certificado expira em " + str(days) + " dias",
                        "source": "tls",
                        "detail": "Confirmar o processo de renovação do certificado.",
                    }
                )
        except ValueError:
            pass
    return findings


def investigate(value, deep=False, expand=False, refresh=False, with_cti=False):
    started = time.monotonic()
    host, url, kind = target(value)
    tasks = {
        "network": (
            lambda: {
                "addresses": public_addresses(host),
                "source": "Resolução DNS do sistema",
            }
        )
    }
    if kind == "ip":
        tasks["ip"] = lambda: ip_info(host)
    else:
        tasks.update(
            dns=lambda: dns_info(host),
            website=lambda: site_info(url),
            tls=lambda: certificate(host),
        )
        tasks["ip"] = lambda: ip_info(public_addresses(host)[0])
    if deep:
        tasks.update(
            registration=lambda: registration(host, kind),
            reverse=lambda: reverse_dns(host),
        )
        if kind != "ip":
            tasks.update(
                transparency=lambda: transparency(host),
                archives=lambda: archives(host),
                discovery=lambda: discovery(url),
            )

    def execute(fn):
        CONTEXT.refresh = refresh
        return guarded(fn)

    futures = {name: POOL.submit(execute, fn) for name, fn in tasks.items()}
    results = {name: f.result() for name, f in futures.items()}
    if deep and expand and kind != "ip":
        results["subdomains"] = guarded(subdomains, host, results)
    if with_cti:
        addresses = results.get("network", {}).get("data", {}).get("addresses", [])
        results["threat_intelligence"] = guarded(
            cti_service().correlate, host, addresses, refresh
        )
    report = {
        "version": 3,
        "target": host,
        "input": value,
        "type": kind,
        "mode": "deep" if deep else "standard",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "summary": {
            "completed": sum(r["status"] == "ok" for r in results.values()),
            "total": len(results),
            "findings": summarize(results),
        },
        "results": results,
    }
    report["graph"] = graph(report)
    return report


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; frame-ancestors 'none'; base-uri 'none'"
                if self.path.startswith("/cti/")
                else "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            ),
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, data):
        self.send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def allowed_host(self):
        try:
            return (
                urllib.parse.urlsplit("http://" + self.headers.get("Host", "")).hostname
                in ("localhost", "127.0.0.1", "::1")
                or os.environ.get("ATLAS_ALLOW_REMOTE") == "1"
            )
        except ValueError:
            return False

    def do_GET(self):
        if not self.allowed_host():
            return self.json(403, {"error": "Acesso local apenas."})
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/health":
                return self.json(
                    200,
                    {"status": "ok", "app": "atlas", "version": 3, "build": APP_BUILD},
                )
            if path in ("/api/cti/feed", "/api/feed"):
                force = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(self.path).query
                ).get("force") == ["1"]
                return self.json(200, cti_service().feed(force))
            if path == "/cti":
                self.send_response(302)
                self.send_header("Location", "/cti/")
                self.end_headers()
                return
            if path == "/api/projects":
                return self.json(200, store().projects())
            if re.fullmatch(r"/api/projects/[a-f0-9]{32}", path):
                return self.json(200, store().project(path.rsplit("/", 1)[1]))
            if re.fullmatch(r"/api/reports/[a-f0-9]{32}", path):
                return self.json(200, store().report(path.rsplit("/", 1)[1]))
            if path == "/api/compare":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                old, new = store().report(q.get("before", [""])[0]), store().report(
                    q.get("after", [""])[0]
                )
                if old["project_id"] != new["project_id"]:
                    raise ValueError("Os relatórios devem pertencer ao mesmo projeto.")
                return self.json(200, compare(old, new))
            if re.fullmatch(r"/api/projects/[a-f0-9]{32}/export", path):
                project = store().project(path.split("/")[3])
                project["reports"] = [
                    store().report(r["id"]) for r in project["reports"]
                ]
                return self.json(200, project)
            files = {
                "/cti/": ("cti/index.html", "text/html"),
                "/cti/app.js": ("cti/app.js", "text/javascript"),
                "/cti/bridge.js": ("cti/bridge.js", "text/javascript"),
                "/cti/styles.css": ("cti/styles.css", "text/css"),
                "/cti/vendor/leaflet.js": ("cti/vendor/leaflet.js", "text/javascript"),
                "/cti/vendor/leaflet.css": ("cti/vendor/leaflet.css", "text/css"),
                "/cti/vendor/world.geojson": (
                    "cti/vendor/world.geojson",
                    "application/geo+json",
                ),
                "/": ("index.html", "text/html"),
                "/style.css": ("style.css", "text/css"),
                "/app.js": ("app.js", "text/javascript"),
                "/workspace.js": ("workspace.js", "text/javascript"),
            }
            if path not in files:
                return self.json(404, {"error": "Não encontrado."})
            name, mime = files[path]
            self.send(
                200, (ROOT / "static" / name).read_bytes(), mime + "; charset=utf-8"
            )
        except KeyError as exc:
            self.json(404, {"error": str(exc)})
        except ValueError as exc:
            self.json(400, {"error": str(exc)})
        except Exception:
            self.json(500, {"error": "Não foi possível ler os dados locais."})

    def do_POST(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in ("http://" + host, "https://" + host):
            return self.json(403, {"error": "Origem inválida."})
        # Local persistent data must not be exposed through DNS rebinding.
        if not self.allowed_host():
            return self.json(
                403,
                {
                    "error": "Acesso local apenas. Consulte a configuração de acesso remoto no README."
                },
            )
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if (
                not 1 <= size <= 8500000
                or self.headers.get("Content-Type", "").split(";")[0]
                != "application/json"
            ):
                raise ValueError("Pedido JSON inválido.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Pedido inválido.")
            path = self.path
            if path == "/api/projects":
                return self.json(201, store().create(data.get("name")))
            if path == "/api/projects/edit":
                return self.json(
                    200, store().edit(data.get("id"), data.get("notes", ""))
                )
            if path == "/api/projects/delete":
                store().delete(data.get("id"))
                return self.json(200, {"deleted": True})
            if path == "/api/reports/save":
                return self.json(
                    201, store().save_report(data.get("project_id"), data.get("report"))
                )
            if path == "/api/reports/annotate":
                return self.json(
                    200,
                    store().annotate(
                        data.get("id"), data.get("notes", ""), data.get("bookmarks", [])
                    ),
                )
            if path == "/api/monitors":
                value = data.get("target")
                if not isinstance(value, str):
                    raise ValueError("Alvo inválido.")
                target(value)
                mid = store().monitor(
                    data.get("project_id"),
                    value,
                    data.get("deep", True),
                    data.get("hours", 24),
                )
                return self.json(201, store().get_monitor(mid))
            if path == "/api/monitors/toggle":
                store().set_monitor(data.get("id"), data.get("enabled"))
                return self.json(200, {"updated": True})
            if path not in (
                "/api/investigate",
                "/api/company",
                "/api/monitors/run",
                "/api/cti/lookup",
            ):
                return self.json(404, {"error": "Não encontrado."})
            if not LIMIT.acquire(blocking=False):
                return self.json(
                    429,
                    {
                        "error": "Há quatro pesquisas em curso. Tente novamente dentro de instantes."
                    },
                )
            try:
                if path == "/api/monitors/run":
                    return self.json(200, run_monitor(data.get("id")))
                if path == "/api/cti/lookup":
                    return self.json(200, cti_report(data.get("indicator")))
                if path == "/api/company":
                    return self.json(200, company_search(data.get("query")))
                if not isinstance(data.get("target"), str):
                    raise ValueError("Indique um alvo válido.")
                if any(
                    type(data.get(key, False)) is not bool
                    for key in ("deep", "expand", "refresh", "cti")
                ):
                    raise ValueError("O modo de pesquisa não é válido.")
                result = investigate(
                    data["target"],
                    data.get("deep", False),
                    data.get("expand", False),
                    data.get("refresh", False),
                    data.get("cti", False),
                )
                return self.json(200, result)
            finally:
                LIMIT.release()
        except KeyError as exc:
            self.json(404, {"error": str(exc)})
        except (ValueError, UnicodeError) as exc:
            self.json(400, {"error": str(exc)})
        except Exception:
            self.json(
                500,
                {
                    "error": "Não foi possível concluir a operação. Verifique o acesso à pasta de dados."
                },
            )

    def log_message(self, fmt, *args):
        # Do not log submitted targets or report contents.
        pass


MONITOR_LOCK = threading.Lock()


def run_monitor(mid):
    if not MONITOR_LOCK.acquire(blocking=False):
        raise ValueError("Já está a decorrer uma monitorização. Aguarde a conclusão.")
    try:
        monitor = store().get_monitor(mid)
        report = investigate(
            monitor["target"],
            bool(monitor["deep"]),
            bool(monitor["deep"]),
            refresh=True,
        )
        previous = store().previous(
            monitor["project_id"], report["target"], report["mode"]
        )
        if previous:
            report["comparison"] = compare(previous, report)
        saved = store().save_report(monitor["project_id"], report)
        failures = [
            name for name, r in report["results"].items() if r["status"] != "ok"
        ]
        store().finish_monitor(
            mid,
            saved["saved_id"],
            "Fontes indisponíveis: " + ", ".join(failures) if failures else None,
        )
        return saved
    except Exception as exc:
        store().finish_monitor(mid, None, str(exc)[:300])
        raise
    finally:
        MONITOR_LOCK.release()


def monitor_loop(stop):
    while not stop.wait(30):
        try:
            for monitor in store().due():
                if stop.is_set():
                    return
                if not LIMIT.acquire(blocking=False):
                    break
                try:
                    run_monitor(monitor["id"])
                except Exception:
                    pass
                finally:
                    LIMIT.release()
        except Exception:
            pass


def serve(host=None, port=None, ready=None):
    host = host or os.environ.get("ATLAS_HOST", "127.0.0.1")
    port = port if port is not None else int(os.environ.get("PORT", "8000"))
    database = store()
    with InstanceLock(database.path.parent):
        server = ThreadingHTTPServer((host, port), Handler)
        state_path = database.path.parent / "server.json"
        state_path.write_text(
            json.dumps({"port": server.server_port}), encoding="utf-8"
        )
        stop = threading.Event()
        worker = threading.Thread(target=monitor_loop, args=(stop,), daemon=True)
        worker.start()
        if ready:
            ready(server.server_port)
        print(
            f"Atlas 03 iniciado na porta {server.server_port}. Ctrl+C para terminar.",
            flush=True,
        )
        try:
            server.serve_forever()
        finally:
            stop.set()
            server.server_close()
            state_path.unlink(missing_ok=True)


if __name__ == "__main__":
    serve()
