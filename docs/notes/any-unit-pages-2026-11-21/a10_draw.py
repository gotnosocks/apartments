"""Draw the pages for blind reads and write one dossier per page, asks and dollar figures masked.

Pages hold two or more candidate ads and the latest-split held-out ad of a unit. Marked:
10 text-marked and 10 overlap-marked pages a half, at random. Unmarked: one page with
neither mark from each of 20 of the marked pages' buildings, at random, ten a half where
the buildings allow. The dossier lists the page's candidate ads (the 12 latest when it has
more) with dates, coded counts, size, unit label and text, and no ask. Read ids are
shuffled so the order says nothing of the stratum. The key stays in scratch until the
reads are in.
"""

import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/any-unit")
READS = OUT / "reads"
MONEY = re.compile(
    r"\$\s?\d[\d,.]*\s?[kK]?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{4,5}\s?(?:/|per|a)\s?(?:mo|month)\w*",
    re.I,
)


def mask(s):
    return MONEY.sub("[$]", s or "")


if __name__ == "__main__":
    rng = np.random.default_rng(20261121)
    c = duckdb.connect()
    held = set(pd.read_parquet(OUT / "heldout.parquet", columns=["unit_id"]).unit_id)
    M = pd.read_parquet(OUT / "marks.parquet")
    M = M[M.unit_id.isin(held)]
    picks = []
    for h in "AB":
        x = M[M.half == h]
        for mk in ("m_text", "m_overlap"):
            pool = x[x[mk] & ~x.unit_id.isin([p[0] for p in picks])]
            for u in rng.choice(pool.unit_id.to_numpy(), 10, replace=False):
                picks.append((u, f"{mk[2:]}_{h}"))
    marked_b = M.set_index("unit_id").loc[[p[0] for p in picks], ["building", "half"]]
    blds = marked_b.drop_duplicates("building")
    un = []
    for h in "AB":
        bh = blds[blds.half == h].building.to_numpy()
        rng.shuffle(bh)
        for b in bh:
            pool = M[(M.building == b) & ~M.m_any]
            if len(pool) and sum(1 for _, s in un if s.endswith(h)) < 10:
                un.append((rng.choice(pool.unit_id.to_numpy()), f"unmarked_{h}"))
    picks += un
    print("marked", len(picks) - len(un), "unmarked", len(un))
    key = pd.DataFrame(picks, columns=["unit_id", "stratum"])
    key = key.sample(frac=1, random_state=7).reset_index(drop=True)
    key["read_id"] = [f"P{i + 1:02d}" for i in range(len(key))]
    key = key.merge(
        M[["unit_id", "building", "half", "m_text", "m_overlap"]], on="unit_id"
    )
    key.to_parquet(OUT / "read_key.parquet")
    READS.mkdir(exist_ok=True)
    c.sql("set memory_limit='1500MB'; set threads=2")
    units = ", ".join(f"'{u}'" for u in key.unit_id)
    A = c.sql(f"""select listing_id, unit_id, first_day, end_day, bedrooms, full_baths,
                  square_feet from '{OUT}/ads.parquet' where unit_id in ({units})""").df()
    ids = ", ".join(f"'{x}'" for x in A.listing_id)
    T = c.sql(f"""select listing_id, label, description from '{OUT}/texts.parquet'
                  where listing_id in ({ids})""").df()
    A = A.merge(T, on="listing_id", how="left")
    for r in key.itertuples():
        ads = A[A.unit_id == r.unit_id].sort_values("first_day").tail(12)
        lines = [
            f"Page {r.read_id}. Building: {r.building}. Ads on this page: "
            f"{len(ads)} shown, oldest first.\n"
        ]
        for i, a in enumerate(ads.itertuples(), 1):
            sq = "" if pd.isna(a.square_feet) else f", {int(a.square_feet)} sq ft"
            fb = "" if pd.isna(a.full_baths) else f", {a.full_baths:g} full baths"
            bd = "?" if pd.isna(a.bedrooms) else f"{a.bedrooms:g}"
            txt = mask(a.description)[:1500].replace("\n", " ")
            lines.append(
                f"Ad {i}: ran {a.first_day.date()} to {a.end_day.date()}; unit label "
                f"{a.label!r}; coded {bd} bedrooms{fb}{sq}.\nText: {txt}\n"
            )
        (READS / f"{r.read_id}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(key.stratum.value_counts().to_dict())
    print(
        "buildings in the draw",
        key.building.nunique(),
        "the-rheingold pages",
        int((key.building == "the-rheingold").sum()),
    )
