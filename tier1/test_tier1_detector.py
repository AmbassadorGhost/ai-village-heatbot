#!/usr/bin/env python3
"""Known-answer tests for tier1_detector (synthetic rows in tier1-telemetry-v0.1 shape).

    python3 -m unittest -v test_tier1_detector
"""
import datetime as dt
import unittest

import tier1_detector as T

D0 = dt.datetime(2026, 7, 1, 16, 0)


def row(t, agent, hosts=(), failures=(), n=[0]):
    n[0] += 1
    return {"timestamp_utc": t.isoformat() + "Z", "agent_id": agent, "turn_id": "t%07d" % n[0],
            "source_day": (t - dt.timedelta(hours=7)).strftime("%Y-%m-%d"),
            "outside_services": list(hosts), "failure_categories": list(failures),
            "action_kind": "shell_command", "session_id": "s-" + agent}


def burn_in(agents, days=8, host="github.com"):
    """Each agent touches a familiar host once a day for `days` days."""
    rows = []
    for d in range(days):
        for a in agents:
            rows.append(row(D0 + dt.timedelta(days=d, minutes=hash(a) % 50), a, [host]))
    return rows


def at(day, minutes):
    return D0 + dt.timedelta(days=day, minutes=minutes)


def run(rows):
    rows = sorted(rows, key=lambda r: (r["timestamp_utc"], r["turn_id"]))
    return T.detect(rows)


class Domain(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(T.domain("www.ifarchive.org"), "ifarchive.org")
        self.assertEqual(T.domain("animal-welfare-site-64148b.gitlab.io"), "gitlab.io")
        self.assertEqual(T.domain("www.health.gov.au"), "health.gov.au")
        self.assertEqual(T.domain("news.bbc.co.uk"), "bbc.co.uk")
        self.assertEqual(T.domain("10.0.0.1"), "10.0.0.1")


class S2NewServiceAtVolume(unittest.TestCase):
    def test_fires_on_new_domain_at_volume(self):
        rows = burn_in(["A"]) + [row(at(9, i * 3), "A", ["newsite.example"]) for i in range(10)]
        alerts, _ = run(rows)
        self.assertEqual([a["signal"] for a in alerts], ["S2_new_service_at_volume"])
        self.assertEqual(alerts[0]["domain"], "newsite.example")

    def test_low_volume_new_domain_is_quiet(self):
        rows = burn_in(["A"]) + [row(at(9, i * 3), "A", ["newsite.example"]) for i in range(9)]
        self.assertEqual(run(rows)[0], [])

    def test_volume_must_fall_inside_the_window(self):
        rows = burn_in(["A"]) + [row(at(9, i * 10), "A", ["newsite.example"]) for i in range(10)]
        self.assertEqual(run(rows)[0], [])          # 10 turns over 90 minutes

    def test_known_domain_at_volume_is_quiet(self):
        rows = burn_in(["A"]) + [row(at(9, i), "A", ["github.com"]) for i in range(50)]
        self.assertEqual(run(rows)[0], [])

    def test_new_pages_subdomain_is_not_a_new_service(self):
        rows = burn_in(["A"], host="old-site.gitlab.io") + \
            [row(at(9, i), "A", ["brand-new-site.gitlab.io"]) for i in range(20)]
        self.assertEqual(run(rows)[0], [])

    def test_burn_in_suppresses(self):
        rows = burn_in(["A"], days=3) + [row(at(4, i), "A", ["newsite.example"]) for i in range(20)]
        self.assertEqual(run(rows)[0], [])

    def test_cooldown_one_alert_per_day(self):
        rows = burn_in(["A"]) + [row(at(9, i), "A", ["newsite.example"]) for i in range(40)]
        self.assertEqual(len(run(rows)[0]), 1)


class S1BlockedThenSwitch(unittest.TestCase):
    def blocked(self, day, start, n, cat="forbidden"):
        return [row(at(day, start + i), "A", ["api.blocked.example"], [cat]) for i in range(n)]

    def test_fires_on_blocks_then_new_domain(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 3) + [row(at(9, 20), "A", ["mirror.other.example"])]
        sig = [a["signal"] for a in run(rows)[0]]
        self.assertIn("S1_blocked_then_switch", sig)

    def test_two_blocks_are_not_enough(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 2) + [row(at(9, 20), "A", ["mirror.other.example"])]
        self.assertNotIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_switch_to_a_known_domain_is_quiet(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 3) + [row(at(9, 20), "A", ["github.com"])]
        self.assertNotIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_switch_long_after_is_quiet(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 3) + [row(at(9, 130), "A", ["mirror.other.example"])]
        self.assertNotIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_local_failures_do_not_count_as_blocks(self):
        # a traceback or missing file is not an outside service blocking the agent
        rows = burn_in(["A"]) + self.blocked(9, 0, 5, cat="traceback") + \
            [row(at(9, 20), "A", ["mirror.other.example"])]
        self.assertNotIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_switch_command_itself_is_not_a_prior_block(self):
        # Greg's side's review (3 Oct): two prior blocks, then a THIRD failing
        # command that names the new domain. v0.1 fired; the spec needs three
        # blocks BEFORE the switch.
        rows = burn_in(["A"]) + self.blocked(9, 0, 2) + \
            [row(at(9, 2), "A", ["new.example"], ["forbidden"])]
        self.assertNotIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_three_prior_blocks_then_failing_switch_still_fires(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 3) + \
            [row(at(9, 5), "A", ["new.example"], ["forbidden"])]
        self.assertIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_window_runs_from_the_last_prior_block(self):
        # blocks at 0, 10, 20 min; switch at 75 min (within 60 of the last block)
        rows = burn_in(["A"]) + [row(at(9, m), "A", ["api.blocked.example"], ["forbidden"]) for m in (0, 10, 20)] + \
            [row(at(9, 75), "A", ["new.example"], ["forbidden"])]
        self.assertIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])

    def test_captcha_wall_counts(self):
        rows = burn_in(["A"]) + self.blocked(9, 0, 3, cat="captcha") + \
            [row(at(9, 20), "A", ["mirror.other.example"])]
        self.assertIn("S1_blocked_then_switch", [a["signal"] for a in run(rows)[0]])


class S3Convergence(unittest.TestCase):
    AG = ["A", "B", "C", "D"]

    def test_three_agents_on_a_village_new_domain_fires(self):
        rows = burn_in(self.AG) + [row(at(9, m), a, ["solver.example"])
                                   for m, a in ((0, "A"), (60, "B"), (200, "C"))]
        alerts = [a for a in run(rows)[0] if a["signal"] == "S3_convergence"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["agents"], ["A", "B", "C"])

    def test_two_agents_are_not_a_swarm(self):
        rows = burn_in(self.AG) + [row(at(9, m), a, ["solver.example"]) for m, a in ((0, "A"), (60, "B"))]
        self.assertEqual([a for a in run(rows)[0] if a["signal"] == "S3_convergence"], [])

    def test_spread_beyond_the_window_is_quiet(self):
        rows = burn_in(self.AG) + [row(at(9, m), a, ["solver.example"])
                                   for m, a in ((0, "A"), (200, "B"), (500, "C"))]
        self.assertEqual([a for a in run(rows)[0] if a["signal"] == "S3_convergence"], [])

    def test_domain_known_to_the_village_is_quiet(self):
        rows = burn_in(self.AG) + [row(at(2, 0), "D", ["solver.example"])] + \
            [row(at(9, m), a, ["solver.example"]) for m, a in ((0, "A"), (60, "B"), (120, "C"))]
        self.assertEqual([a for a in run(rows)[0] if a["signal"] == "S3_convergence"], [])


class Summary(unittest.TestCase):
    def test_burden_uses_observed_days(self):
        rows = burn_in(["A"], days=14)
        _, s = run(rows)
        self.assertEqual(s["observed_days"], 14)
        self.assertEqual(s["observed_weeks"], 2.0)
        self.assertEqual(s["alerts_per_observed_week"], 0.0)
        self.assertIn("Not a false-alarm rate", s["note"])
        self.assertEqual(s["detector"], T.DETECTOR_VERSION)


if __name__ == "__main__":
    unittest.main()
