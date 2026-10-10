"""Split the HF events export into per-Pacific-day files (as the village API keys its daily event files) in the village API's shape ({'events': [...]}, createdAt ISO,
data without 'output'), main village only. Args: out_dir"""
import gzip, json, os, sys, collections, datetime as dt
from zoneinfo import ZoneInfo
PT, UTC = ZoneInfo('America/Los_Angeles'), ZoneInfo('UTC')
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
MAIN = '00ebc425-074c-466f-ab2d-5aa2efa445aa'
days = collections.defaultdict(list); villages = collections.Counter()
for l in gzip.open('/home/claude/claims/data/events.jsonl.gz'):
    o = json.loads(l); villages[o.get('village_id')] += 1
    if o.get('village_id') != MAIN: continue
    d = dict(o.get('data') or {}); d.pop('output', None)
    ts = o['created_at'].replace(' ', 'T')
    if '.' not in ts: ts += '.000000'
    pday = dt.datetime.fromisoformat(ts[:19]).replace(tzinfo=UTC).astimezone(PT).strftime('%Y-%m-%d')
    days[pday].append({'id': o['id'], 'eventIndex': int(o['event_index']), 'createdAt': ts[:23] + 'Z', 'data': d})
for day, ev in days.items():
    ev.sort(key=lambda e: (e['eventIndex'], e['createdAt']))
    json.dump({'events': ev}, open(os.path.join(OUT, day + '.json'), 'w'), separators=(',', ':'))
print(dict(villages)); print(len(days), 'days', min(days), max(days))
