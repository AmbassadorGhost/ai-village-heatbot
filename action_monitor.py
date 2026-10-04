"""Action telemetry monitoring; no raw commands, outputs, or automatic responses."""
from collections import Counter
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from tier1 import detector, failure_classifier, outside_services

VILLAGES = {'main': '00ebc425-074c-466f-ab2d-5aa2efa445aa',
            'open-chat': '25a9bc78-7ff4-4136-a948-aa6fbeea9e92'}
DAY_ZONE = ZoneInfo('America/Los_Angeles')
POLL_SECONDS = 300
BOOTSTRAP_DAYS = 14
MAX_RESPONSE_BYTES = 256 * 1024 * 1024
TRANSFER_SECONDS = 90
SOURCE_HASHES = {
    'detector.py': 'c740ffe541b2d1aa67572b8a4ed6573de1d3fe2ad8ecd4aa9357d4d1f8e1255d',
    'outside_services.py': '26d30e5baf7dbdb9c1172356cc53d5522f2bfc9dee2a9d5a7c59095080b5d578',
    'failure_classifier.py': '7dd39faa3292df153c3f2066f44ef97698a81c32f5b14433e039f8f434558a64',
}
SIGNALS = {'S1_blocked_then_switch': 'Failures followed by a new service',
           'S2_new_service_at_volume': 'New service at volume',
           'S3_convergence': 'Several agents converge'}
NOTICE = ('Action alerts are candidates for human review. Destinations are inferred from '
          'supported commands; they do not prove completed requests or misconduct. GUI actions, '
          'scripts and dynamic targets can be missed. Result availability and early-warning lead '
          'time are unverified. No alerts are sent to agents or acted on automatically.')


def utc_stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def normalize(data, village):
    """Use the existing target parser and frozen failure classifier on in-day turns."""
    day = data.get('windowDate')
    dt.date.fromisoformat(day)
    if not isinstance(data.get('sessions'), list):
        raise ValueError('Unexpected telemetry schema')
    rows, names, counts = {}, {}, Counter()
    for session in data['sessions']:
        if session.get('villageId') != VILLAGES[village]:
            raise ValueError('Telemetry village mismatch')
        agent = session.get('agentId')
        if not isinstance(agent, str) or not agent:
            counts['missing_agent'] += 1
            continue
        name = (session.get('agent') or {}).get('name')
        if isinstance(name, str):
            names[agent] = name[:120]
        for turn in session.get('turns') or []:
            counts['returned_turns'] += 1
            try:
                timestamp = dt.datetime.fromisoformat(str(turn.get('createdAt')).replace('Z', '+00:00'))
                if timestamp.tzinfo is None:
                    raise ValueError('Missing timezone')
                timestamp = timestamp.astimezone(dt.timezone.utc)
            except (ValueError, TypeError):
                counts['invalid_time'] += 1
                continue
            if timestamp.astimezone(DAY_ZONE).date().isoformat() != day:
                counts['outside_requested_day'] += 1
                continue
            action = turn.get('agentAction') or {}
            command = action.get('command') if isinstance(action, dict) else None
            fields = outside_services.extract(command) if isinstance(command, str) else {
                'outside_services': [], 'target_status': 'unsupported_action'}
            def as_text(obj):
                return obj if isinstance(obj, str) else '' if obj is None else canonical(obj)
            failures = failure_classifier.classify(as_text(turn.get('error')), as_text(turn.get('system')), as_text(turn.get('output')))
            identity = turn.get('id')
            if not identity:
                identity = 'fallback:' + hashlib.sha256(canonical([session.get('id'), turn]).encode()).hexdigest()
                counts['fallback_ids'] += 1
            row = {'turn_id': str(identity), 'agent_id': agent,
                   'timestamp_utc': timestamp.isoformat(timespec='microseconds').replace('+00:00', 'Z'),
                   'source_day': day, 'outside_services': fields['outside_services'],
                   'failure_categories': failures, 'target_status': fields['target_status'],
                   'command_sha256': outside_services.command_fingerprint(command) if isinstance(command, str) else None}
            previous = rows.get(row['turn_id'])
            if previous and canonical(previous) != canonical(row):
                raise ValueError('Conflicting duplicate telemetry')
            rows[row['turn_id']] = row
    counts['rows'] = len(rows)
    counts['target_bearing_turns'] = sum(bool(r['outside_services']) for r in rows.values())
    counts['unsupported_or_unresolved'] = sum(r['target_status'] in ('unsupported_action', 'unresolved_or_opaque') for r in rows.values())
    return list(rows.values()), names, dict(counts)


def alert_id(alert):
    return hashlib.sha256(canonical(alert).encode()).hexdigest()[:24]


def public_alert(alert, names, origin, observed_at=None):
    result = {k: alert[k] for k in ('signal', 'time', 'detector', 'domain', 'turns', 'blocked_turns', 'first_contact') if k in alert}
    agents = alert.get('agents') or ([alert['agent']] if alert.get('agent') else [])
    result.update(id=alert_id(alert), label=SIGNALS.get(alert['signal'], alert['signal']),
                  agents=[{'id': a, 'name': names.get(a, a)} for a in agents], origin=origin)
    if observed_at:
        result['first_observed_at'] = observed_at
    return result


class ActionMonitor:
    def __init__(self, root, data, village, *, backend=None, normalizer=None, namespace="actions", source_hashes=None):
        self.root, self.data, self.village = Path(root), Path(data), village
        self.detector = backend or detector
        self.normalizer = normalizer or normalize
        self.source_hashes = source_hashes or SOURCE_HASHES
        for filename, expected in self.source_hashes.items():
            if hashlib.sha256((self.root / 'tier1' / filename).read_bytes()).hexdigest() != expected:
                raise ValueError('Action source version mismatch: ' + filename)
        self.lock = threading.Lock()
        self.db = self.data / (namespace + '.sqlite3')
        self.state_path = self.data / (namespace + '_snapshot.json')
        self.names = {}
        self.bundle = {'status': {'phase': 'starting', 'poll_seconds': POLL_SECONDS, 'village': village,
                                 'last_success': None, 'error': None}, 'live_alerts': [], 'startup_replay': [],
                       'coverage': {}, 'notice': NOTICE, 'detector': self.detector.DETECTOR_VERSION}
        try:
            saved = json.loads(self.state_path.read_text(encoding='utf-8'))
            self.bundle.update(saved)
            self.names = saved.get('names', {})
            self.bundle['status'].update(phase='starting', error=None)
        except (OSError, ValueError):
            pass
        try:
            self.replays = json.loads((self.root / 'tier1' / 'recorded_replays.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.replays = []
        self.bootstrap_end = dt.datetime.now(DAY_ZONE).date()
        self.bootstrap = [(self.bootstrap_end - dt.timedelta(days=i)).isoformat()
                          for i in range(BOOTSTRAP_DAYS - 1, -1, -1)]

    def format_alert(self, alert, rows, origin, observed_at):
        return public_alert(alert, self.names, origin, observed_at)

    def connect(self):
        conn = sqlite3.connect(self.db)
        conn.execute('CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, time TEXT, day TEXT, agent TEXT, payload TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, fetched_at TEXT, counts TEXT)')
        conn.execute('CREATE INDEX IF NOT EXISTS turns_time ON turns(time,id)')
        return conn

    def fetch(self, day):
        url = 'https://theaidigest.org/village/api/computer-use-sessions?' + urlencode({'villageId': VILLAGES[self.village], 'date': day})
        deadline = time.monotonic() + TRANSFER_SECONDS
        with urlopen(Request(url, headers={'User-Agent': 'Heatbot human-review action monitor/0.1'}), timeout=45) as response:
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Telemetry transfer exceeded time budget')
                # A socket timeout alone permits an indefinitely slow stream.
                # read1 returns available bytes without waiting to fill a buffer.
                chunk = response.read1(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError('Telemetry response exceeds size limit')
                chunks.append(chunk)
        raw = b''.join(chunks)
        data = json.loads(raw)
        if data.get('windowDate') != day:
            raise ValueError('Telemetry date mismatch')
        return data

    def store_day(self, conn, day, response):
        rows, names, counts = self.normalizer(response, self.village)
        self.names.update(names)
        for row in rows:
            prior = conn.execute('SELECT payload FROM turns WHERE id=?', (row['turn_id'],)).fetchone()
            if prior:
                old = json.loads(prior[0])
                if any(old.get(k) != row.get(k) for k in ('agent_id', 'timestamp_utc', 'command_sha256', 'outside_services')):
                    raise ValueError('Source changed an existing turn identity')
            conn.execute('INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?)',
                         (row['turn_id'], row['timestamp_utc'], row['source_day'], row['agent_id'], canonical(row)))
        conn.execute('INSERT OR REPLACE INTO days VALUES (?,?,?)', (day, utc_stamp(), canonical(counts)))
        conn.commit()

    def evaluate(self, conn, baseline_ready, cycle_success=True, failed_dates=(), live_failed_dates=()):
        rows = [json.loads(row[0]) for row in conn.execute('SELECT payload FROM turns ORDER BY time,id')]
        alerts, summary = self.detector.detect(rows)
        stamp = utc_stamp()
        agent_days = {}
        for row in rows:
            agent_days.setdefault(row['agent_id'], set()).add(row['source_day'])
        ready_agents = sum(len(d) > self.detector.BURN_IN_DAYS for d in agent_days.values())
        with self.lock:
            status = dict(self.bundle['status'])
            baseline = status.get('monitoring_since')
            if not baseline and baseline_ready and ready_agents:
                baseline = stamp
                status['monitoring_since'] = baseline
            previous = {a['id']: a for a in self.bundle.get('live_alerts', []) + self.bundle.get('startup_replay', [])}
        live, startup = [], []
        for alert in alerts:
            is_live = bool(baseline and self.detector.parse_ts(alert['time']) >= self.detector.parse_ts(baseline))
            item = self.format_alert(alert, rows, 'live' if is_live else 'startup_replay',
                                previous.get(alert_id(alert), {}).get('first_observed_at', stamp))
            (live if is_live else startup).append(item)
        dates = [r[0] for r in conn.execute('SELECT day FROM days ORDER BY day')]
        coverage = {'successful_source_dates': dates, 'missing_bootstrap_dates': sorted(set(self.bootstrap) - set(dates)),
                    'observed_days': summary['observed_days'], 'rows': summary['rows'],
                    'target_bearing_turns': sum(bool(r['outside_services']) for r in rows),
                    'first_turn': rows[0]['timestamp_utc'] if rows else None,
                    'last_turn': rows[-1]['timestamp_utc'] if rows else None,
                    'agents_ready': ready_agents,
                    'agents_observed': len(agent_days), 'required_prior_observed_days': self.detector.BURN_IN_DAYS,
                    'day_timezone': DAY_ZONE.key,
                    'note': 'Successful empty days do not prove inactivity. Only days with turns count toward burn-in; new means first observed in this available history.'}
        status.update(last_evaluated=stamp, error=None, failed_dates=list(failed_dates),
                      live_failed_dates=list(live_failed_dates),
                      history_failed_dates=[d for d in failed_dates if d not in live_failed_dates],
                      phase='monitoring' if baseline and coverage['agents_ready'] else 'warming_up',
                      polling=False, bootstrap_days_loaded=len(set(dates) & set(self.bootstrap)),
                      bootstrap_days_requested=len(self.bootstrap))
        if live_failed_dates:
            status.update(phase='feed_error', error='Latest action telemetry could not be fetched; retaining observed records.')
        elif baseline and coverage['agents_ready'] and coverage['missing_bootstrap_dates']:
            status['phase'] = 'history_incomplete'
        if cycle_success:
            status['last_success'] = stamp
        result = {'status': status, 'coverage': coverage, 'live_alerts': live[-100:],
                  'live_alert_count': len(live), 'startup_replay': startup[-50:],
                  'startup_replay_count': len(startup), 'rules': summary['rules'],
                  'detector': self.detector.DETECTOR_VERSION, 'source_sha256': self.source_hashes,
                  'notice': NOTICE, 'names': self.names}
        temp = self.state_path.with_suffix('.tmp')
        temp.write_text(canonical(result), encoding='utf-8')
        temp.replace(self.state_path)
        with self.lock:
            self.bundle = result

    def collect(self):
        with closing(self.connect()) as conn:
            loaded = {r[0] for r in conn.execute('SELECT day FROM days')}
            pending = [d for d in self.bootstrap if d not in loaded]
            today = dt.datetime.now(DAY_ZONE).date()
            current = [(today - dt.timedelta(days=1)).isoformat(), today.isoformat()]
            with self.lock:
                initial = not self.bundle['status'].get('last_evaluated')
            dates = list(dict.fromkeys(current + (pending if initial else pending[:2])))
            errors = []
            for day in dates:
                with self.lock:
                    self.bundle['status'].update(polling=True, fetching_day=day,
                        fetching_kind='live' if day in current else 'history',
                        bootstrap_days_loaded=len(loaded & set(self.bootstrap)), bootstrap_days_requested=len(self.bootstrap))
                try:
                    response = self.fetch(day)
                    self.store_day(conn, day, response)
                    loaded.add(day)
                except Exception as exc:
                    conn.rollback()
                    errors.append((day, type(exc).__name__))
                    print('Action telemetry day unavailable:', self.village, day, type(exc).__name__, flush=True)
                if day == current[-1]:
                    live_errors = [d for d, _ in errors if d in current]
                    # Publish new action detection before attempting a potentially
                    # slow historical backfill. Initial history still warms up.
                    self.evaluate(conn, not initial, cycle_success=not live_errors,
                                  failed_dates=[d for d, _ in errors], live_failed_dates=live_errors)
            # Missing days stay visible. They do not prevent monitoring ready agents
            # once the initial collection has been attempted; unobserved days never
            # count toward burn-in.
            self.evaluate(conn, True, cycle_success=False, failed_dates=[d for d, _ in errors],
                          live_failed_dates=[d for d, _ in errors if d in current])

    def loop(self):
        # A restart can immediately evaluate persisted observations; it need not
        # discard a usable baseline while fetching the latest source dates.
        if self.db.exists():
            try:
                with closing(self.connect()) as conn:
                    self.evaluate(conn, True, cycle_success=False)
            except Exception as exc:
                print('Action cached replay unavailable:', type(exc).__name__, flush=True)
        while True:
            try:
                self.collect()
            except Exception as exc:
                with self.lock:
                    self.bundle['status'].update(phase='feed_error', polling=False,
                        error='Action telemetry unavailable; showing last successful observations.')
                print('Action monitor error:', type(exc).__name__, flush=True)
            time.sleep(POLL_SECONDS)

    def payload(self):
        with self.lock:
            result = {k: v for k, v in self.bundle.items() if k != 'names'}
            # Serialize under lock; callers receive an independent snapshot.
            result = json.loads(canonical(result))
        result['recorded_replays'] = self.replays
        return result
