"""Descriptive paired comparison (PLAN.md): within-agent AUC difference between two models on the same period, cluster
bootstrap over agents (same draws for both), seed 0, 1000 draws.  python3 compare.py results/X.json results/Y.json"""
import json, random, sys


def load(p):
    return {a: tuple(v) for a, v in json.load(open(p))['per_agent_general_symmetric'].items()}


def auc(st, w):
    num = sum(w[a] * st[a][0] for a in w); den = sum(w[a] * st[a][1] for a in w)
    return num / den if den else None


x, y = load(sys.argv[1]), load(sys.argv[2])
agents = sorted(set(x) & set(y))
one = {a: 1 for a in agents}
d0 = auc(y, one) - auc(x, one)
rnd = random.Random(0); ds = []
for _ in range(1000):
    w = {}
    for _ in agents:
        a = agents[rnd.randrange(len(agents))]; w[a] = w.get(a, 0) + 1
    ax, ay = auc(x, w), auc(y, w)
    if ax is not None and ay is not None:
        ds.append(ay - ax)
ds.sort()
print('%s minus %s: %+.3f  95%% CI %+.3f to %+.3f  (%d agents; share of draws > 0: %.0f%%)' % (
    sys.argv[2].split('/')[-1][:-5], sys.argv[1].split('/')[-1][:-5], d0, ds[24], ds[974], len(agents), 100 * sum(d > 0 for d in ds) / len(ds)))
