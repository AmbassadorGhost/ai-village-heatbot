# Handoff: v0.3 (final). Run it, then score the fresh month once

**From:** Adam and Claude · **To:** Greg and his agent · **When:** Sat 3 Oct, about 17:20 CT
**Branch:** `tier1-detector` at `5971452` or later. **Detector only:** your v0.2.1 exports are reused as they are.

Thank you again. Stopping at the gate, and the rotation bug report, were both exactly right. Adam has decided to **depart from the one-revision rule, openly**. It's recorded as Deviation D-v0.3 in `tier1/TIER1_V02_SPEC.md`:
- **The training months are now our development set,** not a gate.
- **Every change has to be justified from first principles,** not by the alerts it removes.
- **v0.3 is final. It's scored once on the fresh month, whatever its training result, and whatever comes back gets reported.**

**v0.3 changes:**
1. A rate limit counts as persisting only if the agent **didn't slow down**.
2. A browser identity alone moves to Tier 2.
3. Your U2S fix: refused agents are no longer counted as "others".
4. "Established" needs use that's **at least 7 days old**, so a swarm can't make its own target look normal.

## Steps (no re-export needed)

1. **Pull.** `tier1/tier1_v02.py` should hash to `71070232…`, and `action_features.py` is unchanged (`4b0929ed…`). Tests:
   - `cd tier1 && python -m unittest test_tier1_v02 test_tier1_live test_tier1_detector` should give **77 OK**;
   - `test_action_features` should give **32 OK**.
2. **Training (development set, for the record):** `python tier1/tier1_v02.py <v021 training telemetry 6a7d6226…> --out training_alerts.jsonl --summary training_summary.json`. **Whatever the number, continue.**
3. **The fresh month, ONCE:** `python tier1/tier1_v02.py <v021 fresh telemetry c38ce9df…> --out fresh_alerts.jsonl --summary fresh_summary.json`.
4. **Rating pack** (each alert shown as the live notice would show it):
   ```text
   python tier1/render_rating_pack.py --alerts fresh_alerts.jsonl --telemetry <fresh telemetry> \
       --village main --cache <your private_source_cache> --names agent_name_id_map.json \
       --sample 20 --seed 20261004 --out-md RATE_THESE_V03.md --out-json RATING_TEMPLATE_V03.json
   ```
   If there are 20 alerts or fewer, all are included. If there are zero, say so: that's a result.
5. **Botme demo:** run the same detector command on the v0.2.1 Open Chat telemetry (`aaab9286…`).
6. **Send Adam:** the summaries, alert files and rating pack. The coverage files are unchanged from v0.2.1.

**If Greg has a moment tonight:** the live deploy (webhook in `discord.local.json`) and a screenshot of the viewer's Urgent panel. The live collector uses v0.3 automatically.

Tomorrow Adam works alone. Anything that needs Greg's machine has to happen tonight.
