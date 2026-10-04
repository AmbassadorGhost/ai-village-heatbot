"""Frozen v0.3 rules on the bounded, independent public-telemetry worker.

Commands and tool outputs are used only in memory to extract metadata. Startup
history is quiet; new notices are opt-in and have persistent delivery retries.
"""
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import time

import action_monitor as base
import discord_alerts
from tier1 import tier1_v02 as detector, action_notices
from tier1.exporter_addon import action_features as features

SOURCE_HASHES = {
    'tier1_v02.py': '911d27289b638cb2b0191040c3f699e0a6577e51d652aa8fe3109f7bf3b94893',
    'exporter_addon/action_features.py': '4b0929ed6b48fd54148b7841c81d85260aeda926d0c6e0c53c172ed1c6b17200',
    'outside_services.py': base.SOURCE_HASHES['outside_services.py'],
    'failure_classifier.py': base.SOURCE_HASHES['failure_classifier.py'],
}
NOTICE = ('v0.3 command-pattern candidates for human review, not findings of harm. '
          'Captured commands do not establish completed requests or intent. Browser/GUI '
          'actions and opaque scripts can be missed. The fresh-month test produced two '
          'alerts, too few to establish reliability; v0.3 did not flag the Botme challenge '
          'domain. Older v0.1.1 novelty replays are separate. No automatic action is taken.')


def normalize(data, village):
    rows, names, counts = base.normalize(data, village)
    by_id = {r['turn_id']: r for r in rows}
    seen = {}
    for session in data['sessions']:
        for turn in session.get('turns') or []:
            identity = turn.get('id') or ('fallback:' + hashlib.sha256(
                base.canonical([session.get('id'), turn]).encode()).hexdigest())
            row = by_id.get(str(identity))
            if row is None:
                continue
            try:
                stamp = dt.datetime.fromisoformat(str(turn.get('createdAt')).replace('Z', '+00:00'))
                if stamp.tzinfo is None or stamp.astimezone(base.DAY_ZONE).date().isoformat() != data['windowDate']:
                    continue
            except (ValueError, TypeError):
                continue
            command = (turn.get('agentAction') or {}).get('command') if isinstance(turn.get('agentAction'), dict) else None
            enrichment = {'session_id': session.get('id'), 'schema_version': 'tier1-telemetry-v0.2',
                          'refusal': features.refusal(*(value if isinstance(value, str) else
                              '' if value is None else base.canonical(value)
                              for value in (turn.get('error'), turn.get('system'), turn.get('output'))))}
            if isinstance(command, str):
                enrichment['action'] = features.extract(command)
            if str(identity) in seen and seen[str(identity)] != enrichment:
                raise ValueError('Conflicting duplicate action features')
            seen[str(identity)] = enrichment
            row.update(enrichment)
    # Include every normalized turn. Non-command turns count toward observed-day
    # coverage but cannot supply command features, matching the exported contract.
    return rows, names, counts


class V3ActionMonitor(base.ActionMonitor):
    def __init__(self, root, data, village, context=None, transport=None):
        super().__init__(root, data, village, backend=detector, normalizer=normalize,
                         namespace='tier1_actions', source_hashes=SOURCE_HASHES)
        self.context = context or (lambda: {})
        self.transport = transport or discord_alerts.post
        for replay in self.replays:
            if replay.get('summary', {}).get('detector') != detector.DETECTOR_VERSION:
                replay['title'] = 'Earlier v0.1.1 · ' + replay['title']
        self.bundle['notice'] = NOTICE

    def connect(self):
        conn = super().connect()
        conn.execute('CREATE TABLE IF NOT EXISTS notices '
                     '(id TEXT PRIMARY KEY, tier TEXT, payload TEXT, delivered INTEGER DEFAULT 0, '
                     'attempts INTEGER DEFAULT 0, retry_at REAL DEFAULT 0)')
        return conn

    def format_alert(self, alert, rows, origin, observed_at):
        ids = alert.get('agents') or ([alert['agent']] if alert.get('agent') else [])
        details = {k: v for k, v in alert.items() if k not in
                   ('signal', 'time', 'detector', 'agent', 'agents', 'target', 'targets')}
        return {'id': base.alert_id(alert), 'signal': alert['signal'], 'time': alert['time'],
                'detector': detector.DETECTOR_VERSION,
                'label': action_notices.SIGNAL_TITLES.get(alert['signal'], alert['signal']),
                'domain': alert.get('target'), 'targets': alert.get('targets', []),
                'agents': [{'id': a, 'name': self.names.get(a, a)} for a in ids],
                'tier': action_notices.tier_for(alert, rows), 'detail': details,
                'origin': origin, 'first_observed_at': observed_at}

    def policy(self):
        cfg = discord_alerts.load(self.root / 'discord.local.json', {})
        def url(field, enabled):
            if not enabled:
                return None
            try:
                return discord_alerts.validate_url(cfg.get(field, ''))
            except (ValueError, TypeError):
                return None
        return {'detection': url('webhook_url', cfg.get('enabled') and cfg.get('detection_enabled', False)),
                'urgent': url('urgent_webhook_url', cfg.get('urgent_enabled', False))}

    def evaluate(self, conn, baseline_ready, **kwargs):
        super().evaluate(conn, baseline_ready, **kwargs)
        policy = self.policy()
        rows = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM turns ORDER BY time,id')]
        if self.bundle['status']['phase'] in ('monitoring', 'history_incomplete'):
            raw_alerts, _ = detector.detect(rows)
            since = self.bundle['status'].get('monitoring_since')
            for alert in raw_alerts:
                identity = base.alert_id(alert)
                if not since or detector.parse_ts(alert['time']) < detector.parse_ts(since):
                    continue
                tier = action_notices.tier_for(alert, rows)
                if policy[tier]:
                    msg = action_notices.notice(alert, self.names, self.context(),
                        'Open Chat' if self.village == 'open-chat' else 'Main village', rows, tier)
                    conn.execute('INSERT OR IGNORE INTO notices(id,tier,payload) VALUES(?,?,?)',
                                 (identity, tier, base.canonical(msg)))
            conn.commit()
            self.deliver(conn, policy)
        pending = conn.execute('SELECT COUNT(*) FROM notices WHERE delivered=0').fetchone()[0]
        delivered = conn.execute('SELECT COUNT(*) FROM notices WHERE delivered=1').fetchone()[0]
        with self.lock:
            self.bundle.update(notice=NOTICE, notifications={'detection_enabled': bool(policy['detection']),
                'urgent_enabled': bool(policy['urgent']), 'pending': pending, 'delivered': delivered})
        # Save the public safe status as well as the persistent private outbox.
        temp = self.state_path.with_suffix('.tmp')
        temp.write_text(base.canonical(self.bundle), encoding='utf-8')
        temp.replace(self.state_path)

    def deliver(self, conn, policy):
        for identity, tier, payload, attempts in conn.execute(
                'SELECT id,tier,payload,attempts FROM notices WHERE delivered=0 AND retry_at<=? ORDER BY rowid LIMIT 5',
                (time.time(),)).fetchall():
            if not policy.get(tier):
                continue
            try:
                result = self.transport(policy[tier], json.loads(payload))
            except Exception:
                result = {'ok': False, 'retry_after': 60}
            delay = max(1, min(3600, float(result.get('retry_after', 60))))
            conn.execute('UPDATE notices SET delivered=?,attempts=?,retry_at=? WHERE id=?',
                         (int(bool(result.get('ok'))), attempts + 1, time.time() + delay, identity))
            conn.commit()
            if not result.get('ok'):
                break  # Respect rate limiting and keep every remaining item queued.

    def store_day(self, conn, day, response):
        if response.get('windowDate') != day:
            raise ValueError('Telemetry date mismatch')
        super().store_day(conn, day, response)
        cutoff = (dt.datetime.now(base.DAY_ZONE).date() - dt.timedelta(days=30)).isoformat()
        conn.execute('DELETE FROM turns WHERE day<?', (cutoff,))
        conn.execute('DELETE FROM days WHERE day<?', (cutoff,))
        conn.commit()

    def payload(self):
        result = super().payload()
        result['notice'] = NOTICE
        policy = self.policy()
        result.setdefault('notifications', {}).update(detection_enabled=bool(policy['detection']),
                                                      urgent_enabled=bool(policy['urgent']))
        return result
