import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import heatbot as hb
import live_server as live


class CollectorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        for obj, key, value in [(live, 'DATA', self.folder),
                                (hb, 'STATE_PATH', str(self.folder / 'heatbot.state.json')),
                                (hb, 'LOG_PATH', str(self.folder / 'heatbot.log.jsonl'))]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.now = dt.datetime(2026, 10, 2, 17, 0)
        p = patch.object(live, 'utc', return_value=self.now)
        p.start()
        self.addCleanup(p.stop)
        self.collector = live.Collector()
        self.collector.discord.config_path = self.folder / 'discord.local.json'

    def source(self, path):
        if path.startswith('/villages?'):
            return {'id': 'test-village'}
        if path.startswith('/villages/'):
            return {'id': 'test-village', 'agents': [{'id': 'a', 'name': 'Agent A', 'isParticipating': True}]}
        return {'events': [{'id': 'event-1', 'eventIndex': 1,
                            'createdAt': '2026-10-02T16:59:00.000Z',
                            'data': {'agentId': 'a', 'actionType': 'AGENT_TALK',
                                     'content': 'Status update: still monitoring compliance and coordination.'}}]}

    def test_failed_fetch_preserves_last_snapshot_and_does_not_score(self):
        self.collector.bundle = {'sentinel': 'old'}
        with patch.object(self.collector, 'fetch', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                self.collector.collect()
        self.assertEqual(self.collector.bundle, {'sentinel': 'old'})
        self.assertFalse((self.folder / 'heatbot.state.json').exists())

    def test_restart_does_not_double_count_events_and_keeps_history(self):
        with patch.object(self.collector, 'fetch', side_effect=self.source):
            self.collector.collect()
        first = self.collector.bundle['dashboard']['agents']['Agent A']['heat']
        second = live.Collector()
        with patch.object(second, 'fetch', side_effect=self.source):
            second.collect()
        self.assertEqual(first, second.bundle['dashboard']['agents']['Agent A']['heat'])
        self.assertTrue(second.bundle['history']['agents']['Agent A']['heat_peak'])
        self.assertEqual(len(json.loads((self.folder / 'heatbot.state.json').read_text())['seen']), 1)

    def test_observation_only_defaults(self):
        cfg = self.collector.cfg
        self.assertFalse(cfg['memory_watch']['enabled'])
        self.assertFalse(cfg['sinks']['discord']['enabled'])
        self.assertFalse(cfg['sinks']['email']['enabled'])
        self.assertNotIn('memory', cfg['channels_enabled'])

    def test_unexpected_event_shape_aborts_before_state_write(self):
        def bad(path):
            return {} if path.startswith('/events') else self.source(path)
        with patch.object(self.collector, 'fetch', side_effect=bad):
            with self.assertRaises(ValueError):
                self.collector.collect()
        self.assertFalse((self.folder / 'heatbot.state.json').exists())


class Routes(unittest.TestCase):
    def handler(self, path, host='127.0.0.1:8765'):
        h = object.__new__(live.Handler)
        h.path, h.headers, h.wfile = path, {'Host': host}, io.BytesIO()
        h.code = None
        h.send_error = lambda code: setattr(h, 'code', code)
        h.send_response = lambda code: setattr(h, 'code', code)
        h.sent_headers = {}
        h.send_header = lambda k, v: h.sent_headers.__setitem__(k, v)
        h.end_headers = lambda: None
        return h

    def test_private_files_and_traversal_not_served(self):
        for p in ['/heatbot.state.json', '/live_snapshot.json', '/../heatbot_model.json', '/.git/config', '/discord.local.json', '/discord.state.json']:
            h = self.handler(p)
            h.do_GET()
            self.assertEqual(h.code, 404)

    def test_foreign_host_rejected(self):
        h = self.handler('/', 'other.example:8765')
        h.do_GET()
        self.assertEqual(h.code, 403)

    def test_index_served(self):
        h = self.handler('/')
        h.do_GET()
        self.assertEqual(h.code, 200)
        self.assertIn(b'Live behavioral heat', h.wfile.getvalue())

    def test_scripts_served_and_csp_forbids_inline_scripts(self):
        for p in ['/app.js', '/evidence.js', '/discord_setup.js']:
            h = self.handler(p)
            h.do_GET()
            self.assertEqual(h.code, 200)
            self.assertTrue(h.sent_headers['Content-Type'].startswith('text/javascript'))
        csp = h.sent_headers['Content-Security-Policy']
        self.assertIn("script-src 'self';", csp)
        for p in ['/', '/discord']:
            h = self.handler(p)
            h.do_GET()
            page = h.wfile.getvalue().decode()
            self.assertNotRegex(page, r'<script>|<script(?![^>]*\ssrc=)[^>]*>')
        self.assertIn('<meta name="csrf" content="%s">' % live.SETUP_TOKEN, page)

    def test_discord_setup_unavailable_through_tunnel(self):
        for header in live.PROXY_HEADERS:
            h = self.handler('/discord')
            h.headers[header] = '203.0.113.9'
            h.do_GET()
            self.assertEqual(h.code, 404)
            self.assertNotIn(live.SETUP_TOKEN.encode(), h.wfile.getvalue())
            # Host and Origin forged to look local, with a valid token: still refused.
            p = self.post_handler({'csrf': live.SETUP_TOKEN, 'action': 'disable'})
            p.headers[header] = '203.0.113.9'
            with patch.object(live.discord_alerts, 'save') as save:
                p.do_POST()
                self.assertEqual(p.code, 403)
                save.assert_not_called()
        h = self.handler('/')
        h.headers['Cf-Connecting-IP'] = '203.0.113.9'
        h.do_GET()
        self.assertEqual(h.code, 200)

    def post_handler(self, body, origin='http://127.0.0.1:8765'):
        h = self.handler('/api/discord-config')
        raw = json.dumps(body).encode()
        h.headers.update({'Origin': origin, 'Content-Length': str(len(raw))})
        h.rfile = io.BytesIO(raw)
        return h

    def test_setup_rejects_foreign_origin_and_missing_token(self):
        for body, origin in [({'csrf': live.SETUP_TOKEN}, 'https://example.com'), ({}, 'http://127.0.0.1:8765')]:
            h = self.post_handler(body, origin)
            with patch.object(live.discord_alerts, 'post') as send:
                h.do_POST()
                self.assertEqual(h.code, 403)
                send.assert_not_called()

    def test_setup_only_enables_after_success_and_never_echoes_secret(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(live, 'ROOT', Path(folder)):
            path = Path(folder) / 'discord.local.json'
            body = {'csrf': live.SETUP_TOKEN, 'action': 'enable', 'webhook_url': 'https://discord.com/api/webhooks/123/test-secret'}
            with patch.object(live.discord_alerts, 'post', return_value={'ok': False}):
                h = self.post_handler(body)
                h.do_POST()
                self.assertEqual(h.code, 400)
                self.assertFalse(path.exists())
            with patch.object(live.discord_alerts, 'post', return_value={'ok': True}):
                h = self.post_handler(body)
                h.do_POST()
                self.assertEqual(h.code, 200)
                self.assertTrue(json.loads(path.read_text())['enabled'])
                self.assertNotIn(b'test-secret', h.wfile.getvalue())
            h = self.post_handler({'csrf': live.SETUP_TOKEN, 'action': 'disable'})
            h.do_POST()
            self.assertFalse(json.loads(path.read_text())['enabled'])

    def test_setup_rejects_non_discord_url_without_delivery(self):
        h = self.post_handler({'csrf': live.SETUP_TOKEN, 'action': 'enable', 'webhook_url': 'https://example.com/secret'})
        with patch.object(live.discord_alerts, 'post') as send:
            h.do_POST()
            self.assertEqual(h.code, 400)
            send.assert_not_called()


class LogTrimTests(unittest.TestCase):
    def test_old_rows_dropped_recent_and_unparseable_kept(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(live, 'DATA', Path(folder)):
            now = dt.datetime(2026, 10, 2, 17, 0)
            rows = {'heatbot.log.jsonl': ('ts', '2026-08-01T10:00:00', '2026-09-30T10:00:00'),
                    'situation.jsonl': ('hour', '2026-08-01T10:00Z', '2026-09-30T10:00Z'),
                    'heat_hourly.jsonl': ('hour', '2026-08-01T10:00Z', '2026-09-30T10:00Z')}
            for name, (field, old, new) in rows.items():
                (Path(folder) / name).write_text(
                    json.dumps({field: old}) + '\n' + 'not json\n' + json.dumps({field: new}) + '\n', encoding='utf-8')
            live.trim_logs(now)
            for name, (field, old, new) in rows.items():
                text = (Path(folder) / name).read_text(encoding='utf-8')
                self.assertNotIn(old, text)
                self.assertIn(new, text)
                self.assertIn('not json', text)


class EvidenceTests(unittest.TestCase):
    def test_exact_join_dedup_and_only_public_chat(self):
        events = [
            {'id': 'chat', 'createdAt': '2026-10-02T12:00:00Z', 'data': {'agentId': 'a', 'actionType': 'AGENT_TALK', 'content': '<script>bad()</script>', 'reasoning': 'PRIVATE'}},
            {'id': 'pause', 'createdAt': '2026-10-02T12:01:00Z', 'data': {'agentId': 'a', 'actionType': 'PAUSE', 'seconds': 60, 'content': 'NOT CHAT'}},
        ]
        sources, messages = live.source_context(events + events, {'a': 'A'}, hb.Goals({}, {'a': 'A'}))
        self.assertEqual(len(sources), 2)
        self.assertEqual(len(messages['A']), 1)
        self.assertEqual(sources['chat']['text'], '<script>bad()</script>')
        self.assertNotIn('text', sources['pause'])
        self.assertNotIn('PRIVATE', json.dumps(sources))
        self.assertNotIn('NOT CHAT', json.dumps(sources))

    def test_excerpt_truncation_and_scrubbing_are_explicit(self):
        content = 'https://example.com/private?token=123 ' + ('word ' * 3000)
        e = {'id': 'x', 'createdAt': '2026-10-02T12:00:00Z', 'data': {'agentId': 'a', 'actionType': 'AGENT_TALK', 'content': content}}
        sources, _ = live.source_context([e], {'a': 'A'}, hb.Goals({}, {'a': 'A'}))
        self.assertTrue(sources['x']['truncated'])
        self.assertEqual(len(sources['x']['text']), 12000)
        self.assertNotIn('token=123', sources['x']['text'])


if __name__ == '__main__':
    unittest.main()
