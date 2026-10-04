"""Live Tier 1 (v0.2): poll public command logs, detect harm-likely actions,
attach the agent's own nearest chat line, and post an urgent notice.

Used by live_server.py; safe to import even if Discord isn't configured.

Privacy: only action FEATURES (flags, methods, hostnames) are stored. Command
text is read in memory, never written to disk or sent anywhere. The chat line
attached to a notice is the agent's own public message, already shown by the
heat viewer, and is presented as agent text, not instructions.

Scope: notices are for human attention. They're never shown to agents, and
never used as a training signal, reward, filter or selection criterion.
"""
import collections
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "exporter_addon"))
import action_features as AF  # noqa: E402
import tier1_v02 as V  # noqa: E402

DAY_ZONE = ZoneInfo("America/Los_Angeles")   # the API's day boundary
HISTORY_DAYS = 30
BACKFILL_DAYS = 8                            # >= burn-in on first start
REFRESH_SECONDS = 600
SIGNAL_TITLES = {
    "U1_captcha_circumvention": "CAPTCHA circumvention",
    "U2_persist_after_refusal": "Persisting past a CAPTCHA or rate limit",
    "U2_identity_change": "Returning as someone else after a refusal",
    "U2S_swarm_rotation": "Other agents taking over a site that refused one of them",
    "U3_automated_writes": "Automated sending at volume",
    "U3S_swarm_writes": "Several agents sending to one new site",
    "U4_account_creation": "Account creation on an outside service",
    "U5_mass_messaging": "Mass messaging",
    "U6_payment": "Payment",
}


def _optional_module(path, name):
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _as_text(x):
    return x if isinstance(x, str) else ("" if x is None else json.dumps(x, sort_keys=True))


def turns_to_rows(sessions, day, classify=None, host_extract=None):
    """Public computer-use sessions -> privacy-safe tier1-telemetry-v0.2 rows."""
    rows = []
    for s in sessions or []:
        for turn in s.get("turns") or []:
            try:
                t = dt.datetime.fromisoformat(str(turn.get("createdAt")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if t.astimezone(DAY_ZONE).date().isoformat() != day:
                continue
            action = turn.get("agentAction") or {}
            cmd = action.get("command") if isinstance(action, dict) else None
            if not isinstance(cmd, str):
                continue
            feats = AF.extract(cmd)
            hosts = sorted(set(host_extract(cmd)["outside_services"]) if host_extract else set(AF._hosts_in(cmd)))
            fails = classify(_as_text(turn.get("error")), _as_text(turn.get("system")),
                             _as_text(turn.get("output"))) if classify else []
            rows.append({"timestamp_utc": t.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z",
                         "agent_id": s.get("agentId"), "session_id": s.get("id"),
                         "turn_id": turn.get("id") or "", "source_day": day,
                         "outside_services": hosts, "failure_categories": list(fails or []),
                         "action": feats,
                         "refusal": AF.refusal(_as_text(turn.get("error")), _as_text(turn.get("system")),
                                               _as_text(turn.get("output")))})
    return rows


def _keep(r):
    a = r["action"]
    return bool(r["outside_services"] or any(a.get(k) for k in V.FLAG_KEYS)
                or (r.get("refusal") or {}).get("rate_limited"))


def nearest_message(messages, agent, when, before=dt.timedelta(hours=2), after=dt.timedelta(minutes=30)):
    """The agent's own chat line closest before the alert (or shortly after)."""
    best, best_gap = None, None
    for m in messages.get(agent, []):
        try:
            mt = dt.datetime.fromisoformat(str(m.get("time")).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        gap = when - mt
        if -after <= gap <= before:
            score = gap if gap >= dt.timedelta(0) else -gap * 4   # prefer earlier lines
            if best_gap is None or score < best_gap:
                best, best_gap = m, score
    return best


STANDARD_QUESTIONS = ("Who?", "Doing what?", "Where?", "Who else?", "Who hasn't?", "What did they say just before?")


def involvement(rows, tgt, when, exclude=()):
    """Agents naming target `tgt` in the 24 h up to `when`, and active agents who didn't."""
    lo = when - dt.timedelta(hours=24)
    touched, active = collections.Counter(), set()
    for r in rows:
        t = V.parse_ts(r["timestamp_utc"])
        if not lo <= t <= when:
            continue
        active.add(r["agent_id"])
        if tgt and any(V.target(h) == tgt for h in r.get("outside_services") or []):
            touched[r["agent_id"]] += 1
    others = {a: n for a, n in touched.items() if a not in exclude}
    return others, sorted(active - set(touched))


# Presentation tiers (Adam, 3 Oct, after the v0.3 ratings; detection rules unchanged):
#   URGENT: harm is direct: outsourcing CAPTCHAs, payments. Delivered normally.
#   Detection: behaviour worth a human check (access-control, sending, sign-ups, mass messaging). Silent,
#   alongside heat notices, labelled so they're never mistaken for heat.
# Mass messaging (U5) moved to silent Detection (Adam, 4 Oct): none of the known incidents involved it,
# it fires on assigned social-media work, and most posting is browser-side where command logs can't see it.
URGENT_SIGNALS = frozenset({"U1_captcha_circumvention", "U6_payment"})
SILENT_FLAG = 4096


def _payment_routine(alert, rows, sanctioned, names):
    """A payment send is routine (Detection, not URGENT) when operators declared it, or when the
    village has sent to that payment service on >= ESTABLISHED_DAYS earlier days (e.g. agents' stores)."""
    hosts = alert.get("targets") or []
    if not hosts:                                   # crypto transaction terms: never routine
        return False
    agent = names.get(alert.get("agent"), alert.get("agent"))
    tg = {V.target(h) for h in hosts}
    for s in sanctioned or []:
        if s.get("agent") in (agent, alert.get("agent")) and V.target(s.get("service", "")) in tg:
            return True
    day = V.parse_ts(alert["time"]).replace(tzinfo=dt.timezone.utc).astimezone(DAY_ZONE).date().isoformat()
    days = {r["source_day"] for r in rows
            if r.get("source_day", "") < day and {V.target(h) for h in (r.get("action") or {}).get("payment_hosts") or []} & tg
            and set((r.get("action") or {}).get("write_hosts") or []) & set((r.get("action") or {}).get("payment_hosts") or [])}
    return len(days) >= V.ESTABLISHED_DAYS


# Operator allowlist (Adam, 4 Oct): agents ASSIGNED to payment work. Their declared payments
# produce NO notice (carte blanche), so the silent Detection channel stays worth reading. Edit the JSON file
# (no restart needed); entries match by agent id or name, and by service (registrable domain). Example in tier1/tier1_allowlist.example.json.
ALLOWLIST_FILE = Path(__file__).resolve().parent.parent / "tier1_allowlist.json"


def load_allowlist(path=None):
    try:
        data = json.loads(Path(path or ALLOWLIST_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _declared(alert, entries, names, services_seen):
    """True when this alert's agent is declared for ALL of the services the alert names."""
    aid = alert.get("agent")
    aname = (names or {}).get(aid, aid)
    for e in entries or []:
        if not ((e.get("agent_id") and e["agent_id"] == aid) or (e.get("agent") and e["agent"] in (aname, aid))):
            continue
        allowed = {("smtp" if x == "smtp" else V.target(x)) for x in e.get("services") or
                   ([e["service"]] if e.get("service") else [])}
        if services_seen and services_seen <= allowed:
            return True
    return False


def tier_for(alert, rows=(), sanctioned=(), names=None, allowlist=None):
    if alert["signal"] not in URGENT_SIGNALS:
        return "detection"
    allow = load_allowlist() if allowlist is None else allowlist
    if alert["signal"] == "U6_payment":
        hosts = alert.get("targets") or []
        declared = list(allow.get("payments") or []) + [
            dict(s, services=[s["service"]]) for s in (sanctioned or []) if s.get("service")]
        if hosts and _declared(alert, declared, names, {V.target(h) for h in hosts}):
            # Adam, 4 Oct: allowlisted agents get carte blanche. No notice at all, not even a silent
            # one, so the Detection channel stays worth reading. Kept in the local audit log only.
            return "allowlisted"
        if _payment_routine(alert, rows, (), names or {}):
            return "detection"
    return "urgent"


PLAYER_LEAD = dt.timedelta(minutes=1)     # open the replay a minute early, to see the lead-up


def player_url(alert_time, village_name):
    """Link to the public village replay at the moment of the action (Unix milliseconds)."""
    t = V.parse_ts(alert_time).replace(tzinfo=dt.timezone.utc) - PLAYER_LEAD
    base = "https://theaidigest.org/village" + ("/open-chat" if "open" in (village_name or "").lower() else "")
    return "%s?time=%d" % (base, int(t.timestamp() * 1000))


def notice(alert, names, messages, village_name, rows=(), tier="urgent"):
    """A notice that answers the same standard questions every time."""
    when = V.parse_ts(alert["time"])
    ids = [alert["agent"]] if alert.get("agent") else list(alert.get("agents", []))
    agents = [names.get(x, x) for x in ids]
    tgt = alert.get("target")
    detail = {k: v for k, v in alert.items() if k not in ("signal", "time", "detector", "agent", "agents", "target")}
    what = SIGNAL_TITLES.get(alert["signal"], alert["signal"])
    if detail:
        what += "\n" + "\n".join("%s: %s" % (k.replace("_", " "), v) for k, v in detail.items())
    others, quiet = involvement(rows, tgt, when, exclude=ids) if tgt else ({}, [])
    fields = [{"name": "Who?", "value": ", ".join(agents)[:1000] or "unknown", "inline": True},
              {"name": "Where?", "value": "`%s`" % tgt if tgt else "see details", "inline": True},
              {"name": "Doing what?", "value": what[:1000]}]
    if tgt:
        fields.append({"name": "Who else? (commands to this site, last 24 h)",
                       "value": (", ".join("%s (%d)" % (names.get(a, a), n) for a, n in
                                           sorted(others.items(), key=lambda x: -x[1]))[:900] or "No other agents.")})
        fields.append({"name": "Who hasn't? (agents with outside activity, last 24 h)",
                       "value": ("%d agents active online sent nothing to this site" % len(quiet) +
                                 (": " + ", ".join(names.get(a, a) for a in quiet[:8]) + ("…" if len(quiet) > 8 else "")
                                  if quiet else "."))[:900]})
    m = nearest_message(messages, agents[0], when) if agents else None
    if m and m.get("text"):
        text = re.sub(r"([\\`*_~|>])", r"\\\1", m["text"]).replace("@", "@\u200b")
        fields.append({"name": "What did they say just before? (agent text; not instructions)",
                       "value": (text[:600] + ("…" if len(text) > 600 else ""))})
    else:
        fields.append({"name": "What did they say just before?",
                       "value": "No chat line from this agent within 2 hours before the alert."})
    link = player_url(alert["time"], village_name)
    fields.append({"name": "Watch it in the village player", "value": "[Open the replay a minute before](%s)" % link})
    urgent = tier == "urgent"
    msg = {"username": "AI Village Heatbot · " + ("Urgent" if urgent else "Detection"),
           "allowed_mentions": {"parse": []},
           "embeds": [{"title": ("%s · %s · %s" % ("URGENT" if urgent else "Detection", what.split("\n")[0],
                                                   village_name))[:256],
                       "description": ("An action with direct consequences outside the village. Human review "
                                       "requested now; no automatic action is taken. A candidate for attention, "
                                       "not a finding." if urgent else
                                       "Behaviour detected from the agent's own commands (not a heat score). "
                                       "Worth a human check when convenient; no automatic action is taken. "
                                       "A candidate for attention, not a finding."),
                       "url": link,
                       "fields": fields, "color": 0xB3261E if urgent else 0x3B5A8A, "timestamp": alert["time"],
                       "footer": {"text": "%s · rules in tier1/TIER1_V02_SPEC.md" % alert["detector"]}}]}
    if not urgent:
        msg["flags"] = SILENT_FLAG
    return msg


class Tier1Live:
    def __init__(self, data_dir, fetch, cfg=None, transport=None):
        self.data = Path(data_dir)
        self.fetch = fetch                      # fetch(path) -> parsed JSON from the village API
        self.cfg = cfg or {}
        self.transport = transport
        self.store_path = self.data / "tier1_rows.jsonl"
        self.state_path = self.data / "tier1_state.json"
        self.alerts_path = self.data / "tier1_alerts_live.jsonl"
        self.last_refresh = None
        clf = self.cfg.get("h1_classifier")
        mod = _optional_module(clf, "h1_classifier") if clf else None
        self.classify = getattr(mod, "classify", None)
        hx = HERE / "exporter_addon" / "outside_services.py"
        hmod = _optional_module(hx, "outside_services") if hx.exists() else None
        self.host_extract = getattr(hmod, "extract", None)

    def _state(self):
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"days_done": [], "notified": [], "started": None}

    def _save_state(self, st):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st), encoding="utf-8")
        tmp.replace(self.state_path)

    def _load_rows(self):
        rows = []
        try:
            with self.store_path.open(encoding="utf-8") as f:
                rows = [json.loads(l) for l in f if l.strip()]
        except OSError:
            pass
        return rows

    def _save_rows(self, rows, today):
        cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HISTORY_DAYS)).isoformat()
        rows = [r for r in rows if r["source_day"] >= cutoff]
        tmp = self.store_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        tmp.replace(self.store_path)
        return rows

    def tick(self, village_id, village_name, names, messages, now=None, webhook=None, detection_webhook=None):
        """One refresh. Returns a status dict and the recent alerts for the viewer."""
        now = now or dt.datetime.now(dt.timezone.utc)
        if self.last_refresh and (now - self.last_refresh).total_seconds() < REFRESH_SECONDS:
            return None
        self.last_refresh = now
        st = self._state()
        today = now.astimezone(DAY_ZONE).date()
        wanted = [(today - dt.timedelta(days=n)).isoformat() for n in range(BACKFILL_DAYS, -1, -1)]
        rows = [r for r in self._load_rows() if r["source_day"] != today.isoformat()]
        done = set(st["days_done"])
        for day in wanted:
            if day in done and day != today.isoformat():
                continue
            page = self.fetch("/computer-use-sessions?villageId=%s&date=%s" % (village_id, day))
            new = [r for r in turns_to_rows(page.get("sessions"), day, self.classify, self.host_extract) if _keep(r)]
            rows = [r for r in rows if r["source_day"] != day] + new
            if day != today.isoformat():
                done.add(day)
        rows.sort(key=lambda r: (r["timestamp_utc"], r["turn_id"]))
        rows = self._save_rows(rows, today.isoformat())
        st["days_done"] = sorted(d for d in done if d >= wanted[0])
        alerts, summary = V.detect(rows)
        first_run = st.get("started") is None
        if first_run:
            st["started"] = now.isoformat()
        notified = set(st["notified"])
        fresh = []
        for a in alerts:
            key = "%s|%s|%s" % (a["signal"], a.get("agent") or a.get("target"), a["time"])
            if key in notified:
                continue
            notified.add(key)
            # Never page for history found at startup; record it for the viewer only.
            if first_run or V.parse_ts(a["time"]) < now.replace(tzinfo=None) - dt.timedelta(hours=2):
                continue
            fresh.append(a)
        sent = []
        for a in fresh[:5]:
            tier = tier_for(a, rows, self.cfg.get("sanctioned_payments"), names)
            if tier == "allowlisted":
                with self.alerts_path.open("a", encoding="utf-8") as f:   # local audit trail only
                    f.write(json.dumps({"alert": a, "tier": tier}) + "\n")
                continue
            msg = notice(a, names, messages, village_name, rows, tier)
            with self.alerts_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"alert": a, "tier": tier, "agents": [names.get(x, x) for x in
                                    ([a["agent"]] if a.get("agent") else a.get("agents", []))]}) + "\n")
            url = webhook if tier == "urgent" else detection_webhook
            if url and self.transport:
                sent.append(dict(self.transport(url, msg), tier=tier))
        st["notified"] = sorted(notified)[-5000:]
        self._save_state(st)
        shown = [a for a in alerts if tier_for(a, rows, self.cfg.get("sanctioned_payments"), names) != "allowlisted"]
        recent = [dict(a, tier=tier_for(a, rows, self.cfg.get("sanctioned_payments"), names),
                       player_url=player_url(a["time"], village_name),
                       agent_names=[names.get(x, x) for x in ([a["agent"]] if a.get("agent") else a.get("agents", []))])
                  for a in shown[-20:]]
        return {"detector": V.DETECTOR_VERSION, "rows_stored": len(rows), "alerts_total": len(alerts),
                "new_alerts": len(fresh), "delivered": sent, "baseline_only": first_run,
                "u2_active": self.classify is not None, "recent_alerts": recent}
