# E2/P8: comparison of the two independent reviews

**Date:** 2 October 2026 (America/New_York). **Rules:** pre-registration v1.2, Part A, and deviations v3.1.

**Both sides agree on every deciding category and on the testing sequence.** No category disagreement was found. Adam-side estimates match ours after allowing for display rounding.

## What that means in plain English

The older, frozen Heatbot model did not meet the agreed usefulness threshold in this held-out test. Its real-time effect is **ruled out at the predefined AUC 0.60 threshold**. The study did not demonstrate an early-warning headline.

This does not establish that every smaller signal is absent. It also does not evaluate the later exploratory novelty update in the live product.

## Category comparison

| Claim | Greg-side reviewer | Adam-side reviewer | Status under the sequence |
|---|---|---|---|
| P8 real time / symmetric | Ruled out | Ruled out | First formal test; sequence stops here |
| P8 forward | Ruled out | Ruled out | Descriptive only after the stop |
| P8 onset / lead time | Ruled out | Ruled out | Descriptive only after the stop |
| E2 general hot+ alert claim | Untestable | Untestable | Declared before unsealing; estimates remain descriptive |

The first P8 claim has AUC **0.4803**, with 95% CI **0.4098-0.5610**. All five folds count, but only three hold. The CI upper bound is below the agreed 0.60 threshold, giving the category above. Forward and onset upper bounds are also below 0.60, but the formal sequence has already stopped. Neither is a later formal rejection or a passing headline.

The E2 claim has **9** general hot+ alerts, split **4, 3, 2, 0, 0** across folds. Each fold requires **20**, and none reaches that minimum. Descriptive symmetric lift of 2.23 (CI 0-9.75) does not override the P8 result or make the alert claim testable.

## Reporting wording

> Under the pre-registered rules, the frozen general-heat model's real-time within-agent effect at the useful-size threshold (AUC 0.60) was ruled out in the held-out period. The fixed sequence stopped at that first claim. Forward and onset were reported descriptively with the same categories; no early-warning claim was demonstrated. Alert-level claims remained untestable because too few alerts fired.

Adam's three-mode summary agrees with the categories. Keep the explicit descriptive-only qualification for forward/onset wherever that summary is used.

## What is still pending

- Complete local raw-data replay/bootstrap verification: some original event, monitor and calibration inputs were not supplied. Reviewer agreement is not an independent data replication.
- Option C's combined paging-channel descriptive result and a DeepSeek-included within-agent P8 sensitivity are absent from the supplied result files. Per-channel aggregates cannot reconstruct Option C. The available E2 inclusion sensitivities are retained separately.
- H1/H1b are separate analyses. Their training power statement, roster review and implementation/input prerequisites must be completed before prospective scoring. These heat results do not assign them a category.
- The signed access-history and unequal family-measurement caveats remain applicable.

## Practical next steps

Share this comparison with Adam and use the agreed scope in the write-up. Treat the current live heat display as exploratory. Evaluate later novelty or telemetry changes separately rather than describing this frozen-model result as validation of those changes.

Greg does not need to complete the optional personal statistics worksheet. The two teams' independent reviewer assessments have now been compared.

## Provenance

Our original assessment was recorded and hashed before receiving Adam/Claude's categorisation. Its three locked-file hashes were rechecked and all matched. The received Adam-side document and the original Greg-side assessment are copied byte-for-byte alongside this new comparison; neither was edited to create agreement.

Adam-side independence and historical custody are attributed attestations. This comparison directly checks the supplied categorisation against our recorded result and verified summary estimates.

The source hashes and all numerical comparison checks are in COMPARISON_RECORD.json. No signed document, frozen code, original assessment or product configuration was changed.
