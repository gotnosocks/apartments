"""S14, part 3: precision and recall of the three patterns against the readers' labels.

The readers wrote one JSON line per ad to `read/labelsNN.jsonl`. The script joins them to the
draws of `u1_text.py` and reads, for each kind:

1. precision on the 100 matched ads, with a Wilson 95% interval, overall and split by
   whether the text or only the unit label matched;
2. recall over the listings the draws came from, as S7 estimated it. The found ads are the
   matched count times the precision. The missed ads come from three parts of the unmatched
   listings:
     - those with the kind's weaker words, at the true rate of the kind's weak draw;
     - those with no mark and no weaker word of any kind, at the rate of the random draw;
     - the rest, which other kinds mark or name with weaker words, at the plain true rate of
       the reads in that part, from whichever draw they came.
   The interval comes from 20,000 Jeffreys beta draws of the four rates."""

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

OUT = c.OUT + "unusual-units/"
KINDS = {"pen": "penthouse", "gar": "garden_apartment", "town": "townhouse_floor"}

lab = pd.concat(
    pd.read_json(f, lines=True) for f in sorted(glob.glob(OUT + "read/labels*.jsonl"))
)
picks = pd.read_parquet(
    OUT + "u1_picks.parquet", columns=["listing_id", "sample", "read_id"]
)
print("labels", len(lab), "of", len(picks), "reads", flush=True)
x = pd.read_parquet(OUT + "u1_text.parquet")
ids = set(pd.read_parquet(c.DATA, columns=["listing_id"]).listing_id.astype(str))
x = x[x.listing_id.isin(ids) & (x.desc_len > 80)].reset_index(drop=True)
r = picks.merge(lab, on="read_id", how="inner").merge(x, on="listing_id", how="left")
none_noweak = (
    ~x.pen & ~x.gar & ~x.town & ~x.pen_weak & ~x.gar_weak & ~x.town_weak
).to_numpy()
r_none_noweak = ~r.pen & ~r.gar & ~r.town & ~r.pen_weak & ~r.gar_weak & ~r.town_weak


def wilson(k, n, z=1.96):
    if n == 0:
        return [float("nan")] * 3
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [p, mid - half, mid + half]


def rate(m, truth):
    return {"n": int(m.sum()), "true": int(truth[m].sum())}


rng = np.random.default_rng(20261115)
res = {"labels": len(lab), "reads": len(r)}
for k, key in KINDS.items():
    truth = r[key].astype(bool)
    matched = r["sample"].str.contains(k + "_matched")
    out = {"precision": wilson(truth[matched].sum(), matched.sum())}
    for part in ("text", "label"):
        sub = matched & r[k + "_text"] if part == "text" else matched & ~r[k + "_text"]
        out["precision_" + part] = wilson(truth[sub].sum(), sub.sum()) + [
            int(sub.sum())
        ]
    weak_draw = r["sample"].str.contains(k + "_weak")
    rest = ~r[k] & ~r[k + "_weak"]
    out["rates"] = {
        "matched": rate(matched, truth),
        "weak": rate(weak_draw, truth),
        "random": rate(r["sample"].str.contains("unmatched_random"), truth),
        "other": rate(rest & ~r_none_noweak, truth),
    }
    on = x[k].to_numpy()
    wk = x[k + "_weak"].to_numpy()
    out["listings"] = {
        "matched": int(on.sum()),
        "weak": int((~on & wk).sum()),
        "random": int(none_noweak.sum()),
        "other": int((~on & ~wk & ~none_noweak).sum()),
    }
    draws = {
        s: rng.beta(v["true"] + 0.5, v["n"] - v["true"] + 0.5, 20000)
        for s, v in out["rates"].items()
    }
    n = out["listings"]
    found = draws["matched"] * n["matched"]
    missed = sum(draws[s] * n[s] for s in ("weak", "random", "other"))
    recall = found / (found + missed)
    point = {s: v["true"] / max(v["n"], 1) for s, v in out["rates"].items()}
    f0 = point["matched"] * n["matched"]
    m0 = sum(point[s] * n[s] for s in ("weak", "random", "other"))
    out["recall"] = [f0 / (f0 + m0), *np.percentile(recall, [2.5, 97.5]).tolist()]
    out["missed_point"] = {s: point[s] * n[s] for s in ("weak", "random", "other")}
    res[k] = out
    print(k, json.dumps(out, default=float), flush=True)

# what the readers said about the other kinds within each matched draw
res["cross"] = {
    s: {key: int(v[key].astype(bool).sum()) for key in KINDS.values()} | {"n": len(v)}
    for s, v in r.groupby("sample")
}
print(json.dumps(res["cross"]), flush=True)
json.dump(res, open(OUT + "u3_readers.json", "w"), indent=1, default=float)
