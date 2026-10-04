"""Read-only public facade. Never forward visitor paths, headers or request bodies."""
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent
PORT = 8780
CACHE = {}
LOCK = threading.Lock()
OPENER = build_opener(ProxyHandler({}))


def snapshot(port, actions_only=False):
    key = (port, actions_only)
    with LOCK:
        cached = CACHE.get(key)
        if cached and time.monotonic() - cached[0] < 5:
            return cached[1]
        with OPENER.open('http://127.0.0.1:%d/api/live' % port, timeout=8) as response:
            data = json.load(response)
        if actions_only:
            payload = json.dumps(data.get('action_alerts', {})).encode()
            CACHE[key] = (time.monotonic(), payload)
            return payload
        # Only the public viewer contract; exclude notifier status and diagnostics.
        public = {k: data[k] for k in ('dashboard', 'history', 'roster', 'latest_event',
                  'events_in_window', 'source_days_utc', 'scoring', 'action_alerts') if k in data}
        status = data.get('status', {})
        public['status'] = {k: status.get(k) for k in ('last_success', 'polling', 'village_name', 'poll_seconds')}
        public['status']['error'] = 'Source feed unavailable; showing last snapshot.' if status.get('error') else None
        payload = json.dumps(public).encode()
        CACHE[key] = (time.monotonic(), payload)
        return payload


def page(open_chat=False):
    text = (ROOT / 'index.html').read_text(encoding='utf-8')
    text = text.replace('http://127.0.0.1:8765', '/').replace('http://127.0.0.1:8766', '/open-chat/')
    text = text.replace('<a href="/discord">Configure Discord alerts</a>', 'Public read-only demo')
    text = text.replace('Discord: disabled', 'Experimental scores · human review only')
    text = text.replace("$('discordStatus').textContent=ds.error?'Discord: '+ds.error:ds.enabled?'Discord enabled · '+(ds.sent||0)+' alerts sent':'Discord: disabled';", "$('discordStatus').textContent='Experimental scores · human review only';")
    text = text.replace('your existing Heatbot scorer', 'public demo')
    text = text.replace('read-only local viewer', 'public read-only viewer')
    text = text.replace('Updates pause when this computer sleeps.', 'Updates pause when the host computer sleeps.')
    text = text.replace('The local collector is unavailable. Restart with START_HEATMAP.cmd.', 'The demo feed is temporarily unavailable.')
    if open_chat:
        text = text.replace("fetch('/api/live'", "fetch('/open-chat/api/live'")
    return text.encode()


class Handler(BaseHTTPRequestHandler):
    server_version = 'HeatbotDemo'
    sys_version = ''

    def log_message(self, *args):
        pass

    def do_GET(self):
        # Exact allowlist, including query strings: no generic proxy or filesystem serving.
        try:
            if self.path in ('/', '/index.html', '/open-chat', '/open-chat/'):
                body, mime = page(self.path.startswith('/open-chat')), 'text/html; charset=utf-8'
            elif self.path in ('/evidence.js', '/action_alerts.js'):
                body, mime = (ROOT / self.path[1:]).read_bytes(), 'text/javascript; charset=utf-8'
            elif self.path in ('/api/live', '/open-chat/api/live'):
                body, mime = snapshot(8766 if self.path.startswith('/open-chat') else 8765), 'application/json'
            elif self.path in ('/api/actions', '/open-chat/api/actions'):
                body, mime = snapshot(8766 if self.path.startswith('/open-chat') else 8765, True), 'application/json'
            elif self.path == '/robots.txt':
                body, mime = b'User-agent: *\nDisallow: /\n', 'text/plain'
            else:
                self.send_error(404)
                return
        except Exception:
            self.send_error(503, 'Demo feed temporarily unavailable')
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_error(405, 'Read-only demo')

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
