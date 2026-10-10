"""Model D = C's pipeline and data, with DeepSeek-V3.2 left out of training: its hours don't count when the word lists
are chosen, the channel weights are fitted, background rates are counted or thresholds are set. The engine still
scores it at run time. Run inside D/: python3 ../fit_model_noDS.py D"""
import json, os, sys, time, glob
sys.path.insert(0, os.getcwd())
import e3_fit as E
EXCLUDE = {'DeepSeek-V3.2'}
name = sys.argv[1]; t0 = time.time()
rows = E.load_cache(os.path.join(os.getcwd(), 'e3_cache.pkl'))
dates = sorted(os.path.basename(p)[:-5] for p in glob.glob('events_all/*.json'))
agents = sorted({r['agent'] for r in rows} - EXCLUDE)
print('hours', len(rows), 'kept agents', len(agents), 'excluded', sorted(EXCLUDE),
      'excluded hours', sum(1 for r in rows if r['agent'] in EXCLUDE), flush=True)
m = E.fit(agents, dates, thresholds=True, cache=rows)
m.update(version=3, name=name, label_fix='monitor stamps: bare HH:MM:SS = UTC, date-prefixed = PT',
         excluded_from_training=sorted(EXCLUDE))
json.dump(m, open('heatbot_model_%s.json' % name, 'w'), indent=1)
print('done in %.0fs; thresholds %s' % (time.time() - t0, json.dumps(m['thresholds'])))
for c, lex in m['lexicons'].items(): print(c, ', '.join(t for t, w in lex[:15]))
