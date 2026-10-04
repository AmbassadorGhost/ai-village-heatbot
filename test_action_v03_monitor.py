from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import action_monitor as base
import action_v03_monitor as M
from test_action_monitor import response, turn

ROOT = Path(__file__).resolve().parent
URL = 'https://discord.com/api/webhooks/123/TEST_TOKEN'

class V3Tests(unittest.TestCase):
    def test_all_turns_and_failures_retained_without_raw_text(self):
        rows, _, _ = M.normalize(response('2026-10-03', [
            turn('gui','2026-10-03T16:00:00Z'),
            turn('shell','2026-10-03T16:01:00Z','curl https://x.example -H "Authorization: SECRET"', 'HTTP 429 Too Many Requests'),
            turn('captcha','2026-10-03T16:02:00Z','curl https://x.example', 'CAPTCHA required')]), 'main')
        self.assertEqual(len(rows), 3)
        self.assertNotIn('action', rows[0])
        self.assertTrue(rows[1]['refusal']['rate_limited'])
        self.assertIn('captcha', rows[2]['failure_categories'])
        self.assertNotIn('SECRET', json.dumps(rows))
        self.assertNotIn('PRIVATE', json.dumps(rows))

    def test_wrong_village_and_naive_timestamps(self):
        with self.assertRaises(ValueError):
            M.normalize(response('2026-10-03', [], 'open-chat'), 'main')
        rows, _, _ = M.normalize(response('2026-10-03', [turn('bad','2026-10-03T16:00:00')]), 'main')
        self.assertEqual(rows, [])

    def test_context_never_uses_later_chat(self):
        self.assertIsNone(M.action_notices.nearest_message({'A': [{'time': '2026-10-03T16:01:00Z', 'text': 'later'}]}, 'A', dt.datetime(2026,10,3,16)))

    def test_default_policy_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            mon = M.V3ActionMonitor(ROOT, tmp, 'main')
            with patch.object(M.discord_alerts, 'load', return_value={'enabled':True, 'webhook_url':URL}):
                self.assertEqual(mon.policy(), {'detection':None,'urgent':None})

    def test_delivery_failure_retries_and_cap_keeps_remaining_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def send(url,msg):
                calls.append(msg)
                return {'ok':len(calls)>1,'retry_after':1}
            mon=M.V3ActionMonitor(ROOT,tmp,'main',transport=send)
            with closing(mon.connect()) as conn:
                for i in range(8):
                    conn.execute('INSERT INTO notices(id,tier,payload) VALUES(?,?,?)',(str(i),'detection','{}'))
                conn.commit()
                mon.deliver(conn,{'detection':URL})
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM notices WHERE delivered=0').fetchone()[0],8)
                conn.execute('UPDATE notices SET retry_at=0');conn.commit()
                mon.deliver(conn,{'detection':URL})
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM notices WHERE delivered=0').fetchone()[0],3)
                mon.deliver(conn,{'detection':URL})
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM notices WHERE delivered=0').fetchone()[0],0)
                mon.deliver(conn,{'detection':URL})
                self.assertEqual(len(calls),9)

    def test_startup_quiet_new_detection_silent_and_restart_deduplicated(self):
        now=dt.datetime.now(dt.timezone.utc)
        today=now.astimezone(base.DAY_ZONE).date()
        sent=[]
        cfg={'enabled':True,'webhook_url':URL,'detection_enabled':True}
        with tempfile.TemporaryDirectory() as tmp, patch.object(M.discord_alerts,'load',return_value=cfg):
            mon=M.V3ActionMonitor(ROOT,tmp,'main',transport=lambda u,m: sent.append(m) or {'ok':True})
            with closing(mon.connect()) as conn:
                for offset in range(9,0,-1):
                    day=(today-dt.timedelta(days=offset)).isoformat()
                    mon.store_day(conn,day,response(day,[turn(day,day+'T16:00:00Z')]))
                day=today.isoformat()
                mon.store_day(conn,day,response(day,[turn('old',(now-dt.timedelta(minutes=5)).isoformat(),'curl https://2captcha.com')]))
                mon.evaluate(conn,True)
                self.assertEqual(sent,[])
                self.assertEqual(mon.payload()['startup_replay'][0]['tier'],'urgent')
                new=now+dt.timedelta(minutes=1)
                mon.store_day(conn,day,response(day,[turn('new',new.isoformat(),'curl -d x=1 https://register.example/signup')]))
                mon.evaluate(conn,True)
                self.assertEqual(len(sent),1)
                self.assertEqual(sent[0]['flags'],4096)
                self.assertEqual(sent[0]['allowed_mentions'],{'parse':[]})
                self.assertEqual(mon.payload()['live_alerts'][0]['tier'],'detection')
            restarted=M.V3ActionMonitor(ROOT,tmp,'main',transport=lambda u,m: sent.append(m) or {'ok':True})
            with closing(restarted.connect()) as conn:
                restarted.evaluate(conn,True)
            self.assertEqual(len(sent),1)

    def test_ids_separate_same_agent_time_different_targets(self):
        a={'signal':'U4_account_creation','agent':'a','time':'2026-10-03T12:00:00Z','target':'one.example'}
        self.assertNotEqual(base.alert_id(a),base.alert_id(dict(a,target='two.example')))

    def test_public_gateway_retains_action_tiers(self):
        import demo_server as demo
        blob=demo.page(True).decode()
        self.assertIn("fetch('/open-chat/api/live'",blob)
        self.assertIn('/action_alerts.js',blob)
        self.assertNotIn('Configure Discord alerts',blob)

if __name__=='__main__': unittest.main()
