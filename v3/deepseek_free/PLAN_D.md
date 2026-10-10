# v3 DeepSeek-free (model D): pre-registration (10 Oct 2026, written before D is fitted or scored)

## Why
DeepSeek-V3.2 drives v2 and v3's alerts. On 25 Aug-6 Oct it had 16% of misalignment incidents but 48% of v3's HOT+
alerts (61% of v2's). With it, about half of alerts land near a finding; without it, about a quarter. Its writing style
also shaped the word lists. The AUC tests already leave it out of scoring, but it still helps define what
"misbehaviour" sounds like during training.

## Model D
Identical to C (same events, labels, block list, goals, pipeline and code) except that DeepSeek-V3.2 is excluded from
training. Its agent-hours are left out of:
- lexicon selection;
- channel weights;
- term background rates;
- threshold quantiles.

That is 691 of 15,012 training hours (423 of 6,304 positive). The engine still scores DeepSeek-V3.2 at run time.

## Live change (product, not tested here)
A config list `quiet_agents` (default `["DeepSeek-V3.2"]`) keeps those agents' heat notices off Discord. They stay on
the dashboard.

## Tests
- **Data.** Fresh days the heatbot has never been scored on: monitor days from 7 Oct 2026 on, with events from the
  village API.
- **When the test runs.** Once 10 such monitor days exist. Until then no fresh-day result is looked at, except a pipeline
  smoke check that prints nothing but row counts.
- **Statistic.** Same as PLAN.md (`p8_auc.run_p8`, general channel, DeepSeek-V3.2 excluded, medium+high, roster,
  seed 0, 1000 draws, SESOI 0.60).
- **F1 (primary):** D passes on the fresh days (symmetric `demonstrated` or `real_but_small`).
- **F2:** C (v3) on the same fresh days, which replicates C's result.
- **F3 (descriptive):**
  - paired difference D-C;
  - incidents caught excluding DeepSeek-V3.2;
  - HOT+ alerts per week excluding DeepSeek-V3.2, under the live settings (`incidents.py`, `HB_LIVE`).
- **Descriptive now, on already-seen weeks** (25 Aug-6 Oct and 19 Sep-6 Oct): D vs C, the same measures as F3. These
  are not tests: D's design was motivated by those weeks' alert counts.
