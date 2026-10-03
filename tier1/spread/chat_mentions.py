#!/usr/bin/env python3
"""Who mentioned a topic in public village chat, and when. Exports NO text.

For each chat message (agent or human) containing any keyword, writes one row:
time, event id, speaker kind (agent / human), agent id if an agent, the
action type, and which keywords matched. Human speakers are never identified.

Reads Greg's cached pages (`open-chat_events_<day>_page<N>.json.gz`) when
present; otherwise fetches the public events API (the same URL as
locate_botme.py) and caches the pages.

    python tier1/spread/chat_mentions.py --village open-chat \
        --dates 2026-09-01:2026-09-23 --keywords botme dunkirk \
        --cache private_source_cache --out botme_mentions.jsonl
"""
import argparse
import datetime as dt
import gzip
import json
import urllib.request
from pathlib import Path

VILLAGES = {"main": "00ebc425-074c-466f-ab2d-5aa2efa445aa",
            "open-chat": "25a9bc78-7ff4-4136-a948-aa6fbeea9e92"}
API = "https://theaidigest.org/village/api/events?villageId=%s&date=%s&page=%d"
TALK = {"AGENT_TALK", "USER_TALK"}
MAX_BYTES = 20 * 1024 * 1024


def pages(village, day, cache):
    for page in range(1, 41):
        path = cache / ("%s_events_%s_page%d.json.gz" % (village, day, page))
        if path.exists():
            raw = gzip.decompress(path.read_bytes())
        else:
            req = urllib.request.Request(API % (VILLAGES[village], day, page),
                                         headers={"User-Agent": "Heatbot research data preparation/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("page exceeds size cap")
            cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(raw))
        data = json.loads(raw)
        if data.get("windowDate") not in (None, day):
            raise ValueError("source date mismatch")
        yield data
        if not data.get("hasMore"):
            return
    raise ValueError("page limit reached for %s" % day)


def mentions(events, keywords):
    out = []
    for e in events:
        d = e.get("data") or {}
        action = d.get("actionType")
        if action not in TALK:
            continue
        content = d.get("content")
        if not isinstance(content, str):
            continue
        low = content.casefold()
        hit = sorted(k for k in keywords if k in low)
        if not hit:
            continue
        human = action == "USER_TALK" or (d.get("speakerType") or "").upper() == "HUMAN"
        out.append({"time": e.get("createdAt"), "event_id": e.get("id"),
                    "speaker_kind": "human" if human else "agent",
                    "agent_id": None if human else (d.get("agentId") or d.get("speakerId")),
                    "action_type": action, "keywords": hit})
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--village", choices=VILLAGES, required=True)
    p.add_argument("--dates", required=True, help="START:END inclusive, YYYY-MM-DD")
    p.add_argument("--keywords", nargs="+", required=True)
    p.add_argument("--cache", type=Path, default=Path("private_source_cache"))
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    start, end = (dt.date.fromisoformat(x) for x in a.dates.split(":"))
    kws = [k.casefold() for k in a.keywords]
    rows, seen, coverage = [], set(), []
    day = start
    while day <= end:
        n = 0
        try:
            for data in pages(a.village, day.isoformat(), a.cache):
                for m in mentions(data.get("events") or [], kws):
                    if m["event_id"] in seen:
                        continue
                    seen.add(m["event_id"])
                    rows.append(m)
                    n += 1
            coverage.append({"day": day.isoformat(), "status": "complete", "mentions": n})
        except Exception as exc:
            coverage.append({"day": day.isoformat(), "status": "failed", "error_type": type(exc).__name__})
        day += dt.timedelta(days=1)
    rows.sort(key=lambda r: (r["time"] or "", r["event_id"] or ""))
    with a.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    a.out.with_suffix(".coverage.json").write_text(json.dumps(
        {"village": a.village, "keywords": kws, "days": coverage,
         "note": "Chat messages only (AGENT_TALK/USER_TALK). No text exported; humans not identified. "
                 "Failed days are not zero mentions."}, indent=2), encoding="utf-8")
    print(json.dumps({"mentions": len(rows), "failed_days": [c["day"] for c in coverage if c["status"] != "complete"]}))


if __name__ == "__main__":
    main()
