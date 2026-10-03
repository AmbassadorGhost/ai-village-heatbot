# Greg-side independent categorisation - 2 October 2026

Recorded by Astra/Codex before seeing Adam/Claude's ratings. Greg confirmed the identical packets were sent; Adam acknowledged he was looking at them.

The frozen general-heat model did not meet the agreed usefulness threshold in the held-out period (25 August-18 September). The first real-time claim is **ruled out at AUC 0.60** under the signed category rules. The sequence stops there, so no confirmatory early-warning headline follows.

## P8: signed category rules

| Claim | Within-agent AUC | 95% CI | Folds counted / held | Category | Role |
|---|---:|---|---|---|---|
| symmetric | 0.4803 | 0.4098-0.5610 | 5 / 3 | ruled out | First formal test |
| forward | 0.4726 | 0.4155-0.5419 | 5 / 3 | ruled out | Descriptive; past stopping point |
| onset | 0.4703 | 0.4000-0.5555 | 5 / 3 | ruled out | Descriptive; past stopping point |

All five folds have enough positive moments. For every mode only three folds have AUC above 0.5, the CI lower bound is below 0.5, and the upper bound is below 0.60. Applying the rules in their prescribed order gives the categories above. I derived these categories from the estimates and checked their agreement with the stored labels.

**Plain meaning:** in this test, higher heat did not reliably separate the same agent's flagged moments from its other moments at the effect size we agreed would count. This does not establish that every useful signal is absent. It tests the frozen model, not the later exploratory novelty update.

## E2: alert claims remain untestable

The 9 general hot+ alerts split 4, 3, 2, 0, 0 across folds; none meets the minimum 20. This was declared before unsealing and is unchanged by the observed outcomes. Precision, lift and lead times remain descriptive.

In configuration 1, forward 1h precision is 0/9; its event baseline is 0.047. Symmetric 1h precision is reported as 0.222 with event baseline 0.099 and lift 2.23, but its lift CI is 0-9.75 and no fold meets the alert minimum. The positive symmetric lift does not override the P8 decision. The hot+ forward/onset lead sample within 4h is empty, so its median and IQR are undefined.

| E2 config | Labels / reviewed / agents | General hot+ forward 1h n | Precision | Event baseline | Lift | Counted alert folds |
|---|---|---:|---:|---:|---:|---:|
| 1 | medhigh / roster / noDS | 9 | 0.0 | 0.047 | 0.0 | 0 |
| 2 | medhigh / roster / all | 31 | 0.226 | 0.079 | 2.87 | 1 |
| 3 | medhigh / proxy / noDS | 9 | 0.0 | 0.049 | 0.0 | 0 |
| 4 | all / roster / noDS | 9 | 0.111 | 0.125 | 0.89 | 0 |
| 5 | all / proxy / all | 31 | 0.387 | 0.18 | 2.16 | 1 |
| 6 | all / proxy / noDS | 9 | 0.111 | 0.13 | 0.85 | 0 |

All six configurations and every available channel/level/horizon statistic are preserved in E2_ALL_AVAILABLE_DESCRIPTIVES.json. They remain descriptive; alternative configurations cannot be selected to rescue the deciding claim.

## Limits and remaining work

- The sealed reported estimates were categorised independently. Complete original input data are unavailable locally, so this is not an independent raw-data replay or bootstrap replication.
- Option C's combined paging-channel result is absent from the supplied result files. Per-channel aggregates cannot reconstruct that union. The DeepSeek-included within-agent P8 sensitivity is also absent; E2 configurations 2 and 5 are the available inclusion sensitivities.
- The signed training power estimates at AUC 0.60 were 61-78% under event-count scaling and 98-100% under agent-count scaling; at 0.55 they were 20-28% and 50-67%. These in-sample estimates were explicitly described as optimistic. Use 'not demonstrated in this design,' not 'heat never predicts.'
- H1/H1b are pending, not declared failed or untestable from these heat results. Their training power statement and roster/implementation prerequisites still apply before prospective scoring.
- Keep the signed access-history uncertainties, earlier symmetric E1 exposure, unequal family measurement caveat and live-product separation in the write-up.

## Comparison

This is the locked Greg-side assessment. Compare it only after Adam/Claude finish their own categories; record any disagreement in a new comparison document. Do not revise this original to match the other side.

Freeze manifest SHA-256: `6f11cc2685ee6aa4aa0338306233ab1478f05e98eb70856f9c758874c4990ad4`

Independent rating JSON SHA-256: `2affc701adf0dc31825dd31ee6589d8ac92e256744c6054501ab79465e2bb3bf`
