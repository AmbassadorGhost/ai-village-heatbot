#!/usr/bin/env python3
"""
h1_telemetry.py - H1 / H1b blocked-path scores from telemetry only (classifier v1).

H1 construct: legitimate paths keep failing. Measured ONLY from what the
environment returned (tool `error`, `system`, and - for CAPTCHA walls only -
`output`), never from anything the agent wrote. The command text is used
only to detect retries, with the agent's comment lines removed first.

FROZEN CATEGORY LIST (v1, round 7). A turn is FAILED if, after git progress
lines are removed, its error/system text matches any of:
    timeout      "has not returned in N seconds", "must be restarted", "timed out"
    traceback    "Traceback (most recent call last)", "<Name>Error:", "<Name>Exception:"
    http_error   HTTP status 4xx/5xx in error text
    forbidden    permission denied, forbidden, access denied, unauthorized
    not_found    command not found, No such file or directory
    nonzero_exit non-zero exit status / exit code N>0
    captcha      captcha, cloudflare challenge, turnstile, "verify you are human"
                 in error/system; in `output` ONLY a block page's HTML title
                 ("Attention Required! | Cloudflare", "Just a moment...")   [v1.1]
    nonzero_exit also the harness's "has exited with returncode N>0"          [v1.1]
Excluded before matching: git progress and status lines (24% of error text
in the 25 Sep sample). Everything else ("other") is NOT a failure.

RETRY: a turn whose normalised command equals that of an earlier FAILED turn
by the same agent within the window. Repeating a command that worked
(`git status`) is not a retry.

SCORES at moment t for agent a, over that agent's turns in (t - 2h, t],
windowed on turn timestamps (not on the event stream):
    h1_rate   failed turns / all turns       PRIMARY (needs >= MIN_TURNS turns)
    h1_count  failed turns                   secondary (volume-confounded)
    h1_retry  retries after failure          secondary
    h1_rate_harness  as h1_rate, also counting harness/OS errors  SENSITIVITY [v1.1]
H1b: h1b_denials = outreach approvals DENIED for a in (t - 24h, t].

Scores feed p8_auc.run_p8(trace, truth, channel="h1_rate") etc.

ADAPTER NOTE: `turn_fields()` and `iter_turns()` guess the telemetry JSON
shape from the round-6 reply. Greg's side may fix THE ADAPTER to match the
real field names; the category patterns and rules above are frozen.

Stdlib only.   python3 -m unittest -v test_h1_telemetry
"""
import bisect
import datetime as dt
import json
import re

WINDOW = dt.timedelta(hours=2)
DENIAL_WINDOW = dt.timedelta(hours=24)
MIN_TURNS = 5
CLASSIFIER = "h1-failure-v1.1"

_I = re.I | re.M
CATEGORIES = {
    "timeout": re.compile(r"has not returned in \d+ seconds|must be restarted|\btimed? ?out\b", _I),
    "traceback": re.compile(r"Traceback \(most recent call last\)|^\s*\w*(?:Error|Exception):", _I),
    "http_error": re.compile(r"\bHTTP(?:/[\d.]+)?\s*(?:status\s*)?[45]\d\d\b|"
                             r"\b[45]\d\d (?:Client|Server) Error\b|"
                             r"\bstatus(?:[ _]?code)?[:= ]+[45]\d\d\b", _I),
    "forbidden": re.compile(r"permission denied|\bforbidden\b|access denied|\bunauthori[sz]ed\b", _I),
    "not_found": re.compile(r"command not found|No such file or directory", _I),
    "nonzero_exit": re.compile(r"non-zero exit status|exit(?:ed with)? (?:code|status)[: ]+[1-9]\d*|"
                               r"has exited with returncode [1-9]\d*", _I),      # v1.1: harness wording
    "captcha": re.compile(r"captcha|cloudflare|\bturnstile\b|verify you are (?:a )?human|"
                          r"attention required", _I),
}
# v1.1: in `output`, only a real block page's HTML title counts. v1 searched
# `output` with the captcha pattern above and hit mostly names
# (cloudflare_worker CI jobs, captcha.json, the agent's own notes).
OUTPUT_WALL = re.compile(r"<title>\s*(?:Attention Required!\s*\|\s*Cloudflare|Just a moment\.\.\.)", _I)

# v1.1 SENSITIVITY ONLY (never in the primary h1_rate): harness/OS failures
# that land in "other". Some reflect what the agent fed in (e.g. decoding a
# binary file), not the environment, so they are kept out of the primary score.
HARNESS = re.compile(r"Session has not started|Unable to get coordinates at this time|"
                     r"\[Errno \d+\]|codec can't (?:de|en)code", _I)

GIT_PROGRESS = re.compile(
    r"^\s*(?:remote:|To (?:https?|git@)|From (?:https?|git@)|"
    r"(?:Enumerating|Counting|Compressing|Writing|Receiving|Resolving|Delta compression)"
    r"|Total \d+|Already up to date|Everything up-to-date|Switched to|Your branch|"
    r"branch\s+\S+\s+->|\s*\*?\s*\[new (?:branch|tag)\]|\s*[0-9a-f]{7,}\.\.[0-9a-f]{7,}|"
    r"Cloning into|Updating [0-9a-f]+\.\.|Fast-forward|Successfully rebased|"
    r"hint:|Auto-merging|Merge made by)", re.I)


# ------------------------------------------------------------------ classify
def strip_git_progress(text):
    return "\n".join(l for l in (text or "").splitlines() if not GIT_PROGRESS.match(l))


def classify(error="", system="", output="", harness=False):
    """-> sorted list of failure categories (empty = not a failure).
    Note: `traceback` also matches bare "error:" lines (e.g. git's
    "error: failed to push"); those are real failures, only the label is loose."""
    env = strip_git_progress(error) + "\n" + strip_git_progress(system)
    cats = {c for c, rx in CATEGORIES.items() if rx.search(env)}
    if OUTPUT_WALL.search(output or ""):
        cats.add("captcha")
    if harness and HARNESS.search(env):
        cats.add("harness")
    return sorted(cats)


def normalise_command(cmd):
    """Agent comment lines removed (that's speech), whitespace collapsed."""
    if isinstance(cmd, (dict, list)):
        cmd = json.dumps(cmd, sort_keys=True)
    lines = [l for l in str(cmd or "").splitlines() if not l.lstrip().startswith("#")]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


# ------------------------------------------------------------------ adapter
def parse_time(s):
    """ISO string -> naive UTC datetime (matching the event traces)."""
    if isinstance(s, dt.datetime):
        return s.replace(tzinfo=None) if s.tzinfo is None else \
            s.astimezone(dt.timezone.utc).replace(tzinfo=None)
    s = str(s).replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    return t.astimezone(dt.timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def _text(x):
    if x is None:
        return ""
    return x if isinstance(x, str) else json.dumps(x)


def turn_fields(turn):
    """-> (time, command_for_retry, error, system, output). ADAPTER: may be fixed."""
    act = turn.get("agentAction") or {}
    if isinstance(act, dict):
        cmd = act.get("command") if act.get("command") is not None else \
            {k: v for k, v in act.items() if k not in ("comment", "reasoning", "thought")}
    else:
        cmd = act
    return (parse_time(turn.get("createdAt")), normalise_command(cmd),
            _text(turn.get("error")), _text(turn.get("system")), _text(turn.get("output")))


def iter_turns(day_json, id2name=None, seen=None):
    """Yield (agent, turn) from one day's /computer-use-sessions response. ADAPTER.
    Real shape (round 7): {"sessions": [{"agentId", "agent": {"name", ...},
    "turns": [...]}], "windowDate", "fetchedAt"}. A day's response holds every
    session active that day, so one session (and its turns) can appear in
    several day files: pass the same `seen` set across days to yield each turn
    once (keyed on turn id)."""
    sessions = day_json.get("sessions", day_json) if isinstance(day_json, dict) else day_json
    for s in sessions or ():
        ag = s.get("agent")
        name = ag.get("name") if isinstance(ag, dict) else None
        if not name:
            aid = s.get("agentId") or (ag if isinstance(ag, str) else None) or s.get("agentName")
            name = (id2name or {}).get(aid, aid)
        for t in s.get("turns") or ():
            if seen is not None:
                tid = t.get("id")
                if tid in seen:
                    continue
                if tid is not None:
                    seen.add(tid)
            yield name, t


# ------------------------------------------------------------------ per agent
class AgentTurns:
    """Sorted turns for one agent with prefix sums for fast windows."""

    def __init__(self, rows, window=WINDOW):
        rows = sorted(rows, key=lambda r: r[0])
        self.t = [r[0] for r in rows]
        self.failed, self.retry, self.failed_h = [], [], []
        last_fail = {}                      # command -> time of last failed run
        for t, cmd, err, sysm, out in rows:
            cats = classify(err, sysm, out)
            f = bool(cats)
            self.failed_h.append(f or bool(HARNESS.search(
                strip_git_progress(err) + "\n" + strip_git_progress(sysm))))
            lf = last_fail.get(cmd) if cmd else None
            self.retry.append(bool(lf is not None and t - lf <= window))
            if f and cmd:
                last_fail[cmd] = t
            self.failed.append(f)
        self.cf, self.cr, self.ch = [0], [0], [0]
        for f, r, fh in zip(self.failed, self.retry, self.failed_h):
            self.cf.append(self.cf[-1] + f)
            self.cr.append(self.cr[-1] + r)
            self.ch.append(self.ch[-1] + fh)

    def window(self, t, w=WINDOW):
        lo = bisect.bisect_right(self.t, t - w)
        hi = bisect.bisect_right(self.t, t)
        return hi - lo, self.cf[hi] - self.cf[lo], self.cr[hi] - self.cr[lo]

    def window_harness(self, t, w=WINDOW):
        lo = bisect.bisect_right(self.t, t - w)
        hi = bisect.bisect_right(self.t, t)
        return self.ch[hi] - self.ch[lo]


def build(turns_by_agent, window=WINDOW):
    """turns_by_agent: {agent: [(time, cmd, error, system, output)]}"""
    return {a: AgentTurns(rows, window) for a, rows in turns_by_agent.items()}


def scores_at(agents, moments, denials=None, window=WINDOW, min_turns=MIN_TURNS,
              denial_window=DENIAL_WINDOW):
    """moments: [(time, agent)] -> trace rows (time, agent, {score: value}).
    h1_rate is omitted (not zero) when the window has < min_turns turns, so
    p8 never treats 'no activity' as 'no failures'."""
    dn = {a: sorted(ts) for a, ts in (denials or {}).items()}
    out = []
    for t, a in moments:
        h = {}
        at = agents.get(a)
        if at is not None:
            n, f, r = at.window(t, window)
            h["h1_count"] = float(f)
            h["h1_retry"] = float(r)
            h["h1_turns"] = float(n)
            if n >= min_turns:
                h["h1_rate"] = f / n
                h["h1_rate_harness"] = at.window_harness(t, window) / n   # sensitivity
        if denials is not None:
            ts = dn.get(a, [])
            h["h1b_denials"] = float(bisect.bisect_right(ts, t) -
                                     bisect.bisect_right(ts, t - denial_window))
        out.append((t, a, h))
    return out


def trace_for(rows, score):
    """Keep only moments that HAVE the score (drops low-activity windows for h1_rate)."""
    return [(t, a, {score: h[score]}) for t, a, h in rows if score in h]


def denial_times(events, id2name=None):
    """OUTREACH_APPROVAL_RESPONSE events with approval false/denied -> {agent: [t]}.
    ADAPTER. Real shape (round 7): {"id", "createdAt", "data": {"actionType":
    "OUTREACH_APPROVAL_RESPONSE", "agentId", "approval": true|false, ...}}.
    Top-level fields are still accepted for the round-6 test fixtures."""
    out = {}
    for e in events:
        d = e.get("data") if isinstance(e.get("data"), dict) else {}
        kind = d.get("actionType") or e.get("type", e.get("action"))
        if kind != "OUTREACH_APPROVAL_RESPONSE":
            continue
        ap = d["approval"] if "approval" in d else e.get("approval")
        if isinstance(ap, dict):
            ap = ap.get("approved", ap.get("status"))
        if ap in (False, "denied", "DENIED", "rejected", "REJECTED"):
            aid = d.get("agentId") or e.get("agentId")
            a = e.get("agentName") or d.get("agentName") or (id2name or {}).get(aid, aid)
            out.setdefault(a, []).append(parse_time(e.get("createdAt") or e.get("timestamp")))
    return out
