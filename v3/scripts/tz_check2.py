"""Per timestamp format: date range, and how often the agent was active within +-1h when the stamp is read as UTC
vs as Pacific (what the heatbot pipeline did for every format)."""
import gzip, json, collections, datetime as dt, bisect, sys, re
sys.path.insert(0, '/home/claude/hb3/repo'); from pt_time import pt_to_utc
names = {a['id']: a['name'] for a in map(json.loads, gzip.open('/home/claude/claims/data/agents.jsonl.gz'))}
ev = collections.defaultdict(list)
for l in gzip.open('/home/claude/claims/data/events.jsonl.gz'):
    o = json.loads(l); d = o.get('data') or {}
    a = d.get('agentId') or d.get('speakerId')
    if a in names and o['created_at'] >= '2026-04-01':
        ev[names[a]].append(dt.datetime.fromisoformat(o['created_at'][:19]))
for v in ev.values(): v.sort()
def near(name, t, h=1):
    v = ev.get(name, []); i = bisect.bisect_left(v, t - dt.timedelta(hours=h))
    return i < len(v) and v[i] <= t + dt.timedelta(hours=h)
F = json.load(open(sys.argv[1]))
S = collections.defaultdict(lambda: dict(n=0, utc=0, pt=0, d0='9', d1='0', cats=collections.Counter()))
for f in F:
    ts = f.get('timestamp') or ''
    shape = re.sub(r'\d', '9', ts)
    m = re.search(r'(\d\d):(\d\d)', ts)
    if not m: continue
    dm = re.match(r'\[?(\d{4}-\d\d-\d\d)', ts); date = dm.group(1) if dm else f['_date']
    hh, mm = int(m.group(1)), int(m.group(2))
    s = S[shape]; s['n'] += 1; s['d0'] = min(s['d0'], f['_date']); s['d1'] = max(s['d1'], f['_date'])
    s['utc'] += near(f['model'], dt.datetime.strptime(date, '%Y-%m-%d').replace(hour=hh, minute=mm))
    s['pt'] += near(f['model'], pt_to_utc(date, hh, mm))
    if f['category'] in ('off-goal','emotional-or-erratic','surreptitious-or-deceptive','conflict','unsolicited-outreach'): s['cats']['mis'] += 1
for k, s in S.items():
    print('%-28s n=%5d  %s..%s  active as UTC %5.1f%%  as PT %5.1f%%  misaligned %d' % (k, s['n'], s['d0'], s['d1'], 100*s['utc']/s['n'], 100*s['pt']/s['n'], s['cats']['mis']))
