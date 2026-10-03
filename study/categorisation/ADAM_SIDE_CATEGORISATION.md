# Independent categorisation: Adam's side

**Prepared by:** Claude (measurement and validity, Adam's side), for Adam.
**When:** 2 Oct 2026, about 21:35 CT, before seeing Greg's side's categorisation.
**Rules applied:** `PREREGISTRATION_SIGNOFF_v1.2.md`, Part A (A.1, A.2), as amended by `DEVIATIONS_v3.1.md`. Applied **by hand** from the reported numbers, then compared with the categories the frozen code printed.

## Integrity checks, done before reading any result
- **E2:** all 12 result files are byte-identical to the copy Adam's side has held sealed since 23 Sep. The deciding file is `01c23fd1…e00d3`.
- **P8:** the result is `158b7db5…2721`, identical to the sealed copy from the round-7 reply.
- **Frozen code:** `p8_auc.py`, `test_p8_auc.py`, `forward_eval.py`, `h1_telemetry.py` and `test_h1_telemetry.py` are identical to Adam's side's copies. The model is `107192d5…` (the frozen E2 model).
- **Signed documents:** they differ from the copy Claude signed only by Adam's signature row.

## A.2: P8, within-agent AUC of `general` heat, 1h

Settings: med/high labels, roster-reviewed, DeepSeek-V3.2 excluded, 27,222 moments, 23 contributing agents, seed 0, 1,000 draws, SESOI 0.60.

| claim | within-agent AUC | 95% CI | folds counting (≥20 pos.) | folds holding (>0.5) | category, by hand | code |
|---|---|---|---|---|---|---|
| **symmetric** (real time) | 0.480 | 0.410–0.561 | 5 / 5 | 3 | **ruled out** (CI upper < 0.60; CI lower ≤ 0.5) | ruled_out ✓ |
| forward | 0.473 | 0.416–0.542 | 5 / 5 | 3 | ruled out | ruled_out ✓ |
| onset (lead time) | 0.470 | 0.400–0.556 | 5 / 5 | 3 | ruled out | ruled_out ✓ |

**How each one was classified.** All three claims are testable (5 of 5 folds count). None meets "demonstrated" or "real but small," which need a CI lower bound above 0.5 and at least 4 folds holding. Each has a CI upper bound below 0.60, so each is **"ruled out."**

**Fixed sequence.** Symmetric is tested first and doesn't pass, so the sequence stops. **No claim is headlined.** Forward and onset are reported descriptively, both "ruled out."

**Wording, per the P2 categories:** *a within-agent effect of the pre-registered useful size (AUC ≥ 0.60) is ruled out for real-time, forward and lead-time detection.* This is **not** a claim that heat carries no information. The point estimates are at or slightly below 0.5, and every CI includes 0.5.

## A.1: E2, alert-level claims (declared untestable before unsealing)

| | value |
|---|---|
| hot+ `general` alerts, primary analysis | 9 (folds 4, 3, 2, 0, 0) |
| category | **untestable,** as pre-declared; no fold reaches 20 |

**Descriptive (P5), deciding file, general, hot+, 1h:**

| mode | precision | `base_event` | lift (CI) |
|---|---|---|---|
| symmetric | 0.222 (2 of 9) | 0.099 | 2.23 (0.0–9.75) |
| forward | 0.0 | 0.047 | 0.0 |
| onset | 0.0 | 0.041 | 0.0 |

- **Median lead time:** none (n = 0).
- **AUC of raw heat (pooled):** forward 0.491 / 0.515 / 0.520 / 0.506, and onset 0.491 / 0.513 / 0.519 / 0.505, at 30m / 1h / 2h / 4h.

## Pre-specified descriptive numbers from P8 (not deciding)

| mode | pooled AUC | per-agent AUC: median (IQR), how many above 0.5 | top 1%: lift pooled / own-baseline | top 5%: lift pooled / own-baseline |
|---|---|---|---|---|
| symmetric | 0.532 | 0.518 (0.395–0.588), 12 of 23 | 0.92 / 1.53 | 0.88 / 1.36 |
| forward | 0.515 | 0.502 (0.383–0.594), 12 of 23 | 0.00 / 0.48 | 0.56 / 0.92 |
| onset | 0.513 | 0.502 (0.378–0.547), 12 of 23 | 0.00 / 0.20 | 0.69 / 0.59 |

## Not interpreted here
This record applies the rules and nothing more. Interpretation (why, and what it means for the product and the write-up) waits until both sides' categorisations have been compared.
