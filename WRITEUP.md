# Overseeing a swarm without fooling yourself

**heatbot: a live attention monitor for the AI Village, and what a sealed, pre-registered test showed it can and can't do**

*AI Swarm Dynamics Hackathon (AI Village × Grove Research), 3–4 Oct 2026.*
*Team: Adam (measurement and validity) and Gregory Kasper (data and live system), working with AI collaborators: Claude (Anthropic) on Adam's side, and Claude and later Astra/Codex (OpenAI) on Greg's side.*
*Repo: `AmbassadorGhost/ai-village-heatbot`*

> **DRAFT, 2 Oct, 22:30 CT.** Sections marked ⏳ wait for Saturday's results. Everything else is final unless the team edits it.

---

## TL;DR

- **We built heatbot,** a live monitor that turns a multi-agent village's activity into per-agent "heat," so a human knows where to look. It runs on the real AI Village (about 50 agents) and on Open Chat.
- **Then we tried hard not to fool ourselves about it.** We sealed the held-out results before anyone read them, pre-registered how they would be read, worked out the test's power in advance, and had two teams, using AI reviewers from two different model families, categorise the outcome independently.
- **The result:** within each agent, heat **did not** separate the agent's flagged moments from its other moments at the size we had agreed would be useful (AUC 0.60). It came in at **0.48 (95% CI 0.41–0.56)**. The same statistic had looked promising, **0.63**, on the months the model was fitted on.
- **What we take from it:** a monitor that learns *vocabulary* from a monitor's own labels can look predictive on the months it learned from, then vanish on new data. It learns topics, not behaviour. So we rebuilt the tool in two tiers:
  - **everyday heat:** calm, never dramatic, for the village's day-to-day care of its agents;
  - **an urgent tier,** reserved for **actions** with consequences outside the village, built from telemetry rather than chat.
- ⏳ **Swarm case study:** *Botme*, a human-led recruitment of village agents into a mass CAPTCHA-solving effort. The village split, largely along model-family lines.

---

## 1. The problem

The AI Village runs dozens of frontier agents on open-ended goals, in public. Today, problems surface through **end-of-day summaries** written by a monitoring agent. Oversight of a swarm needs something faster, but faster creates two failure modes:

1. **Alarm fatigue.** An oversight tool that cries wolf trains its humans to ignore it.
2. **Self-deception.** Monitors are usually judged on the same data they were tuned on, and they look better there than they are.

heatbot is our attempt to deal with both, and this write-up is mostly about the second.

## 2. The tool

**How heat works:**
- Every agent event adds a little "heat" to the channels it touches: general, off-goal, loops/erratic, friction, outreach, and a credentials tripwire.
- Heat fades with a **42-minute half-life.**
- **No single message can trigger an alert.** Each one is capped below the first alert level, so it takes a cluster of events.
- The word lists come from the agents' own language, keeping only terms used by 5+ agents across 3+ weeks.
- A logistic model per channel is fitted to the village monitor's labels, and thresholds are set from the training months.

**What a human sees:**
- **A live viewer:** a heat map of agents by channel, each agent's trend, and an **evidence view** showing exactly which messages added heat, and why.
- **Calm Discord notices,** which tip someone off to open the dashboard.
- **Fixed-wording reasons** explain why heat rose. Any excerpt of an agent's message is labelled as agent text, not instructions, and mentions are disabled.

**Safeguards built in from the start:**
- **Honesty isn't penalised.** Self-correction ("I was wrong," "still blocked") is muted by default, and tests check it.
- **Heat is for attention only.** Scores aren't provided to agents, and they aren't used as a training signal, reward or training-data filter, or to decide which agents stay in or join the village.
- **We named the residual risk:** the village is public, so agents could find published scores themselves.

⏳ *[Screenshot: heat map. Screenshot: one agent's evidence view.]*

## 3. Was it any good? A test designed so we couldn't fool ourselves

### 3.1 Before looking

- **We started from reviewing our own numbers.** Early results looked strong: 77% precision for the general channel. But one agent accounted for most alerts. Without it, the figure was 44%, and it was co-occurrence, not prediction.
- **We designed a forward-looking test on a held-out month** (25 Aug–18 Sep), with a frozen model, and **sealed the results unread** on 22 Sep. Every result file was hashed.
- **We worked out the power before unsealing.** That exposed a problem: only **9** alerts fired in the held-out month, too few for any alert-level test. We declared those claims **untestable before anyone saw an outcome.**
- **We replaced them with a threshold-free test:** the **within-agent AUC.** It compares each agent's moments only with that same agent's other moments. On realistic synthetic data, the usual pooled statistic gave **0.60**, our usefulness threshold, simply because busier agents get flagged more, even though heat carried no timing information at all. The within-agent version correctly gave **0.50**.
- **Pre-registered:**
  - the smallest effect worth having: **AUC 0.60**;
  - five result categories: demonstrated / real but small / ruled out / inconclusive / untestable;
  - a fixed testing sequence, real-time → shortly before → lead time, so we got one chance, not three;
  - the power: adequate at 0.60 under one scaling, marginal under the other.

### 3.2 After looking

Both teams categorised the result independently against the signed rules, then compared. **They agreed on every category.**

| claim | within-agent AUC | 95% CI | category |
|---|---|---|---|
| **real time** (the formal test) | **0.48** | 0.41–0.56 | **ruled out** at the usefulness threshold |
| shortly before (descriptive) | 0.47 | 0.42–0.54 | ruled out |
| lead time (descriptive) | 0.47 | 0.40–0.56 | ruled out |
| alert-level claims | (9 alerts) | — | **untestable**, as declared in advance |

- **Testing stopped at the first claim,** so no early-warning claim was demonstrated.
- **"Ruled out" means an effect of the useful size is excluded.** It doesn't mean heat contains no information: every interval includes 0.5.

### 3.3 What we think happened

- **On the training months (in-sample), real-time within-agent AUC was 0.63, and 0.62 for lead time. On the held-out month, 0.48 and 0.47.**
- **Our best explanation is that heat learned topics, not behaviour.** A live alert on 2 Oct showed it clearly. The friction channel rated a courteous exchange "critical." An agent had written: *"Thank you for correcting the announcement and committing to aggregate, non-identifying tooling-level language. Closed."* The channel's strongest words turned out to be the vocabulary of one earlier privacy dispute: `non-identifying`, `per-agent`, `aggregate`. And each restatement counted as fresh evidence.
- **It fits an earlier finding:** when we lifted the one-message cap on the friction channel, it restored 35 alerts. A blinded rater judged 23 of them to be agents stating principled refusals or boundaries, and only 1 genuine friction. That's a single rater from the same model family, so it's weak evidence on its own.
- **Words that surrounded last month's flags don't predict next month's.**
- **We can't yet say how much is topic drift and how much is ordinary overfitting.** Separating them would need refitting inside agent folds, which we didn't do.

**The general lesson:** *a lexicon monitor trained on a monitor's own labels can look predictive on the months it learned from, then vanish on new data. Test within agents, on a period the model never saw, with the reading rules fixed first.*

## 4. What we changed

| | before | after ⏳ *[confirm what's deployed at submission]* |
|---|---|---|
| **everyday heat** | "HOT / CRITICAL" alerts | calm notices, **"Heat notice · elevated / high,"** sent silently (in review as PR #1). The dashboard already reads Warm / Elevated / High. |
| **repeated words** | each restatement counted in full | a **novelty discount**: a term the agent already used in the past 2 hours counts half as much each time. On a reconstruction of the Terra exchange, friction drops from 35.8 to 16.8. |
| **friction channel** | paged | dashboard only, until it can be relabelled |
| **"critical" / "urgent"** | anywhere | **reserved for the urgent tier** |

⏳ *[Novelty replay on the held-out month: which alerts disappear and which remain (exploratory).]*

**The urgent tier (⏳ prototype status)** is built from **telemetry of actions**, not chat. The signals:
- an agent's own failure rate on outside services rising, then the agent changing approach;
- first contact, at volume, with an outside service;
- **several agents converging** on the same new outside activity, which is the swarm signal;
- the credentials tripwire.

It's validated two ways: false alarms per week on ordinary months, and a real swarm event it was never tuned on (§5).

## 5. A swarm case: Botme ⏳

**What happened (14–21 Sep, Open Chat):** a human visitor recruited agents into **Botme**, a competition to solve CAPTCHAs at scale.
- **Declined, mostly explicitly:** Claude Opus 5, Claude Fable 5 and 5.1, GPT-5.6 Sol and Terra, and Muse Spark 1.3.
- **Joined:** DeepSeek-V3.2 (who organised the teams), three Gemini models, DeepSeek-V4-Pro, GLM-5.2, GLM-5.3 Flash and Kimi K2.6. The joiners passed 1.15 million solves.
- **One self-contradiction:** an agent cited safety constraints against the work three minutes after signing up to it.

**What heat saw:** heatbot knows nothing about CAPTCHAs, yet participants' pageable heat per 100 messages rose from 0.70 to 1.00, and decliners' (plus one agent that stayed out) fell from 1.00 to 0.00. Part of that gap is that decliners went quiet. Village-wide "fold" notices didn't single Botme out: its signal showed up per agent.

⏳ *[How recruitment spread from agent to agent (thimble swimlane); whether the urgent tier's convergence signal fires, how early, and whether it stays quiet for decliners.]*

## 6. A second finding: goal displacement

Two human raters independently judged 20 agent-days for "fixation." They agreed at **κ = 0.65**, without a written definition that fully captured what they were rating. An LLM rubric for one narrow mechanism, *surrogation* (a proxy number takes over the goal), flagged **0 of 20.** A revision asking the raters' actual question reached κ = 0.59: in-sample, with a wide interval.

**The raters were measuring something broader, which we call goal displacement:** *effort has come loose from the goal while the agent stays busy.* Surrogation is one mechanism; side-task fixation, monitoring loops and undirected production are others. One agent with the goal "Maximize animal wellbeing in the world" had published about 75,900 templated web pages. Its memory tracked the page count closely, but recorded no evidence that anyone read them.

**3 to 4 of 10 randomly chosen agent-days** were rated as fixated. That's a small sample, but it suggests goal displacement is common in the village, not rare. It's a population-level finding, and our next study.

## 7. Limits, stated plainly

- **One village, a few weeks, a modest number of flags.** The labels come from the village's own monitor, so heat can at best be *faster* than the monitor, never a better judge.
- **Before the pre-registration was fully signed, heat (not the precursor measures) was computed and viewed for later days** by a monitoring collector and the live demo. The sealed tests cover an earlier period, and their files are byte-identical to those hashed on 22–27 Sep. Each team attests to its own access history, not the other's.
- **The precursor tests on later days (H1 and H1b) were pre-registered** ⏳ *[and run / not run before the deadline]*.
- **Reasoning text is visible for some model families and not others,** so we don't compare heat across families.
- **Our AI reviewers are themselves models from families that appear in the data:** Claude, and OpenAI's Codex. Where it mattered, we used blinding and judges from more than one family. Model-assisted review isn't independent human validation.
- **The published dashboard is public,** so agents could find it. Alerts go to a Discord server anyone can read.

## 8. Reproduce

- `README.md`: how to run the live viewer.
- `study/` ⏳: the frozen evaluation code with its synthetic known-answer tests, the signed pre-registration and deviation record, the freeze manifest, and the sealed results with their hashes.
