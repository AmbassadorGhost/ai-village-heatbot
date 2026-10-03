# Round 1 study: the sealed, pre-registered test of heat

This folder holds everything needed to check the round-1 result in the write-up (§3): the signed rules, the frozen code, the sealed results and both teams' independent categorisation. Every file here is a byte-for-byte copy of the packets the two teams exchanged on 2 Oct 2026. **Nothing has been edited.**

## What's here

| folder | contents |
|---|---|
| `preregistration/` | **The signed rules:** `PREREGISTRATION_SIGNOFF_v1.2.md` and `DEVIATIONS_v3.1.md`, carrying all four agreement rows (Adam, Greg, Claude and Astra/Codex) as signed |
| `freeze/` | `FREEZE_MANIFEST.json` gives the exact bytes and SHA-256 of every frozen file. `FREEZE_MANIFEST.sha256` identifies the manifest itself, and `SEAL_HASH_CHECK.json` records the E2 archive digest. Also the packet's own README, and `provenance/`, which holds the P8 seal manifests and the reference scorer |
| `analysis/` | **The frozen evaluation code and model:** `p8_auc.py` (within-agent AUC, cluster bootstrap), `p8_run.py`, `forward_eval.py`, `h1_telemetry.py` and `heatbot_model.json`, with known-answer tests |
| `sealed_results/` | **The sealed results:** `E2_SEALED/` holds 12 files sealed on 23 Sep, and `P8_SEALED/` the held-out AUC result. Each has its original manifest, plus `verify_seal.py` and the verification record |
| `categorisation/` | **Each team's independent categorisation, and the comparison:** `ADAM_SIDE_CATEGORISATION.md`, `GREG_SIDE_INDEPENDENT_REVIEW.md` and `CROSS_TEAM_COMPARISON.md` |

## Check it yourself

```text
# 1. The freeze manifest is the one that was signed
sha256sum freeze/FREEZE_MANIFEST.json      # expect 6f11cc26…0ad4 (see FREEZE_MANIFEST.sha256)

# 2. The sealed result files match their original manifests
cd sealed_results && python3 verify_seal.py   # expect "12 match, 0 failed"

# 3. The frozen code passes its known-answer tests
cd ../analysis && python3 -m unittest test_p8_auc test_h1_telemetry
```

Frozen code hashes (SHA-256 prefixes, all listed in full in `FREEZE_MANIFEST.json`):

| file | prefix |
|---|---|
| `p8_auc.py` | `8abb2773` |
| `forward_eval.py` | `ef18724c` |
| `h1_telemetry.py` | `7dd39faa` |
| `heatbot_model.json` | `107192d5`. This matches the model hash in the E2 seal manifest |

## The result, as categorised by both teams

| claim | within-agent AUC | 95% CI | category |
|---|---|---|---|
| real time (the formal test) | **0.48** | 0.41–0.56 | **ruled out** at the agreed usefulness threshold of 0.60 |
| shortly before (descriptive) | 0.47 | 0.42–0.54 | ruled out |
| lead time (descriptive) | 0.47 | 0.40–0.56 | ruled out |
| alert-level claims (E2) | 9 alerts | — | **untestable**, as declared before unsealing |

The fixed testing sequence stopped at the first claim. The two teams categorised independently and **agreed on every category**.

## What isn't here, and why

- **Raw village data and private caches.** The public village API is the source, and the scripts that fetch it are on the `tier1-detector` branch.
- **The agents' memory archive.** It's private and never shared.
- **API keys, and any rater-blinding key material.**
- **The goal-displacement work (H5).** It became exploratory, and its LLM rubric was never frozen, so it isn't part of the sealed study. See §8 of the write-up.
