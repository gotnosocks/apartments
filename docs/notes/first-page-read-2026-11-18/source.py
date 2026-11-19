"""Free check: the ad's source and photo count against its place in the backtest (`range-j`).

For the backtest's open ads with no caution it reads `listingSource.sourceType` and the
number of photos from each ad's latest stored record, then prints by source and by photo
count: the share of ads, the share placed in the lowest and highest tenth, and for the
lowest tenth the later cuts, raises and days on the market.

Run from the repo root with PYTHONPATH=frontier/src: python docs/notes/first-page-read-2026-11-18/source.py
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from rentfrontier import drift_deals

W = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
REC = "/data1/apartments/pipeline/datasets/records-0d20eb92b9f08c7d.parquet"
J = next(
    Path("/data1/apartments/frontier/runs").glob(
        "drift-building-bedtext-layout-range-b0-market-*-range-j"
    )
)
CACHE = Path("/data1/apartments/tmp/first-page-read-2026-11-18/source-j.parquet")


def sources(ids, path=REC):
    """The source type and photo count of each ad's latest record."""
    want = {int(x) for x in ids}
    rec = pq.ParquetFile(path)
    parts = []
    for g in range(rec.metadata.num_row_groups):
        got = rec.read_row_group(g, columns=["listing_id"]).column(0).to_numpy()
        if not want.intersection(got.tolist()):
            continue
        part = rec.read_row_group(
            g, columns=["listing_id", "collected_at", "raw_listing_json"]
        ).to_pandas()
        part = part[part.listing_id.isin(want)]
        j = part.raw_listing_json.map(json.loads)
        part["source"] = j.map(
            lambda v: (v.get("listingSource") or {}).get("sourceType")
        )
        part["photos"] = j.map(
            lambda v: len((v.get("media") or {}).get("photos") or [])
        )
        parts.append(part.drop(columns="raw_listing_json"))
    out = pd.concat(parts).sort_values("collected_at").groupby("listing_id").tail(1)
    return out.assign(listing_id=out.listing_id.astype(str)).set_index("listing_id")


if __name__ == "__main__":
    t = drift_deals.deals(J, ADS)
    lid, p, ok, days, change = place.places(J, ADS)
    ids = pd.Index([str(x) for x in lid])
    c = t.assign(listing_id=t.listing_id.astype(str)).set_index("listing_id").cautions
    plain = ~c.reindex(ids).map(
        lambda v: bool(v) if isinstance(v, (list, tuple, np.ndarray)) else False
    ).to_numpy(bool)
    if not CACHE.exists():
        sources(ids[ok]).to_parquet(CACHE)
    s = pd.read_parquet(CACHE).reindex(ids)
    base = ok & plain
    print(
        "open uncautioned backtest ads",
        base.sum(),
        "with a record",
        (base & s.source.notna().to_numpy()).sum(),
    )
    bins = pd.cut(s.photos, [-1, 3, 6, 10, 15, 25, 1000]).astype(str)
    for name, key in (("source", s.source.fillna("none")), ("photos", bins)):
        print(name)
        for v in sorted(key[base].unique()):
            m = base & (key == v).to_numpy()
            k = m & (p < 0.1)
            print(
                f"  {v:14s} ads {m.sum():6d} ({100 * m.sum() / base.sum():5.1f}%) "
                f"lowest tenth {100 * k.sum() / m.sum():5.1f}% highest tenth "
                f"{100 * (m & (p > 0.9)).sum() / m.sum():5.1f}% median place {np.median(p[m]):.3f} | "
                f"lowest tenth: cut {100 * (change[k] < -0.001).mean():5.1f}% "
                f"raised {100 * (change[k] > 0.001).mean():5.1f}% median days {np.median(days[k]) if k.any() else float('nan'):.0f} | "
                f"all: median days {np.median(days[m]):.0f}"
            )
