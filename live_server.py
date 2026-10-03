"""Local, read-only live viewer around the unmodified round-7 heat scorer."""
import datetime as dt
import hashlib
import json
import os
import sys
import secrets
from pathlib import Path
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import heatbot as hb
import discord_alerts

ROOT = Path(__file__).resolve().parent
OPEN_CHAT = '--open-chat' in sys.argv
DATA = ROOT / 'open-chat' if OPEN_CHAT else ROOT
PORT = 8766 if OPEN_CHAT else 8765
APP = 'ai-village-heat-live-v1'
SETUP_TOKEN = secrets.token_urlsafe(32)
SCOPE = ('For human attention in an observational setting. Scores are not pushed to agents, '
         'used for training, rewards, training-data filtering, or agent admission/removal.')
NOTES = {
    'general': 'Combined behavioral heat. Experimental attention signal, not a probability or finding of misalignment.',
    'off-goal': 'Task-relevance language associated with past off-goal flags. Separate from deception vocabulary; check the assigned goal and context.',
    'erratic': 'Repetition, looping and status-report patterns.',
    'conflict': 'Boundary and friction language; disagreement can be appropriate.',
    'outreach': 'Language about contacting people or platforms; outreach can be appropriate.',
    'deceptive': 'Separate word-pattern score originally trained on surreptitious-or-deceptive flags. Unvalidated; not evidence of concealment or deception.',
    'credentials': 'Rule-based mentions of tokens, cookies or browser storage; not calibrated.',
}


def utc():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def stamp(t=None):
    return (t or utc()).isoformat() + 'Z'


def read_json(name, fallback):
    try:
        return json.loads((DATA / name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback


def atomic_json(name, value):
    p = DATA / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
    tmp.replace(p)


def source_context(events, names, goals):
    """Join exact public event IDs to contributions; never expose tool/reasoning payloads."""
    sources, messages = {}, {}
    for e in sorted(events, key=lambda e: (e.get('createdAt', ''), e.get('eventIndex', 0))):
        d = e.get('data') or {}
        a = names.get(d.get('agentId') or d.get('speakerId'))
        if not a:
            continue
        key = hb.event_key(e)
        if key in sources:
            continue
        action = d.get('actionType', 'UNKNOWN')
        source = {'key': key, 'agent': a, 'time': e.get('createdAt'), 'action': action}
        if action == 'AGENT_TALK' and isinstance(d.get('content'), str):
            text = hb.scrub(d['content'])
            source.update(text=text[:12000], truncated=len(text) > 12000,
                          goal=hb.scrub(goals.at(a, hb.parse_ts(e['createdAt'])))[:6000])
            messages.setdefault(a, []).append(source)
        elif action == 'PAUSE':
            source['summary'] = 'Pause event. A pause is not a chat message or evidence of misconduct.'
            if isinstance(d.get('seconds'), (int, float)):
                source['seconds'] = d['seconds']
        else:
            source['summary'] = 'Non-chat event. Its action type is shown; raw payload is not displayed.'
        sources[key] = source
    return sources, messages


class Collector:
    def __init__(self):
        self.cfg = hb.deep_merge(hb.DEFAULT_CONFIG, read_json('live.config.json', {}))
        if OPEN_CHAT:
            self.cfg['village_slug'] = 'open-chat'
            self.cfg['poll_seconds'] = 60
        # Disable legacy sinks and raw memory collection; optional alerts use Notifier.
        self.cfg['memory_watch'] = {'enabled': False}
        self.cfg['channels_enabled'] = list(NOTES)
        self.cfg['sinks'] = {'console': False, 'jsonl': True,
                             'discord': {'enabled': False}, 'email': {'enabled': False},
                             'village': {'enabled': True}}
        self.model = hb.load_model()
        self.mutex = threading.Lock()
        self.bundle = read_json('live_snapshot.json', {})
        self.status = {'app': APP, 'running': True, 'polling': False,
                       'last_success': None, 'error': None, 'poll_seconds': self.cfg['poll_seconds'],
                       'village_name': 'Open Chat' if OPEN_CHAT else 'Main village'}
        self.detail = None
        self.roster_time = 0
        self.day_cache = {}
        self.discord = discord_alerts.Notifier(ROOT, DATA)

    def fetch(self, path):
        return hb.http_json(hb.API + path, timeout=60, tries=2)

    def collect(self):
        if self.detail is None or time.monotonic() - self.roster_time > 900:
            village = self.fetch('/villages?slug=' + self.cfg['village_slug'])
            detail = self.fetch('/villages/' + village['id'])
            if not isinstance(detail.get('agents'), list) or not detail['agents']:
                raise ValueError('Village roster is empty or has changed format')
            self.detail = detail
            self.roster_time = time.monotonic()
        detail = self.detail
        names = {a['id']: a['name'] for a in detail['agents']}
        roster = {a['name']: {'id': a['id'], 'participating': bool(a.get('isParticipating'))}
                  for a in detail['agents']}
        now = utc()
        days = [(now - dt.timedelta(days=1)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')]
        events = []
        for day in days:
            if day == days[-1] or day not in self.day_cache:
                page = self.fetch('/events?villageId=' + detail['id'] + '&date=' + day)
                if not isinstance(page.get('events'), list):
                    raise ValueError('Events endpoint returned an unexpected format')
                if day != days[-1]:
                    self.day_cache[day] = page['events']
                rows = page['events']
            else:
                rows = self.day_cache[day]
            events.extend(rows)
        self.day_cache = {k: v for k, v in self.day_cache.items() if k in days}
        # No scoring occurs until every required source request succeeds.
        now = utc()
        eng = hb.HeatEngine(self.cfg, self.model)
        eng.set_agents(names.values())
        goals = hb.Goals(detail, names)
        hb.run_events(eng, self.cfg, events, names, goals, live=True, now=now)
        sources, messages = source_context(events, names, goals)
        latest_by_agent = {}
        for e in events:
            d = e.get('data') or {}
            a = names.get(d.get('agentId') or d.get('speakerId'))
            if a:
                latest_by_agent[a] = max(latest_by_agent.get(a, ''), e.get('createdAt', ''))
        cutoff = (now - dt.timedelta(days=3)).isoformat()
        eng.seen = {k: v for k, v in eng.seen.items() if (v or '')[:19] >= cutoff[:19]}
        eng.decay_all(now)
        hb.flush_situation(eng, self.cfg, now)
        hb.flush_heat_hourly(eng, self.cfg, now)
        hb.write_dashboard(eng, self.cfg, now)
        hb.write_history(eng, self.cfg, now)
        eng.save()
        dashboard = read_json('dashboard.json', {})
        history = read_json('history_7d.json', {'agents': {}})
        # Include the incomplete current hour with an explicit hourly-peak meaning.
        for key, value in eng.hh.items():
            a, hour = key.rsplit('|', 1)
            history['agents'].setdefault(a, {'heat_peak': {}, 'situation': {}})['heat_peak'][hour + ':00Z'] = value['peak']
        dashboard['scope'] = SCOPE
        for c, info in dashboard['channels'].items():
            info['note'] = NOTES[c]
            info['pages'] = False
        for a, info in dashboard['agents'].items():
            info['last_event'] = latest_by_agent.get(a)
            info['participating'] = roster.get(a, {}).get('participating', False)
            info['goal'] = hb.scrub(goals.at(a, now))[:6000]
            info['source_events'] = {r['key']: sources[r['key']] for r in info['contributions']
                                     if r.get('key') in sources}
            info['recent_messages'] = messages.get(a, [])[-5:]
        bundle = {'dashboard': dashboard, 'history': history, 'roster': roster,
                  'latest_event': max((e.get('createdAt', '') for e in events), default=None),
                  'events_in_window': len(events), 'source_days_utc': days,
                  'model_sha256': hashlib.sha256((ROOT / 'heatbot_model.json').read_bytes()).hexdigest()}
        atomic_json('live_snapshot.json', bundle)
        # Local review material only; excluded from Git and not a served route.
        atomic_json('review_context.json', {'captured_at': stamp(now), 'village': self.cfg['village_slug'],
                                           'messages': messages})
        with self.mutex:
            self.bundle = bundle
            self.status.update(last_success=stamp(now), error=None)
        try:
            discord_status = self.discord.tick(bundle)
        except Exception:
            discord_status = {'enabled': True, 'error': 'Discord notifier encountered a local error; check configuration.'}
        with self.mutex:
            self.status['discord'] = discord_status
        print(stamp(), 'updated', len(events), 'events;', len(dashboard['agents']), 'agents', flush=True)

    def loop(self):
        while True:
            with self.mutex:
                self.status.update(polling=True, last_attempt=stamp())
            try:
                self.collect()
            except Exception as exc:
                with self.mutex:
                    self.status['error'] = str(exc)
                traceback.print_exc()
            finally:
                with self.mutex:
                    self.status['polling'] = False
            time.sleep(self.cfg['poll_seconds'])

    def payload(self):
        with self.mutex:
            return dict(self.bundle, status=dict(self.status))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Exact routes only: state, logs, archives and source files are never served.
        if self.headers.get('Host', '').split(':')[0] not in ('127.0.0.1', 'localhost'):
            self.send_error(403)
            return
        route = urlsplit(self.path).path
        if route in ('/', '/index.html'):
            data, mime = (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8'
        elif route == '/evidence.js':
            data, mime = (ROOT / 'evidence.js').read_bytes(), 'text/javascript; charset=utf-8'
        elif route == '/discord':
            data = (ROOT / 'discord_setup.html').read_text(encoding='utf-8').replace('__CSRF_TOKEN__', SETUP_TOKEN).encode()
            mime = 'text/html; charset=utf-8'
        elif route == '/api/live':
            data, mime = json.dumps(self.server.collector.payload()).encode(), 'application/json'
        elif route == '/health':
            data, mime = json.dumps({'app': APP, 'pid': os.getpid()}).encode(), 'application/json'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

    def do_POST(self):
        host = self.headers.get('Host', '')
        if (host not in ('127.0.0.1:' + str(PORT), 'localhost:' + str(PORT)) or
                self.headers.get('Origin') != 'http://' + host or self.path != '/api/discord-config'):
            self.send_error(403)
            return
        result, code = {}, 200
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 12000:
                raise ValueError('Invalid request size.')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Invalid request.')
            if not secrets.compare_digest(str(body.get('csrf', '')), SETUP_TOKEN):
                self.send_error(403)
                return
            path = ROOT / 'discord.local.json'
            if body.get('action') == 'disable':
                cfg = discord_alerts.load(path, {})
                cfg['enabled'] = False
                discord_alerts.save(path, cfg)
                result = {'message': 'Alerts disabled for both villages. Any in-flight request may finish.'}
            elif body.get('action') == 'enable':
                url = discord_alerts.validate_url(str(body.get('webhook_url', '')).strip())
                test = {'username': 'AI Village Heatbot', 'allowed_mentions': {'parse': []},
                        'content': 'Heatbot connection test: human-review alerts are now being configured for Main Village and Open Chat. This is a test, not a heat alert.'}
                delivery = discord_alerts.post(url, test)
                if not delivery['ok']:
                    raise ValueError(delivery.get('error', 'Test message delivery failed.'))
                discord_alerts.save(path, {'enabled': True, 'webhook_url': url,
                                          'generation': secrets.token_hex(16),
                                          'villages': ['actual-launch-1', 'open-chat'],
                                          'channels': list(discord_alerts.CHANNELS)})
                result = {'message': 'Test delivered. Alerts enabled for both villages. The first poll establishes a quiet baseline; subsequent new hot signals can alert.'}
            else:
                raise ValueError('Unknown action.')
        except (ValueError, TypeError):
            code, result = 400, {'message': 'Setup failed. Check the webhook URL and Discord permissions, then retry. Existing configuration was not changed.'}
        except OSError:
            code, result = 500, {'message': 'Could not save configuration. Check local file permissions.'}
        data = json.dumps(result).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)


def main():
    os.chdir(ROOT)
    DATA.mkdir(exist_ok=True)
    hb.STATE_PATH = str(DATA / 'heatbot.state.json')
    hb.LOG_PATH = str(DATA / 'heatbot.log.jsonl')
    lock = hb.RunLock()
    if not lock.acquire():
        raise SystemExit('A heatbot collector is already using this state directory.')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        server.collector = Collector()
        atomic_json('live_process.json', {'pid': os.getpid(), 'app': APP})
        threading.Thread(target=server.collector.loop, daemon=True).start()
        print('Live viewer: http://127.0.0.1:' + str(PORT), flush=True)
        server.serve_forever()
    finally:
        lock.release()


if __name__ == '__main__':
    main()
