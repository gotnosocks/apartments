"""The readers' codes against the gaps of the ads they read.

Joins `codes_*.json` (written by six Sonnet readers from `dossier_*.json`, blind to rents and
gaps) to the key in `picked.csv`. Prints, by role of the building (miss, control, named), how
many ads say anything about their own unit and how often each trait turns up; then, for ads
of 2 or more bedrooms, the gap less the building's mean over the read ads of that bedroom
count, by trait.
"""

import glob
import json

import numpy as np
import pandas as pd

from b1 import OUT

TRAITS = [
    "unit_specific",
    "plan_named",
    "sqft_stated",
    "floor_stated",
    "exposure_stated",
]
TRAITS += ["corner", "view_stated", "outdoor_any", "duplex", "penthouse", "convertible"]
TRAITS += ["home_office_extra", "primary_suite", "new_development_first_lease"]

if __name__ == "__main__":
    pd.set_option("display.width", 200)
    rows, blds = [], []
    for f in sorted(glob.glob(str(OUT / "codes_*.json"))):
        for b in json.load(open(f))["buildings"]:
            blds.append((b["building"], bool(b["plan_priced"]), b["summary"]))
            for a in b["ads"]:
                rows.append({"building": b["building"], **a})
    c = pd.DataFrame(rows)
    c["ad"] = c.ad.astype(str)
    c["plan_named"] = c.plan_name.notna() | c.line_in_text.notna()
    c["sqft_stated"] = c.sqft_text.notna()
    c["floor_stated"] = c.floor_text.notna()
    c["exposure_stated"] = c.exposure.notna()
    c["view_stated"] = c.view.notna()
    c["outdoor_any"] = ~c.outdoor.fillna("none").isin(["none", "juliet"])
    for t in TRAITS:
        c[t] = c[t].fillna(False).astype(bool)
    key = pd.read_csv(OUT / "picked.csv")
    gaps = pd.concat(
        [
            pd.read_parquet(
                OUT / f"{w}_held.parquet",
                columns=["listing_id", "building", "bedrooms", "gap", "half"],
            ).assign(set=w)
            for w in ("bt", "l2")
        ]
    )
    c = c.merge(key[["building", "set", "role"]], on="building")
    c = c.merge(
        gaps.rename(columns={"listing_id": "ad"}),
        on=["ad", "building", "set"],
        how="left",
    )
    print("ads coded", len(c), "matched to a gap", c.gap.notna().sum())
    print(
        "buildings",
        c.building.nunique(),
        "halves",
        c.groupby("half").building.nunique().to_dict(),
    )
    pp = pd.DataFrame(blds, columns=["building", "plan_priced", "summary"]).merge(key)
    print("\nbuildings the readers called plan priced, by role")
    print(pp.groupby("role").plan_priced.agg(["sum", "size"]).to_string())
    print(pp[pp.plan_priced][["building", "role", "mean_gap"]].round(3).to_string())
    print("\nshare of read ads with each trait, by role")
    t = c.groupby("role")[TRAITS].mean().T
    t["all"] = c[TRAITS].mean()
    t["ads"] = c[TRAITS].sum()
    print(t.round(3).to_string())
    print(c.groupby("role").size().to_dict())
    print("\nbuildings by the share of their read ads that are unit specific")
    u = c.groupby(["role", "building"]).unit_specific.mean()
    print(u.groupby("role").describe().round(2).to_string())
    big = c[(c.bedrooms >= 2) & c.gap.notna()].copy()
    big["x"] = big.gap.clip(-0.5, 0.5)
    big["dev"] = big.x - big.groupby(["building", "bedrooms"]).x.transform("mean")
    big["n"] = big.groupby(["building", "bedrooms"]).x.transform("size")
    big = big[big.n >= 2]
    print("\n2+ bedroom read ads in a building and count with two or more:", len(big))
    out = []
    for t in TRAITS:
        m = big[t]
        # only groups where the trait varies carry information
        v = big.groupby(["building", "bedrooms"])[t].transform("nunique") > 1
        d1, d0 = big.dev[m & v], big.dev[~m & v]
        se = np.sqrt(d1.var() / max(len(d1), 1) + d0.var() / max(len(d0), 1))
        out.append(
            (t, int((m & v).sum()), int((~m & v).sum()), d1.mean() - d0.mean(), se)
        )
    print(
        pd.DataFrame(out, columns=["trait", "with", "without", "diff", "se"]).round(3)
    )
    print("\nsd of the gap within building and count:", round(big.dev.std(), 4))
    c.drop(columns=["other"]).to_parquet(OUT / "read_codes.parquet")
