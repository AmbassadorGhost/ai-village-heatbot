#!/usr/bin/env python3
"""Agreement between two raters on the Tier 1 training-alert sample.

    python tier1/rating_agreement.py tier1/results/ratings/adam_ratings.json \
        tier1/results/ratings/greg_ratings.json

Primary (planned): Cohen's kappa on items BOTH raters rated (blank is not a
negative rating). Descriptive extras: 3-category kappa treating blank as its
own category, and the cross-table.
"""
import collections
import json
import sys

LAB = {"worth a human look": "look", "not worth a human look": "no look", None: "blank"}


def kappa(pairs):
    n = len(pairs)
    po = sum(x == y for x, y in pairs) / n
    cats = {c for p in pairs for c in p}
    pe = sum((sum(x == c for x, _ in pairs) / n) * (sum(y == c for _, y in pairs) / n) for c in cats)
    return n, po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main(a_path, b_path):
    A, B = (json.load(open(p, encoding="utf-8")) for p in (a_path, b_path))
    ra, rb = A["ratings"], B["ratings"]
    assert [x["sample_id"] for x in ra] == [x["sample_id"] for x in rb], "sample order differs"
    a = [LAB[x["rating"]] for x in ra]
    b = [LAB[x["rating"]] for x in rb]
    print(f"{A['rater']}: {dict(collections.Counter(a))}")
    print(f"{B['rater']}: {dict(collections.Counter(b))}")
    both = [(x, y) for x, y in zip(a, b) if "blank" not in (x, y)]
    n, po, k = kappa(both)
    print(f"PRIMARY  binary, items both rated: n={n}, agreement={po:.3f}, kappa={k:.3f}")
    n, po, k = kappa(list(zip(a, b)))
    print(f"descriptive  3-category (blank as category): n={n}, agreement={po:.3f}, kappa={k:.3f}")
    print(f"cross-table ({A['rater']}, {B['rater']}):")
    for (x, y), c in sorted(collections.Counter(zip(a, b)).items()):
        print(f"  {x:8s} {y:8s} {c}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
