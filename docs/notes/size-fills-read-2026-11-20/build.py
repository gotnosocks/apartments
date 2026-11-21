"""Every ad of the latest-split run's dataset (l2bt) with the source of its size and the
makeup of that source.

The model's size is `building_zones_floor_asof.size_table`: the ad's own stated size, else
`sizefill.asof_size` from training rows priced on earlier days (the unit layer, then the line
layer). I call that function for the size the fit read, and rebuild the two layers beside it
with `sizefill.earlier_sum`, split by where the source sizes come from:

- unit layer: source ads of the same piece (`unit_id`) with the ad's bedroom count, and with
  another bedroom count;
- line layer: other apartments on the line, and other pieces of the ad's own apartment (the
  `unit_id` less its `~n` suffix) that the line layer reads as other units.

The same candidates are built for ads that state a size, where the stated size is a check on
the fill the cascade would have made. `truth` is the median size stated by the apartment's
other ads with the ad's bedrooms and full baths that no fill could read: training ads of the
same or a later day, and held-out ads. Rents enter only as the held-out `gap` and `cdf`
columns, which no mark reads.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import building_zones_floor_asof as asof
from rentfrontier import data, drift_score, sizefill
from rentfrontier import run as R

OUT = Path("/data1/apartments/tmp/po-size-fills")
SEED = "history-scan-2026-11-18"
RUN = R.RUNS / "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
COLS = ["listing_id", "building", "unit_id", "price_at", "bedrooms", "full_baths"]
COLS += ["half_baths"]


def half(building: str) -> str:
    """The halves of buildings of the history scan (A is its half 0)."""
    return "AB"[hashlib.sha1((SEED + str(building)).encode()).digest()[0] % 2]


def mean(s, n):
    """exp of sum over count, NaN where the count is 0."""
    return np.where(n > 0, np.exp(s / np.maximum(n, 1)), np.nan)


if __name__ == "__main__":
    ds = drift_score.dataset_dir(RUN)
    res = json.loads((RUN / "result.json").read_text())
    r = pd.read_parquet(ds / "rows.parquet", columns=COLS)
    s = np.load(RUN / "pred_scores.npz")
    held = s["heldout"]
    train = ~held
    ads = pd.read_parquet(
        res["asof"]["pipeline_rows"], columns=["listing_id", *asof.AD_FIELDS]
    )
    rows = asof.ad_rows(r, ads)
    del ads
    t = asof.size_table(rows, train)
    assert (t.listing_id.to_numpy() == r.listing_id.astype(str).to_numpy()).all()

    lo, hi = sizefill.MIN_SQFT, sizefill.MAX_SQFT
    sq = rows.square_feet.astype(float)
    src = (sq.between(lo, hi) & train).to_numpy()  # rows a fill may read
    lsq = np.log(sq.where(src))
    day = pd.to_datetime(rows.price_at, utc=True).dt.floor("D")
    unit = rows.unit_id.astype(str)
    apt = unit.str.replace(r"~\d+$", "", regex=True)
    beds = rows.bedrooms.round().clip(0, 5).astype(float)
    baths = rows.full_baths.astype(float)
    bkey = unit + "|" + beds.astype(str)

    us, un = sizefill.earlier_sum(unit, day, unit[src], day[src], lsq[src])
    ss, sn = sizefill.earlier_sum(bkey, day, bkey[src], day[src], lsq[src])

    frame = rows.assign(canonical_unit_url=rows.page.fillna("").astype(str))
    rooms = "|" + beds.astype(str) + "|" + baths.astype(str)
    line = data.unit_line_key(frame) + rooms
    f = pd.DataFrame({"unit": unit, "apt": apt, "key": line, "day": day, "lsq": lsq})
    f = f[src & line.notna().to_numpy()]
    f = f.sort_values("day", kind="stable").groupby(["unit", "key"]).head(1)
    ls, ln = sizefill.earlier_sum(line, day, f.key, f.day, f.lsq)
    os_, on = sizefill.earlier_sum(
        line + "|" + unit, day, f.key + "|" + f.unit, f.day, f.lsq
    )
    as_, an = sizefill.earlier_sum(
        line + "|" + apt, day, f.key + "|" + f.apt, f.day, f.lsq
    )

    stated = sq.where((sq >= 100) & (sq <= 10_000))
    med = stated[train].groupby(rows.bedrooms.clip(upper=4)[train]).median()
    out = pd.DataFrame(
        {
            "listing_id": t.listing_id,
            "building": rows.building.to_numpy(),
            "apt": apt.to_numpy(),
            "unit": unit.to_numpy(),
            "day": day.dt.tz_localize(None).to_numpy(),
            "held": held,
            "bedrooms": rows.bedrooms.to_numpy(),
            "full_baths": rows.full_baths.to_numpy(),
            "half_baths": r.half_baths.to_numpy(),
            "stated": stated.to_numpy(),
            "sqft": t.sqft.to_numpy(),
            "source": t.size_source.to_numpy(),
            "bed_median": rows.bedrooms.clip(upper=4).map(med).to_numpy(),
            "unit_n": un,
            "unit_fill": mean(us, un),
            "unit_same_n": sn,
            "unit_same_fill": mean(ss, sn),
            "unit_other_n": un - sn,
            "unit_other_fill": mean(us - ss, un - sn),
            "line_n": ln - on,
            "line_fill": mean(ls - os_, ln - on),
            "line_piece_n": an - on,
            "line_piece_fill": mean(as_ - os_, an - on),
            "line_else_n": ln - an,
            "line_else_fill": mean(ls - as_, ln - an),
        }
    )
    # The rebuilt layers must give the size the fit read.
    for k in ("unit", "line"):
        m = (out.source == k).to_numpy()
        err = np.abs(np.log(out[k + "_fill"][m] / out.sqft[m]))
        print(
            k,
            "rows",
            m.sum(),
            "rebuilt fill missing",
            err.isna().sum(),
            "max log diff",
            err.max(),
        )
    # Sizes no fill could read: held-out ads, and training ads of the same or a later day.
    k = ["apt", "bedrooms", "full_baths"]
    e = out.loc[out.stated.between(lo, hi), [*k, "day", "held", "stated", "listing_id"]]
    q = out[[*k, "day", "listing_id"]].merge(e, on=k, suffixes=("", "_e"))
    q = q[(q.listing_id != q.listing_id_e) & (q.held | (q.day_e >= q.day))]
    g = q.groupby("listing_id").stated
    out["truth"] = out.listing_id.map(g.median())
    out["truth_n"] = out.listing_id.map(g.size()).fillna(0).astype(int)
    out["gap"] = np.nan
    out["cdf"] = np.nan
    assert (out.listing_id[held].to_numpy() == s["listing"].astype(str)).all()
    out.loc[held, "gap"] = s["y"] - s["pred"]
    out.loc[held, "cdf"] = s["cdf"]
    out["half"] = out.building.map({b: half(b) for b in out.building.unique()})
    out["year"] = out.day.dt.year
    out.to_parquet(OUT / "sizes.parquet")
    print("rows", len(out), "held", int(held.sum()))
    print(pd.crosstab(out.source, out.held).to_string())
    print("bedroom medians", med.round(0).to_dict())
    print(
        "truth known by source", out[out.truth.notna()].source.value_counts().to_dict()
    )
