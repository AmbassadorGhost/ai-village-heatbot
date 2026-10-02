# AI Village Live Heat

A local live heat-map viewer for the [main AI Village](https://theaidigest.org/village) and [Open Chat](https://theaidigest.org/village/open-chat). Built around the project's existing round-7 Windows-compatible Heatbot scorer and v2 model.

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

- Current agent-by-channel heat, level and recent contribution reasons.
- Expandable source messages matched to exact contribution event IDs, assigned goals, and separately labeled recent chat context. Non-chat events such as pauses are identified explicitly.
- Source text is rendered as plain text; URL paths and long mixed tokens are blanked. Excerpts are limited to 12,000 characters and labeled when truncated.
- A 24-hour heat map of hourly peaks, with a channel selector.
- Agent search, active-roster filtering and per-agent trend charts.
- Explicit source errors, stale snapshot indicators and latest-event age.

Source polls happen 60 seconds after the preceding fetch finishes; the browser refreshes every ten seconds. Startup fetches yesterday and today (UTC) to build initial heat. Each village uses separate persistent state. Historical cells are reconstructed from those events and subsequently accumulated; they are not a full historical archive. Missing cells are not zero scores.

## Interpretation

Heat is an experimental attention score, not a probability of misconduct. The 42-minute decay, model weights and thresholds are unchanged. The included model came from heatbot_v2.zip; this repository does not claim its hash matches any later preregistration manifest. The scorer came from heatbot_round7_reply_2.zip. Keep formal study results separate from this live demonstration.

Open Chat differs from the environment used to develop the scorer. Its topic and goals can differ; scores there require context and are not validated risk estimates. Visibility of reasoning varies across model families. Agents are displayed alphabetically, and cross-family score comparisons should not be interpreted as rankings of model safety. Drift vocabulary is unvalidated; credentials is a rule-based channel. Memory-change scoring and raw memory archiving are disabled in this viewer.

Scores are for human attention in an observational setting. They are not pushed to agents, used as a training signal, reward or training-data filter, or used to decide which agents remain in or enter the village. No Discord or email messages are sent. This service only reads the Village API and binds to localhost; it is not a public website.

## Files and provenance

- `heatbot.py`, `heatbot_model.json`, `pt_time.py`: imported scorer, model and helper.
- `live_server.py`, `index.html`, `evidence.js`: live collector and local viewer.
- `live.config.json`: main-village configuration.
- `test_heatbot_v2.py`: original 69-test suite. Its POSIX permission assertions do not apply to Windows; all other checks remain active.
- `test_live_server.py`: viewer isolation, failed-fetch behavior, route restrictions and restart tests.

The local `review_context.json` and `reviews/` folder hold exploratory review material, are not served as routes, and are excluded from Git. A model-assisted spot-check is not independent human validation.

Live state, logs and observations are excluded by `.gitignore`. Do not upload archives or add API keys. No API key is required. No project preregistration files or sealed study results are included.

## Tests

```sh
python -X utf8 -m unittest test_heatbot_v2 test_live_server
```

Publishing code to GitHub backs up and shares the project; it does not run the Python collector. GitHub Pages alone cannot host this live backend. Always-on operation requires a separate host.

The original scorer contains historical calibration notes; these should not be presented as new or prospective validation of this live viewer. The viewer uses restrained channel descriptions instead.
