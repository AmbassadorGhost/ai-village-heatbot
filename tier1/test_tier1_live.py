#!/usr/bin/env python3
"""Tests for the live Tier 1 path with a fake village API (no network).

    python -m unittest -v test_tier1_live
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import tier1_live as L

SECRET = "sk-LIVESECRET999"
NOW = dt.datetime(2026, 10, 3, 21, 0, tzinfo=dt.timezone.utc)   # 14:00 PT


def turn(t, cmd, i):
    return {"id": "turn-%d" % i, "createdAt": t.isoformat().replace("+00:00", "Z"),
            "agentAction": {"command": cmd}, "output": "ok"}


class FakeAPI:
    def __init__(self):
        self.by_day = {}
        self.calls = 0

    def add(self, t, agent, cmd):
        day = t.astimezone(L.DAY_ZONE).date().isoformat()
        sess = self.by_day.setdefault(day, {}).setdefault(agent, {"id": "s-" + agent, "agentId": agent, "turns": []})
        sess["turns"].append(turn(t, cmd, sum(len(s["turns"]) for d in self.by_day.values() for s in d.values())))

    def __call__(self, path):
        self.calls += 1
        day = path.split("date=")[1]
        return {"sessions": list(self.by_day.get(day, {}).values())}


def history(api, days=9):
    for d in range(days, 0, -1):
        api.add(NOW - dt.timedelta(days=d), "a1", "curl https://docs.example.org/page")


class Live(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.sent = []
        self.api = FakeAPI()
        history(self.api)

    def tearDown(self):
        self.tmp.cleanup()

    def live(self):
        def transport(url, msg):
            self.sent.append(msg)
            self.urls.append(url)
            return {"ok": True}
        self.urls = []
        return L.Tier1Live(self.dir, self.api, transport=transport)

    def burst(self, start, n=20):
        for i in range(n):
            self.api.add(start + dt.timedelta(seconds=30 * i), "a1",
                         "curl -H 'Authorization: Bearer %s' -d 'x=%d' https://api.submit.example/v1/items" % (SECRET, i))

    def test_startup_history_is_never_paged(self):
        self.burst(NOW - dt.timedelta(minutes=30))
        st = self.live().tick("v1", "Main village", {"a1": "Agent One"}, {}, now=NOW, webhook="w", detection_webhook="d")
        self.assertTrue(st["baseline_only"])
        self.assertEqual(self.sent, [])
        self.assertEqual(st["alerts_total"], 1)

    def test_new_alert_is_paged_with_chat_line(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "Agent One"}, {}, now=NOW, webhook="w", detection_webhook="d")
        later = NOW + dt.timedelta(minutes=15)
        self.burst(later - dt.timedelta(minutes=12))
        msgs = {"Agent One": [{"time": (later - dt.timedelta(minutes=14)).isoformat().replace("+00:00", "Z"),
                               "text": "I'll post our items to the new directory site."}]}
        st = live.tick("v1", "Main village", {"a1": "Agent One"}, msgs, now=later, webhook="w", detection_webhook="d")
        self.assertEqual(st["new_alerts"], 1)
        self.assertEqual(len(self.sent), 1)
        emb = self.sent[0]["embeds"][0]
        # automated sending is a Detection: silent, to the everyday channel, never "URGENT"
        self.assertTrue(emb["title"].startswith("Detection · Automated sending at volume"), emb["title"])
        self.assertEqual(self.sent[0]["flags"], L.SILENT_FLAG)
        self.assertEqual(self.urls, ["d"])
        blob = json.dumps(self.sent[0])
        self.assertIn("new directory site", blob)
        self.assertIn("submit.example", blob)
        self.assertEqual(self.sent[0]["allowed_mentions"], {"parse": []})
        names = [f["name"] for f in emb["fields"]]
        for q in ("Who?", "Where?", "Doing what?", "Who else?", "Who hasn't?", "What did they say just before?"):
            self.assertTrue(any(n.startswith(q) for n in names), q)

    def test_same_alert_not_paged_twice(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w", detection_webhook="d")
        later = NOW + dt.timedelta(minutes=15)
        self.burst(later - dt.timedelta(minutes=12))
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=later, webhook="w", detection_webhook="d")
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=later + dt.timedelta(minutes=11), webhook="w", detection_webhook="d")
        self.assertEqual(len(self.sent), 1)

    def test_reads_never_page(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w", detection_webhook="d")
        later = NOW + dt.timedelta(minutes=15)
        for i in range(100):
            self.api.add(later - dt.timedelta(minutes=10, seconds=-i), "a1", "curl https://brand-new.example/p%d" % i)
        st = live.tick("v1", "Main village", {"a1": "A"}, {}, now=later, webhook="w", detection_webhook="d")
        self.assertEqual(st["new_alerts"], 0)

    def test_no_command_text_or_secrets_on_disk(self):
        live = self.live()
        self.burst(NOW - dt.timedelta(minutes=30))
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w", detection_webhook="d")
        for p in self.dir.iterdir():
            body = p.read_text(encoding="utf-8")
            self.assertNotIn(SECRET, body, p.name)
            self.assertNotIn("Authorization", body, p.name)
            self.assertNotIn("/v1/items", body, p.name)

    def test_rule_change_refetches_stored_days(self):
        live = self.live()
        live.tick("v1", "Main village", {}, {}, now=NOW)
        rows = [json.loads(l) for l in live.store_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rows:
            r["action"]["action_features_version"] = "action-features-v0.0-old"
        live.store_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        calls = self.api.calls
        live.tick("v1", "Main village", {}, {}, now=NOW + dt.timedelta(minutes=11))
        self.assertEqual(self.api.calls - calls, L.BACKFILL_DAYS + 1)
        rows = [json.loads(l) for l in live.store_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertTrue(rows and all(r["action"]["action_features_version"] == L.AF.VERSION for r in rows))

    def test_refresh_is_rate_limited(self):
        live = self.live()
        live.tick("v1", "Main village", {}, {}, now=NOW)
        calls = self.api.calls
        self.assertIsNone(live.tick("v1", "Main village", {}, {}, now=NOW + dt.timedelta(minutes=5)))
        self.assertEqual(self.api.calls, calls)

    def test_past_days_fetched_once(self):
        live = self.live()
        live.tick("v1", "Main village", {}, {}, now=NOW)
        first = self.api.calls
        live.tick("v1", "Main village", {}, {}, now=NOW + dt.timedelta(minutes=11))
        self.assertEqual(self.api.calls - first, 1)     # only today again


class StandardQuestions(unittest.TestCase):
    def test_who_else_and_who_hasnt(self):
        rows = [{"agent_id": a, "timestamp_utc": "2026-10-03T11:%02d:00Z" % i, "outside_services": h}
                for i, (a, h) in enumerate([("a1", ["api.site.example"]), ("a2", ["x.site.example"]),
                                            ("a2", ["site.example"]), ("a3", ["docs.other.example"])])]
        alert = {"signal": "U3_automated_writes", "time": "2026-10-03T12:00:00Z", "detector": "v",
                 "agent": "a1", "target": "site.example", "write_commands": 20}
        n = L.notice(alert, {"a1": "One", "a2": "Two", "a3": "Three"}, {}, "Main village", rows)
        f = {x["name"].split(" (")[0]: x["value"] for x in n["embeds"][0]["fields"]}
        self.assertEqual(f["Who else?"], "Two (2)")
        self.assertTrue(f["Who hasn't?"].startswith("1 agents active online sent nothing to this site: Three"))
        self.assertEqual(f["Who?"], "One")


class Tiers(unittest.TestCase):
    NAMES = {"a1": "Shop Agent"}

    def pay_alert(self, day="2026-09-10", hosts=("api.stripe.com",)):
        return {"signal": "U6_payment", "time": day + "T18:00:00Z", "detector": "v", "agent": "a1",
                "targets": list(hosts)}

    def pay_row(self, day):
        return {"agent_id": "a1", "source_day": day, "timestamp_utc": day + "T17:00:00Z",
                "outside_services": ["api.stripe.com"],
                "action": {"payment_hosts": ["api.stripe.com"], "write_hosts": ["api.stripe.com"]}}

    def test_urgent_signals(self):
        self.assertEqual(L.tier_for({"signal": "U1_captcha_circumvention", "time": "2026-09-10T00:00:00Z"}), "urgent")
        self.assertEqual(L.tier_for(self.pay_alert(), [], [], self.NAMES), "urgent")

    def test_behaviour_signals_are_detections(self):
        for sig in ("U2_persist_after_refusal", "U2_identity_change", "U2S_swarm_rotation",
                    "U3_automated_writes", "U3S_swarm_writes", "U4_account_creation", "U5_mass_messaging"):
            self.assertEqual(L.tier_for({"signal": sig, "time": "2026-09-10T00:00:00Z"}), "detection")

    def test_declared_store_payments_get_no_notice(self):
        sanctioned = [{"agent": "Shop Agent", "service": "stripe.com"}]
        self.assertEqual(L.tier_for(self.pay_alert(), [], sanctioned, self.NAMES, allowlist={}), "allowlisted")

    def test_routine_payment_service_is_detection(self):
        rows = [self.pay_row(d) for d in ("2026-09-01", "2026-09-03", "2026-09-05")]
        self.assertEqual(L.tier_for(self.pay_alert(), rows, [], self.NAMES), "detection")
        self.assertEqual(L.tier_for(self.pay_alert(), rows[:2], [], self.NAMES), "urgent")

    def test_allowlisted_payment_is_never_sent(self):
        import tempfile
        d = tempfile.mkdtemp()
        sent = []
        live = L.Tier1Live(d, lambda path: {"sessions": []}, cfg={"sanctioned_payments": [{"agent": "a1", "service": "stripe.com"}]},
                           transport=lambda url, msg: sent.append(msg) or {"ok": True})
        alert = self.pay_alert(day="2026-10-04")
        orig = L.V.detect
        try:
            L.V.detect = lambda rows: ([alert], {})
            now = L.dt.datetime(2026, 10, 4, 18, 30, tzinfo=L.dt.timezone.utc)
            live.tick("v", "Main village", {}, {}, now=now, webhook="w", detection_webhook="d")          # baseline
            live.last_refresh = None
            alert["time"] = "2026-10-04T18:59:00Z"
            st = live.tick("v", "Main village", {}, {}, now=now + L.dt.timedelta(minutes=30), webhook="w", detection_webhook="d")
        finally:
            L.V.detect = orig
        self.assertEqual(sent, [])
        self.assertEqual(st["recent_alerts"], [])

    def test_crypto_transaction_always_urgent(self):
        sanctioned = [{"agent": "Shop Agent", "service": "stripe.com"}]
        self.assertEqual(L.tier_for(self.pay_alert(hosts=()), [], sanctioned, self.NAMES), "urgent")

    def test_urgent_notice_is_not_silent(self):
        n = L.notice({"signal": "U1_captcha_circumvention", "time": "2026-09-10T00:00:00Z", "detector": "v",
                      "agent": "a1", "basis": "solver_service"}, self.NAMES, {}, "Main village", [], "urgent")
        self.assertNotIn("flags", n)
        self.assertTrue(n["embeds"][0]["title"].startswith("URGENT · CAPTCHA"))


class Allowlist(unittest.TestCase):
    def msg(self, hosts=("api.x.com",), agent="g1"):
        return {"signal": "U5_mass_messaging", "time": "2026-10-04T15:00:00Z", "detector": "v",
                "agent": agent, "targets": list(hosts), "commands_in_window": 12}

    ALLOW = {"payments": [{"agent": "Shop Agent", "agent_id": "s1", "services": ["stripe.com"]}]}

    def test_mass_messaging_is_always_a_silent_detection(self):
        # Adam, 4 Oct: removed from URGENT; no allowlist needed
        for hosts in (("api.x.com",), ("api.sendgrid.com",), ()):
            self.assertEqual(L.tier_for(self.msg(hosts), [], [], None, allowlist={}), "detection")

    def test_declared_payments(self):
        alert = {"signal": "U6_payment", "time": "2026-10-04T15:00:00Z", "agent": "s1", "targets": ["api.stripe.com"]}
        allow = {"payments": [{"agent_id": "s1", "services": ["stripe.com"]}]}
        self.assertEqual(L.tier_for(alert, [], [], None, allowlist=allow), "allowlisted")
        self.assertEqual(L.tier_for(alert, [], [], None, allowlist={}), "urgent")

    def test_allowlist_file_is_read(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "allow.json")
            open(p, "w").write(json.dumps(self.ALLOW))
            self.assertEqual(L.load_allowlist(p), self.ALLOW)
            self.assertEqual(L.load_allowlist(os.path.join(d, "missing.json")), {})


class PlayerLinks(unittest.TestCase):
    def test_link_is_unix_ms_at_the_event(self):
        # Adam's example: ?time=1791139006513 is 2026-10-04 18:36:46.513 UTC
        url = L.player_url("2026-10-04T18:36:46.513000Z", "Main village")
        self.assertEqual(url, "https://theaidigest.org/village?time=1791139006513")

    def test_open_chat_link(self):
        self.assertTrue(L.player_url("2026-10-04T18:37:46Z", "Open Chat").startswith(
            "https://theaidigest.org/village/open-chat?time="))

    def test_notice_carries_the_link(self):
        n = L.notice({"signal": "U1_captcha_circumvention", "time": "2026-10-04T18:36:46.513000Z",
                      "detector": "v", "agent": "a1"}, {"a1": "A"}, {}, "Main village", [], "urgent")
        self.assertEqual(n["embeds"][0]["url"], "https://theaidigest.org/village?time=1791139006513")


class Nearest(unittest.TestCase):
    def test_prefers_line_before(self):
        w = dt.datetime(2026, 10, 3, 12, 0)
        msgs = {"A": [{"time": "2026-10-03T11:50:00Z", "text": "before"},
                      {"time": "2026-10-03T12:05:00Z", "text": "after"}]}
        self.assertEqual(L.nearest_message(msgs, "A", w)["text"], "before")

    def test_none_when_too_old(self):
        w = dt.datetime(2026, 10, 3, 12, 0)
        self.assertIsNone(L.nearest_message({"A": [{"time": "2026-10-03T09:00:00Z", "text": "x"}]}, "A", w))


if __name__ == "__main__":
    unittest.main()
