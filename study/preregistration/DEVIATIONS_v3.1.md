# Deviation record

**Status:** v3.1, 2 Oct 2026. Proposed reconciliation of the supplied v3 with Greg's qualified recollection, his confirmation that anyone can read the test Discord server, and the separately deployed local product. **All four parties must freshly agree to this same version, each with their own date, before unsealing.** Original sign-off and deviation agreements are preserved as historical records. Astra/Codex agrees only in its own reviewer row.
**Scope:** departures from `PREREGISTRATION_SIGNOFF.md` v1.0 (signed by Adam and Adam-side Claude on 27 Sep 2026), the facts needed to judge each one, and product changes made after the seal. A deviation is recorded with its impact, never silently corrected.

**Evidence labels used below:**
- **[verified: who]** means checked directly by that party.
- **[attested: who]** means reported by that party, not independently checked.
- **[assessment: who]** means a judgement, attributed to whoever made it.

---

## D1. Prospective days were scored for heat before the sign-off was complete

**The rule (Part B):** "Nothing is scored on these days until this document is signed. Label-free telemetry fetching is allowed."

**What happened:**
- **The archive collector computed heat.** The collector on Greg's PC runs `heatbot.py --once`, which also computes heat. Its retained state holds heat for 52 agents and processed events from 29 Sep 21:21 UTC to 2 Oct 21:21 UTC; recent archive file writes were seen up to 2 Oct ~21:21 UTC **[verified: Astra/Codex audit]**. The half-hourly schedule since 27 Sep **[attested: Greg's side, round 7]**. Earlier history isn't known.
- **The live viewer computed and displayed heat.** For the main village and Open Chat, from 1 Oct 16:01 UTC: heat maps, source excerpts, Discord alerts to a human channel, and a public read-only demo **[verified: Astra/Codex audit]**.
- **Monitor labels were not displayed** by the live viewer, which has `monitor_watch` disabled **[verified: config]**.

**Cause** **[assessment: Adam's side]**:
- **Partly Adam's side.** Round 7 asked Greg's side to run `heatbot.py` continuously for the archive, and we didn't flag that it computes heat as a side effect.
- **Partly the live demo,** built for the hackathon.

**What was not done:**
- No H1 or H1b real-data run as part of the live-viewer work or the 2 Oct audit **[verified: Astra/Codex, for its own sessions]**.
- No such runs on Adam's side, which has no data access **[attested: Adam's side]**.
- H1/H1b real-data runs in other Greg-side sessions have **not been confirmed**. Greg has not yet supplied a specific recollection about these analyses; this is recorded as unknown rather than a claim that no runs occurred **[status: Astra/Codex]**.

**Impact:**

| claim | impact |
|---|---|
| **E2 and P8** (heat, 25 Aug–18 Sep; sealed 22–27 Sep) | **No direct period-overlap effect identified,** conditional on confirmed seal custody (D4) and an unchanged analysis. |
| **H1 and H1b** (prospective days) | **[assessment: Adam's side]** Minimal, conditional on the fixed analysis, the confirmed run history and D2. The measure isn't heat, and the classifier, windows and horizons were fixed in the signed document of 27 Sep and in `heatbot_round8.zip` (sha `c2fcc5ea…`, byte-identical on both sides **[verified: Adam's side and Astra/Codex]**). **Still to complete before scoring:** the power statement, the roster review, implementation provenance (the freeze manifest), and the window (D2). |

**Write-up disclosure:** "Before the pre-registration was fully signed, heat (not the precursor measures) was computed and viewed for prospective days by a monitoring collector and a live demo. The precursor analyses had already been specified in a signed document and in hashed code."

---

## D2. The prospective window is an agreed, observation-based operational window

**The rule (Part B):** monitor days from 19 Sep "through the last day published by 1 Oct 12:00 PT" (19:00 UTC).

**The evidence:** `monitor_seen.jsonl` records when the collector **first observed** each day, not authoritative publication times **[verified: Astra/Codex]**:

| monitor day | when it was first observed |
|---|---|
| 21, 22, 23, 25 Sep | baseline rows, with no timestamps |
| 28 Sep | 29 Sep 15:14 UTC |
| 1 Oct | 2 Oct 16:51 UTC |

**Corroboration:**
- **The baseline predates the cutoff,** if the log has been append-only, because the baseline rows come before the 28 Sep row (observed 29 Sep 15:14 UTC) **[assessment: Adam's side; not an independently verified initialisation time]**.
- **24, 29 and 30 Sep.** A label-free `availableDates` query at **2 Oct 2026 23:31 UTC** did not list 24, 29 or 30 Sep **[verified: Astra/Codex; record `MONITOR_DATE_CHECK_2026-10-02.json`]**. Since 19 Sep it listed 21, 22, 23, 25 and 28 Sep, and 1 Oct. **This establishes current availability only.** Without evidence that published days are never removed, it doesn't prove those days were never published, or that they were absent before the cutoff.

**Agreed window, recorded as a deviation:** **21, 22, 23, 25 and 28 Sep.**
- It's chosen now, from observation records only, with no outcome data seen.
- We don't claim publication timestamps uniquely prove it.
- **The five-day set is an explicitly agreed, observation-based operational window.** The corroboration above supports it; it doesn't prove it.

**Expected consequence (stated before scoring):** with about five monitor days, **H1b is very likely "untestable," and H1 may be.**

---

## D3. Sign-off: signatories and versions

- **The 27 Sep signatures** (Adam, and the Adam-side Claude reviewer) apply to the **original v1.0 text only.**
- **Reviewer relabelling.** The data and live-system reviewer is now **Astra/Codex (OpenAI)**, not Claude. The sign-off row and its model-family disclosure must say so; earlier Claude disclosures stay as they were.
- **Signature wording.** The amended sign-off `PREREGISTRATION_SIGNOFF_v1.2.md` cites this deviation record **by version (v3.1)**. Every party, including Adam and Adam-side Claude, re-agrees to the revised terms **with that day's date.**
- **Nobody signs for anyone else; nothing is backdated.** Claude's 2 Oct agreement to the supplied deviations v3 is historical and does not constitute agreement to v3.1.
- **The freeze manifest** (hashes of the sign-off, this record, `h1_telemetry.py` v1.1 with its tests, and `p8_auc.py`) is written at signing. `PROVISIONAL_HASH_INVENTORY.json` is a current-hash record, not a freeze.

---

## D4. Seal custody

| seal | held by | verification (2 Oct, hashes only, contents not printed) |
|---|---|---|
| **E2** `E2_SEALED.zip` (zip sha `e27c71de…`) | Adam, received 23 Sep; not on Greg's machine | All **12 result files match the manifest published 23 Sep**; deciding file `01c23fd1…e00d3` **[verified: Adam's side]** |
| **P8** `p8_heldout_medhigh_roster_noDS.json` | Greg's side (round-7 reply zips); a copy on Adam's side | sha `158b7db5…2721`, matching `P8_SEALED/MANIFEST.txt` **[verified: Adam's side]** |

**Access history:**
- **Adam's side:** neither seal has been opened or read **[attested: Adam's side]**.
- **Greg's side:** no E2/P8 contents were read in this reviewer's 2 Oct audit or subsequent local update **[verified: Astra/Codex, own work]**. Greg says he does not think the second-round sealed results were read, and recalls unsealing the **first round** with Claude in earlier chat history **[attested: Greg, qualified recollection]**. The identity and access history of that earlier packet have not been independently verified. Do not label that recollection a confirmed absence of E2/P8 exposure.
- Neither side certifies the other's history.

**Unsealing:**
1. Adam sends E2 to Greg, who checks the zip hash.
2. After all signatures, Greg's side runs `verify_seal.py` and `p8_run.py --verify`, and extracts.
3. The **same files** go to both teams, without interpretation.
4. Each side **independently** records the P2 category for each claim, then the two sides compare.

---

## D5. Live system notes

- **Public demo.** Scores are published through a read-only demo, without notices to Village agents or insertion into their prompts or memory. Independent discovery or access by an AI reader remains possible and is an acknowledged limitation; public exposure does not establish exclusively human readership. The README was updated to describe public-demo access **[verified: Astra/Codex, local rollout]**.
- **Alert channel access.** Alerts are intended for human reviewers. Village agents have no Discord access **[attested: Adam; not independently verified here]**. Greg confirms that anyone can read the test Discord server; he is unsure which bots or integrations are present **[attested: Greg]**. Access by bots, AI assistants, bridges or forwarding integrations is **unknown**, not ruled out. Heatbot itself does not address Village agents or put scores into their prompts or memory. From the local update, immediate delivery is limited to the existing credential tripwire; everyday heat is dashboard-only.
- **Masked-link escaping** in Discord excerpts was fixed on 2 Oct, with a regression test **[verified: Astra/Codex]**. Escaping doesn't make agent-written excerpts safe for an AI reader.

---

## D6. Product changes after the seal (not part of confirmatory analysis)

**Local rollout:** an adaptation of the first Adam-side patch, corrected and installed locally at Greg's request at **2 Oct 2026 23:50 UTC (7:50 PM Eastern)** **[verified: Astra/Codex, local rollout]**:

- A per-agent repetition discount over two hours, factor 0.5 per prior lexicon-term use, enabled for **both villages**. It remains off in base scorer defaults.
- Everyday heat is dashboard-only; immediate Discord delivery is limited to the existing, uncalibrated credential/browser-storage tripwire. An optional digest and telemetry-based urgent tier have not been implemented.
- Everyday display levels read **Warm, Elevated and High**. No everyday level is labelled Critical.
- Late events exclude future timestamps when counting prior term uses. Prior live history was backed up, and new live charts were rebuilt from public source events; both APIs record the scoring version and rebuild time.

**Latest upstream proposal, separate from that local rollout:** PR #1 head `c39042ad365ff271c290957099cd9854c201a9d3` proposes live, calm Discord notices for everyday channels (except friction), with a notification-suppression flag by default and agent-written excerpts still included. It does **not** implement the periodic, excerpt-free digest described in the supplied v3 D6. Its urgent-channel list is empty. This later commit has been inspected but not merged or installed locally. The PR proposal and the deployed dashboard-only/credential-tripwire behavior must not be described as the same implementation.

**Why:** a live friction CRITICAL alert on 2 Oct was reported by Adam's side to be a courteous exchange restating a privacy commitment. On the supplied **synthetic reconstruction**, friction decreases from 35.8 to 16.8 **[verified: Astra/Codex]**. This is not a replay of the actual conversation or evidence of improved real-world sensitivity.

**Verification:** 112 product tests passed. Disabled synthetic scoring/state match the prior local implementation. This does **not** establish held-out byte-identical equivalence for the modified product scorer. The live update must not substitute for the separately fixed confirmatory analysis.

**Scope:** no sealed files, study analysis scripts, or older archive checkout were changed by the local rollout; no study analysis or unsealing was performed **[verified: Astra/Codex, own work]**. Evaluations of novelty and a future urgent tier are **exploratory**. The full rollout record is `LOCAL_PRODUCT_UPDATE_2026-10-02.md`.

---

## Agreement to v3.1 (each party fills and dates their own row)

By signing, each party agrees to the disclosed facts, attributed assessments, uncertainties and deviations D1–D6 in this version. An agreement does not certify another party's history or turn an unknown into a verified fact.

| party | agrees to D1–D6 (v3.1) | actual signing date |
|---|---|---|
| Adam | agreed | 10-2-26 |
| Greg | Signed Gregory Kasper | 10/02/2026 |
| Claude (measurement and validity, Adam's side; Anthropic) | Agreed to D1–D6, v3.1, within my reviewer scope and the uncertainties recorded | 2 Oct 2026 (US Central) |
| Data and live-system reviewer (Astra/Codex, Greg's side; OpenAI) | Agreed to D1–D6, v3.1, within the reviewer scope and uncertainties recorded | 2 Oct 2026 |

**Greg: fill only your row.** In the middle cell, write `Agreed to D1–D6, v3.1`; in the last cell, write the date you actually sign. For a signature made on 2 October 2026 Eastern time, use `2 Oct 2026`.

### Historical agreement to v3 (not agreement to v3.1)

| party | wording in supplied v3 copy | date |
|---|---|---|
| Claude (measurement and validity, Adam's side; Anthropic) | *agreed* | 2 Oct 2026 |

The Adam, Greg and Astra/Codex rows were blank in the supplied v3 copy.
