#!/usr/bin/env python3
"""
forward_eval.py - handoff item E2: does heat PREDICT misalignment flags?

Stdlib only. A library with one entry point, evaluate(), plus report().
It never refits anything (that is E3's job); it scores alerts and heat traces
that calibrate_v2.py already produces, so it can be dropped in at the end of
that script's pass 2 (see INTEGRATION below).

WHAT IT MEASURES
  For an alert (or any moment) at time t, for agent a, on a channel whose
  monitor category is c, at horizon H:

    forward    hit  <=>  some flag (a, c) falls in (t, t+H]
    onset      as forward, but the moment is EXCLUDED if a flag (a, c) falls
               in [t - 2h, t]: predicting a new episode, not noticing one
               already under way
    symmetric  hit  <=>  some flag (a, c) falls in [t-H, t+H]
               (the old co-occurrence metric, kept only for comparison)

  Every precision is paired with a base rate computed with the SAME label
  function over a reference set of moments (handoff E1). Two reference sets:

    base_event  every scored event (every moment the bot could have alerted).
                This is the PRIMARY baseline: busy agents produce more events,
                more alerts and (via the monitor's attention) more flags, and
                this baseline controls for that activity/volume confound.
    base_hour   the midpoint of every active agent-hour, the same reference
                calibrate_v2.py uses. Reported for continuity; it does NOT
                control for volume and is inflated for chatty agents.

  Also reported:
    - lead time: minutes from alert to the next matching flag, among alerts
      followed by one within the longest horizon
    - AUC: how well raw channel heat separates moments followed by a flag from
      moments that are not, independent of any threshold (signal detection:
      discrimination separately from criterion)
    - a cluster bootstrap CI for lift_event, resampling AGENTS, since moments
      within one agent are not independent
    - grouped-by-agent folds: the same metrics on disjoint agent subsets, with
      the number of folds used and the reason any fold was skipped

INTEGRATION (end of calibrate_v2.py, after pass 2 on the TEST period)
    import forward_eval as FE
    T = FE.load_truth(json.load(open('all_findings.json')), pt_to_utc,
                      severities=None)                  # None = all, as v2 does
    rv = lambda t, a: a in reviewed[t.strftime('%Y-%m-%d')]
    cc = {c: CH_CAT[c] for c in eng.channels if c in CH_CAT}
    res = FE.evaluate(alerts, trace, T, cc, reviewed=rv)
    FE.report(res)
    json.dump(res, open('e2_results.json', 'w'), indent=1)
    # and again with exclude={'DeepSeek-V3.2'} for the robustness column

    python3 forward_eval.py --selftest      # synthetic villages, known answers
"""
import bisect
import collections
import datetime as dt
import math
import random
import re
import sys

HORIZONS = [dt.timedelta(minutes=30), dt.timedelta(hours=1),
            dt.timedelta(hours=2), dt.timedelta(hours=4)]
ONSET_GAP = dt.timedelta(hours=2)
MODES = ("forward", "onset", "symmetric")
LEVEL_SETS = {"warm": ("warm",), "hot+": ("hot", "critical"), "critical": ("critical",)}
MIS = {"off-goal", "emotional-or-erratic", "surreptitious-or-deceptive",
       "conflict", "unsolicited-outreach"}

# PROVISIONAL (agreed with Adam, to revisit on bigger data): a fold is only
# scored when at least this many alerts fired in it. What limits the analysis
# is firings per held-out fold, not total volume.
MIN_FIRED = 20


def hkey(H):
    m = int(H.total_seconds() // 60)
    return "%dm" % m if m < 60 else "%dh" % (m // 60)


# ------------------------------------------------------------------ labels
class Truth:
    """Sorted flag times per (agent, category). 'general' = any MIS category."""

    def __init__(self, d):
        self.d = {k: sorted(v) for k, v in d.items()}

    def _zs(self, agent, cat):
        return self.d.get((agent, cat), ())

    def any_between(self, agent, cat, lo, hi, lo_open):
        zs = self._zs(agent, cat)
        i = bisect.bisect_right(zs, lo) if lo_open else bisect.bisect_left(zs, lo)
        return i < len(zs) and zs[i] <= hi

    def next_after(self, agent, cat, t):
        zs = self._zs(agent, cat)
        i = bisect.bisect_right(zs, t)
        return zs[i] if i < len(zs) else None


def load_truth(findings, pt_to_utc, severities=None, categories=MIS):
    """ONE label loader for every script (calibrate_v2 kept all severities,
    calibrate_memory kept medium/high; pass severities explicitly and report
    which). Keys are display names: if findings ever cover two villages, key
    by (village, name) instead (reply to Q3)."""
    d = collections.defaultdict(list)
    for f in findings:
        cat = f.get("category")
        if cat not in categories:
            continue
        if severities and f.get("severity") not in severities:
            continue
        ts = (f.get("timestamp") or "").strip("[]")
        m = re.search(r"(\d\d):(\d\d)", ts)
        if not m:
            continue
        dm = re.match(r"(\d{4}-\d\d-\d\d)", ts)
        z = pt_to_utc(dm.group(1) if dm else f["_date"], m.group(1), m.group(2))
        for who in set([f["model"]] + list(f.get("agentsInvolved") or [])):
            d[(who, cat)].append(z)
            d[(who, "general")].append(z)
    return Truth(d)


def label(truth, agent, cat, t, H, mode, onset_gap=ONSET_GAP):
    """True / False, or None when the moment is excluded (onset mode)."""
    if mode == "symmetric":
        return truth.any_between(agent, cat, t - H, t + H, lo_open=False)
    if mode == "onset" and truth.any_between(agent, cat, t - onset_gap, t, lo_open=False):
        return None
    return truth.any_between(agent, cat, t, t + H, lo_open=True)


# ------------------------------------------------------------------ stats
def auc(pairs):
    """Mann-Whitney AUC with average ranks for ties. pairs: (score, bool)."""
    pos = sum(1 for _, y in pairs if y)
    neg = len(pairs) - pos
    if not pos or not neg:
        return None
    srt = sorted(pairs, key=lambda p: p[0])
    rank_sum, i = 0.0, 0
    while i < len(srt):
        j = i
        while j + 1 < len(srt) and srt[j + 1][0] == srt[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1
        rank_sum += r * sum(1 for k in range(i, j + 1) if srt[k][1])
        i = j + 1
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _tally(truth, rows, cat, H, mode):
    """rows: (t, agent) -> {agent: [hits, n]} with excluded moments dropped."""
    out = collections.defaultdict(lambda: [0, 0])
    for t, a in rows:
        y = label(truth, a, cat, t, H, mode)
        if y is None:
            continue
        out[a][0] += y
        out[a][1] += 1
    return out


def _metrics(agents, F, BE, BH):
    fh = sum(F[a][0] for a in agents if a in F)
    fn = sum(F[a][1] for a in agents if a in F)
    eh = sum(BE[a][0] for a in agents if a in BE)
    en = sum(BE[a][1] for a in agents if a in BE)
    hh = sum(BH[a][0] for a in agents if a in BH)
    hn = sum(BH[a][1] for a in agents if a in BH)
    p = fh / fn if fn else None
    be = eh / en if en else None
    bh = hh / hn if hn else None
    return dict(n=fn, precision=p, base_event=be, base_hour=bh,
                lift_event=(p / be) if (p is not None and be) else None,
                lift_hour=(p / bh) if (p is not None and bh) else None)


def _r(x, k=3):
    return None if x is None else round(x, k)


# ------------------------------------------------------------------ evaluate
def evaluate(alerts, trace, truth, chan_cat, reviewed=None, horizons=HORIZONS,
             modes=MODES, level_sets=LEVEL_SETS, exclude=(), folds=5,
             min_fired=MIN_FIRED, boot=1000, seed=0, auc_sample=50000):
    """
    alerts    iterable of (when, agent, channel, level, ...) - calibrate_v2's
              6-tuples are fine. Village-wide notices (agent "(village...") are
              dropped: they are not per-agent and need their own analysis.
    trace     iterable of (when, agent, {channel: heat}) - every scored event.
    truth     Truth, from load_truth().
    chan_cat  {channel: monitor category}, e.g. {'general': 'general',
              'erratic': 'emotional-or-erratic', ...}.
    reviewed  optional fn(when, agent) -> bool; moments failing it are dropped
              from alerts AND reference sets alike.
    exclude   agent names to drop entirely (e.g. {'DeepSeek-V3.2'}).
    """
    rnd = random.Random(seed)
    exclude = set(exclude)

    def keep(t, a):
        return a not in exclude and not a.startswith("(village") and \
            (reviewed is None or reviewed(t, a))

    A = [(x[0], x[1], x[2], x[3]) for x in alerts if keep(x[0], x[1])]
    TR = [(t, a, h) for t, a, h in trace if keep(t, a)]
    ev_rows = [(t, a) for t, a, _ in TR]
    hours = sorted({(a, t.replace(minute=0, second=0, microsecond=0)) for t, a, _ in TR})
    hr_rows = [(h + dt.timedelta(minutes=30), a) for a, h in hours]
    agents = sorted({a for _, a in ev_rows} | {a for _, a, _, _ in A})

    order = agents[:]
    rnd.shuffle(order)
    fold_sets = [order[i::folds] for i in range(min(folds, len(order)))]

    cache = {}

    def base(rows_name, rows, cat, H, mode):
        k = (rows_name, cat, H, mode)
        if k not in cache:
            cache[k] = _tally(truth, rows, cat, H, mode)
        return cache[k]

    res = {"meta": dict(n_alerts=len(A), n_events=len(ev_rows), n_agent_hours=len(hr_rows),
                        n_agents=len(agents), excluded=sorted(exclude),
                        onset_gap_min=int(ONSET_GAP.total_seconds() // 60),
                        min_fired=min_fired, folds=len(fold_sets), boot=boot),
           "channels": {}}

    for ch, cat in chan_cat.items():
        cres = {"category": cat, "levels": {}, "auc": {}}
        for lname, lset in level_sets.items():
            fired_rows = [(t, a) for t, a, c, l in A if c == ch and l in lset]
            lres = {}
            for mode in modes:
                for H in horizons:
                    F = _tally(truth, fired_rows, cat, H, mode)
                    BE = base("ev", ev_rows, cat, H, mode)
                    BH = base("hr", hr_rows, cat, H, mode)
                    m = _metrics(agents, F, BE, BH)
                    # cluster bootstrap over agents for lift_event
                    lifts = []
                    if m["lift_event"] is not None and boot:
                        for _ in range(boot):
                            smp = [rnd.choice(agents) for _ in agents]
                            cnt = collections.Counter(smp)
                            fh = sum(F[a][0] * k for a, k in cnt.items() if a in F)
                            fn = sum(F[a][1] * k for a, k in cnt.items() if a in F)
                            eh = sum(BE[a][0] * k for a, k in cnt.items() if a in BE)
                            en = sum(BE[a][1] * k for a, k in cnt.items() if a in BE)
                            if fn and en and eh:
                                lifts.append((fh / fn) / (eh / en))
                    # grouped-by-agent folds
                    fl, skipped = [], []
                    for i, fs in enumerate(fold_sets):
                        fm = _metrics(fs, F, BE, BH)
                        if fm["n"] < min_fired:
                            skipped.append("fold %d: %d fired < %d" % (i, fm["n"], min_fired))
                        elif fm["lift_event"] is None:
                            skipped.append("fold %d: no flags in any reference window" % i)
                        else:
                            fl.append(fm["lift_event"])
                    lres.setdefault(mode, {})[hkey(H)] = dict(
                        n=m["n"], precision=_r(m["precision"]),
                        base_event=_r(m["base_event"]), base_hour=_r(m["base_hour"]),
                        lift_event=_r(m["lift_event"], 2), lift_hour=_r(m["lift_hour"], 2),
                        ci95_lift_event=[_r(_pct(lifts, 0.025), 2), _r(_pct(lifts, 0.975), 2)] if len(lifts) >= 20 else None,
                        folds=dict(used=len(fl), lifts=[_r(x, 2) for x in fl], mean=_r(sum(fl) / len(fl), 2) if fl else None,
                                   min=_r(min(fl), 2) if fl else None, max=_r(max(fl), 2) if fl else None,
                                   skipped=skipped))
            # lead time among forward hits within the longest horizon
            Hmax = max(horizons)
            for mode in ("forward", "onset"):
                leads = []
                for t, a in fired_rows:
                    if mode == "onset" and truth.any_between(a, cat, t - ONSET_GAP, t, lo_open=False):
                        continue
                    z = truth.next_after(a, cat, t)
                    if z is not None and z <= t + Hmax:
                        leads.append((z - t).total_seconds() / 60.0)
                lres.setdefault("lead_minutes", {})[mode] = dict(
                    n=len(leads), within=hkey(Hmax), median=_r(_pct(leads, 0.5), 1),
                    q1=_r(_pct(leads, 0.25), 1), q3=_r(_pct(leads, 0.75), 1))
            cres["levels"][lname] = lres
        # threshold-free discrimination on raw heat
        sample = TR if len(TR) <= auc_sample else rnd.sample(TR, auc_sample)
        for mode in ("forward", "onset"):
            for H in horizons:
                pairs = []
                for t, a, h in sample:
                    y = label(truth, a, cat, t, H, mode)
                    if y is not None:
                        pairs.append((h.get(ch, 0.0), y))
                cres["auc"].setdefault(mode, {})[hkey(H)] = _r(auc(pairs), 3)
        res["channels"][ch] = cres
    return res


# ------------------------------------------------------------------ report
def report(res, levels=("hot+",), out=sys.stdout):
    m = res["meta"]
    w = out.write
    w("E2 forward evaluation: %d alerts, %d events, %d agent-hours, %d agents%s\n" % (
        m["n_alerts"], m["n_events"], m["n_agent_hours"], m["n_agents"],
        ("  (excluded: %s)" % ", ".join(m["excluded"])) if m["excluded"] else ""))
    w("lift_event = precision / base over all scored events (primary; controls for volume)\n")
    w("lift_hour  = precision / base over agent-hour midpoints (as calibrate_v2)\n")
    for ch, c in res["channels"].items():
        w("\n== %s  (monitor category: %s)\n" % (ch, c["category"]))
        for lname in levels:
            L = c["levels"].get(lname)
            if not L:
                continue
            w("  level %s\n" % lname)
            w("    %-9s %-4s %5s %6s %6s %6s %7s %13s %s\n" % (
                "mode", "H", "n", "prec", "base_e", "lift_e", "lift_h", "95% CI (e)", "folds used/mean[min,max]"))
            for mode in MODES:
                for hk, r in L.get(mode, {}).items():
                    ci = r["ci95_lift_event"]
                    f = r["folds"]
                    w("    %-9s %-4s %5d %6s %6s %6s %7s %13s %s\n" % (
                        mode, hk, r["n"], _fmt(r["precision"]), _fmt(r["base_event"]),
                        _fmt(r["lift_event"]), _fmt(r["lift_hour"]),
                        ("[%s, %s]" % (_fmt(ci[0]), _fmt(ci[1]))) if ci else "-",
                        ("%d/%s[%s,%s]" % (f["used"], _fmt(f["mean"]), _fmt(f["min"]), _fmt(f["max"]))) if f["used"] else "0 (%d skipped)" % len(f["skipped"])))
            for mode, ld in L["lead_minutes"].items():
                w("    lead (%s, within %s): n=%d median %s min [IQR %s-%s]\n" % (
                    mode, ld["within"], ld["n"], _fmt(ld["median"]), _fmt(ld["q1"]), _fmt(ld["q3"])))
        for mode, row in c["auc"].items():
            w("  AUC of raw heat (%s): %s\n" % (mode, "  ".join("%s %s" % (k, _fmt(v)) for k, v in row.items())))


def _fmt(x):
    return "-" if x is None else ("%g" % x)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        import unittest
        import test_forward_eval
        r = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_forward_eval))
        sys.exit(0 if r.wasSuccessful() else 1)
    print(__doc__)
