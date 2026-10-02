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
        h.send_header = lambda *args: None
        h.end_headers = lambda: None
        return h

    def test_private_files_and_traversal_not_served(self):
        for p in ['/heatbot.state.json', '/live_snapshot.json', '/../heatbot_model.json', '/.git/config']:
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
