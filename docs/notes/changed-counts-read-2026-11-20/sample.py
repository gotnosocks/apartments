"""Draw the ads to read and write the readers' dossiers, with no rent, gap or group in them.

From the changed-count held-out ads of 2025 and 2026 with both texts: 100 below the model's
5% point, 100 above its 95% point and 100 between its 30% and 70% points, at most two per
building over the whole sample, seed 20261120. Each dossier entry holds the held-out ad (`ad_1`) and
the apartment's most recent training ad of other counts (`ad_2`): coded bedrooms, baths, size, unit
label, first day and the full text with dollar amounts masked. `sample.csv` keeps the key.
"""

import json
import re

import numpy as np
import pandas as pd

from build import OUT

MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?k?|\b\d[\d,]{3,}(?:\.\d+)?\s?(?=(?:/|per |a )mo)", re.I
)
PER = 100
BATCH = 30


def side(r, pre: str) -> dict:
    g = lambda k: getattr(r, pre + k)  # noqa: E731
    return {
        "listed": str(g("first_day"))[:10] if pd.notna(g("first_day")) else None,
        "unit_label": g("label"),
        "coded_bedrooms": float(g("bedrooms")),
        "coded_baths": float(g("baths")),
        "coded_square_feet": None if pd.isna(g("square_feet")) else g("square_feet"),
        "text": MONEY.sub("[amount]", g("text")),
    }


if __name__ == "__main__":
    rng = np.random.default_rng(20261120)
    c = pd.read_parquet(OUT / "changed2.parquet")
    c = c[(c.year >= 2025) & c.text.notna() & c.o_text.notna()]
    c["group"] = np.where(
        c.cdf < 0.05,
        "low",
        np.where(c.cdf > 0.95, "high", np.where(c.cdf.between(0.3, 0.7), "mid", "")),
    )
    c = c[c.group != ""].iloc[rng.permutation((c.group != "").sum())]
    per_bld: dict[str, int] = {}
    took = {"low": [], "high": [], "mid": []}
    for i, (b, g) in enumerate(zip(c.building, c.group)):
        if len(took[g]) < PER and per_bld.get(b, 0) < 2:
            took[g].append(i)
            per_bld[b] = per_bld.get(b, 0) + 1
    s = c.iloc[sum(took.values(), [])]
    s = s.iloc[rng.permutation(len(s))].reset_index(drop=True)
    s["batch"] = s.index // BATCH
    keep = ["listing_id", "o_listing", "building", "half", "group", "batch", "dir"]
    keep += ["back", "cdf", "gap", "label_differs", "sqft_ratio"]
    s[keep].to_csv(OUT / "sample.csv", index=False)
    print(s.groupby(["group", "half"]).size().unstack().to_string())
    print("buildings", s.building.nunique(), "max per building", max(per_bld.values()))
    for k, g in s.groupby("batch"):
        ads = []
        for r in g.itertuples():
            ads.append(
                {
                    "ad": r.listing_id,
                    "building": r.building,
                    "ad_1": side(r, ""),
                    "ad_2": side(r, "o_"),
                }
            )
        (OUT / f"dossier_{k}.json").write_text(json.dumps(ads, indent=1))
        chars = sum(len(a["ad_1"]["text"]) + len(a["ad_2"]["text"]) for a in ads)
        print(k, len(ads), "ads", chars, "chars")
