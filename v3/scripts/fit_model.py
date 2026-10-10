"""Fit one model with the unchanged e3 pipeline. Run inside a model dir (B or C): python3 ../fit_model.py NAME
Writes heatbot_model_NAME.json and fit_NAME.log-friendly prints. Training = every day in events_all, all agents."""
import json, os, sys, time, glob
sys.path.insert(0, os.getcwd())
import e3_fit as E
name = sys.argv[1]
t0 = time.time()
rows = E.load_cache(os.path.join(os.getcwd(), 'e3_cache.pkl'))
dates = sorted(os.path.basename(p)[:-5] for p in glob.glob('events_all/*.json'))
agents = sorted({r['agent'] for r in rows})
print('hours', len(rows), 'agents', len(agents), 'dates', len(dates), dates[0], dates[-1], flush=True)
if '--lexcheck' in sys.argv:                      # B only: year-week fix must be a no-op on one year
    import lexicon as L, lexicon_orig as L0
    a = L.select(rows, hour_terms=lambda r: r['hour_terms']); b = L0.select(rows, hour_terms=lambda r: r['hour_terms'])
    print('lexicon identical with and without the (year, week) fix:', a == b); sys.exit(0)
m = E.fit(agents, dates, thresholds=True, cache=rows, verbose=False)
m['version'] = 3; m['label_fix'] = 'monitor stamps: bare HH:MM:SS = UTC, date-prefixed = PT'; m['name'] = name
json.dump(m, open('heatbot_model_%s.json' % name, 'w'), indent=1)
print('done in %.0fs; thresholds %s' % (time.time() - t0, json.dumps(m['thresholds'])))
for c, lex in m['lexicons'].items(): print(c, len(lex), ', '.join(t for t, w in lex[:15]))
