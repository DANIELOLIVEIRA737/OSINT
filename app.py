"""Public OSINT workbench. Python 3.12+, no third-party dependencies."""
import concurrent.futures
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
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
    for kind in ('A', 'AAAA', 'MX', 'NS', 'TXT', 'CAA'):
        url = 'https://dns.google/resolve?' + urllib.parse.urlencode({'name': host, 'type': kind})
        status, _, body, _ = fetch(url)
        if status != 200:
            raise RuntimeError('Serviço DNS respondeu HTTP ' + str(status))
        result = json.loads(body)
        if result.get('Status') not in (0, 3):
            raise RuntimeError('Consulta DNS falhou: ' + str(result.get('Status')))
        records[kind] = [{'value': a['data'], 'ttl': a['TTL']} for a in result.get('Answer', [])]
    return {'records': records, 'source': 'https://dns.google/'}


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links, self.title, self.in_title = base, set(), '', False
    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
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
            self.title += data[:500]


def site_info(url):
    # Connect to a validated literal IP, preserving the original Host and TLS SNI.
    # This prevents DNS rebinding and never sends a supplied URL to an outbound proxy.
    import http.client
    for _ in range(4):
        host, url, _ = target(url)
        addresses = public_addresses(host)
        parsed = urllib.parse.urlsplit(url)
        port = 443 if parsed.scheme == 'https' else 80
        connection = http.client.HTTPConnection(addresses[0], port, timeout=8)
        connection.connect()
        if port == 443:
            connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=host)
        try:
            connection.request('GET', urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, '')), headers={'Host': parsed.netloc, 'User-Agent': 'PublicOSINT/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            headers = dict(response.getheaders())
            location = response.getheader('Location')
            if response.status in (301, 302, 303, 307, 308) and location:
                url = urllib.parse.urljoin(url, location)
                continue
            body = response.read(524289)
            parser = Links(url)
            if 'html' in response.getheader('Content-Type', ''):
                parser.feed(body[:524288].decode('utf-8', errors='replace'))
            # Cookies can contain session identifiers; omit them from reports.
            headers = {k: v for k, v in headers.items() if k.lower() != 'set-cookie'}
            return {'url': url, 'status': response.status, 'headers': headers, 'title': parser.title.strip(), 'links': sorted(parser.links), 'truncated': len(body) > 524288, 'source': url}
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


def guarded(fn, *args):
    try:
        return {'status': 'ok', 'data': fn(*args)}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)[:300]}


def investigate(value):
    host, url, kind = target(value)
    tasks = {'network': (lambda: {'addresses': public_addresses(host), 'source': 'Resolução DNS do sistema'})}
    if kind == 'ip':
        tasks['ip'] = lambda: ip_info(host)
    else:
        tasks.update(dns=lambda: dns_info(host), website=lambda: site_info(url), tls=lambda: certificate(host))
        def network_ip():
            return ip_info(public_addresses(host)[0])
        tasks['ip'] = network_ip
    futures = {name: POOL.submit(guarded, fn) for name, fn in tasks.items()}
    return {'target': host, 'type': kind, 'created_at': datetime.now(timezone.utc).isoformat(), 'results': {name: f.result() for name, f in futures.items()}}


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
            if not LIMIT.acquire(blocking=False):
                return self.send(429, b'{"error":"Tente novamente dentro de instantes."}')
            try:
                result = investigate(data['target'])
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
