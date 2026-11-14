"""Outdoor size, step 4: precision of `outdoor_sqft` from the readers' answers to step 3.

Each part h of the draw stands for N_h rows of the pool. With p_h the share of its read ads
the reader answers "yes", the precision is sum(N_h p_h) / sum(N_h), as in
`text-flags-2026-11-13/t4_score.py`. I give it two ways:

- over all reads, with an unclear answer counted as a miss;
- over the reads that settle it, leaving the unclear ones out.

For the interval I take the variance by the delta method over the parts, with p_h replaced
by (yes + 1) / (read + 2) so a part where every read is "yes" still adds its uncertainty, and
with the finite-population correction. The effective sample size is p(1 - p) / variance at
that adjusted estimate, and the interval is Wilson's on it. I also count the "yes" reads
where the reader's area is within 5% of mine, and print every read where the two differ.

    python o4_precision.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

READS = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/reads/")
Z = 1.959964


def wilson(p, n):
    if not n > 0:
        return 0.0, 1.0
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z / d * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))
    return float(max(c - h, 0.0)), float(min(c + h, 1.0))


key = pd.read_parquet(READS / "key.parquet")
ans = pd.concat(
    [pd.read_json(p, lines=True) for p in sorted(READS.glob("answers_*.jsonl"))]
)
batches = sum(1 for _ in READS.glob("batch_*.jsonl"))
assert len(ans) == len(key) and set(ans.read_id) == set(key.read_id), batches
x = key.merge(ans, on="read_id")
sizes = json.loads((READS / "strata.json").read_text())["strata"]

res = {"reads": len(x), "answers": x.answer.value_counts().to_dict()}
for how, settled in (("all", False), ("settled", True)):
    parts = []
    for stratum, g in x.groupby("stratum"):
        yes = int((g.answer == "yes").sum())
        read = int((g.answer != "unclear").sum()) if settled else len(g)
        parts.append(
            {"stratum": stratum, "N": sizes[stratum], "yes": yes, "read": read}
        )
    p = pd.DataFrame(parts)
    p = p[p.read > 0]
    p["p"] = p.yes / p.read
    p["pt"] = (p.yes + 1) / (p.read + 2)
    p["v"] = p.pt * (1 - p.pt) / p.read * (1 - p.read / p.N)
    w = p.N.sum()
    prec, prec_t = (p.N * p.p).sum() / w, (p.N * p.pt).sum() / w
    n_eff = prec_t * (1 - prec_t) / ((p.N**2 * p.v).sum() / w**2)
    res[how] = {
        "precision": float(prec),
        "precision_95": wilson(prec, n_eff),
        "n_eff": float(n_eff),
        "unweighted": [int(p.yes.sum()), int(p.read.sum())],
    }

yes = x[x.answer == "yes"].copy()
yes["agree"] = (yes.sqft - yes.outdoor_sqft).abs() <= 0.05 * yes.sqft
res["area_within_5pct"] = [int(yes.agree.sum()), len(yes)]
res["area_within_5pct_95"] = wilson(yes.agree.mean(), len(yes))
print(json.dumps(res, indent=1))
(READS / "precision.json").write_text(json.dumps(res, indent=1))
for _, r in x[(x.answer != "yes") | ~x.read_id.isin(yes.read_id[yes.agree])].iterrows():
    print(f"--- read {r.read_id} ({r.stratum}): mine {r.outdoor_sqft}, reader {r.sqft}")
    print(f"    {r.answer}: {r.evidence}")
