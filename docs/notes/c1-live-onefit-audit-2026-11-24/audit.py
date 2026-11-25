"""Post-gate audit & blind expert-read batch builder for `c1-live-of` (2026-11-24).

Splits held-out buildings deterministically 50/50 (seed 20261124) into:
  - Half A (discovery / blind broker reads)
  - Half B (held-back unbiased confirmation)

Outputs:
  - Full quantitative calibration & worst-miss breakdown on Half A (and Half B confirmation)
  - Live `/deals` top-100 comparison vs `range-m4` backup
  - Three blind JSONL batches (rents/CDFs stripped) + separate answer keys for expert readers:
      1. `batch_closed_low.jsonl`: 25 closed Half-A `cdf < 0.01` + 25 controls (`0.25 <= cdf <= 0.75`)
      2. `batch_closed_high.jsonl`: 20 closed Half-A `cdf > 0.99` + 20 controls
      3. `batch_deals_top.jsonl`: 25 live uncautioned top deals + 25 mid-table controls
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
ADS_PATH = Path("/data1/apartments/site/diagnostics/ads.parquet")
DEALS_PATH = Path("/data1/apartments/site/deals/deals.json")
OLD_DEALS_PATH = Path(
    "/data1/apartments/tmp/site-backup-before-c1-onefit-20261123/deals/deals.json"
)
RUN_DIR = Path(
    "/data1/apartments/frontier/runs/drift-building-phase-unitkn-ablate-b0-onefit-00bc8849-c1-live-of"
)
RECORDS_PATH = Path(
    "/data1/apartments/pipeline/datasets/records-c16a4dc45e496b75.parquet"
)
TEXTS_PATH = Path(
    "/data1/apartments/tmp/deals-refresh/"
    "drift-building-phase-unitkn-ablate-b0-onefit-00bc8849-c1-live-of/texts.parquet"
)
CATALOG_PATH = Path("/data1/apartments/pipeline/datasets/catalog.ndjson")
SEED = 20261124


def half_of_building(bld: str) -> str:
    h = hashlib.blake2b(f"{SEED}:{bld}".encode(), digest_size=8).digest()
    return "A" if (int.from_bytes(h, "little") & 1) == 0 else "B"


def summarize_group(df: pd.DataFrame, col: str, min_n: int = 50) -> list[dict]:
    rows = []
    for k, g in df.groupby(col, observed=True, dropna=False):
        n = len(g)
        if n < min_n:
            continue
        gap = g["gap"].to_numpy(float)
        pit = g["pit"].to_numpy(float)
        rows.append(
            {
                "group": str(k),
                "n": int(n),
                "bias": float(np.median(gap)),
                "mean_gap": float(np.mean(gap)),
                "mae": float(np.median(np.abs(gap))),
                "cov80": float(((pit >= 0.10) & (pit <= 0.90)).mean()),
                "low1": float((pit < 0.01).mean()),
                "low5": float((pit < 0.05).mean()),
                "high1": float((pit > 0.99).mean()),
                "high5": float((pit > 0.95).mean()),
                "sd_z": float(np.std(g["z"].to_numpy(float))),
            }
        )
    return rows


def find_latest_records_path() -> Path:
    lines = [l for l in CATALOG_PATH.read_text().splitlines() if l.strip()]
    for line in reversed(lines):
        j = json.loads(line)
        if j.get("rows", {}).get("path") == "rows-b157a29e19aa837a.parquet":
            return CATALOG_PATH.parent / j["records"]["path"]
    return CATALOG_PATH.parent / json.loads(lines[-1])["records"]["path"]


def load_descriptions(listing_ids: set[str]) -> dict[str, dict]:
    rec_path = find_latest_records_path()
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='2GB'; SET threads=2;")
    id_df = pd.DataFrame({"listing_id": sorted(listing_ids)})
    con.register("wanted_ids", id_df)
    rows = con.execute(
        f"""
        SELECT CAST(r.listing_id AS VARCHAR) AS lid, r.raw_listing_json
        FROM read_parquet('{rec_path}') r
        SEMI JOIN wanted_ids w ON CAST(r.listing_id AS VARCHAR) = w.listing_id
        """
    ).fetchall()
    con.close()
    out: dict[str, dict] = {}
    for lid, raw in rows:
        if lid in out or not raw:
            continue
        try:
            j = json.loads(raw)
        except Exception:
            continue
        out[lid] = {
            "description": (j.get("description") or "").strip()[:1400],
            "title": j.get("title") or "",
            "leaseTerm": j.get("leaseTerm"),
            "monthsFree": j.get("monthsFree"),
            "amenities": (j.get("amenities") or [])[:20],
            "buildingAmenities": (j.get("buildingAmenities") or [])[:20],
            "exposure": j.get("exposure"),
            "furnished": j.get("furnished"),
            "noFee": j.get("noFee"),
        }
    return out


def make_blind_batch(
    pos_df: pd.DataFrame,
    ctrl_df: pd.DataFrame,
    desc_map: dict[str, dict],
    seed: int,
    stem: str,
) -> None:
    rng = np.random.default_rng(seed)
    combined = pd.concat(
        [pos_df.assign(_label="miss"), ctrl_df.assign(_label="control")],
        ignore_index=True,
    )
    order = rng.permutation(len(combined))
    combined = combined.iloc[order].reset_index(drop=True)

    blind_lines = []
    key_lines = []
    for idx, r in combined.iterrows():
        lid = str(r["listing_id"])
        meta = desc_map.get(lid, {})
        blind_item = {
            "item_id": f"{stem}_{idx:02d}",
            "neighbourhood": r.get("neighbourhood"),
            "building": r.get("building"),
            "address": r.get("address"),
            "unit": r.get("unit"),
            "day": str(r.get("day"))[:10],
            "bedrooms": r.get("bedrooms"),
            "full_baths": r.get("full_baths"),
            "half_baths": r.get("half_baths"),
            "square_feet": None
            if pd.isna(r.get("square_feet"))
            else float(r["square_feet"]),
            "model_sqft": None
            if pd.isna(r.get("model_sqft"))
            else float(r["model_sqft"]),
            "size_source": r.get("size_source"),
            "floor": None if pd.isna(r.get("floor")) else float(r["floor"]),
            "building_floors": None
            if pd.isna(r.get("building_floors"))
            else float(r["building_floors"]),
            "building_elevator": r.get("building_elevator"),
            "building_doorman": r.get("building_doorman"),
            "year_built": None
            if pd.isna(r.get("year_built"))
            else int(r["year_built"]),
            "building_class": r.get("building_class"),
            "lot_units": None if pd.isna(r.get("lot_units")) else float(r["lot_units"]),
            "months_free": None
            if pd.isna(r.get("months_free"))
            else float(r["months_free"]),
            "lease_term": r.get("lease_term") or meta.get("leaseTerm"),
            "unit_ads": None if pd.isna(r.get("unit_ads")) else int(r["unit_ads"]),
            "building_ads": None
            if pd.isna(r.get("building_ads"))
            else int(r["building_ads"]),
            "prev_bedrooms": None
            if pd.isna(r.get("prev_bedrooms"))
            else float(r["prev_bedrooms"]),
            "prev_day": None if pd.isna(r.get("prev_day")) else str(r["prev_day"])[:10],
            "source_type": r.get("source_type"),
            "lister_kind": r.get("lister_kind"),
            "photos": None if pd.isna(r.get("photos")) else int(r["photos"]),
            "floorplans": None
            if pd.isna(r.get("floorplans"))
            else int(r["floorplans"]),
            "private_outdoor": r.get("private_outdoor"),
            "washer_dryer": r.get("washer_dryer"),
            "dishwasher": r.get("dishwasher"),
            "central_ac": r.get("central_ac"),
            "penthouse": r.get("penthouse"),
            "top_floor": r.get("top_floor"),
            "flags": r.get("flags"),
            "cautions": r.get("cautions"),
            "description": meta.get("description", ""),
            "amenities": meta.get("amenities", []),
            "buildingAmenities": meta.get("buildingAmenities", []),
            "furnished": meta.get("furnished"),
            "noFee": meta.get("noFee"),
        }
        blind_lines.append(json.dumps(blind_item, default=str))
        key_lines.append(
            json.dumps(
                {
                    "item_id": f"{stem}_{idx:02d}",
                    "listing_id": lid,
                    "label": r["_label"],
                    "ask": None if pd.isna(r.get("ask")) else float(r["ask"]),
                    "model_median": None
                    if pd.isna(r.get("model_median"))
                    else float(r["model_median"]),
                    "gap": None if pd.isna(r.get("gap")) else float(r["gap"]),
                    "pit": None if pd.isna(r.get("pit")) else float(r["pit"]),
                    "z": None if pd.isna(r.get("z")) else float(r["z"]),
                    "below_share": None
                    if pd.isna(r.get("below_share"))
                    else float(r["below_share"]),
                    "discount_pct": None
                    if pd.isna(r.get("discount_pct"))
                    else float(r["discount_pct"]),
                    "prev_ask": None
                    if pd.isna(r.get("prev_ask"))
                    else float(r["prev_ask"]),
                },
                default=str,
            )
        )
    (OUT_DIR / f"{stem}_blind.jsonl").write_text("\n".join(blind_lines) + "\n")
    (OUT_DIR / f"{stem}_key.jsonl").write_text("\n".join(key_lines) + "\n")


def main() -> None:
    ads = pd.read_parquet(ADS_PATH)
    ads["half"] = ads["building"].astype(str).map(half_of_building)
    ads["year"] = pd.to_datetime(ads["day"]).dt.year
    ads["bed_bin"] = pd.cut(
        ads["bedrooms"].fillna(-1),
        [-2, -0.5, 0.5, 1.5, 2.5, 3.5, 20],
        labels=["unk", "0BR", "1BR", "2BR", "3BR", "4+BR"],
    )
    ads["bath_bin"] = pd.cut(
        ads["full_baths"].fillna(-1),
        [-2, 0.5, 1.5, 2.5, 20],
        labels=["0/unk", "1ba", "2ba", "3+ba"],
    )
    ads["floor_bin"] = np.where(
        ads["floor"].isna(),
        "unk",
        np.where(
            ads["floor"] <= 1,
            "F1",
            np.where(
                ads["floor"] <= 4, "F2-4", np.where(ads["floor"] <= 10, "F5-10", "F11+")
            ),
        ),
    )
    ads["size_bin"] = pd.cut(
        ads["model_sqft"].fillna(-1),
        [-2, 0, 500, 800, 1100, 1500, 100000],
        labels=["unk", "<500", "500-800", "800-1100", "1100-1500", "1500+"],
    )
    ads["bld_ads_bin"] = pd.cut(
        ads["building_ads"].fillna(0),
        [-1, 0, 5, 20, 100, 100000],
        labels=["0", "1-5", "6-20", "21-100", "100+"],
    )
    ads["unit_ads_bin"] = pd.cut(
        ads["unit_ads"].fillna(0),
        [-1, 0, 1, 3, 100000],
        labels=["0 (new)", "1", "2-3", "4+"],
    )
    # Gap in days since unit's previous ad
    day_dt = pd.to_datetime(ads["day"])
    prev_dt = pd.to_datetime(ads["prev_day"], errors="coerce")
    gap_days = (day_dt - prev_dt).dt.days
    ads["gap_days_bin"] = pd.cut(
        gap_days.fillna(-1),
        [-2, -0.5, 90, 180, 365, 730, 100000],
        labels=["none", "<=90d", "91-180d", "181-365d", "1-2yr", "2+yr"],
    )
    ads["changed_bed"] = ads["prev_bedrooms"].notna() & (
        ads["bedrooms"] != ads["prev_bedrooms"]
    )
    ads["top3_pred"] = ads["model_median"] >= ads["model_median"].quantile(0.97)
    ads["top10_pred"] = ads["model_median"] >= ads["model_median"].quantile(0.90)
    ads["has_free"] = ads["months_free"].fillna(0) > 0
    ads["has_cut"] = ads["n_cuts"].fillna(0) > 0
    ads["has_raise"] = ads["n_raises"].fillna(0) > 0
    ads["long_dom"] = ads["days_listed"].fillna(0) >= 60

    closed = ads[ads["source"] != "market"].copy()
    mkt = ads[ads["source"] == "market"].copy()
    closed_a = closed[closed["half"] == "A"]
    closed_b = closed[closed["half"] == "B"]
    closed_2022_a = closed_a[closed_a["year"] >= 2022]
    closed_2022_b = closed_b[closed_b["year"] >= 2022]

    print(
        f"Total ads: {len(ads):,} (closed: {len(closed):,} [A={len(closed_a):,}, B={len(closed_b):,}], market: {len(mkt):,})"
    )

    dims = [
        "year",
        "bed_bin",
        "bath_bin",
        "floor_bin",
        "size_bin",
        "size_source",
        "bld_ads_bin",
        "unit_ads_bin",
        "gap_days_bin",
        "changed_bed",
        "top3_pred",
        "top10_pred",
        "has_free",
        "has_cut",
        "has_raise",
        "long_dom",
        "building_elevator",
        "building_doorman",
        "tenure",
        "source_type",
        "lister_kind",
        "private_outdoor",
        "penthouse",
        "top_floor",
    ]

    summary = {
        "counts": {"closed": len(closed), "market": len(mkt)},
        "closed_all_A": {},
        "closed_all_B": {},
        "closed_2022_A": {},
        "closed_2022_B": {},
        "market": {},
    }
    for col in dims:
        summary["closed_all_A"][col] = summarize_group(closed_a, col)
        summary["closed_all_B"][col] = summarize_group(closed_b, col)
        summary["closed_2022_A"][col] = summarize_group(closed_2022_a, col)
        summary["closed_2022_B"][col] = summarize_group(closed_2022_b, col)
        summary["market"][col] = summarize_group(mkt, col, min_n=30)

    # Worst-miss excess summary: print groups where low1 > 0.015 or high1 > 0.015 or cov80 < 0.77 or |bias| > 0.012 on BOTH halves
    print(
        "\n=== SYSTEMATIC ANOMALIES ON CLOSED HELD-OUT (ALL YEARS, CONFIRMED ON HALF A & HALF B) ==="
    )
    for col in dims:
        a_map = {r["group"]: r for r in summary["closed_all_A"][col]}
        b_map = {r["group"]: r for r in summary["closed_all_B"][col]}
        for g in a_map:
            if g not in b_map:
                continue
            ra, rb = a_map[g], b_map[g]
            if (
                (ra["cov80"] < 0.775 and rb["cov80"] < 0.775)
                or (ra["low1"] > 0.014 and rb["low1"] > 0.014)
                or (ra["high1"] > 0.014 and rb["high1"] > 0.014)
                or (
                    abs(ra["bias"]) > 0.012
                    and abs(rb["bias"]) > 0.012
                    and np.sign(ra["bias"]) == np.sign(rb["bias"])
                )
            ):
                print(
                    f"  {col}={g:14s} | A(n={ra['n']:5d}): bias={ra['bias']:+.4f} cov80={ra['cov80']:.3f} low1={ra['low1']:.3%} hi1={ra['high1']:.3%}"
                    f" | B(n={rb['n']:5d}): bias={rb['bias']:+.4f} cov80={rb['cov80']:.3f} low1={rb['low1']:.3%} hi1={rb['high1']:.3%}"
                )

    print(
        "\n=== SYSTEMATIC ANOMALIES ON CLOSED 2022+ (CONFIRMED ON HALF A & HALF B) ==="
    )
    for col in dims:
        a_map = {r["group"]: r for r in summary["closed_2022_A"][col]}
        b_map = {r["group"]: r for r in summary["closed_2022_B"][col]}
        for g in a_map:
            if g not in b_map:
                continue
            ra, rb = a_map[g], b_map[g]
            if (
                (ra["cov80"] < 0.775 and rb["cov80"] < 0.775)
                or (ra["low1"] > 0.014 and rb["low1"] > 0.014)
                or (ra["high1"] > 0.014 and rb["high1"] > 0.014)
                or (
                    abs(ra["bias"]) > 0.012
                    and abs(rb["bias"]) > 0.012
                    and np.sign(ra["bias"]) == np.sign(rb["bias"])
                )
            ):
                print(
                    f"  {col}={g:14s} | A(n={ra['n']:5d}): bias={ra['bias']:+.4f} cov80={ra['cov80']:.3f} low1={ra['low1']:.3%} hi1={ra['high1']:.3%}"
                    f" | B(n={rb['n']:5d}): bias={rb['bias']:+.4f} cov80={rb['cov80']:.3f} low1={rb['low1']:.3%} hi1={rb['high1']:.3%}"
                )

    print("\n=== MARKET OPEN ADS (n=6,200) BY KEY DIMS ===")
    for col in (
        "bed_bin",
        "bath_bin",
        "floor_bin",
        "size_bin",
        "unit_ads_bin",
        "bld_ads_bin",
        "top3_pred",
    ):
        print(f"  [{col}]")
        for r in summary["market"][col]:
            print(
                f"    {r['group']:14s} n={r['n']:4d} bias={r['bias']:+.4f} mae={r['mae']:.4f} cov80={r['cov80']:.3f} low5={r['low5']:.2%} hi5={r['high5']:.2%}"
            )

    # Compare live /deals vs backup range-m4
    deals = pd.DataFrame(json.loads(DEALS_PATH.read_text()))
    old_deals = pd.DataFrame(json.loads(OLD_DEALS_PATH.read_text()))
    deals["cautioned"] = deals["cautions"].map(
        lambda c: len(c) > 0 if isinstance(c, list) else False
    )
    old_deals["cautioned"] = old_deals["cautions"].map(
        lambda c: len(c) > 0 if isinstance(c, list) else False
    )
    deals["cautious_saving"] = (deals["model_lo80"] - deals["ask"]) / deals[
        "model_lo80"
    ]
    old_deals["cautious_saving"] = (
        old_deals["model_lo80"] - old_deals["ask"]
    ) / old_deals["model_lo80"]

    # Sort uncautioned default order (cautious saving desc, matching deals.py default pop where unit_ads>0 or bld_ads>=5)
    mkt_meta = mkt[
        [
            "listing_id",
            "building_ads",
            "basis",
            "floor",
            "model_sqft",
            "size_source",
            "building_floors",
            "building_elevator",
            "building_doorman",
            "year_built",
            "building_class",
            "lot_units",
            "lease_term",
            "prev_bedrooms",
            "source_type",
            "lister_kind",
            "photos",
            "floorplans",
            "private_outdoor",
            "washer_dryer",
            "dishwasher",
            "central_ac",
            "penthouse",
            "top_floor",
            "flags",
            "gap",
            "pit",
            "z",
        ]
    ].copy()
    mkt_meta["listing_id"] = mkt_meta["listing_id"].astype(str)
    deals["listing_id"] = deals["listing_id"].astype(str)
    old_deals["listing_id"] = old_deals["listing_id"].astype(str)
    deals = deals.merge(mkt_meta, on="listing_id", how="left")

    def default_top(df: pd.DataFrame) -> pd.DataFrame:
        ok = ~df["cautioned"]
        if "building_ads" in df.columns:
            ok = ok & (
                (df["unit_ads"].fillna(0) > 0) | (df["building_ads"].fillna(0) >= 5)
            )
        return (
            df[ok]
            .sort_values("cautious_saving", ascending=False)
            .reset_index(drop=True)
        )

    new_top = default_top(deals)
    old_unc = (
        old_deals[~old_deals["cautioned"]]
        .sort_values("cautious_saving", ascending=False)
        .reset_index(drop=True)
    )
    top100_new_ids = set(new_top.head(100)["listing_id"])
    top100_old_ids = set(old_unc.head(100)["listing_id"])
    entered = new_top.head(100)[~new_top.head(100)["listing_id"].isin(top100_old_ids)]
    print(f"\n=== LIVE /DEALS TOP-100 UNCAUTIONED ===")
    print(
        f"Default uncautioned pool: {len(new_top)} ads; overlap with range-m4 top-100: {len(top100_new_ids & top100_old_ids)}/100; newly entered: {len(entered)}"
    )
    print(
        "Top-100 by bedrooms:",
        new_top.head(100)["bedrooms"].value_counts().sort_index().to_dict(),
    )
    print(
        "Top-100 by unit_ads==0:",
        int((new_top.head(100)["unit_ads"].fillna(0) == 0).sum()),
        "of 100",
    )
    print(
        "Top-100 by floor==1:", int((new_top.head(100)["floor"] == 1).sum()), "of 100"
    )
    print(
        "Top-100 by months_free>0:",
        int((new_top.head(100)["months_free"].fillna(0) > 0).sum()),
        "of 100",
    )
    print(
        "Top-100 by basis:",
        new_top.head(100)["basis"].value_counts(dropna=False).to_dict(),
    )

    # Build the 3 blind batches for expert reading
    rng = np.random.default_rng(SEED)
    # 1. Closed Half-A 2022+ worst low misses (cdf < 0.01) vs controls (0.25..0.75)
    c22a = closed_2022_a.copy()
    low_pool = c22a[c22a["pit"] < 0.01]
    high_pool = c22a[c22a["pit"] > 0.99]
    ctrl_pool = c22a[(c22a["pit"] >= 0.25) & (c22a["pit"] <= 0.75)]
    low_sample = low_pool.sample(n=min(25, len(low_pool)), random_state=SEED)
    ctrl_low = ctrl_pool.sample(n=25, random_state=SEED + 1)
    high_sample = high_pool.sample(n=min(20, len(high_pool)), random_state=SEED + 2)
    ctrl_high = ctrl_pool.sample(n=20, random_state=SEED + 3)

    # 2. Live /deals top-25 uncautioned vs mid-table controls (below_share in 0.35..0.65)
    deals_top25 = new_top.head(25).copy()
    deals_mid = new_top[
        (new_top["below_share"] >= 0.35) & (new_top["below_share"] <= 0.65)
    ].sample(n=25, random_state=SEED + 4)

    all_ids = (
        set(low_sample["listing_id"].astype(str))
        | set(ctrl_low["listing_id"].astype(str))
        | set(high_sample["listing_id"].astype(str))
        | set(ctrl_high["listing_id"].astype(str))
        | set(deals_top25["listing_id"].astype(str))
        | set(deals_mid["listing_id"].astype(str))
    )
    desc_map = load_descriptions(all_ids)
    print(f"\nLoaded raw descriptions for {len(desc_map)}/{len(all_ids)} sampled ads")

    make_blind_batch(low_sample, ctrl_low, desc_map, SEED + 10, "batch_closed_low")
    make_blind_batch(high_sample, ctrl_high, desc_map, SEED + 20, "batch_closed_high")
    make_blind_batch(deals_top25, deals_mid, desc_map, SEED + 30, "batch_deals_top")

    (OUT_DIR / "audit_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Wrote audit_summary.json and 3 blind batches to {OUT_DIR}")


if __name__ == "__main__":
    main()
