# AI Village Live Heat

**heatbot: a cheap, always-on tripwire for AI agent swarms.** Hackathon write-up: [REPORT.md](REPORT.md) · 2½-minute video: [docs/heatbot_hackathon.mp4](docs/heatbot_hackathon.mp4) (AI Swarm Dynamics Hackathon, 3–4 Oct 2026). The live demo runs from this branch (`main`) with `./run_demo.sh --public`.

A local live heat-map viewer for the [main AI Village](https://theaidigest.org/village) and [Open Chat](https://theaidigest.org/village/open-chat). Built around the project's existing round-7 Windows-compatible Heatbot scorer and v2 model.

## Run the demo on Linux or macOS

```text
./run_demo.sh            # both villages + read-only demo at http://127.0.0.1:8780
./run_demo.sh --public   # also publishes a temporary https://….trycloudflare.com link
```

Needs Python 3.9+ and nothing else (with `--public`, the official `cloudflared` client is
downloaded into the ignored `tools/` folder if it isn't installed). The public link serves only the
read-only gateway (`demo_server.py`): dashboards and JSON feeds, no setup pages, no writes. It
changes each time it starts, and stops when you press Ctrl+C or the computer sleeps.

## Start on Windows

1. Install Python 3.9+ from https://www.python.org/ if it is not already available. No third-party Python packages are required. The launcher also recognizes the bundled Codex Python runtime when available.
2. Download this repository as a ZIP and extract it, or clone it.
3. Double-click **START_HEATMAP.cmd**.
4. Open http://127.0.0.1:8765 for the main village or http://127.0.0.1:8766 for Open Chat.

Double-click **STOP_HEATMAP.cmd** to stop both collectors. The collectors continue when the browser closes, but stop on shutdown and pause during sleep. Restart with START_HEATMAP.cmd after restarting the computer. No startup task is installed.

Alternative, in separate terminals (Windows, macOS or Linux):

```sh
python -X utf8 live_server.py
python -X utf8 live_server.py --open-chat
```

## What you see

- **Action notices:** the round-3 tripwire's notices from agents' own commands (URGENT for CAPTCHA-solving services and payments, everything else a Detection), each linked to the moment in the public village player.
- Current agent-by-channel heat and level, including a rule-based **Needs help** channel (reported errors, blocks, rate limits, help requests) on a neutral blue scale.
- **What's making up this heat:** the contributions that still count after decay, largest first, each with a plain reason and a village-player link.
- Expandable source messages matched to exact contribution event IDs, assigned goals, and separately labeled recent chat context. Non-chat events such as pauses are identified explicitly.
- Source text is rendered as plain text; URL paths and long mixed tokens are blanked. Excerpts are limited to 12,000 characters and labeled when truncated.
- A 24-hour heat map of hourly peaks, with a channel selector.
- Agent search, active-roster filtering and per-agent trend charts.
- Explicit source errors, stale snapshot indicators and latest-event age.

Source polls happen 60 seconds after the preceding fetch finishes; the browser refreshes every ten seconds. Startup fetches yesterday and today (UTC) to build initial heat. Each village uses separate persistent state. Historical cells are reconstructed from those events and subsequently accumulated; they are not a full historical archive. Missing cells are not zero scores.

## Interpretation

Heat is an experimental attention score, not a probability of misconduct. The 42-minute decay, model weights and thresholds are unchanged. The included model came from heatbot_v2.zip; this repository does not claim its hash matches any later preregistration manifest. The scorer came from heatbot_round7_reply_2.zip. Keep formal study results separate from this live demonstration.

Open Chat differs from the environment used to develop the scorer. Its topic and goals can differ; scores there require context and are not validated risk estimates. Visibility of reasoning varies across model families. Agents are displayed alphabetically, and cross-family score comparisons should not be interpreted as rankings of model safety. Credentials and Needs help are rule-based channels. Memory consolidation adds no heat in this viewer, and memory-change scoring and raw memory archiving are disabled.

Scores are for human attention in an observational setting. They are not pushed to agents, used as a training signal, reward or training-data filter, or used to decide which agents remain in or enter the village. Optional Discord alerts go to a human review channel. This service reads the Village API and binds to localhost; it is not a public website.

**The `surreptitious-or-deceptive` channel is not shown in the viewer.** On the
held-out month it tracked one agent's writing style (process and governance
jargon) and scored 0 of 9 elsewhere, so a column labelled "deception" would
claim more than it measures. The scorer still computes it for the frozen study;
weights, thresholds and study results are unchanged.

## Optional Discord channel alerts

1. In your Discord channel, open **Edit Channel → Integrations → Webhooks**, create a webhook and copy its URL. You need permission to manage webhooks.
2. With the viewer running, open http://127.0.0.1:8765/discord and paste the URL into the password field.
3. Select **Save, send test & enable alerts**. Check that the connection test arrives in your intended channel.

Both villages then use that channel. The first successful poll establishes a quiet baseline, so existing high scores do not flood the channel. New hot signals produce grouped, silent heat notices per agent with scores, reasons and a scrubbed source excerpt when available. Friction and Needs help stay on the dashboard. Round-3 Detections post silently to the same channel; URGENT notices go only to a separate urgent webhook, if one is configured. Alerts cannot ping users or roles. Treat excerpts as agent statements to review, not instructions.

Signals rearm after falling below 60% of the hot threshold, with a 90-minute cooldown. Escalation from hot to critical can alert sooner. Each village sends at most three grouped alerts per poll; failed deliveries retry on later polls, respecting Discord rate limits. Pending alerts expire after ten minutes or when the signal is no longer hot. Network failures can leave delivery uncertain and retries can duplicate a message. Failed source fetches do not produce alerts.

Use **Disable alerts** on the setup page to stop both villages. The webhook is stored only in local `discord.local.json`, excluded from Git and unavailable through the web server. It is a secret: do not share or upload that file. Alert state is also excluded from Git. The setup endpoint checks the local origin and a session token. No Discord bot account or third-party package is required.

Your computer and collector must remain running and awake for alerts to arrive. Sharing this repository does not run the service for your partners; they receive alerts in the Discord channel you configured.

## Files and provenance

- `heatbot.py`, `heatbot_model.json`, `pt_time.py`: imported scorer, model and helper.
- `live_server.py`, `index.html`, `evidence.js`: live collector and local viewer.
- `discord_alerts.py`, `discord_setup.html`: optional webhook delivery and local setup.
- `live.config.json`: main-village configuration.
- `test_heatbot_v2.py`: original 69-test suite. Its POSIX permission assertions do not apply to Windows; all other checks remain active.
- `test_live_server.py`: viewer isolation, failed-fetch behavior, route restrictions and restart tests.
- `demo_server.py`, `run_demo.sh`: the read-only public gateway and the Linux/macOS launcher.
- `tier1/`: the round-3 tripwire (rules, live monitor, exporter add-on, `show_turns.py` for checking a notice against the raw command). See `tier1/TIER1_V02_SPEC.md`.
- `study/`: the frozen round-1 evaluation with its sealed results; start with `study/README.md`.

The local `review_context.json` and `reviews/` folder hold exploratory review material, are not served as routes, and are excluded from Git. A model-assisted spot-check is not independent human validation.

Live state, logs and observations are excluded by `.gitignore`. Do not upload archives or add API keys. No API key is required. The round-1 pre-registration and sealed results are in `study/`; nothing else from the study is.

## Tests

```sh
python -X utf8 -m unittest test_heatbot_v2 test_live_server test_discord_alerts test_demo_server
python -X utf8 tier1/test_tier1_live.py && python -X utf8 tier1/test_tier1_v02.py && python -X utf8 tier1/test_tier1_detector.py
cd tier1/exporter_addon && python -X utf8 test_action_features.py
```

Publishing code to GitHub backs up and shares the project; it does not run the Python collector. GitHub Pages alone cannot host this live backend. Always-on operation requires a separate host.

The original scorer contains historical calibration notes; these should not be presented as new or prospective validation of this live viewer. The viewer uses restrained channel descriptions instead.
