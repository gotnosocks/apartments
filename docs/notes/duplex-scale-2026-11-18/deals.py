"""Free check: duplex and penthouse ads in the Deals table and in its backtest.

Joins the text marks `duplex` and `penthouse` to the Deals model's backtest (`range-j`) and
market run (`range-m`). For the backtest it prints, for marked and unmarked open ads with
no caution, the share placed in the lowest tenth and those ads' later cuts, raises and
days on the market. For the market run it prints the marked share of the first 50, 100
and 200 uncautioned ads and of the whole table.

Run from the repo root with PYTHONPATH=frontier/src: python docs/notes/duplex-scale-2026-11-18/deals.py
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from rentfrontier import b0duplex, b0penthouse, drift_deals

W = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
R = Path("/data1/apartments/frontier/runs")
J = next(R.glob("drift-building-bedtext-layout-range-b0-market-*-range-j"))
M = next(R.glob("drift-building-bedtext-layout-range-b0-market-*-range-m"))
TEXTS = "/data1/apartments/tmp/overhaul/texts-m6.parquet"
ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)

if __name__ == "__main__":
    fr = pd.read_parquet(ROWS, columns=["listing_id", "duplex", "penthouse"])
    fr["listing_id"] = fr.listing_id.astype(str)
    fr = fr.drop_duplicates("listing_id").set_index("listing_id")
    marked = fr.duplex.fillna(False) | fr.penthouse.fillna(False)

    t = drift_deals.deals(J, ADS)
    lid, p, ok, days, change = place.places(J, ADS)
    ids = pd.Index([str(x) for x in lid])
    mark = marked.reindex(ids).to_numpy()
    known = ~pd.isna(mark)
    mark = np.where(known, mark, False).astype(bool)
    c = t.assign(listing_id=t.listing_id.astype(str)).set_index("listing_id").cautions
    plain = ~c.reindex(ids).map(
        lambda v: bool(v) if isinstance(v, (list, tuple, np.ndarray)) else False
    ).to_numpy(bool)
    print(
        "backtest open ads", ok.sum(), "found in the duplex dataset", (ok & known).sum()
    )
    for name, m in {"marked": mark, "unmarked": ~mark & known}.items():
        base = ok & plain & m
        k = base & (p < 0.1)
        hi = base & (p > 0.9)
        print(
            f"  {name:9s} uncautioned ads {base.sum():5d} lowest tenth {k.sum():4d} "
            f"({100 * k.sum() / base.sum():.1f}%) highest tenth {100 * hi.sum() / base.sum():.1f}% | "
            f"lowest tenth: cut {100 * (change[k] < -0.001).mean():.1f}% "
            f"raised {100 * (change[k] > 0.001).mean():.1f}% median days {np.median(days[k]):.0f} | "
            f"all: cut {100 * (change[base] < -0.001).mean():.1f}% "
            f"raised {100 * (change[base] > 0.001).mean():.1f}% median days {np.median(days[base]):.0f}"
        )

    # The same split for narrower marks: the duplex mark by the ad's floor, and penthouses.
    a = pd.read_parquet(ADS, columns=["listing_id", "physical_floor", "label_floor"])
    a["listing_id"] = a.listing_id.astype(str)
    a = a.drop_duplicates("listing_id").set_index("listing_id")
    floor = a.physical_floor.fillna(a.label_floor).reindex(ids).to_numpy(float)
    dup = fr.duplex.fillna(False).reindex(ids).fillna(False).to_numpy(bool)
    pent = fr.penthouse.fillna(False).reindex(ids).fillna(False).to_numpy(bool)
    narrow = {
        "duplex, floor 1": dup & (floor <= 1),
        "duplex, floor 2+": dup & (floor > 1),
        "duplex, floor unknown": dup & np.isnan(floor),
        "penthouse, no duplex": pent & ~dup,
        "floor 1, unmarked": ~mark & known & (floor <= 1),
    }
    for name, m in narrow.items():
        base = ok & plain & m
        k = base & (p < 0.1)
        print(
            f"  {name:22s} uncautioned ads {base.sum():5d} lowest tenth {k.sum():4d} "
            f"({100 * k.sum() / max(base.sum(), 1):.1f}%) highest tenth "
            f"{100 * (base & (p > 0.9)).sum() / max(base.sum(), 1):.1f}% | lowest tenth: "
            f"cut {(change[k] < -0.001).sum()} raised {(change[k] > 0.001).sum()} "
            f"median days {np.median(days[k]) if k.any() else float('nan'):.0f}"
        )

    # The market ads are marked from their own descriptions, since the duplex dataset
    # predates many of them.
    tx = pd.read_parquet(TEXTS)
    tx["listing_id"] = tx.listing_id.astype(str)
    col = next(c for c in tx.columns if c != "listing_id")
    texts = tx[col].fillna("").astype(str).tolist()
    tx["mark"] = b0duplex.marks(texts)[1] | b0penthouse.marks(texts)[1]
    m = drift_deals.deals(M, ADS)
    m = m[~m.cautions.map(bool)].reset_index(drop=True)
    mk = tx.set_index("listing_id").mark.reindex(m.listing_id.astype(str))
    print("market uncautioned ads", len(m), "with a description", mk.notna().sum())
    mk = mk.fillna(False).to_numpy(bool)
    for n in (50, 100, 200, len(m) // 10):
        print(f"  first {n}: marked {mk[:n].sum()} ({100 * mk[:n].mean():.1f}%)")
    print(f"  all: marked {100 * mk.mean():.1f}%")
    print(f"  last {len(m) // 10}: marked {100 * mk[-(len(m) // 10) :].mean():.1f}%")
