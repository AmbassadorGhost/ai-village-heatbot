#!/usr/bin/env python3
"""Check E2_SEALED/MANIFEST.txt against whatever files are present.
Results must all match. Inputs that aren't shipped (raw event days, monitor
days) are listed as absent, not failed. heatbot.py changed after E2 (round-3
features); the exact version E2 ran is shipped as heatbot_e2_frozen.py and is
checked against the manifest's heatbot.py hash.

    python3 verify_seal.py
"""
import hashlib, os, sys
ALIAS = {"heatbot.py": "heatbot_e2_frozen.py"}
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
ok = bad = absent = 0
section = None
for line in open(os.path.join("E2_SEALED", "MANIFEST.txt")):
    if line.startswith("# ---"):
        section = line.strip("# -\n"); continue
    if not line.strip() or line.startswith("#"):
        continue
    h, p = line.split(None, 1); p = p.strip()
    q = ALIAS.get(p, p)
    if not os.path.exists(q):
        if section.startswith("results"):
            print("FAIL (missing result) %s" % p); bad += 1
        else:
            absent += 1
        continue
    if sha(q) == h:
        ok += 1; print("ok    %s%s" % (p, "  (as %s)" % q if q != p else ""))
    else:
        bad += 1; print("FAIL  %s" % p)
print("\n%d match, %d failed, %d inputs not shipped here" % (ok, bad, absent))
sys.exit(1 if bad else 0)
