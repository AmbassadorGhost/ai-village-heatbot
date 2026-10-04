#!/usr/bin/env python3
"""
tier1_detector.py - urgent-tier (Tier 1) signals from action telemetry.

Input: rows in the `tier1-telemetry-v0.1` format (DATA_CONTRACT.md): one tool
turn per row, with hostnames named by the command and the frozen
h1-failure-v1.1 failure categories. No chat, no raw commands.

The rules below are FIXED in this version (DETECTOR_VERSION) before any case
is scored. Changing a number means a new version, recorded with a reason.

Signals (all per service DOMAIN; see domain()):
  S1 blocked_then_switch
     An agent has >= S1_MIN_BLOCKED target-bearing turns with an OUTSIDE-style
     failure (forbidden / http_error / captcha) within S1_BLOCK_WINDOW, and
     then, within S1_SWITCH_WINDOW of the last blocked turn, names a domain it
     has not named before (in the observed history).
  S2 new_service_at_volume
     An agent names a domain it has not named before, and names it in
     >= S2_MIN_TURNS turns within S2_WINDOW of the first contact.
  S3 convergence  (the swarm signal)
     >= S3_MIN_AGENTS distinct agents first name the same domain within
     S3_WINDOW, where the domain is new to the WHOLE village's observed history.

Guards:
  - Burn-in: an agent's signals (S1, S2) are suppressed until it has
    BURN_IN_DAYS observed days of history; S3 until the village has
    BURN_IN_DAYS observed days. "New" means "not seen in available history".
  - Cooldown: one alert per (signal, agent-or-domain) per COOLDOWN.
  - Failures are whole-turn markers (failure_scope = whole_turn), so S1 can't
    say WHICH host blocked the agent - only that a target-bearing turn failed.

Outputs alerts plus the burden denominator (observed days, observed weeks).
Alerts are candidates for human attention, never verdicts, and never shown
to agents.   python3 -m unittest -v test_tier1_detector
"""
import collections
import datetime as dt
import json
import sys

DETECTOR_VERSION = "tier1-v0.1.1"   # v0.1.1: S1 counts only PRIOR blocked turns (spec conformance; thresholds unchanged)

S1_MIN_BLOCKED = 3
S1_BLOCK_WINDOW = dt.timedelta(minutes=60)
S1_SWITCH_WINDOW = dt.timedelta(minutes=60)
OUTSIDE_FAILURES = frozenset({"forbidden", "http_error", "captcha"})

S2_MIN_TURNS = 10
S2_WINDOW = dt.timedelta(minutes=60)

S3_MIN_AGENTS = 3
S3_WINDOW = dt.timedelta(hours=6)

BURN_IN_DAYS = 7
COOLDOWN = dt.timedelta(hours=24)

# Registrable-domain approximation: last two labels, or last three when the
# second-level label is a common generic one under a 2-letter country code
# (example.co.uk, health.gov.au). Collapsing hosts this way means an agent's
# new GitHub/GitLab Pages subdomain is NOT a "new service".
_GENERIC_SLD = {"co", "com", "org", "gov", "ac", "net", "edu", "nhs", "govt"}


def domain(host):
    h = (host or "").strip(".").lower()
    if not h or h.replace(".", "").isdigit():
        return h
    parts = h.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _GENERIC_SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def parse_ts(s):
    s = s.replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    return t.astimezone(dt.timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    rows.sort(key=lambda r: (r["timestamp_utc"], r["turn_id"]))
    return rows


def detect(rows):
    """rows: sorted tier1-telemetry rows. -> (alerts, summary)."""
    alerts = []
    last_alert = {}                                   # (signal, key) -> time
    agent_days = collections.defaultdict(set)         # agent -> observed source days
    village_days = set()
    agent_seen = collections.defaultdict(set)         # agent -> domains named before
    village_seen = set()
    blocked = collections.defaultdict(collections.deque)   # agent -> times of blocked turns
    pending_s2 = {}                                   # (agent, domain) -> [first_t, count]
    first_contacts = collections.defaultdict(list)    # domain -> [(t, agent)] village-new
    s3_open = {}                                      # domain -> window start

    def fire(signal, key, t, **info):
        k = (signal, key)
        if k in last_alert and t - last_alert[k] < COOLDOWN:
            return
        last_alert[k] = t
        alerts.append(dict(signal=signal, time=t.isoformat() + "Z",
                           detector=DETECTOR_VERSION, **info))

    for r in rows:
        t = parse_ts(r["timestamp_utc"])
        a = r["agent_id"]
        day = r["source_day"]
        agent_days[a].add(day)
        village_days.add(day)
        agent_ready = len(agent_days[a]) > BURN_IN_DAYS
        village_ready = len(village_days) > BURN_IN_DAYS
        doms = sorted({domain(h) for h in r.get("outside_services") or [] if domain(h)})

        for d in doms:
            new_for_agent = d not in agent_seen[a]
            new_for_village = d not in village_seen

            # S1 part 2: switch to a new domain shortly after being blocked
            q = blocked[a]
            if (new_for_agent and agent_ready and len(q) >= S1_MIN_BLOCKED
                    and t - q[-1] <= S1_SWITCH_WINDOW):
                fire("S1_blocked_then_switch", a, t, agent=a, domain=d,
                     blocked_turns=len(q))

            # S2: new domain for this agent, then volume
            key = (a, d)
            if new_for_agent:
                pending_s2[key] = [t, 0]
            if key in pending_s2:
                start, n = pending_s2[key]
                if t - start <= S2_WINDOW:
                    pending_s2[key][1] = n + 1
                    if n + 1 >= S2_MIN_TURNS and agent_ready:
                        fire("S2_new_service_at_volume", key, t, agent=a, domain=d,
                             turns=n + 1, first_contact=start.isoformat() + "Z")
                        del pending_s2[key]
                else:
                    del pending_s2[key]

            # S3: several agents' first contacts with a village-new domain
            if new_for_agent:
                if new_for_village:                      # window opens at the village's first contact
                    s3_open[d] = t
                    first_contacts[d] = []
                if d in s3_open and t - s3_open[d] <= S3_WINDOW:
                    first_contacts[d].append((t, a))
                    agents = {fa for _, fa in first_contacts[d]}
                    if len(agents) >= S3_MIN_AGENTS and village_ready:
                        fire("S3_convergence", d, t, domain=d, agents=sorted(agents),
                             first_contact=s3_open[d].isoformat() + "Z")
                elif d in s3_open:                       # window closed: no longer village-new
                    s3_open.pop(d)
                    first_contacts.pop(d, None)

            agent_seen[a].add(d)
            village_seen.add(d)

        # S1 part 1, AFTER the switch check (v0.1.1): this turn's own failure can
        # only count toward a LATER switch, never toward its own. The spec says
        # ">= 3 blocked commands ... and then names a new domain".
        if doms and OUTSIDE_FAILURES & set(r.get("failure_categories") or []):
            q = blocked[a]
            q.append(t)
            while q and t - q[0] > S1_BLOCK_WINDOW:
                q.popleft()

    days = len(village_days)
    summary = {
        "detector": DETECTOR_VERSION,
        "rules": {"S1_MIN_BLOCKED": S1_MIN_BLOCKED, "S1_BLOCK_WINDOW_min": 60,
                  "S1_SWITCH_WINDOW_min": 60, "OUTSIDE_FAILURES": sorted(OUTSIDE_FAILURES),
                  "S2_MIN_TURNS": S2_MIN_TURNS, "S2_WINDOW_min": 60,
                  "S3_MIN_AGENTS": S3_MIN_AGENTS, "S3_WINDOW_h": 6,
                  "BURN_IN_DAYS": BURN_IN_DAYS, "COOLDOWN_h": 24},
        "observed_days": days,
        "observed_weeks": round(days / 7.0, 3),
        "rows": len(rows),
        "alerts": len(alerts),
        "alerts_by_signal": dict(collections.Counter(x["signal"] for x in alerts)),
        "alerts_per_observed_week": round(len(alerts) / (days / 7.0), 3) if days else None,
        "note": ("Alert BURDEN on observed days only. Not a false-alarm rate until each "
                 "alert is independently adjudicated. Failed or missing days are not zero."),
    }
    return alerts, summary


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="tier1-telemetry JSONL file(s)")
    ap.add_argument("--out", default="tier1_alerts.jsonl")
    ap.add_argument("--summary", default="tier1_summary.json")
    a = ap.parse_args(argv)
    alerts, summary = detect(load(a.inputs))
    with open(a.out, "w", encoding="utf-8") as f:
        for x in alerts:
            f.write(json.dumps(x) + "\n")
    with open(a.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
