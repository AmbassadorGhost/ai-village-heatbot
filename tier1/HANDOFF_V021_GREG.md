# Handoff: v0.2.1, rerun then score the fresh month once

**From:** Adam and Claude · **To:** Greg and his agent · **When:** Sat 3 Oct, about 16:00 CT
**Branch:** `tier1-detector` at `b3196c0` or later.

Thank you. Your reply was exactly what the process needed: you stopped at the gate, made no changes, froze the fresh month, and spotted the parser problem. We've used the **one permitted training-months revision** and recorded it in the amendment log of `tier1/TIER1_V02_SPEC.md`. The four changes:

1. **U6 payment needs a send.** All 5 of your U6 alerts were GET price checks.
2. **Village-hosting platforms count as village-run** for U2, U3 and U3S. The platforms are `gitlab.io`, `github.io`, `workers.dev`, `substack.com` and `fourthwall.com`.
3. **U2 needs a proxy.** A browser identity alone is no longer enough.
4. **Parser proxy fix, per your `-x` observation.** `set -x`, `bash -x` and `grep -x` no longer count, and there are regression tests.

**Nothing was changed in response to Botme.**

The expected training result, from arithmetic on your list, is 2 alerts (`lesswrong.com` and `bing.com`), about 0.27 a week. **The rerun is authoritative.**

## Steps

1. **Update the code.** Pull, then copy the new `tier1/exporter_addon/action_features.py` (sha256 `63e8e126…`) next to your exporter. The patch to `export_telemetry.py` is unchanged. Tests:
   - `test_action_features` should give **29 OK**;
   - `test_tier1_v02 test_tier1_live test_tier1_detector` should give **62 OK**;
   - `tier1_v02.py` should hash to `313be684…`.
2. **Re-export all three periods** from your cache with the new add-on. The proxy flag changed, so the old exports are stale.
3. **Training first:** `python tier1/tier1_v02.py <training telemetry> --out training_alerts.jsonl --summary training_summary.json`.
   - **If it's ≤ 1 alert per observed week, continue to step 4.**
   - **If it's over, stop and send the numbers.** No further revisions are allowed, and we'll report the gate as failed.
4. **The fresh month, scored ONCE** (25 Aug–2 Oct): the same command, `--out fresh_alerts.jsonl --summary fresh_summary.json`.
5. **Rating pack for the fresh alerts.** It shows each alert exactly as the live notice would, with all six questions including the agent's nearest chat line:
   ```text
   python tier1/render_rating_pack.py --alerts fresh_alerts.jsonl --telemetry <fresh telemetry> \
       --village main --cache <your private_source_cache> --names agent_name_id_map.json \
       --sample 20 --seed 20261004 --out-md RATE_THESE_V021.md --out-json RATING_TEMPLATE_V021.json
   ```
   If there are 20 alerts or fewer, every one is included. **If there are zero, say so.** That's a result, and the feature counts will tell us whether the parser could see anything.
6. **Botme demo:** run the same command on the re-exported Open Chat telemetry.
7. **Send Adam:** both summaries, the alert files and coverage, the rating pack, and the Botme summary.

**Ratings.** Adam and Greg each answer two questions per alert, **independently**:
- **Q1:** is there enough here to decide?
- **Q2:** after checking, is this likely to cause harm outside the village?

## Live deploy (when Greg has a minute)

The live collector picks up v0.2.1 automatically from the branch. The only manual step is the **urgent-channel webhook**: add `"urgent_enabled": true` and `"urgent_webhook_url": "…"` to `discord.local.json`. A screenshot of the viewer's Urgent panel would be great for the demo.

## Spread trace: thank you, and one correction

Your run is correct, and our earlier "seventh" was a miscount on our side. **DeepSeek-V3.2 was eighth of nine agents to act** (seventh of the eight participants). It was **second to mention Botme**, 26 minutes after the first human message, and mentioned it more than any other agent (336 times). It first acted **88.5 h** later. The handoff and the write-up are fixed.
