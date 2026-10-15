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

ROOT = Path(__file__).parent
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8)
LIMIT = threading.BoundedSemaphore(4)


def target(value):
    value = value.strip()
    if not value or len(value) > 2048:
        raise ValueError('Introduza um domínio, URL ou endereço IP válido.')
    try:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise ValueError('Apenas endereços IP públicos são permitidos.')
        return str(ip), None, 'ip'
    except ValueError as exc:
        if 'Apenas' in str(exc):
            raise
    parsed = urllib.parse.urlsplit(value if '://' in value else 'https://' + value)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise ValueError('Use HTTP ou HTTPS, sem credenciais no URL.')
    if parsed.port not in (None, 80, 443):
        raise ValueError('Apenas as portas 80 e 443 são permitidas.')
    host = (parsed.hostname or '').rstrip('.').encode('idna').decode('ascii').lower()
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError('Apenas endereços IP públicos são permitidos.')
    except ValueError as exc:
        if 'Apenas' in str(exc):
            raise
        if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', host):
            raise ValueError('O domínio não é válido.')
    authority = '[' + host + ']' if ':' in host else host
    return host, urllib.parse.urlunsplit((parsed.scheme, authority, parsed.path or '/', parsed.query, '')), 'site'


def public_addresses(host):
    addresses = sorted({r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('O destino resolve para uma rede privada ou reservada.')
    return addresses


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, maximum=524288):
    req = urllib.request.Request(url, headers={'User-Agent': 'PublicOSINT/1.0', 'Accept': 'application/json,text/html;q=0.9,*/*;q=0.5'})
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=8)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(maximum + 1)
        return response.status, dict(response.headers.items()), body[:maximum], len(body) > maximum


def dns_info(host):
    records = {}
    for kind in ('A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'CAA', 'SOA', 'DMARC'):
        url = 'https://dns.google/resolve?' + urllib.parse.urlencode({'name': '_dmarc.' + host if kind == 'DMARC' else host, 'type': 'TXT' if kind == 'DMARC' else kind})
        status, _, body, _ = fetch(url)
        if status != 200:
            raise RuntimeError('Serviço DNS respondeu HTTP ' + str(status))
        result = json.loads(body)
        if result.get('Status') not in (0, 3):
            raise RuntimeError('Consulta DNS falhou: ' + str(result.get('Status')))
        expected_type = {'A': 1, 'AAAA': 28, 'CNAME': 5, 'MX': 15, 'NS': 2, 'TXT': 16, 'CAA': 257, 'SOA': 6, 'DMARC': 16}[kind]
        records[kind] = [{'value': a['data'], 'ttl': a['TTL']} for a in result.get('Answer', []) if a.get('type') == expected_type]
    return {'records': records, 'source': 'https://dns.google/'}


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links, self.title, self.in_title = base, set(), '', False
        self.metadata, self.scripts = {}, set()
    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
        attributes = dict(attrs)
        if tag == 'meta':
            name = (attributes.get('name') or attributes.get('property') or '').lower()
            if name in ('description', 'generator', 'robots', 'og:title', 'og:description', 'og:site_name'):
                self.metadata[name] = (attributes.get('content') or '')[:1000]
        if tag == 'script' and attributes.get('src') and len(self.scripts) < 40:
            self.scripts.add(urllib.parse.urljoin(self.base, attributes['src']))
        if tag == 'a':
            href = dict(attrs).get('href', '')
            url = urllib.parse.urljoin(self.base, href)
            if urllib.parse.urlsplit(url).scheme in ('http', 'https') and len(self.links) < 100:
                self.links.add(url)
    def handle_endtag(self, tag):
        if tag == 'title':
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
            raise ValueError('Redirecionamento para fora do site ignorado.')
        addresses = public_addresses(host)
        parsed = urllib.parse.urlsplit(url)
        port = 443 if parsed.scheme == 'https' else 80
        connection = http.client.HTTPConnection(addresses[0], port, timeout=8)
        connection.connect()
        try:
            if port == 443:
                connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=host)
            connection.request('GET', urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, '')), headers={'Host': parsed.netloc, 'User-Agent': 'PublicOSINT/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            headers = dict(response.getheaders())
            location = response.getheader('Location')
            if response.status in (301, 302, 303, 307, 308) and location:
                redirects.append({'url': url, 'status': response.status})
                url = urllib.parse.urljoin(url, location)
                continue
            body = response.read(524289)
            parser = Links(url)
            if 'html' in response.getheader('Content-Type', ''):
                parser.feed(body[:524288].decode('utf-8', errors='replace'))
            # Cookies can contain session identifiers; omit them from reports.
            headers = {k: v for k, v in headers.items() if k.lower() != 'set-cookie'}
            return {'url': url, 'status': response.status, 'headers': headers, 'title': parser.title.strip(), 'links': sorted(parser.links), 'metadata': parser.metadata, 'scripts': sorted(parser.scripts), 'redirects': redirects, 'security': header_analysis(headers, url), 'technologies': technologies(headers, parser), **({'text': body[:524288].decode('utf-8', errors='replace')} if include_text else {}), 'truncated': len(body) > 524288, 'source': url}
        finally:
            connection.close()
    raise ValueError('Demasiados redirecionamentos.')


def certificate(host):
    address = public_addresses(host)[0]
    with socket.create_connection((address, 443), timeout=8) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as conn:
            cert = conn.getpeercert()
            return {'subject': dict(x[0] for x in cert.get('subject', [])), 'issuer': dict(x[0] for x in cert.get('issuer', [])), 'valid_from': cert.get('notBefore'), 'valid_until': cert.get('notAfter'), 'names': [v for k, v in cert.get('subjectAltName', []) if k == 'DNS'], 'protocol': conn.version(), 'source': host + ':443'}


def ip_info(ip):
    status, _, body, _ = fetch('https://ipwho.is/' + urllib.parse.quote(ip, safe=':'))
    if status != 200:
        raise RuntimeError('Serviço IP respondeu HTTP ' + str(status))
    data = json.loads(body)
    if not data.get('success'):
        raise RuntimeError(data.get('message', 'Consulta IP indisponível.'))
    return {k: data.get(k) for k in ('ip', 'type', 'country', 'region', 'city', 'latitude', 'longitude', 'connection', 'timezone')} | {'source': 'https://ipwho.is/' + ip, 'note': 'Localização aproximada da rede; não identifica uma pessoa ou morada.'}


def header_analysis(headers, url):
    normalized = {k.lower(): v for k, v in headers.items()}
    checks = {
        'HTTPS': urllib.parse.urlsplit(url).scheme == 'https',
        'Strict-Transport-Security': 'strict-transport-security' in normalized,
        'Content-Security-Policy': 'content-security-policy' in normalized,
        'X-Content-Type-Options': normalized.get('x-content-type-options', '').lower() == 'nosniff',
        'Proteção contra framing': ('x-frame-options' in normalized or 'frame-ancestors' in normalized.get('content-security-policy', '').lower()),
        'Referrer-Policy': 'referrer-policy' in normalized,
        'Permissions-Policy': 'permissions-policy' in normalized,
    }
    return {'checks': checks, 'present': sum(checks.values()), 'total': len(checks),
            'note': 'Indicadores de configuração, não uma auditoria de vulnerabilidades. Presença não garante uma política eficaz.'}


def technologies(headers, parser):
    evidence = []
    for key, value in headers.items():
        if key.lower() in ('server', 'x-powered-by'):
            evidence.append({'technology': value[:200], 'evidence': 'Cabeçalho ' + key})
    if parser.metadata.get('generator'):
        evidence.append({'technology': parser.metadata['generator'], 'evidence': 'Meta generator'})
    patterns = {'WordPress': '/wp-content/', 'Next.js': '/_next/', 'Drupal': '/sites/default/', 'Shopify': 'cdn.shopify.com'}
    for technology, marker in patterns.items():
        if any(marker in script for script in parser.scripts):
            evidence.append({'technology': technology, 'evidence': 'Referência pública a script: ' + marker})
    return evidence


def json_source(url, maximum=2097152):
    status, _, body, truncated = fetch(url, maximum)
    if status != 200:
        raise RuntimeError('Fonte respondeu HTTP ' + str(status) + ' (pode existir um limite de utilização).')
    if truncated:
        raise RuntimeError('A resposta excede o limite de leitura; os dados não foram tratados como completos.')
    return json.loads(body)


def registration(host, kind):
    # IANA bootstrap selects an authoritative RDAP service; user input never controls the endpoint host.
    ip = ipaddress.ip_address(host) if kind == 'ip' else None
    family = ('ipv4' if ip.version == 4 else 'ipv6') if ip else 'dns'
    bootstrap = json_source('https://data.iana.org/rdap/' + family + '.json')
    endpoint = None
    for keys, urls in bootstrap['services']:
        match = any(ip in ipaddress.ip_network(key) for key in keys) if ip else host.split('.')[-1] in keys
        if match:
            endpoint = next((u for u in urls if u.startswith('https://')), None)
            break
    if not endpoint:
        raise RuntimeError('Não existe um serviço RDAP HTTPS no registo IANA para este alvo.')
    query = endpoint.rstrip('/') + ('/ip/' if ip else '/domain/') + urllib.parse.quote(host, safe=':')
    data = json_source(query)
    # Domain services sometimes require the registrable parent domain. Do not guess public suffixes.
    nameservers = [n.get('ldhName', '') for n in data.get('nameservers', [])]
    events = [{'event': e.get('eventAction'), 'date': e.get('eventDate')} for e in data.get('events', [])]
    entities = []
    for entity in data.get('entities', []):
        # Keep organization / registrar names, excluding personal contact details.
        if any(role in entity.get('roles', []) for role in ('registrar', 'registrant')):
            names = [v[3] for v in entity.get('vcardArray', [None, []])[1] if v[0] == 'org']
            if 'registrar' in entity.get('roles', []):
                names += [v[3] for v in entity.get('vcardArray', [None, []])[1] if v[0] == 'fn']
            entities.append({'roles': entity.get('roles', []), 'organizations': names, 'handle': entity.get('handle')})
    return {'name': data.get('ldhName', data.get('name')), 'handle': data.get('handle'),
            'status': data.get('status', []), 'events': events, 'nameservers': nameservers,
            'entities': entities, 'start_address': data.get('startAddress'), 'end_address': data.get('endAddress'),
            'country': data.get('country'), 'source': query,
            'note': 'Dados do registo público. Alguns registos ocultam campos; subdomínios podem não ter um registo próprio.'}


def transparency(host):
    query = 'https://crt.sh/?' + urllib.parse.urlencode({'q': '%.' + host, 'output': 'json'})
    data = json_source(query, 4194304)
    names = set()
    for entry in data:
        for name in entry.get('name_value', '').lower().splitlines():
            name = name.removeprefix('*.').rstrip('.')
            if name == host or name.endswith('.' + host):
                if len(name) <= 253:
                    names.add(name)
    return {'domains': sorted(names)[:200], 'total_discovered': len(names), 'shown_limit': 200,
            'certificate_entries': len(data), 'source': query,
            'note': 'Nomes observados em certificados públicos; não prova que estejam ativos nem que pertençam atualmente ao mesmo titular.'}


def archives(host):
    query = 'https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode({
        'url': host + '/*', 'output': 'json', 'filter': 'statuscode:200',
        'collapse': 'urlkey', 'limit': '40', 'fl': 'timestamp,original,mimetype'})
    data = json_source(query)
    rows = data[1:] if data else []
    return {'snapshots': [{'timestamp': row[0], 'url': row[1], 'mime': row[2],
                          'archive': 'https://web.archive.org/web/' + row[0] + '/' + row[1]} for row in rows],
            'limit': 40, 'source': query,
            'note': 'Amostra de URLs históricas, não um inventário completo nem uma lista necessariamente recente.'}


def reverse_dns(host):
    addresses = [host] if is_ip(host) else public_addresses(host)
    records = []
    for address in addresses[:4]:
        try:
            name, _, _ = socket.gethostbyaddr(address)
            records.append({'ip': address, 'hostname': name})
        except (socket.herror, socket.gaierror):
            records.append({'ip': address, 'hostname': None})
    return {'records': records, 'source': 'DNS reverso do sistema', 'note': 'Até quatro IPs. Um nome PTR não confirma a propriedade do endereço.'}


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def discovery(url):
    parsed = urllib.parse.urlsplit(url)
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '/', '', ''))
    documents = {}
    for path in ('robots.txt', 'sitemap.xml', '.well-known/security.txt'):
        result = guarded(site_info, urllib.parse.urljoin(origin, path), True, parsed.netloc)
        if result['status'] == 'ok':
            data = result['data']
            documents[path] = {'status': data['status'], 'url': data['url'],
                               'excerpt': data.get('text', '')[:12000], 'truncated': len(data.get('text', '')) > 12000 or data['truncated']}
        else:
            documents[path] = {'error': result['error']}
    if all('error' in document for document in documents.values()):
        raise RuntimeError('Os três documentos públicos ficaram inacessíveis: ' + next(iter(documents.values()))['error'])
    return {'documents': documents, 'source': origin,
            'note': 'Apenas três caminhos públicos conhecidos. Regras do robots.txt não são percorridas e nenhum caminho descoberto é visitado.'}


def guarded(fn, *args):
    started = time.monotonic()
    try:
        result = {'status': 'ok', 'data': fn(*args)}
    except Exception as exc:
        result = {'status': 'error', 'error': str(exc)[:300]}
    return result | {'duration_ms': round((time.monotonic() - started) * 1000),
                     'checked_at': datetime.now(timezone.utc).isoformat()}


def summarize(results):
    findings = []
    website = results.get('website', {})
    if website.get('status') == 'ok':
        data = website['data']
        for name, present in data.get('security', {}).get('checks', {}).items():
            if not present:
                findings.append({'level': 'review', 'title': name + ' não observado', 'source': 'website',
                                 'detail': 'Verificar se esta configuração é adequada ao site. Não confirma uma vulnerabilidade.'})
        if data.get('status', 200) >= 400:
            findings.append({'level': 'info', 'title': 'A página respondeu HTTP ' + str(data['status']), 'source': 'website', 'detail': data.get('url', '')})
    dns = results.get('dns', {})
    if dns.get('status') == 'ok':
        records = dns['data'].get('records', {})
        for label, present in [('SPF', any('v=spf1' in v['value'].lower() for v in records.get('TXT', []))),
                               ('DMARC', any('v=dmarc1' in v['value'].lower() for v in records.get('DMARC', [])))]:
            if not present:
                findings.append({'level': 'review', 'title': label + ' não observado neste domínio', 'source': 'dns',
                                 'detail': 'O domínio pode não enviar correio. DMARC pode ser herdado de um domínio organizacional.'})
    tls = results.get('tls', {})
    if tls.get('status') == 'ok' and tls['data'].get('valid_until'):
        try:
            days = int((ssl.cert_time_to_seconds(tls['data']['valid_until']) - time.time()) / 86400)
            if days < 30:
                findings.append({'level': 'review', 'title': 'Certificado expira em ' + str(days) + ' dias', 'source': 'tls', 'detail': 'Confirmar o processo de renovação do certificado.'})
        except ValueError:
            pass
    return findings


def investigate(value, deep=False):
    started = time.monotonic()
    host, url, kind = target(value)
    tasks = {'network': (lambda: {'addresses': public_addresses(host), 'source': 'Resolução DNS do sistema'})}
    if kind == 'ip':
        tasks['ip'] = lambda: ip_info(host)
    else:
        tasks.update(dns=lambda: dns_info(host), website=lambda: site_info(url), tls=lambda: certificate(host))
        tasks['ip'] = lambda: ip_info(public_addresses(host)[0])
    if deep:
        tasks.update(registration=lambda: registration(host, kind), reverse=lambda: reverse_dns(host))
        if kind != 'ip':
            tasks.update(transparency=lambda: transparency(host), archives=lambda: archives(host), discovery=lambda: discovery(url))
    futures = {name: POOL.submit(guarded, fn) for name, fn in tasks.items()}
    results = {name: f.result() for name, f in futures.items()}
    return {'version': 2, 'target': host, 'input': value, 'type': kind, 'mode': 'deep' if deep else 'standard',
            'created_at': datetime.now(timezone.utc).isoformat(), 'duration_ms': round((time.monotonic() - started) * 1000),
            'summary': {'completed': sum(r['status'] == 'ok' for r in results.values()), 'total': len(results),
                        'findings': summarize(results)}, 'results': results}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        files = {'/': ('index.html', 'text/html'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
        if self.path == '/health':
            return self.send(200, b'{"status":"ok"}')
        if self.path not in files:
            return self.send(404, b'{"error":"Not found"}')
        name, mime = files[self.path]
        self.send(200, (ROOT / 'static' / name).read_bytes(), mime + '; charset=utf-8')
    def do_POST(self):
        if self.path != '/api/investigate':
            return self.send(404, b'{}')
        # JSON-only requests and same-origin browser requests prevent cross-site submissions.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', '') and origin != 'https://' + self.headers.get('Host', ''):
            return self.send(403, b'{}')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 4096 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Pedido JSON inválido.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or not isinstance(data.get('target'), str):
                raise ValueError('Indique um alvo válido.')
            if not isinstance(data.get('deep', False), bool):
                raise ValueError('O modo de pesquisa não é válido.')
            if not LIMIT.acquire(blocking=False):
                return self.send(429, b'{"error":"Tente novamente dentro de instantes."}')
            try:
                result = investigate(data['target'], data.get('deep', False))
            finally:
                LIMIT.release()
            self.send(200, json.dumps(result).encode())
        except (ValueError, UnicodeError) as exc:
            self.send(400, json.dumps({'error': str(exc)}).encode())
    def log_message(self, fmt, *args):
        # Do not log submitted targets or report contents.
        pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'Public OSINT listening on port {port}', flush=True)
    server.serve_forever()
