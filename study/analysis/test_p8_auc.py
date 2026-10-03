#!/usr/bin/env python3
"""
test_p8_auc.py - known-answer tests for the P8 within-agent AUC claim.

The key scenario is the between-agent confound: a village where heat says
WHO gets flagged but nothing about WHEN. The pooled AUC must look good and
the within-agent AUC must sit at 0.5; otherwise P8 would measure the wrong
thing.

    python3 -m unittest -v test_p8_auc
"""
import datetime as dt
import random
import unittest

import forward_eval as FE
import p8_auc as P

T0 = dt.datetime(2026, 9, 1, 8)
M = dt.timedelta(minutes=1)


class Core(unittest.TestCase):
    def test_mw_u_matches_forward_eval_auc(self):
        rnd = random.Random(3)
        for _ in range(20):
            ps = [(round(rnd.random(), 1), rnd.random() < 0.3) for _ in range(60)]
            U, p, n = P.mw_u(ps)
            ref = FE.auc(ps)
            if ref is not None:
                self.assertAlmostEqual(U / (p * n), ref, places=12)

    def test_ties_count_half(self):
        U, p, n = P.mw_u([(1.0, True), (1.0, False)])
        self.assertEqual((U, p, n), (0.5, 1, 1))

    def test_perfect_within_separation(self):
        stats = P.per_agent({"a": [(2, True), (1, False)], "b": [(9, True), (8, False)]})
        self.assertEqual(P.within_auc(stats), 1.0)

    def test_between_agent_confound_is_not_rewarded(self):
        # 'hot' agent: always heat 5-6, often flagged. 'cool' agent: heat 1-2, rarely.
        # Inside each agent, flagged and unflagged moments have IDENTICAL heat values.
        hot = [(5.0, True), (6.0, True), (5.0, False), (6.0, False)] * 5
        cool = [(1.0, True), (2.0, True)] + [(1.0, False), (2.0, False)] * 10
        pba = {"hot": hot, "cool": cool}
        self.assertAlmostEqual(P.within_auc(P.per_agent(pba)), 0.5, places=12)
        pooled = P.describe(pba)["auc_pooled"]
        self.assertGreater(pooled, 0.7)          # pooled is fooled by "who"

    def test_bootstrap_weight_equals_duplication(self):
        pba = {"a": [(3, True), (1, False), (2, False)], "b": [(1, True), (2, False)]}
        w = P.within_auc(P.per_agent(pba), {"a": 2, "b": 1})
        dup = P.within_auc(P.per_agent({"a": pba["a"], "a2": pba["a"], "b": pba["b"]}))
        self.assertAlmostEqual(w, dup, places=12)

    def test_agents_without_pairs_contribute_nothing(self):
        stats = P.per_agent({"a": [(2, True), (1, False)], "z": [(0, False)] * 5})
        self.assertEqual(P.within_auc(stats), 1.0)


class Rules(unittest.TestCase):
    def test_categories_are_exclusive_and_ordered(self):
        C = P.classify
        self.assertEqual(C(0.6, 0.8, 3, 3), "untestable")          # counting first
        self.assertEqual(C(0.55, 0.70, 5, 4), "demonstrated")
        self.assertEqual(C(0.52, 0.58, 5, 5), "real_but_small")    # the old overlap case
        self.assertEqual(C(0.45, 0.58, 5, 2), "ruled_out")
        self.assertEqual(C(0.55, 0.70, 5, 3), "inconclusive")      # CI ok, folds don't hold
        self.assertEqual(C(0.45, 0.66, 4, 4), "inconclusive")

    def test_fixed_sequence_stops_at_first_failure(self):
        r = {"symmetric": {"category": "demonstrated"},
             "forward": {"category": "inconclusive"},
             "onset": {"category": "demonstrated"}}
        s = P.sequence(r)
        self.assertEqual(s["headline"], "symmetric")      # onset NOT claimed
        self.assertEqual(s["tested_in_sequence"], ["symmetric", "forward"])

    def test_real_but_small_passes_the_gate(self):
        r = {m: {"category": "real_but_small"} for m in P.SEQUENCE}
        self.assertEqual(P.sequence(r)["headline"], "onset")

    def test_fold_needs_min_pos(self):
        fs = [["a"], ["b"], ["c"], ["d"], ["e"]]
        pba = {k: [(1, True)] * 19 + [(0, False)] * 50 for k in "abcd"}
        pba["e"] = [(1, True)] * 20 + [(0, False)] * 50
        res = P.evaluate_claim(pba, fs, boot=50)
        self.assertEqual(res["folds_counted"], 1)
        self.assertEqual(res["category"], "untestable")

    def test_folds_match_forward_eval_recipe(self):
        agents = ["ag%02d" % i for i in range(31)]
        order = sorted(agents)
        random.Random(0).shuffle(order)
        self.assertEqual(P.fe_fold_sets(set(agents)), [order[i::5] for i in range(5)])


def village(n_agents, days, precursor, seed=1):
    """Each agent has its own baseline heat (spread widely), events every 5 min,
    ~1 flag per agent-day. If precursor: heat rises by +3 in the 45 min before
    each flag. Flag counts also scale with baseline, so 'who' is informative."""
    rnd = random.Random(seed)
    trace, d = [], {}
    for i in range(n_agents):
        a = "ag%02d" % i
        base = rnd.uniform(0, 10)
        flags = []
        for day in range(days):
            for _ in range(1 + (base > 5)):
                flags.append(T0 + dt.timedelta(days=day, minutes=rnd.randint(90, 470)))
        d[(a, "general")] = flags
        for day in range(days):
            t = T0 + dt.timedelta(days=day)
            while t < T0 + dt.timedelta(days=day, hours=8):
                h = base + rnd.gauss(0, 1)
                if precursor and any(dt.timedelta(0) < f - t <= 45 * M for f in flags):
                    h += 3
                trace.append((t, a, {"general": h}))
                t += 5 * M
    return trace, FE.Truth(d)


class EndToEnd(unittest.TestCase):
    def test_planted_precursor_is_demonstrated(self):
        trace, truth = village(30, 6, precursor=True)
        r = P.run_p8(trace, truth, exclude=(), boot=200)
        on = r["claims"]["onset"]
        self.assertGreater(on["auc_within"], 0.7)
        self.assertEqual(on["category"], "demonstrated")
        self.assertEqual(r["sequence"]["headline"], "onset")

    def test_who_without_when_is_not_demonstrated(self):
        trace, truth = village(30, 6, precursor=False)
        r = P.run_p8(trace, truth, exclude=(), boot=200)
        on = r["claims"]["onset"]
        self.assertLess(abs(on["auc_within"] - 0.5), 0.05)
        self.assertNotIn(on["category"], P.PASSING)
        # the pooled number would have looked like a signal
        self.assertGreater(r["descriptive"]["onset"]["auc_pooled"], 0.55)

    def test_excluded_agent_is_dropped(self):
        trace, truth = village(10, 2, precursor=True)
        r = P.run_p8(trace, truth, exclude=("ag00",), boot=20)
        agents = sum(f["agents"] for f in r["claims"]["onset"]["folds"])
        self.assertEqual(agents, 9)


if __name__ == "__main__":
    unittest.main()
