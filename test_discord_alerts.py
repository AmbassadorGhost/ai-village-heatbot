import copy
import json
import datetime as dt
import tempfile
from pathlib import Path
import unittest
import discord_alerts as da


class Alerts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sent = []
        self.result = {'ok': True}
        def transport(url, payload):
            self.sent.append(payload)
            return self.result
        self.n = da.Notifier(self.root, self.root, transport)
        da.save(self.n.config_path, {'enabled': True, 'generation': 'test',
                                    'webhook_url': 'https://discord.com/api/webhooks/123/test_token',
                                    'channels': ['general', 'erratic']})
        self.now = 1800000000

    def bundle(self, heat=0, erratic=0):
        return {'dashboard': {'village': 'actual-launch-1',
                'generated_at': dt.datetime.fromtimestamp(self.now,dt.timezone.utc).isoformat(),
                'channels': {c: {'thresholds': {'hot': 10, 'critical': 20}} for c in ['general','erratic']},
                'agents': {'A': {'participating': True, 'heat': {'general': heat, 'erratic': erratic},
                                 'contributions': [], 'source_events': {}}}}}

    def tick(self, h=0, e=0):
        return self.n.tick(self.bundle(h,e), self.now)

    def test_startup_high_is_quiet(self):
        self.tick(15)
        self.tick(15)
        self.assertEqual(self.sent, [])

    def test_new_crossing_groups_channels_and_suppresses_duplicates(self):
        self.tick()
        self.now += 60
        self.tick(15,15)
        self.tick(15,15)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(len(self.sent[0]['embeds'][0]['fields']),2)

    def test_restart_keeps_delivery_state(self):
        self.tick(); self.tick(15)
        other = da.Notifier(self.root,self.root,self.n.transport)
        other.tick(self.bundle(15),self.now)
        self.assertEqual(len(self.sent),1)

    def test_cooldown_then_rearm(self):
        self.tick(); self.tick(15); self.now += 60
        self.tick(0); self.tick(15)
        self.assertEqual(len(self.sent),1)
        self.now += 5400
        self.tick(15)
        self.assertEqual(len(self.sent),2)

    def test_critical_escalation_bypasses_cooldown(self):
        self.tick(); self.tick(15); self.now += 60; self.tick(21)
        self.assertEqual(len(self.sent),2)
        self.assertIn('high', self.sent[-1]['embeds'][0]['title'])
        self.assertNotIn('CRITICAL', json.dumps(self.sent[-1]))

    def test_rate_limit_keeps_pending_and_waits(self):
        self.tick()
        self.result={'ok':False,'status':429,'retry_after':120,'error':'rate limited'}
        self.tick(15); self.now+=60; self.tick(15)
        self.assertEqual(len(self.sent),1)
        self.result={'ok':True};self.now+=61;self.tick(15)
        self.assertEqual(len(self.sent),2)
        self.assertEqual(da.load(self.n.state_path,{})['pending'],{})

    def test_pending_survives_long_outage_while_hot(self):
        self.tick()
        self.result = {'ok': False, 'retry_after': 900}
        self.tick(15)
        self.now += 1000
        self.result = {'ok': True}
        self.assertEqual(self.tick(15)['pending'], 0)
        self.assertEqual(len(self.sent), 2)

    def test_pending_dropped_when_signal_cools(self):
        self.tick()
        self.result = {'ok': False, 'retry_after': 900}
        self.tick(15)
        self.now += 1000
        self.result = {'ok': True}
        self.assertEqual(self.tick(9)['pending'], 0)
        self.assertEqual(len(self.sent), 1)

    def test_stale_does_not_send(self):
        self.tick(); b=self.bundle(15)
        self.n.tick(b,self.now+181)
        self.assertEqual(self.sent,[])

    def test_disabled_sends_nothing(self):
        da.save(self.n.config_path,{'enabled':False})
        self.tick(25)
        self.assertEqual(self.sent,[])

    def test_drift_is_excluded(self):
        self.assertNotIn('deceptive',da.CHANNELS)

    def test_mentions_disabled_and_content_bounded(self):
        info={'contributions':[{'channel':'general','added':2,'key':'x'}],
              'source_events':{'x':{'text':'@everyone **hello** '*1000,'time':'2026-10-02T12:00Z','key':'x','action':'AGENT_TALK'}}}
        p=da.payload('open-chat','A',[('general',15,1)],info,'2026-10-02T12:00Z')
        self.assertEqual(p['allowed_mentions'],{'parse':[]})
        self.assertTrue(all(len(f['value'])<=1024 for f in p['embeds'][0]['fields']))

    def test_rejects_non_discord_destinations_and_query(self):
        for url in ['http://discord.com/api/webhooks/1/token','https://evil.test/api/webhooks/1/token','https://discord.com/api/webhooks/1/token?x=y']:
            with self.assertRaises(ValueError): da.validate_url(url)




class FrictionDoesNotPage(unittest.TestCase):
    """2 Oct: friction is dashboard-only, even if an older saved config lists it."""
    def test_saved_conflict_channel_is_ignored(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); sent = []
        n = da.Notifier(root, root, lambda u, p: (sent.append(p), {'ok': True})[1])
        da.save(n.config_path, {'enabled': True, 'generation': 'g',
                                'webhook_url': 'https://discord.com/api/webhooks/123/test_token',
                                'channels': ['conflict']})
        now = 1800000000
        def b(h):
            return {'dashboard': {'village': 'actual-launch-1',
                    'generated_at': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
                    'channels': {'conflict': {'thresholds': {'hot': 15.4, 'critical': 31.3}}},
                    'agents': {'Terra': {'participating': True, 'heat': {'conflict': h},
                                         'contributions': [], 'source_events': {}}}}}
        n.tick(b(0), now); n.tick(b(34.5), now)
        self.assertEqual(sent, [])
        self.assertNotIn('conflict', da.CHANNELS)


class CalmNotices(unittest.TestCase):
    """2 Oct (Adam): everyday heat goes out live, as calm, silent notices."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.sent = []
        self.n = da.Notifier(self.root, self.root, lambda u, p: (self.sent.append(p), {'ok': True})[1])
        self.cfg = {'enabled': True, 'generation': 'g',
                    'webhook_url': 'https://discord.com/api/webhooks/123/test_token',
                    'channels': list(da.CHANNELS)}
        da.save(self.n.config_path, self.cfg)
        self.now = 1800000000

    def bundle(self, heat):
        return {'dashboard': {'village': 'actual-launch-1',
                'generated_at': dt.datetime.fromtimestamp(self.now, dt.timezone.utc).isoformat(),
                'channels': {'off-goal': {'thresholds': {'hot': 6.8, 'critical': 14.0}}},
                'agents': {'Sonnet': {'participating': True, 'heat': {'off-goal': heat},
                                      'contributions': [], 'source_events': {}}}}}

    def cross(self, h=20):
        self.n.tick(self.bundle(0), self.now); self.now += 60
        self.n.tick(self.bundle(h), self.now)

    def test_everyday_crossing_is_sent_live(self):
        self.cross()
        self.assertEqual(len(self.sent), 1)

    def test_calm_wording_never_critical_or_urgent(self):
        self.cross(20)
        body = json.dumps(self.sent[0])
        self.assertIn('Heat notice', body)
        self.assertIn('high', body)
        self.assertNotIn('critical', body.lower())
        self.assertNotIn('urgent', self.sent[0]['embeds'][0]['title'].lower())
        self.assertEqual(self.sent[0]['allowed_mentions'], {'parse': []})

    def test_notices_are_silent_by_default(self):
        self.cross()
        self.assertEqual(self.sent[0].get('flags'), da.SILENT_FLAG)

    def test_silence_can_be_turned_off(self):
        da.save(self.n.config_path, dict(self.cfg, silent_notices=False))
        self.cross()
        self.assertNotIn('flags', self.sent[0])

    def test_urgent_tier_is_reserved_and_empty(self):
        self.assertEqual(da.URGENT_CHANNELS, ())


if __name__ == '__main__':
    unittest.main()
