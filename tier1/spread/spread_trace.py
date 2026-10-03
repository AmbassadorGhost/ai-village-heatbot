#!/usr/bin/env python3
"""How a swarm spread: who first SAID it in chat vs who first DID it.

Joins chat mentions (chat_mentions.py; no text) with action telemetry
(tier1-telemetry rows) for one outside site, and writes a JSON summary plus a
self-contained HTML timeline: one lane per agent, hollow marks for chat
mentions, filled marks for commands to the site.

    python tier1/spread/spread_trace.py --mentions botme_mentions.jsonl \
        --telemetry open_chat_export/telemetry.jsonl --site dunkirk.sh \
        --names agent_name_id_map.json --labels tier1/spread/botme_labels.json \
        --title "Botme" --out-json botme_spread.json --out-html botme_spread.html

Descriptive only. A chat mention is not proof an agent read or acted on a
message, and commands invisible to the parser (GUI, scripts) are missing.
"""
import argparse
import collections
import datetime as dt
import html
import json


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def load_names(path):
    if not path:
        return {}
    m = json.load(open(path, encoding="utf-8"))
    out = {}
    for village in (m.get("villages") or {}).values():
        for k, v in village.items():
            if isinstance(v, dict) and v.get("names"):
                out[k] = v["names"][0]
    return out


def build(mentions, telemetry_rows, site, names, labels):
    said = collections.defaultdict(list)
    human = []
    for m in mentions:
        if not m.get("time"):
            continue
        if m["speaker_kind"] == "human":
            human.append(ts(m["time"]))
        elif m.get("agent_id"):
            said[m["agent_id"]].append(ts(m["time"]))
    did = collections.defaultdict(list)
    for r in telemetry_rows:
        if any(h == site or h.endswith("." + site) for h in r.get("outside_services") or []):
            did[r["agent_id"]].append(ts(r["timestamp_utc"]))
    agents = set(said) | set(did)
    lanes = []
    for a in agents:
        s, d = sorted(said.get(a, [])), sorted(did.get(a, []))
        name = names.get(a, a[:8])
        lanes.append({"agent_id": a, "name": name, "label": labels.get(name, "unlabelled"),
                      "first_said": s[0].isoformat() + "Z" if s else None,
                      "first_did": d[0].isoformat() + "Z" if d else None,
                      "said_count": len(s), "did_count": len(d),
                      "said_before_did_hours": round((d[0] - s[0]).total_seconds() / 3600, 2) if s and d else None,
                      "said": [x.isoformat() + "Z" for x in s], "did": [x.isoformat() + "Z" for x in d]})
    key = lambda l: min(x for x in (l["first_said"], l["first_did"]) if x)
    lanes.sort(key=key)
    order_said = [l["name"] for l in sorted((l for l in lanes if l["first_said"]), key=lambda l: l["first_said"])]
    order_did = [l["name"] for l in sorted((l for l in lanes if l["first_did"]), key=lambda l: l["first_did"])]
    human = sorted(human)
    return {"site": site, "lanes": lanes,
            "human_mentions": [x.isoformat() + "Z" for x in human],
            "first_human_mention": human[0].isoformat() + "Z" if human else None,
            "order_first_said": order_said, "order_first_did": order_did,
            "said_never_did": [l["name"] for l in lanes if l["first_said"] and not l["first_did"]],
            "did_never_said": [l["name"] for l in lanes if l["first_did"] and not l["first_said"]],
            "note": ("Descriptive. A mention is not proof of reading or acting; commands outside the "
                     "parser's view (browser, scripts) are missing; failed source days are not zero.")}


COLORS = {"joined": "var(--joined)", "declined": "var(--declined)", "stayed out": "var(--out)", "unlabelled": "var(--muted)"}


def render_html(res, title):
    lanes = res["lanes"]
    times = [ts(x) for l in lanes for x in l["said"] + l["did"]] + [ts(x) for x in res["human_mentions"]]
    if not times:
        return "<p>No data.</p>"
    t0 = min(times).replace(hour=0, minute=0, second=0, microsecond=0)
    t1 = max(times).replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
    span = (t1 - t0).total_seconds()
    W, left, lane_h, top = 1000, 190, 26, 34
    rows = [("Humans (unnamed)", "human", [], res["human_mentions"])] + \
           [(l["name"], l["label"], l["did"], l["said"]) for l in lanes]
    H = top + lane_h * len(rows) + 30
    x = lambda s: left + (W - left - 20) * (ts(s) - t0).total_seconds() / span
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s spread timeline" style="width:100%%;min-width:760px">' % (W, H, html.escape(title))]
    d = t0
    while d <= t1:
        xx = left + (W - left - 20) * (d - t0).total_seconds() / span
        out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="var(--grid)"/>' % (xx, xx, top - 8, H - 24))
        out.append('<text x="%.1f" y="%d" class="tick" text-anchor="middle">%s</text>' % (xx, top - 14, d.strftime("%d %b")))
        d += dt.timedelta(days=1)
    for i, (name, label, did, said) in enumerate(rows):
        y = top + i * lane_h + lane_h / 2
        out.append('<text x="%d" y="%.1f" class="lane" text-anchor="end" dominant-baseline="middle">%s</text>' % (left - 10, y, html.escape(name)))
        col = COLORS.get(label, "var(--muted)") if label != "human" else "var(--human)"
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--grid)" stroke-dasharray="2 4"/>' % (left, W - 20, y, y))
        for s in said:
            out.append('<circle cx="%.1f" cy="%.1f" r="4" fill="var(--bg)" stroke="%s" stroke-width="1.6"><title>said · %s</title></circle>' % (x(s), y - 5, col, s))
        for s in did:
            out.append('<rect x="%.1f" y="%.1f" width="3" height="9" fill="%s" opacity=".8"><title>did · %s</title></rect>' % (x(s) - 1.5, y, col, s))
    out.append('<text x="%d" y="%d" class="tick">UTC days</text></svg>' % (left, H - 6))
    tbl = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        html.escape(l["name"]), html.escape(l["label"]), (l["first_said"] or "—")[:16].replace("T", " "),
        (l["first_did"] or "—")[:16].replace("T", " "),
        "%d / %d" % (l["said_count"], l["did_count"])) for l in lanes)
    return """<title>%(t)s Spread Trace</title>
<style>
:root{--bg:#f6f7f5;--fg:#1d2321;--muted:#66706c;--grid:#d6dbd8;--joined:#b4472f;--declined:#2f6d8f;--out:#7a6a2f;--human:#5b5f63;
--display:"Archivo","Segoe UI",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151918;--fg:#e4e8e6;--muted:#9aa5a0;--grid:#2c3431;--joined:#e8846d;--declined:#79b6d8;--out:#cdb86e;--human:#aab0b5;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#151918;--fg:#e4e8e6;--muted:#9aa5a0;--grid:#2c3431;--joined:#e8846d;--declined:#79b6d8;--out:#cdb86e;--human:#aab0b5;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.5 var(--display);padding-inline:16px;padding-block:8px 48px}
.wrap{max-width:1040px;margin:0 auto}h1{font-size:1.6rem;margin:18px 0 4px;text-wrap:balance}
p{max-width:70ch;color:var(--muted)}.chart{overflow-x:auto}
.tick{font:11px var(--mono);fill:var(--muted)}.lane{font:12px var(--display);fill:var(--fg)}
.key{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.85rem;color:var(--muted)}.key b{font-weight:600}
table{border-collapse:collapse;font:.82rem var(--mono);width:100%%}td,th{text-align:left;padding:4px 10px 4px 0;border-bottom:1px solid var(--grid)}
th{color:var(--muted);font-weight:500}.tw{overflow-x:auto}
</style>
<div class="wrap"><h1>%(t)s: who said it, who did it</h1>
<p>Each lane is one agent. Hollow circles are chat messages mentioning %(t)s; filled bars are commands sent to <code>%(site)s</code>. Lane colour is the agent's recorded choice. Descriptive only: a mention isn't proof an agent read or acted on it, and browser or script activity isn't visible.</p>
<div class="key"><span><b style="color:var(--joined)">■</b> joined</span><span><b style="color:var(--declined)">■</b> declined</span><span><b style="color:var(--out)">■</b> stayed out</span><span><b style="color:var(--human)">○</b> humans</span><span>○ said · ▮ did</span></div>
<div class="chart">%(svg)s</div>
<div class="tw"><table><thead><tr><th>agent</th><th>choice</th><th>first said (UTC)</th><th>first did (UTC)</th><th>said / did</th></tr></thead><tbody>%(tbl)s</tbody></table></div></div>
""" % {"t": html.escape(title), "site": html.escape(res["site"]), "svg": "".join(out), "tbl": tbl}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mentions", required=True)
    p.add_argument("--telemetry", required=True)
    p.add_argument("--site", required=True)
    p.add_argument("--names")
    p.add_argument("--labels")
    p.add_argument("--title", default="Topic")
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-html", required=True)
    a = p.parse_args(argv)
    mentions = [json.loads(l) for l in open(a.mentions, encoding="utf-8") if l.strip()]
    rows = (json.loads(l) for l in open(a.telemetry, encoding="utf-8") if l.strip())
    labels = json.load(open(a.labels, encoding="utf-8")) if a.labels else {}
    res = build(mentions, rows, a.site, load_names(a.names), labels)
    json.dump(res, open(a.out_json, "w", encoding="utf-8"), indent=2)
    open(a.out_html, "w", encoding="utf-8").write(render_html(res, a.title))
    print(json.dumps({k: res[k] for k in ("order_first_said", "order_first_did", "said_never_did",
                                          "did_never_said", "first_human_mention")}, indent=2))


if __name__ == "__main__":
    main()
