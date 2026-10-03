#!/usr/bin/env python3
"""
p8_auc.py - the threshold-free confirmatory claim for E2 (P8, round 5).

Question: does an agent's `general` heat run higher shortly before that
SAME agent's flags than at its other moments?  ("when", not "who")

Statistic: WITHIN-AGENT AUC. Positive and negative moments are only ever
compared inside one agent; pairs are pooled across agents:

    AUC_within = sum_i U_i / sum_i (pos_i * neg_i)

(U_i = Mann-Whitney count for agent i, ties = 1/2). Equivalent to a
weighted mean of per-agent AUCs with weights pos_i * neg_i. An agent that
runs hot all the time gains nothing from it: only its own ups and downs
count. The pooled AUC (which also rewards "hotter agents get flagged more")
is reported descriptively only.

Decision rule (pre-registered, round 5):
  - cluster bootstrap over agents, 1000 draws, seed 0, 95% percentile CI
  - seed-0 agent folds built exactly as forward_eval.evaluate builds them
  - a fold COUNTS if it has >= MIN_POS positive moments (from agents that
    contribute pairs); fewer than 4 counting folds -> untestable
  - a fold HOLDS if its within-agent AUC > 0.5
  - categories, applied in this order (each result lands in exactly one):
        untestable     fewer than 4 folds count
        demonstrated   CI lower > 0.5, >= 4 folds hold, CI upper >= SESOI
        real_but_small CI lower > 0.5, >= 4 folds hold, CI upper <  SESOI
        ruled_out      CI upper < SESOI (and not the above)
        inconclusive   everything else
  - fixed sequence: symmetric (real-time) -> forward -> onset. Go on only
    while the claim is demonstrated or real_but_small; the headline is the
    last one that passed. Every claim's category is reported regardless.

Stdlib only.  python3 -m unittest -v test_p8_auc
"""
import datetime as dt
import random

import forward_eval as FE

SESOI = 0.60            # Adam, round 5: smallest AUC of interest
MIN_POS = 20            # positive moments needed for a fold to count
SEQUENCE = ("symmetric", "forward", "onset")
PASSING = ("demonstrated", "real_but_small")
TOP_Q = (0.01, 0.05)    # descriptive top-heat precision


# ------------------------------------------------------------------ core
def mw_u(pairs):
    """(U, pos, neg) for [(score, bool)]. U counts pos>neg pairs, ties 1/2."""
    srt = sorted(pairs, key=lambda p: p[0])
    U, neg_below, i = 0.0, 0, 0
    pos = neg = 0
    while i < len(srt):
        j = i
        while j < len(srt) and srt[j][0] == srt[i][0]:
            j += 1
        gp = sum(1 for k in range(i, j) if srt[k][1])
        gn = (j - i) - gp
        U += gp * (neg_below + 0.5 * gn)
        neg_below += gn
        pos += gp
        neg += gn
        i = j
    return U, pos, neg


def per_agent(pairs_by_agent):
    """{agent: (U, P=pos*neg, pos, neg)}"""
    out = {}
    for a, pairs in pairs_by_agent.items():
        U, p, n = mw_u(pairs)
        out[a] = (U, p * n, p, n)
    return out


def within_auc(stats, weights=None, agents=None):
    """Pooled-within AUC over `agents` (default all); weights = bootstrap counts."""
    agents = list(stats) if agents is None else agents
    num = den = 0.0
    for a in agents:
        w = 1.0 if weights is None else weights.get(a, 0)
        U, P, _, _ = stats[a]
        num += w * U
        den += w * P
    return num / den if den else None


def boot_ci(stats, agents, boot, seed):
    rnd = random.Random(seed)
    vals = []
    for _ in range(boot):
        w = {}
        for _ in agents:
            a = agents[rnd.randrange(len(agents))]
            w[a] = w.get(a, 0) + 1
        v = within_auc(stats, w, agents)
        if v is not None:
            vals.append(v)
    return FE._pct(vals, 0.025), FE._pct(vals, 0.975), len(vals)


def fe_fold_sets(agents, folds=5, seed=0):
    """Exactly forward_eval.evaluate's recipe: sorted agents, Random(seed).shuffle,
    round-robin. Pass the SAME agent set E2 used (event agents | alert agents)."""
    order = sorted(agents)
    random.Random(seed).shuffle(order)
    return [order[i::folds] for i in range(min(folds, len(order)))]


def classify(lo, hi, counted, held, sesoi=SESOI):
    if counted < 4:
        return "untestable"
    if lo is not None and lo > 0.5 and held >= 4:
        return "demonstrated" if hi >= sesoi else "real_but_small"
    if hi is not None and hi < sesoi:
        return "ruled_out"
    return "inconclusive"


def sequence(results, order=SEQUENCE):
    """Fixed-sequence gatekeeping. results: {mode: {'category': ...}}."""
    passed, tested = [], []
    for m in order:
        tested.append(m)
        if results[m]["category"] in PASSING:
            passed.append(m)
        else:
            break
    return {"tested_in_sequence": tested, "passed": passed,
            "headline": passed[-1] if passed else None}


# ------------------------------------------------------------------ claim
def evaluate_claim(pairs_by_agent, fold_sets, boot=1000, seed=0,
                   min_pos=MIN_POS, sesoi=SESOI):
    stats = per_agent(pairs_by_agent)
    agents = sorted(stats)
    point = within_auc(stats)
    lo, hi, nb = boot_ci(stats, agents, boot, seed)
    folds = []
    for fs in fold_sets:
        fa = [a for a in fs if a in stats]
        npos = sum(stats[a][2] for a in fa if stats[a][1] > 0)
        v = within_auc(stats, agents=fa)
        counts = npos >= min_pos and v is not None
        folds.append({"agents": len(fa), "positives": npos,
                      "auc": None if v is None else round(v, 4),
                      "counts": counts, "holds": bool(counts and v > 0.5)})
    counted = sum(f["counts"] for f in folds)
    held = sum(f["holds"] for f in folds)
    return {"auc_within": None if point is None else round(point, 4),
            "ci95": [None if lo is None else round(lo, 4),
                     None if hi is None else round(hi, 4)],
            "boot_valid": nb, "folds": folds, "folds_counted": counted,
            "folds_held": held,
            "agents_contributing": sum(1 for a in agents if stats[a][1] > 0),
            "positives": sum(s[2] for s in stats.values()),
            "moments": sum(s[2] + s[3] for s in stats.values()),
            "category": classify(lo, hi, counted, held, sesoi)}


# ------------------------------------------------------------------ descriptives
def describe(pairs_by_agent):
    """Descriptive only - never part of the decision."""
    allp = [p for ps in pairs_by_agent.values() for p in ps]
    out = {"auc_pooled": FE.auc(allp)}
    per = sorted(v for v in (FE.auc(ps) for ps in pairs_by_agent.values())
                 if v is not None)
    out["per_agent_auc"] = {"n": len(per), "median": FE._pct(per, 0.5),
                            "iqr": [FE._pct(per, 0.25), FE._pct(per, 0.75)],
                            "above_half": sum(1 for v in per if v > 0.5)}
    base = sum(1 for _, y in allp if y) / len(allp) if allp else None
    out["base"] = base
    for q in TOP_Q:
        k = max(1, int(round(len(allp) * q)))
        top = sorted(allp, key=lambda p: -p[0])[:k]
        prec = sum(1 for _, y in top if y) / k
        own = []   # each agent's own top q: "anomalies relative to itself"
        for ps in pairs_by_agent.values():
            kk = max(1, int(round(len(ps) * q)))
            own += sorted(ps, key=lambda p: -p[0])[:kk]
        prec_own = sum(1 for _, y in own if y) / len(own) if own else None
        key = "top%g%%" % (q * 100)
        out[key] = {"pooled_precision": prec,
                    "pooled_lift": prec / base if base else None,
                    "own_baseline_precision": prec_own,
                    "own_baseline_lift": prec_own / base if base and prec_own is not None else None}
    return out


# ------------------------------------------------------------------ run
def pairs_for(trace, truth, mode, H, channel="general", cat="general"):
    """{agent: [(heat, label)]}; onset-excluded moments dropped."""
    out = {}
    for t, a, h in trace:
        y = FE.label(truth, a, cat, t, H, mode)
        if y is None:
            continue
        out.setdefault(a, []).append((h.get(channel, 0.0), bool(y)))
    return out


def run_p8(trace, truth, reviewed=None, exclude=("DeepSeek-V3.2",), alerts=(),
           H=dt.timedelta(hours=1), folds=5, seed=0, boot=1000,
           min_pos=MIN_POS, sesoi=SESOI, channel="general"):
    """trace: [(when, agent, {channel: heat})] - every scored event (E2's trace).
    alerts: E2's alerts, ONLY so the fold agent set matches forward_eval's."""
    def keep(t, a):
        return a not in exclude and not a.startswith("(village") and \
            (reviewed is None or reviewed(t, a))
    TR = [(t, a, h) for t, a, h in trace if keep(t, a)]
    fold_agents = {a for _, a, _ in TR} | {x[1] for x in alerts if keep(x[0], x[1])}
    fold_sets = fe_fold_sets(fold_agents, folds, seed)
    res = {"settings": {"H": FE.hkey(H), "seed": seed, "boot": boot,
                        "min_pos": min_pos, "sesoi": sesoi, "exclude": list(exclude),
                        "channel": channel, "sequence": list(SEQUENCE)},
           "claims": {}, "descriptive": {}}
    for mode in SEQUENCE:
        pba = pairs_for(TR, truth, mode, H, channel)
        res["claims"][mode] = evaluate_claim(pba, fold_sets, boot, seed, min_pos, sesoi)
        res["descriptive"][mode] = describe(pba)
    res["sequence"] = sequence(res["claims"])
    return res
