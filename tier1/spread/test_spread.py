#!/usr/bin/env python3
"""Tests for chat_mentions and spread_trace (synthetic data).

    python -m unittest -v test_spread
"""
import json
import unittest

import chat_mentions as CM
import spread_trace as ST


def ev(i, t, action, content, agent=None, speaker_type=None):
    d = {"actionType": action, "content": content}
    if agent:
        d["agentId"] = agent
    if speaker_type:
        d["speakerType"] = speaker_type
    return {"id": "e%d" % i, "createdAt": t, "data": d}


class Mentions(unittest.TestCase):
    def test_exports_no_text_and_no_human_identity(self):
        events = [ev(1, "2026-09-14T10:00:00Z", "AGENT_TALK", "Join BotMe at the site, password hunter2", agent="a1"),
                  ev(2, "2026-09-14T09:00:00Z", "USER_TALK", "Hi agents, try botme! - Jane Doe")]
        out = CM.mentions(events, ["botme"])
        blob = json.dumps(out)
        for s in ("hunter2", "Jane", "Join", "site"):
            self.assertNotIn(s, blob)
        kinds = {o["event_id"]: (o["speaker_kind"], o["agent_id"]) for o in out}
        self.assertEqual(kinds, {"e1": ("agent", "a1"), "e2": ("human", None)})

    def test_only_chat_messages_count(self):
        events = [ev(1, "t", "TOOL_CALL", "botme"), ev(2, "t", "AGENT_THINK", "botme", agent="a")]
        self.assertEqual(CM.mentions(events, ["botme"]), [])

    def test_case_insensitive_and_keyword_list(self):
        out = CM.mentions([ev(1, "t", "AGENT_TALK", "see DUNKIRK.sh", agent="a")], ["botme", "dunkirk"])
        self.assertEqual(out[0]["keywords"], ["dunkirk"])


class Trace(unittest.TestCase):
    def test_said_vs_did(self):
        mentions = [{"time": "2026-09-14T10:00:00Z", "speaker_kind": "agent", "agent_id": "org"},
                    {"time": "2026-09-14T09:00:00Z", "speaker_kind": "human", "agent_id": None},
                    {"time": "2026-09-14T11:00:00Z", "speaker_kind": "agent", "agent_id": "talker"}]
        rows = [{"agent_id": "doer", "timestamp_utc": "2026-09-14T10:30:00Z", "outside_services": ["x.site.example"]},
                {"agent_id": "org", "timestamp_utc": "2026-09-15T10:00:00Z", "outside_services": ["site.example"]},
                {"agent_id": "other", "timestamp_utc": "2026-09-14T10:00:00Z", "outside_services": ["unrelated.example"]}]
        res = ST.build(mentions, rows, "site.example", {"org": "Org", "doer": "Doer", "talker": "Talker"},
                       {"Org": "joined"})
        self.assertEqual(res["order_first_said"], ["Org", "Talker"])
        self.assertEqual(res["order_first_did"], ["Doer", "Org"])
        self.assertEqual(res["said_never_did"], ["Talker"])
        self.assertEqual(res["did_never_said"], ["Doer"])
        self.assertEqual(res["first_human_mention"], "2026-09-14T09:00:00Z")
        org = next(l for l in res["lanes"] if l["name"] == "Org")
        self.assertEqual(org["said_before_did_hours"], 24.0)
        self.assertNotIn("other", [l["agent_id"] for l in res["lanes"]])
        self.assertIn("<svg", ST.render_html(res, "Test"))


if __name__ == "__main__":
    unittest.main()
