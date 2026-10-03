#!/usr/bin/env python3
"""Pre-registered analysis of the v0.3 fresh-month alert ratings (RATING_PLAN_V03.md).

Fixed on 3 Oct 2026, before any v0.3 alert existed. Do not change after ratings arrive.

    python tier1/rating_analysis_v03.py --summary fresh_summary.json \
        --ratings adam_v03.json greg_v03.json [--population N] --out result_v03.json
"""
import argparse
import json
import math

BURDEN_TARGET = 1.0          # alerts per observed week, village-wide (from TIER1_V02_SPEC.md)
MIN_FOR_PROPORTIONS = 5      # fewer rated alerts: counts only, no outcome category
YES = "yes"


def norm(v):
    if v is None:
        return None
    v = str(v).strip().lower()
    return {"y": "yes", "n": "no", "cant tell": "can't tell", "can't": "can't tell",
            "cannot tell": "can't tell", "unsure": "can't tell"}.get(v, v)


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def kappa(pairs):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "agreement": None, "kappa": None, "note": "no items rated by both"}
    po = sum(a == b for a, b in pairs) / n
    cats = {c for p in pairs for c in p}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    k = None if pe >= 1 else round((po - pe) / (1 - pe), 3)
    return {"n": n, "agreement": round(po, 3), "kappa": k,
            "note": None if k is not None else "kappa undefined: both raters used a single identical category"}


def analyse(summary, raters, population=None):
    names = [r.get("rater") or "rater%d" % i for i, r in enumerate(raters, 1)]
    ids = [x["sample_id"] for x in raters[0]["ratings"]]
    for r in raters[1:]:
        if [x["sample_id"] for x in r["ratings"]] != ids:
            raise ValueError("raters rated different items or in a different order")
    q1 = [[norm(x.get("q1_enough_to_decide")) for x in r["ratings"]] for r in raters]
    q2 = [[norm(x.get("q2_likely_harmful")) for x in r["ratings"]] for r in raters]
    n = len(ids)
    burden = summary.get("alerts_per_observed_week")
    out = {
        "plan": "RATING_PLAN_V03.md",
        "alerts_total": summary.get("alerts"),
        "alerts_rated": n,
        "population_if_sampled": population,
        "observed_days": summary.get("observed_days"),
        "burden_per_observed_week": burden,
        "burden_within_target": None if burden is None else burden <= BURDEN_TARGET,
        "q1_yes_by_rater": {nm: sum(v == YES for v in q) for nm, q in zip(names, q1)},
        "q2_counts_by_rater": {nm: {c: sum(v == c for v in q) for c in ("yes", "no", "can't tell", None)}
                               for nm, q in zip(names, q2)},
    }
    out["q2_counts_by_rater"] = {k: {str(c): v for c, v in d.items()} for k, d in out["q2_counts_by_rater"].items()}
    if len(raters) == 2:
        out["q1_agreement"] = kappa(list(zip(*q1)))
        out["q2_agreement_3cat"] = kappa(list(zip(*q2)))
        out["q2_agreement_yes_vs_not"] = kappa([(None if a is None else a == YES, None if b is None else b == YES)
                                                for a, b in zip(*q2)])
    both_q1 = sum(all(q[i] == YES for q in q1) for i in range(n))
    concern_any = sum(any(q[i] == YES for q in q2) for i in range(n))
    concern_all = sum(all(q[i] == YES for q in q2) for i in range(n))
    out["primary"] = {
        "actionable_both_q1_yes": {"k": both_q1, "n": n, "wilson95": wilson(both_q1, n)},
        "concerning_any_rater_q2_yes": {"k": concern_any, "n": n, "wilson95": wilson(concern_any, n)},
        "concerning_both_raters_q2_yes": {"k": concern_all, "n": n, "wilson95": wilson(concern_all, n)},
    }
    out["discordant_items"] = [
        {"sample_id": ids[i], "q1": [q[i] for q in q1], "q2": [q[i] for q in q2],
         "notes": [r["ratings"][i].get("notes", "") for r in raters]}
        for i in range(n) if len({q[i] for q in q1}) > 1 or len({q[i] for q in q2}) > 1]

    # Outcome category, fixed in advance
    if not summary.get("alerts"):
        cat = "silent"
        why = "No alerts on the fresh month. Report with feature prevalence; silence is not proof of safety."
    elif n < MIN_FOR_PROPORTIONS:
        cat = "too few to judge"
        why = "Fewer than %d alerts rated: report counts and each alert, no proportions." % MIN_FOR_PROPORTIONS
    else:
        within = burden is not None and burden <= BURDEN_TARGET
        precise = concern_any * 2 > n
        actionable = both_q1 * 2 > n
        if within and precise:
            cat = "useful urgent tier"
        elif within and not precise:
            cat = "quiet but imprecise"
        elif not within and precise:
            cat = "precise but too noisy to scale"
        else:
            cat = "not yet useful"
        why = ("burden %s target; %d/%d concerning by at least one rater (majority needed); "
               "%d/%d actionable by both (reported, not part of the category)" %
               ("within" if within else "over", concern_any, n, both_q1, n))
        out["actionable_majority"] = actionable
    out["outcome"] = {"category": cat, "basis": why}
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True)
    p.add_argument("--ratings", nargs="+", required=True)
    p.add_argument("--population", type=int)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    summary = json.load(open(a.summary, encoding="utf-8"))
    raters = [json.load(open(x, encoding="utf-8")) for x in a.ratings]
    res = analyse(summary, raters, a.population)
    json.dump(res, open(a.out, "w", encoding="utf-8"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
