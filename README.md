# AI Village Live Heat

A local live heat-map viewer for the [main AI Village](https://theaidigest.org/village) and [Open Chat](https://theaidigest.org/village/open-chat). Built around the project's existing round-7 Windows-compatible Heatbot scorer and v2 model.

## Start on Windows

1. Install Python 3.9+ from https://www.python.org/ if it is not already available. No third-party Python packages are required. The launcher also recognizes the bundled Codex Python runtime when available.
2. Download this repository as a ZIP and extract it, or clone it.
3. Double-click **START_HEATMAP.cmd**.
4. Open http://127.0.0.1:8765 for the main village or http://127.0.0.1:8766 for Open Chat.

Double-click **STOP_HEATMAP.cmd** to stop both collectors. The collectors continue when the browser closes, but stop on shutdown and pause during sleep. Restart with START_HEATMAP.cmd after restarting the computer. No startup task is installed.

**One-button control:** `TOGGLE_HEATBOT.cmd`, or the installed **Heatbot ON-OFF** desktop shortcut, starts both villages and the temporary public demo when they are off, and stops all four services when they are on. A confirmation window reports the resulting state. Starting can take a little time; rapid double-clicks are ignored while a change is underway. Turning on opens the local dashboard, and the new public address is saved in `tools/demo-url.txt`.

Alternative, in separate terminals (Windows, macOS or Linux):

```sh
python -X utf8 live_server.py
python -X utf8 live_server.py --open-chat
```

## What you see

- Current agent-by-channel heat, level and recent contribution reasons.
- Expandable source messages matched to exact contribution event IDs, assigned goals, and separately labeled recent chat context. Non-chat events such as pauses are identified explicitly.
- Source text is rendered as plain text; URL paths and long mixed tokens are blanked. Excerpts are limited to 12,000 characters and labeled when truncated.
- A 24-hour heat map of hourly peaks, with a channel selector.
- Agent search, active-roster filtering and per-agent trend charts.
- Explicit source errors, stale snapshot indicators and latest-event age.

Source polls happen 60 seconds after the preceding fetch finishes; the browser refreshes every ten seconds. Startup fetches yesterday and today (UTC) to build initial heat. Each village uses separate persistent state. Historical cells are reconstructed from those events and subsequently accumulated; they are not a full historical archive. Missing cells are not zero scores.

## Interpretation

Heat is an experimental attention score, not a probability of misconduct. The 42-minute decay, model weights and thresholds are unchanged. The live product now discounts repeated lexicon terms per agent over a two-hour window (0.5 per prior use), in both villages. This exploratory change reduces repeated-topic heat; it has not established improved real-world sensitivity or false-alarm rates. Warm, Elevated and High describe everyday attention levels; action detections and urgent candidates are shown separately in the v0.3 action panel. The included model came from heatbot_v2.zip; this repository does not claim its hash matches any later preregistration manifest. The scorer came from heatbot_round7_reply_2.zip. Keep formal study results separate from this live demonstration. The October 2 rollout backs up the prior local state and rebuilds the live chart from public source events; the API records the scoring version and rebuild time. Earlier history is retained locally in the ignored backup directory, rather than mixed with the new chart. Late events count only retained term uses at or before their event time; previously scored later events are not retroactively rescored.

Open Chat differs from the environment used to develop the scorer. Its topic and goals can differ; scores there require context and are not validated risk estimates. Visibility of reasoning varies across model families. Agents are displayed alphabetically, and cross-family score comparisons should not be interpreted as rankings of model safety. Deception vocabulary is unvalidated; credentials is a rule-based channel. Memory-change scoring and raw memory archiving are disabled in this viewer.

Scores are for human attention in an observational setting. They are not pushed to agents, used as a training signal, reward or training-data filter, or used to decide which agents remain in or enter the village. Optional credential-tripwire alerts go to a human review channel. The collectors bind to localhost; the separate read-only gateway can publish a temporary public demo. Public availability retains the possibility that an agent discovers the demo, even though no scores are pushed to agents.

**Off-goal and Deception vocabulary\*** are separate language scores. Off-goal
uses patterns learned from past task-divergence flags. Deception vocabulary is
the original `surreptitious-or-deceptive` category, labelled explicitly as
unvalidated; it does not establish concealment, deception or gradual goal drift.
The channels have different lexicons and learned weight vectors, with some
shared words and inputs, so both can rise on the same message. They are not
mutually exclusive or statistically independent. The internal API key remains
`deceptive` for compatibility. This clarification changes labels and explanations,
not model weights, thresholds or the frozen study results.

## Optional Discord channel alerts

1. In your Discord channel, open **Edit Channel → Integrations → Webhooks**, create a webhook and copy its URL. You need permission to manage webhooks.
2. With the viewer running, open http://127.0.0.1:8765/discord and paste the URL into the password field.
3. Select **Save, send test & enable alerts**. Check that the connection test arrives in your intended channel.

Both villages then use that channel for the existing rule-based credential/browser-storage tripwire only. All everyday heat channels are dashboard-only, including under older saved webhook configurations. No digest is implemented yet. The first successful poll establishes a quiet baseline. New elevated credential signals produce alerts with scores, reasons and a scrubbed source excerpt when available. Alerts cannot mention users or roles, though channel notification settings can still notify readers. Treat excerpts as agent statements to review, not instructions.

Credential signals rearm after falling below 60% of the elevated threshold, with a 90-minute cooldown. Escalation from elevated to high can alert sooner. Each village sends at most three grouped alerts per poll; failed deliveries retry on later polls, respecting Discord rate limits. Pending alerts expire after ten minutes or when the signal is no longer elevated. Network failures can leave delivery uncertain and retries can duplicate a message. Failed source fetches do not produce alerts.

Use **Disable alerts** on the setup page to stop both villages. The webhook is stored only in local `discord.local.json`, excluded from Git and unavailable through the web server. It is a secret: do not share or upload that file. Alert state is also excluded from Git. The setup endpoint checks the local origin and a session token. No Discord bot account or third-party package is required.

Your computer and collector must remain running and awake for alerts to arrive. Sharing this repository does not run the service for your partners; they receive alerts in the Discord channel you configured.

## Files and provenance

- `heatbot.py`, `heatbot_model.json`, `pt_time.py`: imported scorer, model and helper.
- `live_server.py`, `index.html`, `evidence.js`: live collector and local viewer.
- `discord_alerts.py`, `discord_setup.html`: optional webhook delivery and local setup.
- `live.config.json`: shared product configuration inherited by both villages; optional Open Chat overrides remain separate. Novelty remains off in the base study-scorer defaults.
- `test_heatbot_v2.py`: original 69-test suite. Its POSIX permission assertions do not apply to Windows; all other checks remain active.
- `test_live_server.py`: viewer isolation, failed-fetch behavior, route restrictions and restart tests.

The local `review_context.json` and `reviews/` folder hold exploratory review material, are not served as routes, and are excluded from Git. A model-assisted spot-check is not independent human validation.

Live state, logs and observations are excluded by `.gitignore`. Do not upload archives or add API keys. No API key is required. No project preregistration files or sealed study results are included.

## Temporary public demo

`demo_server.py` is a separate read-only gateway on localhost port 8780. It exposes the main dashboard at `/`, Open Chat at `/open-chat/`, and JSON feeds at `/api/live` and `/open-chat/api/live`. It caches upstream responses for five seconds and excludes Discord status and internal diagnostics. Setup routes, arbitrary files and write requests are blocked.

On Windows, download the official [Cloudflare tunnel client](https://developers.cloudflare.com/tunnel/downloads/) into `tools/cloudflared.exe`. Run **START_DEMO.cmd** to start the local viewers and publish the gateway through a temporary Cloudflare Quick Tunnel. The HTTPS address is printed and saved in `tools/demo-url.txt`. The link is public; anyone with it can view experimental scores and the same scrubbed public message context as the local viewer. It must not be treated as private sharing.

Run **STOP_DEMO.cmd** to stop public access while leaving the collectors and Discord alerts running. Keep the computer awake and connected during the demo. Restarting the tunnel generates a new address. No startup task is installed and no uptime guarantee is implied. Tunnel binaries, URLs, process records and logs stay in the ignored `tools/` folder. The original local viewer remains local-only; publish only the gateway.

## Action detections and urgent candidates (v0.3)

The panel and `/api/actions` expose the same action object included as
`action_alerts` in `/api/live`. Public equivalents are `/open-chat/api/actions`
and `/open-chat/api/live`. A separate worker fetches public computer-use
telemetry, so a slow historical request cannot freeze the heat dashboard.
Recent dates are fetched first; missing dates and stale snapshots stay visible.
Every valid turn counts toward coverage, including non-command turns. The
frozen H1 failure classifier and outside-service parser are included, with
source hashes checked at startup. Raw commands and tool outputs are not stored
or exposed; only their extracted metadata is retained, for 30 days.

The frozen `tier1-v0.3` rules monitor CAPTCHA-solving services, persistence or
identity changes after refusals, swarm rotation, automated sending, sign-ups,
mass messaging, and payment commands. See `tier1/TIER1_V02_SPEC.md` (the filename
retains the earlier version). These are command-pattern candidates; they do
not prove completed requests, harm, or intent. GUI/browser activity and opaque
scripts can be missed. Sending-volume rules need seven prior observed village
days. "Established" means established in the available observed history.

Presentation distinguishes silent **Detection** from **URGENT candidates**
(CAPTCHA-solving services, mass messaging, and non-routine payments). Detection
delivery is opt-in: set `detection_enabled: true` in the ignored
`discord.local.json`, with the existing enabled webhook. Urgent delivery needs
its own `urgent_webhook_url` and `urgent_enabled: true`; it is off by default.
Everyday heat remains dashboard-only except the credentials tripwire.
Mentions are disabled. Startup history never sends notices. Failed deliveries
stay in a persistent outbox for retries; a five-message batch limit does not
discard later candidates. Delivery can be duplicated after an ambiguous network
failure because Discord webhooks do not provide an idempotency guarantee.

**Validation remains limited.** v0.3's fresh-month replay produced 2 alerts in
29 observed days (0.483 per observed week). Both humans rated them; neither
called either alert likely harmful. The signed outcome is **too few to judge**,
not an established false-alarm rate or evidence of reliability. In the Open Chat
case window, v0.3 produced 13 candidates but **none on Botme's challenge domain**.
The panel's separately labeled **earlier v0.1.1** replays are the novelty prototype:
21 training candidates across 51 days and 9 Open Chat candidates, including 3
on the Botme domain. That earlier retrospective detection was not early warning.
Frozen detector thresholds and the original heat model are unchanged by this
deployment; no fresh-month evaluation was rerun or retuned.

The village header and project board link to public works. The original heat
palette, sticky category labels, chart labels and source context remain.
The memory-history browser is not included.

To update an existing installation, stop its verified collectors, back up code,
preserve local configs/state and gateway, sync reviewed source, then restart.
`START_HEATMAP.cmd` does not download updates or replace running processes.
New clones normalize Python source to LF so frozen-file hash checks survive
Windows Git checkouts. Publishing to GitHub does not run the collectors.

## Verification

```sh
python -X utf8 -m unittest test_heatbot_v2 test_live_server test_discord_alerts test_demo_server test_action_monitor test_action_v03_monitor tier1.test_tier1_detector
```

Publishing code to GitHub backs up and shares the project; it does not run the Python collector. GitHub Pages alone cannot host this live backend. Always-on operation requires a separate host.

The original scorer contains historical calibration notes; these should not be presented as new or prospective validation of this live viewer. The viewer uses restrained channel descriptions instead.
