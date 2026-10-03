#!/usr/bin/env python3
"""P8 run (round 7). Same setup as e2_run.py: frozen heatbot_model.json,
calibrate_v2's simulate, roster reviewed-filter, medium+high labels,
DeepSeek-V3.2 excluded, seed 0, 1000 cluster-bootstrap draws.

    python3 p8_run.py --train   training months (in-sample, for the P6 power
                                statement); prints results
    python3 p8_run.py --seal    held-out month; writes P8_SEALED/ and prints
                                NO result, only hashes
    python3 p8_run.py --verify  recompute hashes against P8_SEALED/MANIFEST.txt
"""
import datetime as dt, glob, hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
SEAL = os.path.join(HERE, "P8_SEALED")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

if "--verify" in sys.argv:
    bad = 0
    for line in open(os.path.join(SEAL, "MANIFEST.txt")):
        if not line.strip() or line.startswith("#"): continue
        h, p = line.split(None, 1); p = p.strip()
        ok = os.path.exists(p) and sha(p) == h; bad += not ok
        print("%s  %s" % ("ok  " if ok else "FAIL", p))
    sys.exit(1 if bad else 0)

mode = "--seal" if "--seal" in sys.argv else "--train"
model_hash = sha("heatbot_model.json")
exec(open("calibrate_v2.py").read().split("files = sorted")[0])
import forward_eval as FE
import p8_auc as P8
from pt_time import PT, UTC

files = sorted(glob.glob("events_all/*.json"))
period = [p for p in files if (p[-15:-5] >= SPLIT) == (mode == "--seal")]
eng, trace, alerts = simulate(period, copy.deepcopy(MODEL), copy.deepcopy(H.DEFAULT_CONFIG))
assert sha("heatbot_model.json") == model_hash

roster = {}
for p in glob.glob("monitor_days/*.json"):
    d = json.load(open(p)); roster[d["date"]] = {a["name"] for a in d.get("agents") or []}
pt_date = lambda t: t.replace(tzinfo=UTC).astimezone(PT).strftime("%Y-%m-%d")
rv = lambda t, a: a in roster.get(pt_date(t), ())
truth = FE.load_truth(json.load(open("all_findings.json")), pt_to_utc, severities=("medium", "high"))

res = P8.run_p8(trace, truth, reviewed=rv, alerts=alerts)
res["meta"] = {"period": mode[2:], "first": period[0][-15:-5], "last": period[-1][-15:-5],
               "event_files": len(period), "model_sha256": model_hash,
               "trace_rows_kept": sum(1 for t, a, _ in trace
                                      if a != "DeepSeek-V3.2" and not a.startswith("(village") and rv(t, a)),
               "agents_kept": len({a for t, a, _ in trace
                                   if a != "DeepSeek-V3.2" and not a.startswith("(village") and rv(t, a)})}

if mode == "--train":
    json.dump(res, open("p8_training.json", "w"), indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("meta", "sequence")}, default=str))
    for m, c in res["claims"].items():
        print(m, {k: c[k] for k in ("auc_within", "ci95", "category", "folds_counted",
                                     "folds_held", "agents_contributing", "positives", "moments")})
        print("   descriptive pooled AUC", res["descriptive"][m]["auc_pooled"])
else:
    os.makedirs(SEAL, exist_ok=True)
    out = os.path.join(SEAL, "p8_heldout_medhigh_roster_noDS.json")
    json.dump(res, open(out, "w"), indent=1, default=str)
    inputs = ["p8_auc.py", "test_p8_auc.py", "p8_run.py", "heatbot_model.json",
              "heatbot.py", "calibrate_v2.py", "forward_eval.py", "pt_time.py",
              "all_findings.json", "id2name.json", "v2.json"] + period + sorted(glob.glob("monitor_days/*.json"))
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    with open(os.path.join(SEAL, "MANIFEST.txt"), "w") as m:
        m.write("# P8 sealed result. Written %s by p8_run.py --seal. Nobody has read it.\n" % now)
        m.write("# Check with: python3 p8_run.py --verify\n")
        m.write("# held-out %s .. %s (%d event files); frozen model sha256 %s\n" % (
            period[0][-15:-5], period[-1][-15:-5], len(period), model_hash))
        m.write("# --- result\n%s  %s\n# --- inputs\n" % (sha(out), os.path.relpath(out, HERE)))
        for p in inputs: m.write("%s  %s\n" % (sha(p), p))
    sys.stderr.write("sealed; see P8_SEALED/MANIFEST.txt\n")
