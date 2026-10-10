# heatbot v3 (10 Oct 2026): fixed label timing + a year of Haiku labels

**Status: local branch `heatbot-v3`, not pushed** (hackathon judging is still under way).
- **Base.** The branch sits on Adam's `post-submission` branch, so it includes Adam's two changes: the optional separate urgent webhook, and heat that holds while the village is paused (decay runs on village time in the live viewer).
- **What v3 is.** A new model file, `heatbot_model_v3.json`, for the same engine.
- **Live viewer.** The main village's live viewer runs v3 through `live.config.json` → `"model_path"`. `heatbot_model.json` stays the frozen v2 study model, and Open Chat keeps v2.
- **When switching models, delete `heatbot.state.json`** so v2-scale heat doesn't carry over. With pause-aware decay, heat no longer cools overnight.

## 1. A timestamp bug in v2's training labels
- **What happened.** Monitor findings from 6 Apr to 27 Jul 2026 are stamped with a bare UTC clock time (`18:43:15`, `[20:39:31]`). From 22 Jul the monitor writes `YYYY-MM-DD HH:MM:SS PT`. v2's pipeline (`build_dataset`, `calibrate_v2`, `forward_eval.load_truth`) read **every** stamp as Pacific, which put 1,682 findings (522 of them misalignment) 7 hours late.
- **How we know.** For each finding, we checked whether the named agent had any event within ±1 h of the stamp:

  | stamp type | read as UTC | read as PT |
  |---|---|---|
  | bare stamps | 100.0% | 21.4% |
  | date-prefixed stamps | 22.9% | 99.9% |

  Script: `scripts/tz_check2.py`.
- **Effect on v2's training hours.** 146 of v2's 1,702 positive agent-hours were the wrong hours, and 1,232 real positive hours were labelled clean. With the fix there are 2,788 positive hours.
- **Effect on round 1.** Its held-out month (25 Aug–18 Sep) used only PT stamps, so the test itself was fair. The model it tested had been trained on mis-timed labels.

## 2. What was tested (pre-registered: `PLAN.md`, hashes in `MANIFEST_*.txt`, deviations in `DEVIATIONS.md`)
All three models share one pipeline (`e3_fit.fit`) and one engine, and are scored with round 1's `p8_auc.run_p8` (unchanged). `score.py` reproduces round 1's sealed result exactly: 0.4803, CI 0.4098–0.561.

| model | training |
|---|---|
| A | v2 as submitted |
| B | v2's data with corrected stamps |
| **C = v3** | B plus Haiku high-confidence labels for 2 Apr 2025–5 Apr 2026 |

**Within-agent AUC, `general` channel, symmetric (real-time), medium+high labels, DeepSeek-V3.2 excluded:**

| held-out period | A | B | **C (v3)** |
|---|---|---|---|
| **25 Aug–6 Oct** (26 days, 4,190 positives; primary) | 0.48 (0.42–0.57) ruled out | 0.53 (0.49–0.60) ruled out | **0.60 (0.54–0.66) demonstrated, 5/5 folds** |
| 19 Sep–6 Oct (8 days; weeks no version was tuned on) | 0.50 (0.39–0.61) inconclusive | 0.63 (0.46–0.75) inconclusive | **0.69 (0.55–0.78) demonstrated** |
| old year, Haiku labels (A and B never saw it) | 0.51 (0.50–0.52) ruled out | 0.53 (0.50–0.55) ruled out | (trained on it) |

- **C's fixed sequence, 25 Aug–6 Oct:**
  - real-time: 0.60, demonstrated;
  - shortly before (the hour ahead of a flag): 0.57 (0.52–0.63), demonstrated;
  - lead time: 0.56 (0.50–0.61), inconclusive.

  The headline is therefore "shortly before".
- **Paired differences, 25 Aug–6 Oct** (cluster bootstrap over agents):
  - B−A: +0.05 (−0.01 to +0.08);
  - C−B: +0.07 (+0.01 to +0.13);
  - C−A: +0.12 (+0.01 to +0.20).
- **Per channel** (descriptive, C, 25 Aug–6 Oct):
  - conflict: 0.68 (0.60–0.75);
  - deceptive: 0.59 (0.53–0.63);
  - outreach: 0.62 (wide CI);
  - off-goal: 0.50;
  - erratic: 0.52.

  v2's own conflict channel already scored 0.69 here; round 1 never tested channels other than `general`.

## 3. Limits
- **0.60 sits exactly on the agreed usefulness bar.** "Demonstrated" means a real effect whose interval reaches the useful size, not an effect clearly above it.
- **Part of the gain is familiarity with returning agents.** This split is post hoc and descriptive. For agents also active in the old year, AUC went from 0.46 (v2) to 0.63 (v3); for agents new since April, from 0.51 to 0.57.
- **Alert burden is high.** C fires about 71 HOT+ alerts per village-week across all channels, about 30 of them from the conflict channel. `general` fires about 5 a week with 89% precision, but nearly all of those are DeepSeek-V3.2.
- **v3's extra alerts didn't find hidden misbehaviour.**
  - Method: we took 82 alert episodes that no misalignment finding covered and mixed them blind with 82 random control moments. Haiku then labelled ±20 min excerpts.
  - Result: it found verified misalignment in 47.6% of both (p = 0.56). The alerts the monitor didn't flag are no richer than random moments.
- **Labels are noisy.** The labels are an LLM monitor's and Haiku's: about half of either survives a strict audit.
- **Live settings** (added after the pre-registered runs; descriptive).
  - **Adam's engine with its defaults** gives identical results.
  - **With the live viewer's settings** (pause-aware decay, term novelty, consolidation off, live channel list), v3 does as well or better.

    | period | v2 | v3 | fixed sequence |
    |---|---|---|---|
    | 25 Aug–6 Oct | 0.46 | 0.59 (0.54–0.63) | all three claims demonstrated, including lead time (0.55, 0.51–0.60) |
    | 19 Sep–6 Oct | 0.48 | 0.70 (0.57–0.78) | |

    The paired difference, v3 − v2, is +0.13 (+0.04 to +0.20).
  - **Live alert burden** is about 31 HOT+ per village-week:
    - conflict: 23 a week, 20% precision. The conflict channel is the one to quieten first.
    - off-goal: 5 a week.
    - general: 1.4 a week.

  Results are in `results_live/`.

## 4. Reproduce
The scripts in `scripts/` use this session's paths: the HF export `aidigestorg/ai-village` (gated; research use only) split by Pacific day, and the round-4 calibration package.

Order:
1. `split_hf_events.py`
2. `build_inputs.py`
3. `build_dataset.py` in each model dir
4. `fit_model.py B|C`
5. `score.py MODEL PERIOD OUT`
6. `compare.py`

The derived label files are not in the repo.
