#!/usr/bin/env python3
"""
test_h1_telemetry.py - known-answer tests for the H1 telemetry classifier.

Key scenario (volume confound): an agent whose failure RATE is constant but
whose busy hours have more turns, more failures and more flags. The count
"predicts"; the rate must not.

    python3 -m unittest -v test_h1_telemetry
"""
import datetime as dt
import random
import unittest

import forward_eval as FE
import h1_telemetry as H
import p8_auc as P

T0 = dt.datetime(2026, 7, 15, 8)
M = dt.timedelta(minutes=1)


class Classify(unittest.TestCase):
    def test_each_category(self):
        cases = {
            "timeout": "Tool has not returned in 300 seconds and must be restarted",
            "traceback": "Traceback (most recent call last):\n  File x\nValueError: bad",
            "http_error": "curl: (22) The requested URL returned error: HTTP 503",
            "forbidden": "fatal: unable to access: The requested URL returned 403 Forbidden",
            "not_found": "bash: glab: command not found",
            "nonzero_exit": "Process exited with code 2",
        }
        for cat, err in cases.items():
            self.assertIn(cat, H.classify(error=err), cat)

    def test_git_progress_is_not_a_failure(self):
        err = ("Enumerating objects: 5, done.\nCounting objects: 100% (5/5)\n"
               "Writing objects: 100% (3/3), 300 bytes\nTo https://gitlab.com/x/y.git\n"
               "   0c9cc8c..e78fd5f  master -> master\nremote: Processing\nEverything up-to-date")
        self.assertEqual(H.classify(error=err), [])

    def test_git_progress_does_not_hide_a_real_failure(self):
        err = "Counting objects: 3\n! [rejected] master -> master\nerror: failed to push\n" \
              "fatal: Authentication failed; permission denied"
        self.assertIn("forbidden", H.classify(error=err))

    def test_captcha_wall_found_in_output(self):
        self.assertEqual(H.classify(output="<title>Just a moment...</title> Verify you are human"),
                         ["captcha"])
        self.assertEqual(H.classify(output="<html><title>Attention Required! | Cloudflare</title>"),
                         ["captcha"])

    def test_v11_names_in_output_are_not_walls(self):
        # the round-7 sample: mostly names and the agent's own notes
        for out in ("deploy cloudflare_worker job passed", "wrote captcha.json",
                    '<input name="recaptcha_token">', "echo 'verify you are human step done'"):
            self.assertEqual(H.classify(output=out), [], out)

    def test_v11_harness_returncode_is_nonzero_exit(self):
        self.assertEqual(H.classify(error="bash has exited with returncode 1"), ["nonzero_exit"])
        self.assertEqual(H.classify(error="bash has exited with returncode 0"), [])

    def test_v11_harness_errors_only_in_sensitivity(self):
        err = "Unable to get coordinates at this time, please retry"
        self.assertEqual(H.classify(error=err), [])
        self.assertEqual(H.classify(error=err, harness=True), ["harness"])
        rows = [(T0 + i * M, "c%d" % i, err if i < 3 else "", "", "") for i in range(6)]
        h = H.scores_at(H.build({"a": rows}), [(T0 + 6 * M, "a")])[0][2]
        self.assertEqual(h["h1_rate"], 0.0)
        self.assertEqual(h["h1_rate_harness"], 0.5)

    def test_output_is_not_searched_for_other_categories(self):
        # a page the agent cat'ed that happens to MENTION an error isn't a failure
        self.assertEqual(H.classify(output="Guide: what does 403 Forbidden mean? Traceback basics"), [])

    def test_ordinary_stderr_is_not_a_failure(self):
        self.assertEqual(H.classify(error="npm WARN deprecated left-pad@1.0.0"), [])


class Speech(unittest.TestCase):
    def test_comment_lines_never_count(self):
        a = H.normalise_command("# I'm stuck again, this is failing\ncurl -s x")
        b = H.normalise_command("# trying once more, still blocked\ncurl  -s x")
        self.assertEqual(a, b)
        self.assertNotIn("stuck", a)

    def test_agent_speech_cannot_create_a_failure(self):
        # the classifier never sees the command, so words in it can't add failures
        at = H.AgentTurns([(T0, H.normalise_command("# ERROR 403 Forbidden, Traceback!\nls"),
                            "", "", "file.txt")])
        self.assertEqual(at.window(T0), (1, 0, 0))


class Windows(unittest.TestCase):
    def rows(self, spec):
        return [(T0 + m * M, cmd, err, "", "") for m, cmd, err in spec]

    def test_retry_only_after_failure(self):
        at = H.AgentTurns(self.rows([(0, "git status", ""), (1, "git status", ""),
                                     (2, "curl x", "HTTP 503"), (3, "curl x", "HTTP 503"),
                                     (4, "curl x", "")]))
        n, f, r = at.window(T0 + 4 * M)
        self.assertEqual((n, f, r), (5, 2, 2))    # git status repeats aren't retries

    def test_retry_expires_outside_window(self):
        at = H.AgentTurns(self.rows([(0, "curl x", "HTTP 503"), (200, "curl x", "")]))
        self.assertEqual(at.window(T0 + 200 * M)[2], 0)

    def test_window_is_2h_on_turn_times(self):
        at = H.AgentTurns(self.rows([(0, "a", "HTTP 500"), (60, "b", ""), (121, "c", "")]))
        n, f, _ = at.window(T0 + 121 * M)
        self.assertEqual((n, f), (2, 0))         # the failure at 0 is > 2h old

    def test_rate_omitted_when_too_few_turns(self):
        agents = H.build({"a": self.rows([(0, "x", "HTTP 500")])})
        row = H.scores_at(agents, [(T0 + M, "a")])[0][2]
        self.assertNotIn("h1_rate", row)
        self.assertEqual(row["h1_count"], 1.0)
        self.assertEqual(H.trace_for([(T0, "a", row)], "h1_rate"), [])

    def test_denials_window(self):
        rows = H.scores_at({}, [(T0, "a"), (T0 + dt.timedelta(hours=30), "a")],
                           denials={"a": [T0 - dt.timedelta(hours=1)]})
        self.assertEqual([r[2]["h1b_denials"] for r in rows], [1.0, 0.0])


class Adapter(unittest.TestCase):
    def test_iter_turns_and_fields(self):
        day = [{"agentId": "id1", "turns": [
            {"createdAt": "2026-07-15T15:00:00.000Z",
             "agentAction": {"type": "bash", "command": "# note\nls"},
             "output": "ok", "error": None, "system": None}]}]
        (agent, turn), = list(H.iter_turns(day, {"id1": "Agent One"}))
        t, cmd, err, sysm, out = H.turn_fields(turn)
        self.assertEqual(agent, "Agent One")
        self.assertEqual(t, dt.datetime(2026, 7, 15, 15, 0))
        self.assertEqual(cmd, "ls")
        self.assertEqual((err, out), ("", "ok"))

    def test_denial_events(self):
        ev = [{"type": "OUTREACH_APPROVAL_RESPONSE", "approval": False, "agentName": "a",
               "createdAt": "2026-07-15T10:00:00Z"},
              {"type": "OUTREACH_APPROVAL_RESPONSE", "approval": True, "agentName": "a",
               "createdAt": "2026-07-15T11:00:00Z"},
              {"type": "USER_TALK", "agentName": "a", "createdAt": "2026-07-15T12:00:00Z"}]
        self.assertEqual(H.denial_times(ev), {"a": [dt.datetime(2026, 7, 15, 10)]})


def village(blocked_precursor, n=24, days=4, seed=2):
    """Each agent has quiet and busy hours. Failure RATE is 10% everywhere,
    except (if blocked_precursor) 60% in the 90 min before each flag.
    Busy hours: 4x turns AND 3x flag chance, so count tracks flags by volume."""
    rnd = random.Random(seed)
    turns, flags, moments = {}, {}, []
    for i in range(n):
        a = "ag%02d" % i
        fl = []
        for d in range(days):
            for h in range(8):
                busy = rnd.random() < 0.3
                if rnd.random() < (0.30 if busy else 0.10):
                    fl.append(T0 + dt.timedelta(days=d, hours=h, minutes=rnd.randint(0, 59)))
        flags[(a, "general")] = fl
        rows = []
        for d in range(days):
            for h in range(8):
                start = T0 + dt.timedelta(days=d, hours=h)
                busy = any(abs((f - start).total_seconds()) < 3600 * 1.5 for f in fl)
                step = 3 if busy else 12
                for m in range(0, 60, step):
                    t = start + m * M
                    p = 0.10
                    if blocked_precursor and any(dt.timedelta(0) < f - t <= 90 * M for f in fl):
                        p = 0.60
                    err = "HTTP 503" if rnd.random() < p else ""
                    rows.append((t, "cmd%d" % rnd.randint(0, 50), err, "", ""))
                    if m % 15 == 0:
                        moments.append((t, a))
        turns[a] = rows
    return H.build(turns), FE.Truth(flags), moments


class RealShapes(unittest.TestCase):
    """Round 7: shapes copied from stored telemetry and the event stream."""

    DAY = {"sessions": [{"id": "s1", "agentId": "uuid-a",
                         "agent": {"id": "uuid-a", "name": "GPT-5.2"},
                         "turns": [{"id": "t1", "sessionId": "s1",
                                    "agentAction": {"command": "ls"},
                                    "output": "x", "error": None, "system": None,
                                    "createdAt": "2026-08-05T10:00:00.000Z"}]}],
           "windowDate": "2026-08-05", "fetchedAt": "2026-09-27T03:17:54.372Z"}

    def test_session_agent_name_is_used(self):
        self.assertEqual([a for a, _ in H.iter_turns(self.DAY)], ["GPT-5.2"])

    def test_a_session_in_two_day_files_is_counted_once(self):
        seen = set()
        n = len(list(H.iter_turns(self.DAY, seen=seen))) + \
            len(list(H.iter_turns(self.DAY, seen=seen)))
        self.assertEqual(n, 1)

    def test_falls_back_to_id2name_without_agent_object(self):
        day = {"sessions": [{"agentId": "uuid-a", "turns": [{"id": "t"}]}]}
        self.assertEqual([a for a, _ in H.iter_turns(day, {"uuid-a": "X"})], ["X"])

    def test_denials_read_from_event_data(self):
        ev = [{"id": "e1", "createdAt": "2026-07-10T12:00:00.000Z",
               "data": {"actionType": "OUTREACH_APPROVAL_RESPONSE",
                        "agentId": "uuid-a", "approval": False}},
              {"id": "e2", "createdAt": "2026-07-10T13:00:00.000Z",
               "data": {"actionType": "OUTREACH_APPROVAL_RESPONSE",
                        "agentId": "uuid-a", "approval": True}},
              {"id": "e3", "createdAt": "2026-07-10T14:00:00.000Z",
               "data": {"actionType": "OUTREACH_APPROVAL_REQUEST",
                        "agentId": "uuid-a"}}]
        d = H.denial_times(ev, {"uuid-a": "GPT-5.2"})
        self.assertEqual(list(d), ["GPT-5.2"])
        self.assertEqual(len(d["GPT-5.2"]), 1)


class EndToEnd(unittest.TestCase):
    def run_score(self, precursor, score):
        agents, truth, moments = village(precursor)
        tr = H.trace_for(H.scores_at(agents, moments), score)
        return P.run_p8(tr, truth, exclude=(), boot=100, channel=score)["claims"]["onset"]

    def test_volume_confound_fools_count_not_rate(self):
        cnt = self.run_score(False, "h1_count")
        rate = self.run_score(False, "h1_rate")
        self.assertGreater(cnt["auc_within"], 0.55)          # count "predicts" via volume
        self.assertLess(abs(rate["auc_within"] - 0.5), 0.05)  # rate correctly shows nothing

    def test_planted_blocking_is_found_by_rate(self):
        rate = self.run_score(True, "h1_rate")
        self.assertGreater(rate["auc_within"], 0.65)
        self.assertIn(rate["category"], P.PASSING)


if __name__ == "__main__":
    unittest.main()
