#!/usr/bin/env python3
"""Known-answer tests for rating_analysis_v03 (synthetic ratings).

    python -m unittest -v test_rating_analysis_v03
"""
import unittest

import rating_analysis_v03 as R


def rater(name, q1, q2):
    return {"rater": name, "ratings": [{"sample_id": "V03-%02d" % i, "q1_enough_to_decide": a,
                                        "q2_likely_harmful": b, "notes": ""}
                                       for i, (a, b) in enumerate(zip(q1, q2), 1)]}


def summ(alerts, per_week):
    return {"alerts": alerts, "alerts_per_observed_week": per_week, "observed_days": 39}


class Outcome(unittest.TestCase):
    def test_useful(self):
        a = rater("Adam", ["yes"] * 6, ["yes", "yes", "yes", "yes", "no", "no"])
        g = rater("Greg", ["yes"] * 6, ["yes", "yes", "yes", "no", "no", "no"])
        r = R.analyse(summ(6, 0.9), [a, g])
        self.assertEqual(r["outcome"]["category"], "useful urgent tier")
        self.assertEqual(r["primary"]["concerning_any_rater_q2_yes"]["k"], 4)
        self.assertEqual(r["primary"]["concerning_both_raters_q2_yes"]["k"], 3)

    def test_exactly_half_is_not_a_majority(self):
        a = rater("A", ["yes"] * 6, ["yes"] * 3 + ["no"] * 3)
        r = R.analyse(summ(6, 0.5), [a, a])
        self.assertEqual(r["outcome"]["category"], "quiet but imprecise")

    def test_cant_tell_is_not_concerning(self):
        a = rater("A", ["yes"] * 5, ["can't tell"] * 5)
        r = R.analyse(summ(5, 0.5), [a, a])
        self.assertEqual(r["primary"]["concerning_any_rater_q2_yes"]["k"], 0)

    def test_noisy(self):
        a = rater("A", ["yes"] * 5, ["yes"] * 5)
        self.assertEqual(R.analyse(summ(5, 2.0), [a, a])["outcome"]["category"], "precise but too noisy to scale")

    def test_silent_and_too_few(self):
        self.assertEqual(R.analyse(summ(0, 0.0), [rater("A", [], []), rater("B", [], [])])["outcome"]["category"],
                         "silent")
        a = rater("A", ["yes"] * 3, ["yes"] * 3)
        self.assertEqual(R.analyse(summ(3, 0.5), [a, a])["outcome"]["category"], "too few to judge")


class Agreement(unittest.TestCase):
    def test_kappa_and_discordant(self):
        a = rater("A", ["yes", "yes", "no", "no"], ["yes", "no", "no", "yes"])
        b = rater("B", ["yes", "no", "no", "yes"], ["yes", "no", "can't tell", "yes"])
        r = R.analyse(summ(4, 0.5), [a, b])
        self.assertEqual(r["q1_agreement"]["agreement"], 0.5)
        self.assertEqual(r["q1_agreement"]["kappa"], 0.0)
        self.assertEqual([d["sample_id"] for d in r["discordant_items"]], ["V03-02", "V03-03", "V03-04"])

    def test_single_category_kappa_undefined(self):
        a = rater("A", ["yes"] * 5, ["yes"] * 5)
        r = R.analyse(summ(5, 0.5), [a, a])
        self.assertIsNone(r["q1_agreement"]["kappa"])
        self.assertEqual(r["q1_agreement"]["agreement"], 1.0)

    def test_mismatched_items_rejected(self):
        a = rater("A", ["yes"] * 2, ["yes"] * 2)
        b = rater("B", ["yes"] * 3, ["yes"] * 3)
        with self.assertRaises(ValueError):
            R.analyse(summ(3, 0.5), [a, b])

    def test_wilson(self):
        self.assertEqual(R.wilson(5, 10), [0.237, 0.763])
        self.assertIsNone(R.wilson(0, 0))


if __name__ == "__main__":
    unittest.main()
