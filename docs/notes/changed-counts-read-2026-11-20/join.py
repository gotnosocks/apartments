"""Join the readers' codes to the sample's key: shares of each code by group and half.

Writes `codes.csv` (the readers' codes with the key) beside this script. The se of a
difference of two shares p1 and p2 over n1 and n2 ads is sqrt(p1(1-p1)/n1 + p2(1-p2)/n2).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from build import OUT

HERE = Path(__file__).parent
CODES = list("abcde")


def shares(d: pd.DataFrame, by: list[str], title: str) -> None:
    n = d.groupby(by).code.value_counts().unstack(fill_value=0)
    n = n.reindex(columns=CODES, fill_value=0)
    tot = n.sum(axis=1)
    out = (
        n.astype(str)
        + " ("
        + (100 * n.div(tot, axis=0)).round(0).astype(int).astype(str)
        + "%)"
    )
    out["n"] = tot
    print("\n" + title)
    print(out.to_string())


def diffs(d: pd.DataFrame, title: str) -> None:
    print("\n" + title + ": share less the ordinary group's, with se")
    m = d[d.group == "mid"]
    for g in ("low", "high"):
        t = d[d.group == g]
        row = []
        for c in CODES + ["not same"]:
            f = (
                (lambda x: x.same_apartment == "no")
                if c == "not same"
                else (lambda x, c=c: x.code == c)
            )
            p1, p2 = f(t).mean(), f(m).mean()
            se = np.sqrt(p1 * (1 - p1) / len(t) + p2 * (1 - p2) / len(m))
            row.append(f"{c} {p1 - p2:+.2f} ({se:.2f})")
        print(g, len(t), "vs", len(m), "|", "  ".join(row))


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    rows = []
    for k in range(10):
        rows += json.loads((OUT / f"codes_{k}.json").read_text())
    r = pd.DataFrame(rows)
    r["ad"] = r.ad.astype(str)
    s = pd.read_csv(OUT / "sample.csv", dtype={"listing_id": str, "o_listing": str})
    d = s.merge(r, left_on="listing_id", right_on="ad", how="left", validate="1:1")
    assert d.code.isin(CODES).all() and len(d) == 300
    d["fresh"] = ~d.back
    keep = ["listing_id", "o_listing", "building", "half", "group", "dir", "fresh"]
    keep += ["label_differs", "code", "same_apartment", "text_beds_1", "text_beds_2"]
    keep += ["text_baths_1", "text_baths_2", "quote"]
    d[keep].to_csv(HERE / "codes.csv", index=False)
    shares(d, ["group"], "codes by group")
    shares(d, ["half", "group"], "codes by half and group")
    shares(d, ["fresh", "group"], "codes by whether the previous ad has other counts")
    shares(d, ["dir", "group"], "codes by direction")
    shares(d, ["label_differs"], "codes by whether the unit labels differ")
    print("\nsame apartment by group")
    print(d.groupby("group").same_apartment.value_counts().unstack(fill_value=0))
    print(
        d.groupby(["half", "group"]).same_apartment.value_counts().unstack(fill_value=0)
    )
    diffs(d, "all")
    for hf in "AB":
        diffs(d[d.half == hf], "half " + hf)
    for fr in (True, False):
        diffs(d[d.fresh == fr], f"previous ad has other counts {fr}")
    print("\nfresh by group")
    print(d.groupby("group").fresh.agg(["mean", "size"]).round(2))
