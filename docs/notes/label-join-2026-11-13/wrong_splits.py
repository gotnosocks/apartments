"""The number of v18's 709 splits that cut one apartment in two, with a 95% interval.

The script reads the readers' verdicts on the 60 sampled splits from `reads.jsonl`, and puts
each split at 175 Spencer Street or elsewhere by the building of its first page. For each of
the two strata it
  1. counts the wrong splits among the decided ones, leaving out the unclear verdicts;
  2. puts a Wilson 95% interval on their share;
  3. scales the share and its interval to the stratum's split pairs.
It then adds the two estimates and combines the intervals by MOVER (Zou and Donner, 2008). The
lower limit is the total less the root sum of squares of each stratum's distance, in pairs,
from its estimate down to its lower limit, and the upper limit is the total plus the same sum
over the distances up to the upper limits. The sample is under a tenth of each stratum, and the
script leaves out the finite-population correction."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

S = "/data1/apartments/tmp/sprint-20261113/label-join"
Z = 1.959964


def wilson(k, n):
    """Wilson's 95% interval on the share k of n."""
    p = k / n
    d = 1 + Z**2 / n
    mid = (p + Z**2 / (2 * n)) / d
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


reads = pd.DataFrame(
    [
        json.loads(line)
        for line in open(Path(__file__).with_name("reads.jsonl"))
        if line.strip()
    ]
)
pick = pd.read_parquet(f"{S}/sample.parquet").merge(reads, on="pid")
pick["spencer"] = pick.building_a.astype(str).str.contains("175-spencer")
split = pick[pick.group == "split"]

pr = pd.read_parquet(f"{S}/pairs_classified.parquet")
pages = pd.read_parquet(f"{S}/pages.parquet", columns=["unit_id", "building"])
split_pairs = pr[pr.joined17 & pr.apart18]
at_spencer = (
    pages.set_index("unit_id")
    .building.reindex(split_pairs.unit_id)
    .astype(str)
    .str.contains("175-spencer")
    .to_numpy()
)
pairs = {"spencer": int(at_spencer.sum()), "elsewhere": int((~at_spencer).sum())}

confidence = split[split.spencer].groupby(["verdict", "confidence"]).size()
res = {
    "spencer_confidence": {f"{v} / {c}": int(n) for (v, c), n in confidence.items()},
    "strata": {},
}
total, below, above = 0.0, 0.0, 0.0
for name, here in (("spencer", split.spencer), ("elsewhere", ~split.spencer)):
    v = split.verdict[here]
    n = int(v.isin(["one_apartment", "two_apartments"]).sum())
    k = int((v == "one_apartment").sum())
    lo, hi = wilson(k, n)
    N = pairs[name]
    est = N * k / n
    total += est
    below += (est - N * lo) ** 2
    above += (N * hi - est) ** 2
    res["strata"][name] = {
        "read": int(len(v)),
        "decided": n,
        "wrong": k,
        "unclear": int((v == "unclear").sum()),
        "share": round(k / n, 4),
        "share_95": [round(lo, 4), round(hi, 4)],
        "pairs": N,
        "wrong_pairs": round(est, 1),
        "wrong_pairs_95": [round(N * lo, 1), round(N * hi, 1)],
    }
res["all"] = {
    "pairs": sum(pairs.values()),
    "wrong_pairs": round(total, 1),
    "wrong_pairs_95": [round(total - below**0.5, 1), round(total + above**0.5, 1)],
    "share_right": round(1 - total / sum(pairs.values()), 4),
    "share_right_95": [
        round(1 - (total + above**0.5) / sum(pairs.values()), 4),
        round(1 - (total - below**0.5) / sum(pairs.values()), 4),
    ],
}
print(json.dumps(res, indent=1))
json.dump(res, open(f"{S}/wrong_splits.json", "w"), indent=1)
