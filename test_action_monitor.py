import datetime as dt
from contextlib import closing
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import action_monitor as M
import demo_server as demo

ROOT = Path(__file__).resolve().parent

def response(day, turns, village='main'):
    return {'windowDate': day, 'sessions': [{'id': 's', 'agentId': 'a',
        'agent': {'name': '<script>untrusted name</script>'}, 'villageId': M.VILLAGES[village], 'turns': turns}]}

def turn(identity, stamp, command=None, error=''):
    return {'id': identity, 'createdAt': stamp, 'agentAction': {'command': command},
            'error': error, 'output': 'PRIVATE TOOL OUTPUT'}

class ActionTests(unittest.TestCase):
    def test_live_detection_published_before_failed_history_backfill(self):
        today=dt.datetime.now(M.DAY_ZONE).date()
        current=today.isoformat()
        yesterday=(today-dt.timedelta(days=1)).isoformat()
        gap=(today-dt.timedelta(days=2)).isoformat()
        event=dt.datetime.combine(today,dt.time(16),dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            monitor=M.ActionMonitor(ROOT,tmp,'main')
            monitor.bootstrap=[gap,yesterday,current]
            with closing(monitor.connect()) as conn:
                for offset in range(10,2,-1):
                    day=(today-dt.timedelta(days=offset)).isoformat()
                    monitor.store_day(conn,day,response(day,[turn(day,day+'T16:00:00Z')]))
                with patch.object(M,'utc_stamp',return_value=(event-dt.timedelta(hours=1)).isoformat()):
                    monitor.evaluate(conn,True)
            def fetch(day):
                if day==gap:
                    # Detection must be visible before an old-date request blocks.
                    published=monitor.payload()
                    self.assertEqual(published['live_alert_count'],1)
                    self.assertIsNotNone(published['status']['last_success'])
                    raise TimeoutError('PRIVATE')
                turns=[] if day==yesterday else [turn(f'new-{i}',(event+dt.timedelta(seconds=i)).isoformat(),'curl https://new.example') for i in range(10)]
                return response(day,turns)
            with patch.object(monitor,'fetch',side_effect=fetch):
                monitor.collect()
            result=monitor.payload()
            self.assertEqual(result['status']['phase'],'history_incomplete')
            self.assertEqual(result['status']['history_failed_dates'],[gap])
            self.assertEqual(result['status']['live_failed_dates'],[])
            self.assertIsNone(result['status']['error'])
            self.assertEqual(result['live_alert_count'],1)
            saved=json.loads(monitor.state_path.read_text())
            self.assertEqual(saved['status'],result['status'])

    def test_slow_stream_stops_at_transfer_budget_and_closes_response(self):
        from unittest.mock import MagicMock
        stream=MagicMock()
        stream.__enter__.return_value=stream
        stream.read1.return_value=b'x'
        with tempfile.TemporaryDirectory() as tmp:
            monitor=M.ActionMonitor(ROOT,tmp,'main')
            with patch.object(M,'urlopen',return_value=stream), patch.object(M.time,'monotonic',side_effect=[0,0,91]):
                with self.assertRaises(TimeoutError):
                    monitor.fetch('2026-10-03')
        stream.read1.assert_called_once()
        stream.__exit__.assert_called_once()

    def test_normalize_date_village_dedup_and_no_raw_content(self):
        t = turn('a','2026-10-03T16:00:00Z', 'curl https://user:SECRET@www.example.com/private?token=SECRET', 'HTTP 403 Forbidden')
        rows, names, counts = M.normalize(response('2026-10-03', [t,t,turn('old','2026-10-03T01:00:00Z')]), 'main')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['outside_services'], ['www.example.com'])
        self.assertIn('forbidden', rows[0]['failure_categories'])
        self.assertNotIn('PRIVATE', json.dumps(rows))
        self.assertNotIn('SECRET', json.dumps(rows))
        self.assertEqual(counts['outside_requested_day'], 1)
        with self.assertRaisesRegex(ValueError, 'village'):
            M.normalize(response('2026-10-03',[t],'open-chat'), 'main')

    def test_startup_separated_and_restart_preserves_live_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = M.ActionMonitor(ROOT, tmp, 'main')
            with closing(monitor.connect()) as conn:
                for day in range(1,8):
                    d = f'2026-09-{day:02d}'
                    monitor.store_day(conn, d, response(d,[turn(d,d+'T16:00:00Z')]))
                def burst(day, domain):
                    stamp = dt.datetime.fromisoformat(day+'T16:00:00+00:00')
                    return [turn(f'{day}-{i}',(stamp+dt.timedelta(seconds=i)).isoformat(),f'curl https://{domain}') for i in range(10)]
                monitor.store_day(conn,'2026-09-08',response('2026-09-08',burst('2026-09-08','old.example')))
                with patch.object(M,'utc_stamp',return_value='2026-09-09T12:00:00Z'):
                    monitor.evaluate(conn,True)
                self.assertEqual(monitor.payload()['live_alert_count'],0)
                self.assertEqual(monitor.payload()['startup_replay_count'],1)
                monitor.store_day(conn,'2026-09-09',response('2026-09-09',burst('2026-09-09','new.example')))
                with patch.object(M,'utc_stamp',return_value='2026-09-09T17:00:00Z'):
                    monitor.evaluate(conn,True)
                first = monitor.payload()['live_alerts']
                self.assertEqual(len(first),1)
                restarted = M.ActionMonitor(ROOT,tmp,'main')
                with patch.object(M,'utc_stamp',return_value='2026-09-10T17:00:00Z'):
                    restarted.evaluate(conn,True)
                self.assertEqual(first,restarted.payload()['live_alerts'])
                self.assertNotIn('names',restarted.payload())

    def test_fetch_failure_is_visible_and_does_not_start_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = M.ActionMonitor(ROOT,tmp,'main')
            with patch.object(monitor,'fetch',side_effect=OSError('PRIVATE SECRET')):
                monitor.collect()
            result=monitor.payload()
            self.assertEqual(result['status']['phase'],'feed_error')
            self.assertIsNone(result['status']['last_success'])
            self.assertNotIn('monitoring_since',result['status'])
            self.assertTrue(result['status']['failed_dates'])
            self.assertNotIn('SECRET',json.dumps(result))

    def test_turn_identity_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor=M.ActionMonitor(ROOT,tmp,'main')
            with closing(monitor.connect()) as conn:
                monitor.store_day(conn,'2026-10-03',response('2026-10-03',[turn('x','2026-10-03T16:00:00Z','curl https://example.com')]))
                with self.assertRaisesRegex(ValueError,'identity'):
                    monitor.store_day(conn,'2026-10-03',response('2026-10-03',[turn('x','2026-10-03T16:00:00Z','curl https://changed.com')]))

    def test_successful_empty_days_do_not_satisfy_burnin(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor=M.ActionMonitor(ROOT,tmp,'main')
            with closing(monitor.connect()) as conn:
                for day in range(1,10):
                    date=f'2026-09-{day:02d}'
                    monitor.store_day(conn,date,response(date,[]))
                monitor.evaluate(conn,True)
            result=monitor.payload()
            self.assertEqual(result['coverage']['observed_days'],0)
            self.assertNotIn('monitoring_since',result['status'])
            self.assertEqual(result['status']['phase'],'warming_up')

    def test_recorded_results_verified_and_gateway_keeps_action_only_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor=M.ActionMonitor(ROOT,tmp,'main')
            replay=monitor.payload()['recorded_replays']
            self.assertEqual(replay[0]['summary']['alerts'],2)
            self.assertEqual(replay[0]['summary']['detector'],'tier1-v0.3')
            replay=[r for r in replay if r['summary']['detector']!='tier1-v0.3']
            self.assertEqual([r['summary']['alerts'] for r in replay],[21,9])
            self.assertEqual(sum(a['domain']=='dunkirk.sh' for a in replay[1]['alerts']),3)
            upstream={'action_alerts':monitor.payload(),'secret':'PRIVATE','status':{'discord':{'webhook':'PRIVATE'}}}
            demo.CACHE.clear()
            with patch.object(demo.OPENER,'open',side_effect=lambda *a,**k:io.BytesIO(json.dumps(upstream).encode())):
                full=json.loads(demo.snapshot(8765))
                actions=json.loads(demo.snapshot(8765,True))
            self.assertEqual(full['action_alerts'],actions)
            self.assertNotIn('PRIVATE',json.dumps(actions))
            demo.CACHE.clear()

if __name__=='__main__':
    unittest.main()
