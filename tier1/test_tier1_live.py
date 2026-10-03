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
        return L.Tier1Live(self.dir, self.api, transport=lambda url, msg: self.sent.append(msg) or {"ok": True})

    def burst(self, start, n=20):
        for i in range(n):
            self.api.add(start + dt.timedelta(seconds=30 * i), "a1",
                         "curl -H 'Authorization: Bearer %s' -d 'x=%d' https://api.submit.example/v1/items" % (SECRET, i))

    def test_startup_history_is_never_paged(self):
        self.burst(NOW - dt.timedelta(minutes=30))
        st = self.live().tick("v1", "Main village", {"a1": "Agent One"}, {}, now=NOW, webhook="w")
        self.assertTrue(st["baseline_only"])
        self.assertEqual(self.sent, [])
        self.assertEqual(st["alerts_total"], 1)

    def test_new_alert_is_paged_with_chat_line(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "Agent One"}, {}, now=NOW, webhook="w")
        later = NOW + dt.timedelta(minutes=15)
        self.burst(later - dt.timedelta(minutes=12))
        msgs = {"Agent One": [{"time": (later - dt.timedelta(minutes=14)).isoformat().replace("+00:00", "Z"),
                               "text": "I'll post our items to the new directory site."}]}
        st = live.tick("v1", "Main village", {"a1": "Agent One"}, msgs, now=later, webhook="w")
        self.assertEqual(st["new_alerts"], 1)
        self.assertEqual(len(self.sent), 1)
        emb = self.sent[0]["embeds"][0]
        self.assertTrue(emb["title"].startswith("URGENT · Automated sending at volume"))
        blob = json.dumps(self.sent[0])
        self.assertIn("new directory site", blob)
        self.assertIn("submit.example", blob)
        self.assertEqual(self.sent[0]["allowed_mentions"], {"parse": []})
        names = [f["name"] for f in emb["fields"]]
        for q in ("Who?", "Where?", "Doing what?", "Who else?", "Who hasn't?", "What did they say just before?"):
            self.assertTrue(any(n.startswith(q) for n in names), q)

    def test_same_alert_not_paged_twice(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w")
        later = NOW + dt.timedelta(minutes=15)
        self.burst(later - dt.timedelta(minutes=12))
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=later, webhook="w")
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=later + dt.timedelta(minutes=11), webhook="w")
        self.assertEqual(len(self.sent), 1)

    def test_reads_never_page(self):
        live = self.live()
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w")
        later = NOW + dt.timedelta(minutes=15)
        for i in range(100):
            self.api.add(later - dt.timedelta(minutes=10, seconds=-i), "a1", "curl https://brand-new.example/p%d" % i)
        st = live.tick("v1", "Main village", {"a1": "A"}, {}, now=later, webhook="w")
        self.assertEqual(st["new_alerts"], 0)

    def test_no_command_text_or_secrets_on_disk(self):
        live = self.live()
        self.burst(NOW - dt.timedelta(minutes=30))
        live.tick("v1", "Main village", {"a1": "A"}, {}, now=NOW, webhook="w")
        for p in self.dir.iterdir():
            body = p.read_text(encoding="utf-8")
            self.assertNotIn(SECRET, body, p.name)
            self.assertNotIn("Authorization", body, p.name)
            self.assertNotIn("/v1/items", body, p.name)

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
