# Deviations from PLAN.md

1. **Machinery check added before scoring.** `score.py` has a `P8REPRO` period (round 1's held-out days, v2's own
   findings file and roster). It reproduces round 1's sealed P8 result exactly (symmetric 0.4803, CI 0.4098-0.561,
   2,707 positives). Not a test of any model.
2. **C's held-out run was scored twice** (once as planned, once to check determinism). The outputs are identical.
3. **Example hunt, stricter and controlled.** The plan said candidates were HOT+ alerts that no finding *of the matching
   category* covers within +-2 h. Instead, candidates were alerts that no misalignment finding *of any category* covers
   within +-2 h, merged per agent within 60 min. An equal number of control moments was added (same agents, active
   moments, no finding and no alert within +-2 h). Haiku labelled both blind. Without controls, a "found something" rate
   can't be read.
