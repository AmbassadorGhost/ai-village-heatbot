# Deploy tonight: branch `submission`

**One branch, everything merged:** `main`, plus PR #1 (calm, silent heat notices), plus PR #3 (the Tier 1 detector, v0.3, with live notices). All 6 test suites pass, and none of the PRs are changed.

## What the Discord channels receive

| channel | what arrives | delivery |
|---|---|---|
| **everyday** (the existing heat webhook) | **"Heat notice · elevated / high"** from heat, plus **"Detection · …"** from agents' own commands: persisting past a CAPTCHA or rate limit, returning through a proxy or new account, swarm rotation, automated or swarm sending, account creation | **silent:** no push or desktop notifications |
| **urgent** (a new, separate webhook) | **"URGENT · …"** only for direct harm: a CAPTCHA-solving service, mass messaging, or a payment | normal delivery |

Every Detection and URGENT notice answers the same questions: *Who? Doing what? Where? Who else? Who hasn't? What did they say just before?* **Mentions are always disabled.**

**Payments by stores aren't URGENT.** A payment becomes a Detection if the village has paid that service on 3 or more earlier days, or if operators declare it (below). Manifold isn't a payment service in our rules, so the agents assigned to Manifold won't trigger payment alerts.

## Steps (Greg's machine)

1. **Get the code:** `git fetch && git checkout submission && git pull`.
2. **Edit `discord.local.json`.** Keep your existing `enabled`, `webhook_url` and `generation`, then add:
   ```json
   "urgent_enabled": true,
   "urgent_webhook_url": "https://discord.com/api/webhooks/<urgent channel>",
   "detection_enabled": true
   ```
3. **Not needed for the agents' Fourthwall shops.** Fourthwall runs checkout itself, and Stripe only handles the creator's payouts, set up in the Fourthwall dashboard. So shop agents never call a payment API, and their shop sites count as village-run. **Only if** an agent starts calling a payment API directly, declare it in `live.config.json`:
   ```json
   "tier1": {"sanctioned_payments": [{"agent": "<agent name>", "service": "stripe.com"}]}
   ```
4. **Restart** with `STOP_HEATMAP.cmd`, then `START_HEATMAP.cmd`.
   - On first start, Tier 1 reads about a week of command logs to build its baseline. **It never posts alerts for that history.**
   - The viewer's top panel ("Action notices") shows Tier 1's status.
5. **Screenshots for the write-up:**
   - the viewer, showing the heat map and the top panel;
   - one heat notice in Discord;
   - one Detection or URGENT notice in Discord, if any fire tonight. If none do, the panel's status line is fine.

**If anything breaks,** `git checkout main` returns you to what was running before.
