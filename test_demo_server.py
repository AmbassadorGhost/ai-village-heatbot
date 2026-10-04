import io
import json
import unittest
from unittest.mock import patch
import demo_server as demo


class DemoTests(unittest.TestCase):
    def handler(self, path):
        h = object.__new__(demo.Handler)
        h.path, h.wfile = path, io.BytesIO()
        h.send_error = lambda code, *args: setattr(h, 'code', code)
        h.send_response = lambda code: setattr(h, 'code', code)
        h.send_header = lambda *args: None
        h.end_headers = lambda: None
        return h

    def test_private_routes_and_encoded_variants_blocked(self):
        for path in ['/discord', '/api/discord-config', '/discord.local.json', '/health',
                     '/heatbot.state.json', '/.git/config', '/../index.html', '/%64iscord',
                     '/api/live?url=http://example.com', '/open-chat/discord',
                     '/history', '/api/history', '/memories', '/api/memories', '/memory-history.sqlite3']:
            h = self.handler(path)
            h.do_GET()
            self.assertEqual(h.code, 404, path)

    def test_mutations_blocked(self):
        for method in ['do_POST', 'do_PUT', 'do_PATCH', 'do_DELETE']:
            h = self.handler('/api/discord-config')
            getattr(h, method)()
            self.assertEqual(h.code, 405)

    def test_public_pages_have_relative_routes_and_no_setup(self):
        for village in (False, True):
            page = demo.page(village).decode()
            self.assertNotIn('127.0.0.1', page)
            self.assertNotIn('href="/discord"', page)
            self.assertNotIn('href="/history"', page)
            self.assertNotIn('START_HEATMAP', page)
            self.assertIn("fetch('/open-chat/api/live'" if village else "fetch('/api/live'", page)

    def test_snapshot_excludes_private_status_and_caches(self):
        demo.CACHE.clear()
        upstream = {'dashboard': {}, 'history': {}, 'secret': 'PRIVATE',
                    'status': {'last_success': 'now', 'discord': {'webhook_url': 'PRIVATE'},
                               'error': 'PRIVATE path'}}
        with patch.object(demo.OPENER, 'open', return_value=io.BytesIO(json.dumps(upstream).encode())) as fetch:
            first = demo.snapshot(8765)
            self.assertNotIn(b'PRIVATE', first)
            self.assertEqual(first, demo.snapshot(8765))
            self.assertEqual(fetch.call_count, 1)
        demo.CACHE.clear()


if __name__ == '__main__':
    unittest.main()
