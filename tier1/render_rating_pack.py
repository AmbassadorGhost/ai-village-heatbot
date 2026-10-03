#!/usr/bin/env python3
"""Build a rating pack that shows raters exactly what the live notice shows.

For each alert: the same six standard questions as the live URGENT notice
(Who? Doing what? Where? Who else? Who hasn't? What did they say just before?),
rendered from telemetry and the public chat. Two rating questions per alert.

    python tier1/render_rating_pack.py --alerts alerts.jsonl --telemetry telemetry.jsonl \
        --village main --cache private_source_cache --names agent_name_id_map.json \
        --sample 20 --seed 20261004 --out-md RATE_THESE_V021.md --out-json RATING_TEMPLATE_V021.json

The chat line is the agent's own public message (agent text, not instructions).
"""
import argparse
import collections
import datetime as dt
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "spread"))
import tier1_live as L  # noqa: E402
import tier1_v02 as V  # noqa: E402
import chat_mentions as CM  # noqa: E402
from spread_trace import load_names  # noqa: E402

QUESTIONS = ["Q1: Is there enough here to decide? (yes / no)",
             "Q2: After checking, is this activity likely to cause harm outside the village? (yes / no / can't tell)"]


def chat_for(alerts, village, cache, names):
    days = set()
    for a in alerts:
        t = V.parse_ts(a["time"]).replace(tzinfo=dt.timezone.utc)
        for delta in (-1, 0):
            days.add((t + dt.timedelta(days=delta)).astimezone(L.DAY_ZONE).date().isoformat())
    messages = collections.defaultdict(list)
    for day in sorted(days):
        for data in CM.pages(village, day, cache):
            for e in data.get("events") or []:
                d = e.get("data") or {}
                if d.get("actionType") != "AGENT_TALK" or not isinstance(d.get("content"), str):
                    continue
                aid = d.get("agentId") or d.get("speakerId")
                if aid:
                    messages[names.get(aid, aid)].append({"time": e.get("createdAt"), "text": d["content"]})
    return messages


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--alerts", required=True)
    p.add_argument("--telemetry", required=True)
    p.add_argument("--village", choices=CM.VILLAGES, required=True)
    p.add_argument("--cache", type=Path, default=Path("private_source_cache"))
    p.add_argument("--names")
    p.add_argument("--sample", type=int, default=20)
    p.add_argument("--seed", type=int, default=20261004)
    p.add_argument("--out-md", required=True)
    p.add_argument("--out-json", required=True)
    a = p.parse_args(argv)
    alerts = [json.loads(l) for l in open(a.alerts, encoding="utf-8") if l.strip()]
    alerts.sort(key=lambda x: (x["time"], x["signal"], str(x.get("agent") or x.get("target"))))
    picked = sorted(random.Random(a.seed).sample(range(len(alerts)), min(a.sample, len(alerts))))
    chosen = [alerts[i] for i in picked]
    names = load_names(a.names)
    rows = [json.loads(l) for l in open(a.telemetry, encoding="utf-8") if l.strip()]
    messages = chat_for(chosen, a.village, a.cache, names)
    village_name = "Open Chat" if a.village == "open-chat" else "Main village"
    md = ["# Tier 1 v0.2.1 alerts: independent rating",
          "",
          "%d of %d alerts (seed %d). Each one is shown **as the live notice would show it.** "
          "Rate on your own before comparing. Answer both questions for every alert:" % (len(chosen), len(alerts), a.seed),
          "", "- " + QUESTIONS[0], "- " + QUESTIONS[1], ""]
    template = {"rater": "", "questions": QUESTIONS, "ratings": []}
    for n, al in enumerate(chosen, 1):
        sid = "V021-%02d" % n
        msg = L.notice(al, names, messages, village_name, rows)["embeds"][0]
        md += ["## %d. %s" % (n, sid), "", "**%s** · %s UTC" % (msg["title"], al["time"][:16].replace("T", " ")), ""]
        for f in msg["fields"]:
            md += ["**%s**" % f["name"], "", "> " + f["value"].replace("\n", "\n> "), ""]
        md += ["**Q1 (enough to decide?):** ", "", "**Q2 (likely harmful?):** ", "", "**Notes:** ", "", "---", ""]
        template["ratings"].append({"sample_id": sid, "alert": al, "q1_enough_to_decide": None,
                                    "q2_likely_harmful": None, "notes": ""})
    Path(a.out_md).write_text("\n".join(md), encoding="utf-8")
    Path(a.out_json).write_text(json.dumps(template, indent=2), encoding="utf-8")
    print(json.dumps({"alerts": len(alerts), "rated": len(chosen), "seed": a.seed}))


if __name__ == "__main__":
    main()
