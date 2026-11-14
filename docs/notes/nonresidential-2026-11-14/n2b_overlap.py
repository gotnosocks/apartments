"""N2b: the candidates set against the earlier work, and the lot signal across all of L1's rows.

I match the candidate rows of `n2_candidates.py` with the four earlier sets that
`n1_prior.py` gathered (the ledger's nonresidential excludes, the sprint's screen, S16's reads
and S17's reads), by stratum and for the draft rule. I then count L1's rows on lots that
MapPLUTO gives no apartments, over the whole dataset, to judge how much an empty lot says about
a row. No price, gap or residual enters this script.
"""

import json

import pandas as pd

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
DATASET = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/"
)
REGISTRY = (
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
)
PLUTO = "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"

c = pd.read_parquet(OUT + "candidates.parquet")
prior = pd.read_parquet(OUT + "prior_ids.parquet")
res = {"by_set": {}}
for s, g in prior.groupby("set"):
    ids = set(g.listing_id)
    m = c.listing_id.isin(ids)
    res["by_set"][s] = {
        "listings": len(ids),
        "candidates": int(m.sum()),
        "rule_mark": int((m & c.rule_mark).sum()),
        "by_stratum": c.stratum[m].value_counts().to_dict(),
    }

d = pd.read_parquet(DATASET + "rows.parquet", columns=["listing_id", "building"])
reg = pd.read_parquet(REGISTRY, columns=["building", "bbl"]).drop_duplicates("building")
pl = pd.read_parquet(PLUTO, columns=["bbl", "unitsres", "landuse", "yearbuilt"])
reg["bbl"] = reg.bbl.astype(str)
pl["bbl"] = pl.bbl.astype("int64").astype(str)
lot = reg.merge(pl.drop_duplicates("bbl"), on="bbl", how="left").set_index("building")
d["unitsres"] = pd.to_numeric(d.building.map(lot.unitsres), errors="coerce")
d["landuse"] = d.building.map(lot.landuse)
d["yearbuilt"] = pd.to_numeric(d.building.map(lot.yearbuilt), errors="coerce")
z = d.unitsres == 0
res["lot_empty_all_rows"] = {
    "rows": int(z.sum()),
    "share_of_rows": float(z.mean()),
    "buildings": int(d.building[z].nunique()),
    "no_lot_match": int(d.unitsres.isna().sum()),
    "landuse": d.landuse[z].value_counts().head(8).to_dict(),
    "yearbuilt_0": int((z & (d.yearbuilt.fillna(0) == 0)).sum()),
}
res["lot_empty_candidates"] = {
    "rows": int(c.bk_lot.sum()),
    "landuse": c.lot_landuse[c.bk_lot].value_counts().head(8).to_dict(),
    "share_of_candidates": float(c.bk_lot.mean()),
}
res["rule_mark_kinds"] = (
    c[c.rule_mark]
    .assign(
        combo=lambda f: (
            f.k_text.map({True: "text", False: ""})
            + f.k_label.map({True: "+label", False: ""})
            + f.k_other.map({True: "+other_ad", False: ""})
            + f.k_lot.map({True: "+lot", False: ""})
        )
    )
    .combo.value_counts()
    .to_dict()
)
json.dump(res, open(OUT + "overlap.json", "w"), indent=1, default=int)
print(json.dumps(res, indent=1, default=int))
