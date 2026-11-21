"""Join the readers' codes to the sample key and print the verdict shares by stratum.

Writes `codes.csv` beside this script: the sample key (no rent, no gap) with the readers'
columns. A share's se is the binomial one. `judged` leaves out the ads coded cannot_tell.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from build import OUT

HERE = Path(__file__).parent

if __name__ == "__main__":
    pd.set_option("display.width", 200)
    s = pd.read_csv(OUT / "sample.csv", dtype={"listing_id": str})
    c = pd.concat(
        [pd.read_csv(OUT / f"codes_{k}.csv", dtype=str) for k in range(8)],
        ignore_index=True,
    )
    c["ad"] = c.ad.str.strip()
    c["verdict"] = c.verdict.str.strip()
    assert c.ad.is_unique and set(c.ad) == set(s.listing_id), (
        "codes do not match the sample"
    )
    assert c.verdict.isin(["plausible", "too_large", "too_small", "cannot_tell"]).all()
    assert c.quote.str.startswith("Ad text:").all()
    j = s.merge(c, left_on="listing_id", right_on="ad").drop(columns="ad")
    keep = ["listing_id", "building", "half", "year", "stratum", "batch", "bedrooms"]
    keep += [
        "full_baths",
        "half_baths",
        "sqft",
        "ratio",
        "text_sqft",
        "verdict",
        "quote",
    ]
    j[keep].round({"sqft": 0, "ratio": 3}).to_csv(HERE / "codes.csv", index=False)
    print("verdicts", j.verdict.value_counts().to_dict())
    print("text states a size", j.text_sqft.notna().sum())

    def shares(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        out = {"n": n}
        for v in ("too_large", "too_small", "cannot_tell"):
            p = (g.verdict == v).mean()
            out[v] = p
            out[v + "_se"] = np.sqrt(p * (1 - p) / n)
        out["low5"] = (g.cdf < 0.05).mean()
        return pd.Series(out)

    print(j.groupby("stratum").apply(shares).round(3).to_string())
    j["group"] = np.where(
        j.stratum.isin(["unit, other beds", "line, over 1.4"]),
        "rule blanks",
        "rule keeps",
    )
    print(j.groupby("group").apply(shares).round(3).to_string())
    print(j.groupby(["group", "half"]).apply(shares).round(3).to_string())
    print("\nheld-out tail by verdict (after the codes were fixed):")
    print(
        j.groupby("verdict")
        .cdf.agg(["size", lambda x: (x < 0.05).mean(), lambda x: (x > 0.95).mean()])
        .round(3)
        .to_string()
    )
    t = j[j.text_sqft.notna()]
    print("\nstated in text:")
    print(
        t.assign(r=t.sqft / t.text_sqft.astype(float))[
            ["listing_id", "stratum", "sqft", "text_sqft", "r", "verdict"]
        ]
        .round(2)
        .to_string()
    )
