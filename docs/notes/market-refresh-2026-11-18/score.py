"""Scores the market refresh's predictions from the Deals tables of Nov 9 and Nov 18.

Reads the Deals table published from `range-m` (the copy saved before the refresh), the
table published from `range-m2`, and the ads file of the new pipeline build. It prints:

- the share of the Nov 9 ads whose status in the new ads file is no longer ACTIVE or
  TEMPORARILY_OFF_MARKET, for all ads and for the first 100 with no caution;
- for the ads in both tables with the same ask, the Spearman correlation of the two
  `below_share` values and the share of the old lowest tenth still in the new lowest tenth;
- the cautioned share of the new table.

Run: python score.py OLD_DEALS_JSON NEW_DEALS_JSON ADS_PARQUET
"""

import json
import sys

import pandas as pd

OPEN = ("ACTIVE", "TEMPORARILY_OFF_MARKET")


def table(path):
    t = pd.DataFrame(json.load(open(path)))
    t["listing_id"] = t.listing_id.astype(str)
    t["plain"] = ~t.cautions.map(bool)
    return t.sort_values("below_share", kind="stable").reset_index(drop=True)


if __name__ == "__main__":
    old, new = table(sys.argv[1]), table(sys.argv[2])
    ads = pd.read_parquet(sys.argv[3], columns=["listing_id", "status"])
    status = (
        ads.assign(listing_id=ads.listing_id.astype(str)).set_index("listing_id").status
    )
    now = old.listing_id.map(status)
    closed = ~now.isin(OPEN)
    print(f"old table {len(old)} ads, new table {len(new)} ads")
    print(f"old ads closed: {closed.sum()} ({100 * closed.mean():.1f}%)")
    print(
        "  their statuses now:", now[closed].fillna("missing").value_counts().to_dict()
    )
    print(
        f"  old ads absent from the new table: {(~old.listing_id.isin(new.listing_id)).sum()}"
    )
    first = old[old.plain].head(100)
    print(f"first 100 uncautioned old ads closed: {closed[first.index].sum()}")
    tenth = old[old.plain].head(int(old.plain.sum()) // 10)
    print(
        f"lowest tenth of uncautioned old ads ({len(tenth)}) closed: "
        f"{100 * closed[tenth.index].mean():.1f}%"
    )

    both = old.merge(new, on="listing_id", suffixes=("_old", "_new"), validate="1:1")
    same = both[both.ask_old == both.ask_new]
    print(f"in both tables {len(both)}, with the same ask {len(same)}")
    rho = same.below_share_old.corr(same.below_share_new, method="spearman")
    print(f"Spearman of the two places: {rho:.4f}")
    k = len(same) // 10
    low_old = set(same.nsmallest(k, "below_share_old").listing_id)
    low_new = set(same.nsmallest(k, "below_share_new").listing_id)
    print(
        f"old lowest tenth ({k}) still in the new lowest tenth: {100 * len(low_old & low_new) / k:.1f}%"
    )
    moved = (same.below_share_new - same.below_share_old).abs()
    print(
        f"change in place: median {moved.median():.4f}, 95th percentile {moved.quantile(0.95):.4f}"
    )

    print(
        f"new table cautioned: {(~new.plain).sum()} of {len(new)} ({100 * (~new.plain).mean():.1f}%)"
    )
    print("  by caution:", new.cautions.explode().dropna().value_counts().to_dict())
