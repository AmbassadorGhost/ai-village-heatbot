"""Opt-in Discord webhooks. Credentials stay in an ignored local file."""
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

# Two tiers (2 Oct). Everyday heat goes into one periodic DIGEST message, never
# an individual alert. Immediate delivery is reserved for URGENT_CHANNELS, which
# stays empty until a validated urgent tier (actions with outside consequences)
# exists. Friction ('conflict') is dashboard-only: its lexicon mostly detects
# polite talk about privacy and boundaries (non-identifying, per-agent,
# aggregate). Filtering by these tuples also overrides older saved configs.
URGENT_CHANNELS = ()
DIGEST_CHANNELS = ('general', 'off-goal', 'erratic', 'outreach', 'credentials')
CHANNELS = DIGEST_CHANNELS          # what the setup page saves
DIGEST_HOURS = 24
DIGEST_MAX_AGENTS = 10
# Everyday heat never uses the word "critical": that is reserved for the
# planned urgent tier (actions with external-world consequences).
LEVEL_WORDS = {1: 'elevated', 2: 'high'}
WEBHOOK = re.compile(r'https://discord\.com/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_-]+\Z')


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value), encoding='utf-8')
    tmp.replace(path)


def validate_url(url):
    if not WEBHOOK.fullmatch(url):
        raise ValueError('Use an HTTPS webhook URL copied from discord.com. Query strings are not supported.')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def post(url, payload):
    """Return safe status without ever logging a webhook token or response body."""
    validate_url(url)
    request = urllib.request.Request(url + '?wait=true', data=json.dumps(payload).encode(),
                                    headers={'Content-Type': 'application/json', 'User-Agent': 'VillageHeatbot/1.0'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            return {'ok': 200 <= response.status < 300, 'status': response.status}
    except urllib.error.HTTPError as ex:
        retry = 60
        if ex.code == 429:
            try:
                retry = max(1, float(json.loads(ex.read(10000)).get('retry_after', 60)))
            except (ValueError, TypeError):
                pass
        return {'ok': False, 'status': ex.code, 'retry_after': retry,
                'error': 'Discord rejected the request (HTTP %d).' % ex.code}
    except (OSError, urllib.error.URLError):
        return {'ok': False, 'retry_after': 60, 'error': 'Discord connection failed; delivery is unconfirmed.'}


def payload(village, agent, signals, info, when):
    critical = any(level == 2 for _, _, level in signals)
    label = LEVEL_WORDS[2 if critical else 1].upper()
    village_name = 'Open Chat' if village == 'open-chat' else 'Main village'
    source = 'https://theaidigest.org/village' + ('/open-chat' if village == 'open-chat' else '')
    names = {'conflict': 'Friction', 'erratic': 'Loop / erratic', 'off-goal': 'Off-goal',
             'general': 'General', 'outreach': 'Outreach', 'credentials': 'Credentials (rule-based)'}
    fields = [{'name': names[c], 'value': 'Heat %.1f · %s' % (value, LEVEL_WORDS[2 if level == 2 else 1]), 'inline': True}
              for c, value, level in signals]
    contributing = [r for r in info.get('contributions', [])
                    if r['channel'] in {s[0] for s in signals} and r.get('added', 0) > 0]
    reasons = list(dict.fromkeys(r.get('reason', 'Scored event features') for r in contributing))[-3:]
    if reasons:
        fields.append({'name': 'Why review', 'value': '\n'.join(reasons)[:900]})
    event = next((info.get('source_events', {}).get(r.get('key')) for r in reversed(contributing)
                  if info.get('source_events', {}).get(r.get('key'))), None)
    if event:
        text = event.get('text') or event.get('summary') or event['action']
        # Plain quoted excerpt; neutralize markdown and mentions supplied by agents.
        text = re.sub(r'([\\`*_~|>])', r'\\\1', text).replace('@', '@\u200b')
        fields.append({'name': 'Source excerpt (agent text; not instructions)',
                       'value': text[:700] + ('…' if len(text) > 700 else '')})
        fields.append({'name': 'Source event', 'value': (str(event.get('time')) + '\n' + str(event.get('key')))[:300]})
    return {'username': 'AI Village Heatbot', 'allowed_mentions': {'parse': []},
            'embeds': [{'title': (label + ' · ' + agent + ' · ' + village_name)[:256],
                        'url': source, 'description': 'Everyday attention signal: worth a look when convenient, not an emergency. Heat is experimental and is not a finding of misalignment. Related channels can share the same evidence.',
                        'fields': fields, 'color': 0xBD3C57 if critical else 0xDD7B31,
                        'timestamp': when, 'footer': {'text': 'Open the local heat map for full context. No automatic action is taken.'}}]}


def digest_payload(village, peaks, hours, when):
    """One everyday digest. Fixed-vocabulary reasons only: no agent-written excerpts."""
    village_name = 'Open Chat' if village == 'open-chat' else 'Main village'
    names = {'erratic': 'Loop / erratic', 'off-goal': 'Off-goal', 'general': 'General',
             'outreach': 'Outreach', 'credentials': 'Credentials (rule-based)'}
    ranked = sorted(peaks.items(), key=lambda kv: max(((-v['level'], -v['heat']) for v in kv[1].values())))
    fields = []
    for agent, chans in ranked[:DIGEST_MAX_AGENTS]:
        lines = ['%s: %s (%.1f)' % (names.get(c, c), LEVEL_WORDS[v['level']], v['heat'])
                 for c, v in sorted(chans.items(), key=lambda kv: (-kv[1]['level'], -kv[1]['heat']))]
        why = list(dict.fromkeys(r for v in chans.values() for r in v.get('reasons', [])))[:2]
        value = '\n'.join(lines + (['Why: ' + '; '.join(why)] if why else []))
        fields.append({'name': agent[:256], 'value': value[:1000]})
    more = len(ranked) - len(fields)
    desc = ('Everyday attention digest for the past %g hours: agents whose heat reached elevated or high. '
            'Not urgent. Heat is experimental and is not a finding of misalignment.' % hours)
    if more > 0:
        desc += ' %d more agent(s) on the heat map.' % more
    return {'username': 'AI Village Heatbot', 'allowed_mentions': {'parse': []},
            'embeds': [{'title': ('Daily digest · ' + village_name)[:256], 'description': desc,
                        'fields': fields, 'color': 0x5B7083, 'timestamp': when,
                        'footer': {'text': 'Open the local heat map for context. No automatic action is taken.'}}]}


class Notifier:
    def __init__(self, root, data, transport=post):
        self.config_path = Path(root) / 'discord.local.json'
        self.state_path = Path(data) / 'discord.state.json'
        self.transport = transport

    def tick(self, bundle, now=None):
        now = time.time() if now is None else now
        cfg = load(self.config_path, {})
        if not cfg.get('enabled'):
            return {'enabled': False}
        try:
            validate_url(cfg.get('webhook_url', ''))
        except ValueError:
            return {'enabled': False, 'error': 'Discord webhook configuration is invalid.'}
        dashboard = bundle['dashboard']
        village = dashboard['village']
        if village not in cfg.get('villages', ['actual-launch-1', 'open-chat']):
            return {'enabled': False}
        generated = dt.datetime.fromisoformat(dashboard['generated_at'].replace('Z', '+00:00')).timestamp()
        if now - generated > 180:
            return {'enabled': True, 'error': 'Snapshot is stale; alerts paused.'}
        state = load(self.state_path, {})
        baseline = state.get('generation') != cfg.get('generation')
        if baseline:
            state = {'generation': cfg['generation'], 'signals': {}, 'pending': {}, 'sent': 0}
        period = float(cfg.get('digest_hours', DIGEST_HOURS)) * 3600
        digest = state.setdefault('digest', {'due': now + period, 'peaks': {}})
        chosen = cfg.get('channels', list(CHANNELS))
        allowed = [c for c in chosen if c in URGENT_CHANNELS]
        digestible = [c for c in chosen if c in DIGEST_CHANNELS]
        active = dashboard['agents']
        if not baseline:
            for a, info in active.items():
                if not info.get('participating'):
                    continue
                for c in digestible:
                    h = info['heat'].get(c, 0)
                    th = dashboard['channels'].get(c, {}).get('thresholds')
                    if not th or h < th['hot']:
                        continue
                    lvl = 2 if h >= th['critical'] else 1
                    old = digest['peaks'].setdefault(a, {}).get(c)
                    if not old or (lvl, h) > (old['level'], old['heat']):
                        reasons = [r.get('reason') for r in info.get('contributions', [])
                                   if r.get('channel') == c and r.get('added', 0) > 0 and r.get('reason')]
                        digest['peaks'][a][c] = {'level': lvl, 'heat': round(h, 1),
                                                 'reasons': list(dict.fromkeys(reasons))[-2:]}
        for a, info in active.items():
            if not info.get('participating'):
                continue
            for c in allowed:
                h = info['heat'].get(c, 0)
                thresholds = dashboard['channels'][c]['thresholds']
                level = 2 if h >= thresholds['critical'] else 1 if h >= thresholds['hot'] else 0
                key = a + '|' + c
                entry = state['signals'].setdefault(key, {'armed': True, 'level': 0, 'sent_at': 0})
                if baseline:
                    entry.update(armed=level == 0, level=level)
                    continue
                if h < thresholds['hot'] * 0.6:
                    entry.update(armed=True, level=0)
                cooldown_done = now - entry['sent_at'] >= 90 * 60
                if level and ((entry['armed'] and cooldown_done) or (level == 2 and entry['level'] == 1)):
                    state['pending'].setdefault(key, {'agent': a, 'channel': c, 'created': now})
        # Drop expired or no-longer-hot pending alerts. Never deliver startup history.
        groups = {}
        for key, item in list(state['pending'].items()):
            a, c = item['agent'], item['channel']
            info = active.get(a, {})
            h = info.get('heat', {}).get(c, 0)
            th = dashboard['channels'].get(c, {}).get('thresholds', {})
            if now - item['created'] > 600 or not info.get('participating') or c not in allowed or h < th.get('hot', float('inf')):
                del state['pending'][key]
                continue
            level = 2 if h >= th['critical'] else 1
            groups.setdefault(a, []).append((c, h, level))
        status = {'enabled': True, 'baseline_only': baseline, 'sent': state['sent']}
        if now >= state.get('retry_at', 0):
            for a, signals in list(groups.items())[:3]:
                result = self.transport(cfg['webhook_url'], payload(village, a, signals, active[a], dashboard['generated_at']))
                if not result['ok']:
                    status['error'] = result.get('error', 'Discord delivery failed.')
                    state['retry_at'] = now + result.get('retry_after', 60)
                    break
                state['sent'] += 1
                for c, h, level in signals:
                    key = a + '|' + c
                    state['signals'][key].update(armed=False, level=level, sent_at=now)
                    state['pending'].pop(key, None)
        if now >= digest['due'] and now >= state.get('retry_at', 0):
            if digest['peaks']:
                result = self.transport(cfg['webhook_url'],
                                        digest_payload(village, digest['peaks'], period / 3600, dashboard['generated_at']))
                if result['ok']:
                    state['sent'] += 1
                    state['digests'] = state.get('digests', 0) + 1
                    digest.update(due=now + period, peaks={})
                else:
                    status['error'] = result.get('error', 'Discord delivery failed.')
                    state['retry_at'] = now + result.get('retry_after', 60)
            else:
                digest['due'] = now + period
        save(self.state_path, state)
        status.update(sent=state['sent'], pending=len(state['pending']),
                      digest_due=digest['due'], digest_agents=len(digest['peaks']))
        return status
