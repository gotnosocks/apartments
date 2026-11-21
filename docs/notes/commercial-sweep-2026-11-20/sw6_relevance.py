"""Held-out gaps of marked rows on the latest split, and the Deals ads near them.

Gaps come from history: the l2bt run's held-out ads (`po-thinlevel/l2_ads.parquet`, built
from its `pred_scores.npz`), gap = log ask minus the model's median. Three views:

1. the marked held-out ads' own gaps. The ratio mark selects on the ask, so its own gap is
   circular; the text and short marks do not use the ask;
2. the gaps of the other held-out ads in buildings that hold a marked l2bt training row,
   which is what an excluded row would change through the building's level;
3. the live Deals ads in buildings that hold a marked training row of the live run, and how
   many of them show as deals (ask under the 80% interval's low end, no caution, and in the
   top 300 by cautious saving among ads with a unit or building basis of five or more ads).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/commercial-sweep")
TL = Path("/data1/apartments/tmp/po-thinlevel")
DEALS = Path("/data1/apartments/site/deals/deals.json")
LEVELS = Path("/data1/apartments/tmp/po-bldmodes/levels_live.parquet")


def summ(g: pd.DataFrame) -> dict:
    return dict(
        n=len(g),
        median_gap=round(float(g.gap.median()), 4) if len(g) else np.nan,
        below5=round(float((g.cdf < 0.05).mean()), 3) if len(g) else np.nan,
        above95=round(float((g.cdf > 0.95).mean()), 3) if len(g) else np.nan,
    )


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    M = pd.read_parquet(OUT / "marks.parquet")
    M["listing_id"] = M.listing_id.astype(str)
    R = pd.read_parquet(OUT / "reads.parquet")
    conf = set(R.listing_id.astype(str)[R.answer.isin(["commercial", "placeholder"])])
    M["m_ratio_text"] = M.m_ratio & M.m_text
    M["m_confirmed"] = M.listing_id.isin(conf)
    marks = ["m_ratio", "m_ratio_text", "m_text", "m_short", "m_confirmed"]

    H = pd.read_parquet(TL / "l2_ads.parquet")
    H["listing_id"] = H.listing_id.astype(str)
    print(
        "l2bt held-out ads", len(H), "share gap<0", round(float((H.gap < 0).mean()), 3)
    )
    print("share cdf<0.5", round(float((H.cdf < 0.5).mean()), 3))
    Hm = H.merge(M[["listing_id", "status", *marks]], on="listing_id", how="left")
    print("held-out ads without a marks row", int(Hm.status.isna().sum()))
    for m in marks:
        Hm[m] = Hm[m].fillna(False).astype(bool)

    print("\n1. own gaps of marked held-out ads")
    rows = [{"set": "all held out", **summ(Hm)}]
    for m in marks:
        rows.append({"set": m, **summ(Hm[Hm[m]])})
        for s in ("train", "ledger", "live", "rule"):
            g = Hm[Hm[m] & (Hm.status == s)]
            if len(g):
                rows.append({"set": f"{m} status {s}", **summ(g)})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n2. other held-out ads in buildings with a marked l2bt training row")
    S = pd.read_parquet(TL / "l2_rows_slim.parquet")
    S["listing_id"] = S.listing_id.astype(str)
    Tr = S[~S.heldout].merge(M[["listing_id", *marks]], on="listing_id", how="left")
    for m in marks:
        Tr[m] = Tr[m].fillna(False).astype(bool)
    rows = [{"set": "all held out", **summ(H)}]
    bands = pd.cut(
        H.n_bld, [-1, 4, 19, 99, 10**9], labels=["0-4", "5-19", "20-99", "100+"]
    )
    for m in marks:
        b = set(Tr.building[Tr[m]])
        sel = H.building.isin(b) & ~Hm[m].to_numpy()
        rows.append({"set": m, "buildings": len(b), **summ(H[sel])})
        for k in bands.cat.categories:
            g = H[sel & (bands == k)]
            rows.append({"set": f"{m} n_bld {k}", **summ(g)})
    for k in bands.cat.categories:
        rows.append({"set": f"all n_bld {k}", **summ(H[bands == k])})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n2b. the same by half of the buildings (this note's seed)")
    hb = H.drop(columns=["half"]).merge(
        M[["listing_id", "half"]], on="listing_id", how="left"
    )
    rows = []
    for m in ("m_ratio", "m_ratio_text", "m_confirmed"):
        b = set(Tr.building[Tr[m]])
        sel = H.building.isin(b) & ~Hm[m].to_numpy()
        for h in ("A", "B"):
            rows.append({"set": m, "half": h, **summ(hb[sel & (hb.half == h)])})
    for h in ("A", "B"):
        rows.append({"set": "all held out", "half": h, **summ(hb[hb.half == h])})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n3. live Deals ads in buildings with a marked live training row")
    D = pd.DataFrame(json.load(open(DEALS)))
    lv = pd.read_parquet(LEVELS, columns=["building", "level", "n_train"])
    D = D.merge(lv, on="building", how="left")
    D["n_train"] = D.n_train.fillna(0)
    D["uncautioned"] = D.cautions.map(len) == 0
    D["saving"] = (D.model_lo80 - D.ask) / D.model_lo80
    D["below_lo80"] = D.ask < D.model_lo80
    pop = D.uncautioned & ((D.unit_ads > 0) | (D.n_train >= 5))
    top = set(D[pop].sort_values("saving", ascending=False).listing_id.head(300))
    D["top300"] = D.listing_id.isin(top)
    print(
        "deals ads",
        len(D),
        "below lo80",
        int(D.below_lo80.sum()),
        "below lo80 and uncautioned",
        int((D.below_lo80 & D.uncautioned).sum()),
        "default population",
        int(pop.sum()),
    )
    t = M[M.status == "train"]
    rows = []
    for m in marks:
        b = set(t.building[t[m]])
        x = D[D.building.isin(b)]
        rows.append(
            dict(
                set=m,
                train_rows=int(t[m].sum()),
                buildings=len(b),
                deals_ads=len(x),
                below_lo80=int(x.below_lo80.sum()),
                below_lo80_uncautioned=int((x.below_lo80 & x.uncautioned).sum()),
                top300=int(x.top300.sum()),
                median_level=round(float(x.level.median()), 3) if len(x) else np.nan,
            )
        )
    print(pd.DataFrame(rows).to_string(index=False))
    print("median level of all deals ads", round(float(D.level.median()), 3))
    for m in ("m_ratio_text", "m_confirmed"):
        b = set(t.building[t[m]])
        x = D[D.building.isin(b) & D.top300].sort_values("saving", ascending=False)
        cols = [
            "listing_id",
            "building",
            "bedrooms",
            "ask",
            "model_lo80",
            "n_train",
            "level",
        ]
        print(f"\n{m} top-300 ads")
        print(x[cols].head(20).to_string(index=False))
