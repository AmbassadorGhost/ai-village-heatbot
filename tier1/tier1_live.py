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
    "U2_block_evasion": "Getting around a block",
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
                         "action": feats})
    return rows


def _keep(r):
    a = r["action"]
    return bool(r["outside_services"] or any(a.get(k) for k in V.FLAG_KEYS))


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


def notice(alert, names, messages, village_name):
    when = V.parse_ts(alert["time"])
    agents = [names.get(x, x) for x in ([alert["agent"]] if alert.get("agent") else alert.get("agents", []))]
    fields = [{"name": "Agent" + ("s" if len(agents) > 1 else ""), "value": ", ".join(agents)[:1000], "inline": True}]
    if alert.get("target"):
        fields.append({"name": "Outside site", "value": "`%s`" % alert["target"], "inline": True})
    detail = {k: v for k, v in alert.items() if k not in ("signal", "time", "detector", "agent", "agents", "target")}
    if detail:
        fields.append({"name": "What the commands did",
                       "value": "\n".join("%s: %s" % (k.replace("_", " "), v) for k, v in detail.items())[:900]})
    m = nearest_message(messages, agents[0], when) if agents else None
    if m and m.get("text"):
        text = re.sub(r"([\\`*_~|>])", r"\\\1", m["text"]).replace("@", "@​")
        fields.append({"name": "Agent's nearest chat line (agent text; not instructions)",
                       "value": (text[:600] + ("…" if len(text) > 600 else ""))})
    else:
        fields.append({"name": "Context", "value": "No chat line from this agent within 2 hours before the alert."})
    return {"username": "AI Village Heatbot · Tier 1", "allowed_mentions": {"parse": []},
            "embeds": [{"title": ("URGENT · %s · %s" % (SIGNAL_TITLES.get(alert["signal"], alert["signal"]),
                                                       village_name))[:256],
                        "description": ("An action likely to affect people or services outside the village. "
                                        "Human review requested; no automatic action is taken. "
                                        "This is a candidate for attention, not a finding."),
                        "fields": fields, "color": 0xB3261E, "timestamp": alert["time"],
                        "footer": {"text": "%s · rules in tier1/TIER1_V02_SPEC.md" % alert["detector"]}}]}


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

    def tick(self, village_id, village_name, names, messages, now=None, webhook=None):
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
            msg = notice(a, names, messages, village_name)
            with self.alerts_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"alert": a, "agents": [names.get(x, x) for x in
                                    ([a["agent"]] if a.get("agent") else a.get("agents", []))]}) + "\n")
            if webhook and self.transport:
                sent.append(self.transport(webhook, msg))
        st["notified"] = sorted(notified)[-5000:]
        self._save_state(st)
        recent = [dict(a, agent_names=[names.get(x, x) for x in ([a["agent"]] if a.get("agent") else a.get("agents", []))])
                  for a in alerts[-20:]]
        return {"detector": V.DETECTOR_VERSION, "rows_stored": len(rows), "alerts_total": len(alerts),
                "new_alerts": len(fresh), "delivered": sent, "baseline_only": first_run,
                "u2_active": self.classify is not None, "recent_alerts": recent}
