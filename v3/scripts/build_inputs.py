"""Build the inputs for heatbot-v3 (runs before any fitting; looks at no outcome).

Writes into work/inputs/:
  findings_v2_fixed.json   the monitor findings v2 trained on (6 Apr-18 Sep), every stamp rewritten as explicit
                           'YYYY-MM-DD HH:MM:SS PT'. Bare stamps (HH:MM:SS, [HH:MM:SS], 6 Apr-27 Jul) are UTC; stamps
                           with a date prefix are Pacific. The unchanged pipeline (which reads every stamp as PT) then
                           places each finding at the right UTC moment.
  findings_eval.json       monitor findings 25 Aug-6 Oct (our own monitor fetch, which is complete on 25 Aug and 11 Sep
                           where v2's copy had 4 and 0 findings), same normalisation. Used only to score held-out weeks.
  findings_haiku.json      Haiku findings for 2 Apr 2025-5 Apr 2026, same shape. High-confidence findings keep their
                           category; the rest become category 'reviewed-only' (they mark the agent-day as reviewed,
                           never a label).
  roster/<date>.json       {'date', 'agents': [{'name'}]}: the monitor's roster for monitor days; for Haiku days, every
                           agent with a packet that day (Haiku reviewed every agent-day).
  id2name.json             v2's map plus main-village agents missing from it (HF agents table).
  v2_goals.json            agentGoals / villageGoals from the HF export, in the API's shape.
  name_tokens.json         lower-case word pieces of every main-village agent name (C's extra lexicon block list).
"""
import collections, datetime as dt, glob, gzip, json, os, re
from zoneinfo import ZoneInfo

PT, UTC = ZoneInfo('America/Los_Angeles'), ZoneInfo('UTC')
W = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(W, 'inputs'); os.makedirs(os.path.join(OUT, 'roster'), exist_ok=True)
HF = '/home/claude/claims/data/'
MIS = {'off-goal', 'emotional-or-erratic', 'surreptitious-or-deceptive', 'conflict', 'unsolicited-outreach'}


def pt_string(utc):
    return utc.replace(tzinfo=UTC).astimezone(PT).strftime('%Y-%m-%d %H:%M:%S PT')


def utc_on_pt_day(pt_day, hh, mm, ss):
    """A bare UTC clock time written on a Pacific village day -> UTC datetime (00:xx UTC belongs to the next UTC day)."""
    t = dt.datetime.strptime(pt_day, '%Y-%m-%d').replace(hour=hh, minute=mm, second=ss)
    if t.replace(tzinfo=UTC).astimezone(PT).strftime('%Y-%m-%d') != pt_day:
        t += dt.timedelta(days=1)
    return t


def normalise(stamp, pt_day):
    """-> ('YYYY-MM-DD HH:MM:SS PT', kind) or (None, 'unparsed')."""
    s = (stamp or '').strip().strip('[]').strip()
    m = re.match(r'(\d{4}-\d\d-\d\d) (\d\d):(\d\d)(?::(\d\d))?', s)
    if m:          # date prefix: Pacific, labelled or not (checked: 99.9-100% match agent activity as PT)
        return '%s %s:%s:%s PT' % (m.group(1), m.group(2), m.group(3), m.group(4) or '00'), 'pt'
    m = re.match(r'(\d\d):(\d\d)(?::(\d\d))?$', s)
    if m:          # bare clock time: UTC (checked: 100% match agent activity as UTC, 21% as PT)
        return pt_string(utc_on_pt_day(pt_day, int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))), 'utc'
    return None, 'unparsed'


def main():
    kinds = collections.Counter()
    # --- v2's own findings, fixed
    F = json.load(open(os.path.join(W, 'common', 'all_findings.json')))
    fixed = []
    for f in F:
        g = dict(f); g['timestamp_original'] = f.get('timestamp')
        g['timestamp'], k = normalise(f.get('timestamp'), f['_date']); kinds['v2:' + k] += 1
        fixed.append(g)
    json.dump(fixed, open(os.path.join(OUT, 'findings_v2_fixed.json'), 'w'))
    # --- held-out monitor findings (our fetch), 25 Aug - 6 Oct
    late, roster = [], {}
    for p in sorted(glob.glob('/home/claude/misalign/monitor/2026-*.json')):
        d = json.load(open(p))
        roster[d['date']] = sorted({a['name'] for a in d.get('agents') or []})
        if not ('2026-08-25' <= d['date'] <= '2026-10-06'):
            continue
        for f in d['findings']:
            g = dict(f, _date=d['date']); g['timestamp_original'] = f.get('timestamp')
            g['timestamp'], k = normalise(f.get('timestamp'), d['date']); kinds['eval:' + k] += 1
            late.append(g)
    json.dump(late, open(os.path.join(OUT, 'findings_eval.json'), 'w'))
    # cross-check: our fetch vs v2's file on the shared days (same findings, same stamps)
    ours = collections.Counter(); theirs = collections.Counter(f['_date'] for f in F)
    for p in glob.glob('/home/claude/misalign/monitor/2026-*.json'):
        d = json.load(open(p))
        if d['date'] <= '2026-09-18': ours[d['date']] = len(d['findings'])
    diff = {k: (theirs[k], ours[k]) for k in set(ours) | set(theirs) if theirs[k] != ours[k]}
    print('monitor days where our fetch differs from v2 all_findings.json:', len(diff), sorted(diff.items())[:8])
    # --- Haiku findings, old year
    idx = json.load(open('/home/claude/misalign/data/agent_days.json'))
    hk = []
    for l in open('/home/claude/misalign/data/findings_combined.jsonl'):
        r = json.loads(l)
        if r['source'] != 'haiku' or r['day'] >= '2026-04-06':
            continue
        m = re.match(r'(\d\d):(\d\d):(\d\d)', r.get('time') or '')
        if not m:
            kinds['haiku:unparsed'] += 1; continue
        ts = pt_string(utc_on_pt_day(r['day'], int(m.group(1)), int(m.group(2)), int(m.group(3))))
        high = r.get('confidence') == 'high' and r.get('evidence_verified') is not False
        hk.append(dict(_date=r['day'], model=r['agent'], timestamp=ts, category=r['category'] if high else 'reviewed-only',
                       category_original=r['category'], severity=r.get('severity'), confidence=r.get('confidence'),
                       agentsInvolved=[a for a in (r.get('agentsInvolved') or []) if isinstance(a, str)],
                       heading=r.get('heading'), id=r['id'], source='haiku'))
        kinds['haiku:' + ('label' if high else 'reviewed-only')] += 1
    json.dump(hk, open(os.path.join(OUT, 'findings_haiku.json'), 'w'))
    for k, v in idx.items():
        if v['day'] < '2026-04-06':
            roster.setdefault(v['day'], [])
            roster[v['day']] = sorted(set(roster[v['day']]) | {v['agent']})
    for d, names in roster.items():
        json.dump({'date': d, 'agents': [{'name': n} for n in names]}, open(os.path.join(OUT, 'roster', d + '.json'), 'w'))
    # --- names, goals
    i2n = json.load(open(os.path.join(W, 'common', 'id2name.json')))
    agents = [json.loads(l) for l in gzip.open(HF + 'agents.jsonl.gz')]
    clash = [(a['id'], i2n[a['id']], a['name']) for a in agents if a['id'] in i2n and i2n[a['id']] != a['name']]
    for a in agents:
        i2n.setdefault(a['id'], a['name'])
    json.dump(i2n, open(os.path.join(OUT, 'id2name.json'), 'w'), indent=0)
    toks = sorted({p for a in agents for w in re.split(r'[^a-z]+', a['name'].lower()) for p in [w] if len(p) >= 3})
    json.dump(toks, open(os.path.join(OUT, 'name_tokens.json'), 'w'))
    iso = lambda s: None if not s else s.replace(' ', 'T')[:19] + '.000Z'
    ag = [dict(id=g['id'], agentId=g['agent_id'], name=g['name'], shortName=g.get('short_name'), description=g.get('description'),
               startTime=iso(g['start_time']), endTime=iso(g.get('end_time'))) for g in map(json.loads, gzip.open(HF + 'agent_goals.jsonl.gz'))]
    vg = [dict(id=g['id'], villageId=g['village_id'], goal=g['goal'], startTime=iso(g['start_time']), endTime=iso(g.get('end_time')))
          for g in map(json.loads, gzip.open(HF + 'village_goals.jsonl.gz'))]
    json.dump(dict(agentGoals=ag, villageGoals=vg), open(os.path.join(OUT, 'v2_goals.json'), 'w'))
    # cross-check goals with v2's API copy
    v2 = json.load(open(os.path.join(W, 'common', 'v2.json')))
    key = lambda g: (g.get('agentId'), g['name'], (g['startTime'] or '')[:16], (g.get('endTime') or '')[:16])
    a_api, a_hf = {key(g) for g in v2['agentGoals']}, {key(g) for g in ag}
    vkey = lambda g: (g['goal'], (g['startTime'] or '')[:16], (g.get('endTime') or '')[:16])
    print('agent goals: api %d hf %d, api-only %d, hf-only %d' % (len(a_api), len(a_hf), len(a_api - a_hf), len(a_hf - a_api)))
    print('village goals: api-only %d, hf-only %d' % (len({vkey(g) for g in v2['villageGoals']} - {vkey(g) for g in vg}),
                                                      len({vkey(g) for g in vg} - {vkey(g) for g in v2['villageGoals']})))
    print('id clashes (v2 name vs HF name):', clash)
    print('stamp kinds:', dict(kinds))
    print('roster days:', len(roster), min(roster), max(roster))


if __name__ == '__main__':
    main()
