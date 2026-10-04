#!/usr/bin/env python3
"""Show one agent's computer-use turns around a moment, straight from the public API.

For checking a detection against the village player:

    python3 tier1/show_turns.py "Grok 4.5" 2026-10-03T18:57:41Z
    python3 tier1/show_turns.py "Grok 4.5" "2026-10-03 2:57:41 PM" --zone America/New_York

Prints each turn's raw createdAt exactly as the API sends it, the same moment in
UTC and in the given zone, the player link the dashboard would build, and the
first part of the command. Public data only; nothing is written.
"""
import argparse
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heatbot as hb          # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exporter_addon"))
import action_features as AF  # noqa: E402
import tier1_live as L        # noqa: E402

PT = ZoneInfo("America/Los_Angeles")


def explain(cmd):
    """Which rules in action_features fired, with the matching text (local diagnostics only)."""
    from urllib.parse import urlsplit
    f = AF.extract(cmd)
    print("  write_hosts:", f["write_hosts"], "| signup_endpoint_hosts:", f["signup_endpoint_hosts"])
    for name, rx in (("python write call", AF._PY_WRITE_CALL), ("method= keyword", AF._PY_METHOD_KW),
                     ("urllib Request with data", AF._URLLIB_WITH_DATA)):
        for m in rx.finditer(cmd):
            a, b = max(0, m.start() - 80), min(len(cmd), m.end() + 80)
            print("  WRITE TRIGGER (%s): ...%s..." % (name, " ".join(cmd[a:b].split())))
    for u in AF._URL.findall(cmd):
        if AF._AUTH_PATH.search(urlsplit(u).path or ""):
            print("  SIGN-UP PATH:", u[:160])


def parse_when(s, zone):
    s = s.strip()
    for fmt in ("%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=zone).astimezone(dt.timezone.utc)
        except ValueError:
            pass
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=zone)).astimezone(dt.timezone.utc)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("agent")
    p.add_argument("when", help="ISO time with Z, or local time read off the dashboard")
    p.add_argument("--zone", default="UTC", help="zone for a time without Z (default UTC)")
    p.add_argument("--minutes", type=int, default=10, help="window either side")
    p.add_argument("--slug", default="actual-launch-1")
    p.add_argument("--explain", action="store_true", help="show which detector rules matched each command")
    a = p.parse_args(argv)
    zone = ZoneInfo(a.zone)
    when = parse_when(a.when, zone)
    village = hb.http_json("%s/villages?slug=%s" % (hb.API, a.slug), timeout=60)
    detail = hb.http_json("%s/villages/%s" % (hb.API, village["id"]), timeout=60)
    ids = [x["id"] for x in detail["agents"] if x["name"].lower() == a.agent.lower()]
    if not ids:
        sys.exit("No agent called %r. Names: %s" % (a.agent, ", ".join(x["name"] for x in detail["agents"])))
    lo, hi = when - dt.timedelta(minutes=a.minutes), when + dt.timedelta(minutes=a.minutes)
    days = sorted({lo.astimezone(PT).date().isoformat(), hi.astimezone(PT).date().isoformat()})
    print("Looking for %s (%s) between %s and %s UTC; API days %s"
          % (a.agent, ids[0], lo.strftime("%H:%M:%S"), hi.strftime("%H:%M:%S"), ", ".join(days)))
    found = 0
    for day in days:
        page = hb.http_json("%s/computer-use-sessions?villageId=%s&date=%s" % (hb.API, village["id"], day), timeout=120)
        for s in page.get("sessions") or []:
            if s.get("agentId") != ids[0]:
                continue
            for turn in s.get("turns") or []:
                raw = turn.get("createdAt")
                try:
                    t = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except ValueError:
                    continue
                naive = t.tzinfo is None
                tu = (t.replace(tzinfo=dt.timezone.utc) if naive else t).astimezone(dt.timezone.utc)
                if not lo <= tu <= hi:
                    continue
                found += 1
                cmd = ((turn.get("agentAction") or {}).get("command") or "") if isinstance(turn.get("agentAction"), dict) else ""
                print("\nraw createdAt: %r%s" % (raw, "   <-- NO ZONE: the live code reads this as the laptop's local time" if naive else ""))
                print("  UTC %s | %s %s | session %s"
                      % (tu.strftime("%H:%M:%S"), a.zone, tu.astimezone(zone).strftime("%I:%M:%S %p"), s.get("id")))
                print("  player:", L.player_url(tu.replace(tzinfo=None).isoformat() + "Z", detail.get("name", "")))
                print("  command:", " ".join(cmd.split())[:240] or "(none)")
                if a.explain and cmd:
                    explain(cmd)
    if not found:
        print("\nNo turns for that agent in the window.")


if __name__ == "__main__":
    main()
