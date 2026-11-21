"""Fresh and back from strictly earlier training ads only, per held-out ad of l2bt.

`mark.py` takes the apartment's most recent training ad of any date, and in the latest split
a training ad can be dated after the held-out ad. The Deals page only has earlier ads, so
this script rebuilds the marks from training ads dated strictly before the held-out ad and
writes one row per held-out ad to `prior.parquet` for `newseen.py` and `factor.py`.

Columns: `anydiff`, `lastdiff` are the any-date marks of `mark.py` (any training ad of the
apartment has other counts; the most recent one has). `p_any`, `p_last`, `p_n` are the same
over strictly earlier training ads. `u_n`, `u_same` count the model unit's training rows and
those with the held-out counts; `up_n` counts its strictly earlier rows. `seen` says whether
any strictly earlier training ad of the model unit has the held-out counts. `bb` counts the
building's training ads with the held-out ad's bedrooms.

The apartment is the unit id less its `~n` suffix, as in `build.py`. The model unit is the
full unit id, the key the model's unit term uses.
"""

import numpy as np
import pandas as pd

from build import COLS, OUT, RUN, half
from rentfrontier import drift_score

if __name__ == "__main__":
    ds = drift_score.dataset_dir(RUN)
    r = pd.read_parquet(ds / "rows.parquet", columns=COLS)
    s = np.load(RUN / "pred_scores.npz")
    r["held"] = s["heldout"]
    r["listing_id"] = r.listing_id.astype(str)
    r["building"] = r.building.astype(str)
    r["day"] = pd.to_datetime(r.price_at, utc=True).dt.tz_localize(None)
    r["baths"] = r.full_baths + 0.5 * r.half_baths.fillna(0)
    r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
    h = r[r.held].reset_index(drop=True)
    assert (h.listing_id.to_numpy() == s["listing"].astype(str)).all()
    h["gap"] = s["y"] - s["pred"]
    h["cdf"] = s["cdf"]
    h["half"] = h.building.map(half)
    h["year"] = h.day.dt.year
    print("held-out rows", len(h), "listings", h.listing_id.nunique())
    print("held-out rows with no unit id", int(h.unit_id.isna().sum()))
    t = r[~r.held & r.apt.notna()]
    print("held-out listing also in training", h.listing_id.isin(t.listing_id).mean())
    keys = ["building", "apt", "unit_id", "bedrooms", "baths", "day"]
    m = h[["listing_id", *keys]].merge(
        t[[*keys, "listing_id"]], on=["building", "apt"], suffixes=("", "_t")
    )
    m["diff"] = (m.bedrooms != m.bedrooms_t) | (m.baths != m.baths_t)
    m["prior"] = m.day_t < m.day
    m["sameunit"] = m.unit_id == m.unit_id_t
    m = m.sort_values("day_t")
    g = m.groupby("listing_id")
    f = pd.DataFrame(
        {
            "anydiff": g["diff"].any(),
            "lastdiff": g["diff"].last(),
            "ntrain": g.size(),
            "days_prev": (g.day.last() - g.day_t.last()).dt.days,
        }
    )
    p = m[m.prior].groupby("listing_id")
    f = f.join(
        pd.DataFrame(
            {"p_any": p["diff"].any(), "p_last": p["diff"].last(), "p_n": p.size()}
        )
    )
    u = m[m.sameunit].assign(same=lambda x: ~x["diff"]).groupby("listing_id")
    f = f.join(pd.DataFrame({"u_n": u.size(), "u_same": u.same.sum()}))
    up = m[m.sameunit & m.prior].assign(same=lambda x: ~x["diff"]).groupby("listing_id")
    f = f.join(pd.DataFrame({"up_n": up.size(), "seen": up.same.any()}))
    h = h.merge(f, left_on="listing_id", right_index=True, how="left")
    bb = t.groupby(["building", "bedrooms"]).listing_id.nunique().rename("bb")
    h = h.merge(bb, left_on=["building", "bedrooms"], right_index=True, how="left")
    h["bb"] = h.bb.fillna(0)
    h.to_parquet(OUT / "prior.parquet")
    a = h[h.year >= 2022]
    print("held-out ads from 2022 on", len(a))
    print("with a training ad of the apartment", int(a.ntrain.notna().sum()))
    print("with a strictly earlier one", int(a.p_n.notna().sum()))
    print("with a strictly earlier one of the model unit", int(a.up_n.notna().sum()))
