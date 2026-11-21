"""Draw the filled held-out ads to read and write the readers' dossiers.

From the held-out ads of 2024 to 2026 whose size is a fill and whose text is known, by
stratum (the fill's class and how far it is over the bedroom median), at most two per
building over the whole sample, seed 20261120. A dossier entry holds the ad's coded bedrooms
and baths, the filled size and the full text with dollar amounts masked. It holds no rent,
no gap and no stratum. `sample.csv` keeps the key.
"""

import json
import re

import numpy as np
import pandas as pd

from build import OUT
from stats import load

TEXTS = "/data1/apartments/tmp/history-scan/texts-b9.parquet"
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?k?|\b\d[\d,]{3,}(?:\.\d+)?\s?(?=(?:/|per |a )mo)", re.I
)
WANT = {
    "unit, other beds": 50,
    "unit, mixed beds": 30,
    "line, over 1.4": 50,
    "line, to 1.4": 40,
    "unit, same beds, over 1.4": 30,
    "unit, same beds, to 1.4": 40,
}
BATCH = 30


def stratum(d: pd.DataFrame) -> np.ndarray:
    big = np.where(d.ratio > 1.4, ", over 1.4", ", to 1.4")
    line = d.klass.str.startswith("line").to_numpy()
    same = (d.klass == "unit, same beds").to_numpy()
    return np.where(line, "line" + big, np.where(same, d.klass + big, d.klass))


if __name__ == "__main__":
    rng = np.random.default_rng(20261120)
    d = load()
    d = d[d.held & (d.year >= 2024) & d.source.isin(["unit", "line"])]
    tx = pd.read_parquet(TEXTS, columns=["listing_id", "description"])
    tx["listing_id"] = tx.listing_id.astype(str)
    d = d.merge(tx, on="listing_id", how="left")
    d = d[d.description.fillna("").str.len() >= 200]
    d["stratum"] = stratum(d)
    print("available", d.stratum.value_counts().to_dict())
    d = d.iloc[rng.permutation(len(d))]
    per_bld: dict[str, int] = {}
    took: dict[str, list] = {k: [] for k in WANT}
    # Scarce strata draw first, so the building cap does not starve them.
    for name in sorted(WANT, key=lambda k: (d.stratum == k).sum()):
        for i in np.flatnonzero((d.stratum == name).to_numpy()):
            b = d.building.iloc[i]
            if len(took[name]) < WANT[name] and per_bld.get(b, 0) < 2:
                took[name].append(i)
                per_bld[b] = per_bld.get(b, 0) + 1
    s = d.iloc[sum(took.values(), [])]
    s = s.iloc[rng.permutation(len(s))].reset_index(drop=True)
    s["batch"] = s.index // BATCH
    keep = [
        "listing_id",
        "building",
        "half",
        "year",
        "stratum",
        "klass",
        "batch",
        "source",
    ]
    keep += [
        "bedrooms",
        "full_baths",
        "half_baths",
        "sqft",
        "ratio",
        "truth",
        "cdf",
        "gap",
    ]
    s[keep].to_csv(OUT / "sample.csv", index=False)
    print(s.groupby(["stratum", "half"]).size().unstack().to_string())
    print(
        "ads",
        len(s),
        "buildings",
        s.building.nunique(),
        "max per building",
        max(per_bld.values()),
    )
    for k, g in s.groupby("batch"):
        ads = []
        for r in g.itertuples():
            ads.append(
                {
                    "ad": r.listing_id,
                    "coded_bedrooms": float(r.bedrooms),
                    "coded_baths": float(r.full_baths + 0.5 * (r.half_baths or 0)),
                    "coded_square_feet": int(round(r.sqft)),
                    "text": MONEY.sub("[amount]", r.description),
                }
            )
        (OUT / f"dossier_{k}.json").write_text(json.dumps(ads, indent=1))
        print(k, len(ads), "ads", sum(len(a["text"]) for a in ads), "chars")
