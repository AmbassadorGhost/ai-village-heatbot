# Handoff: Tier 1 v0.2, one exporter rerun needed tonight

**From:** Adam and Claude (Adam's side) · **To:** Greg and his agent · **When:** Sat 3 Oct, about 15:00 CT
**Branch:** `tier1-detector` (PR #3)

## The decision

v0.1 will **not** ship as the urgent tier. The ratings (`tier1/RATING_RESULT.md`) showed it fires on *novelty*: a site new to an agent. That's Tier 2 quality, and it can't scale to hundreds of agents.

**v0.2 alerts only on outward actions realistically likely to cause harm:** CAPTCHA circumvention, block evasion, automated writes at volume, swarm writes, account creation, mass messaging and payments. Reading a page never fires. The rules are fixed in `tier1/TIER1_V02_SPEC.md`.

## Why we need you

v0.2 needs to know whether a request **read or wrote**, along with browser-identity spoofing, proxy flags and sign-up addresses. The current export strips all of that. We can't fetch the village API from Adam's side, so **the rerun has to happen on your machine, tonight if possible.** If you can't, tell Adam: his laptop can run the same scripts on Sunday.

## Steps

1. **Install the add-on.** Copy `tier1/exporter_addon/action_features.py` next to your `export_telemetry.py`. Then apply `tier1/exporter_addon/export_telemetry_v02.patch`. It's 3 small hunks against the exporter we were sent, with SHA-256 `ecef5e81…`. The patch adds:
   - `import action_features`;
   - schema `tier1-telemetry-v0.2`;
   - `'action': action_features.extract(command) if is_command else None` on each row.
2. **Run the tests:**
   - `cd tier1/exporter_addon && python -m unittest -v test_action_features`, which should give 28 OK, including a privacy test: no command text, paths, queries, header values or credentials in the output;
   - `cd tier1 && python -m unittest test_tier1_v02 test_tier1_detector`, which should give 48 OK, and `python -m unittest test_tier1_live`, which should give 9 OK.
3. **Re-export three periods from your private cache.** Fetch only what's missing.

   | period | village | dates | purpose |
   |---|---|---|---|
   | training | main | 2026-04-06, 2026-06-16:2026-08-24 | burden gate (≤ 1 alert per observed week) |
   | **fresh test** | main | **2026-08-25:2026-10-02** | never used for Tier 1, so this is the clean test (needs fetching) |
   | Botme demo | open-chat | 2026-09-01:2026-09-21 | demonstration only |

   Example: `python fetch_telemetry.py --village main --dates 2026-08-25:2026-10-02`, then `python export_telemetry.py --village main --input private_source_cache/main_telemetry_2026-0[89]-*.json.gz … --output v02_fresh/`.
4. **Run v0.2 on each period:** `python tier1/tier1_v02.py <telemetry.jsonl> --out alerts.jsonl --summary summary.json`.
5. **Send Adam, for each period:**
   - `summary.json`, which includes **feature counts**, so we can see whether the parser detects writes, spoofing and so on;
   - `alerts.jsonl`;
   - a `coverage.json`;
   - if the fresh period has any alerts, a rating pack built the same way as last time (`make_rating_sample.py`), with the evidence rows **plus their `action` fields**.

**Order of operations.**
- **Run the training months first.** If the burden is over 1 alert per week, the spec allows **one** threshold change, on the training months only, recorded as v0.2.1. **Please send us the numbers before changing anything.**
- **Then run the fresh period once.**
- **Botme can run any time,** but it's a demonstration only: we designed v0.2 after seeing it.

## Also tonight, if you can: deploy the live urgent tier

`live_server.py` on this branch now runs Tier 1 v0.2 live, with all tests passing:
- **Every 10 min it reads the public command logs,** and stores flags and hostnames only, never command text.
- **It runs v0.2 and posts an "URGENT" notice for any new alert.** Each notice carries the **agent's own nearest chat line**, the context both raters were missing.
- **Startup history is never paged.**
- **The viewer has a new "Urgent tier" panel.**

**To turn on Discord notices:** create a *separate* webhook for an urgent channel, then add two keys to `discord.local.json`:
- `"urgent_enabled": true`
- `"urgent_webhook_url": "https://discord.com/api/webhooks/…"`

Heat notices are unaffected.

**Optional:**
- To activate block evasion (U2) live, set `"tier1": {"h1_classifier": "<path to frozen h1_telemetry.py>"}` in `live.config.json`.
- Copy your `outside_services.py` into `tier1/exporter_addon/` for the same host parser as the export.

**For the demo:** a screenshot of the viewer with the urgent panel, plus any notice that fires.

## Privacy

The add-on outputs flags, request methods and hostnames only. **No raw text leaves the private cache.** If you spot a field that could carry anything identifying, drop it and tell us.

## Already settled

**`dunkirk.sh` is Botme.** Your Open Chat export shows participants' commands going to `botme.idk.dunkirk.sh` and `cap.dunkirk.sh`.
