"""Memory-safe kept-quantity R-hat & far-thin building report for `c1-live-of`.

Avoids loading `kept/pred_loc` and `kept/bld` simultaneously or recomputing full
score_run quadrature (reads cached `pred_scores.npz` and site `buildings.parquet`).
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_kept_report as dkr
from rentfrontier import run as run_module

RUN_DIR = Path(
    "/data1/apartments/frontier/runs/drift-building-phase-unitkn-ablate-b0-onefit-00bc8849-c1-live-of"
)
BLDS_PATH = Path("/data1/apartments/site/diagnostics/buildings.parquet")
DS_ROWS = Path(
    "/data1/apartments/frontier/datasets/b0-b157a29e19aa837a-alldata-dense-nyc-market-bedtext/rows.parquet"
)
OUT_PATH = Path(__file__).resolve().parent / "kept_report_c1_live_of.json"


def chunked_rhat(arr: np.ndarray, chunk: int = 8192) -> np.ndarray:
    """Compute split R-hat along axis 2 in small chunks to cap peak RAM."""
    n = arr.shape[2]
    out = np.empty(n, dtype=np.float64)
    for i in range(0, n, chunk):
        j = min(i + chunk, n)
        out[i:j] = run_module.building_diagnostics(arr[:, :, i:j])["rhat"]
    return out


def main() -> None:
    scores = np.load(RUN_DIR / "pred_scores.npz")
    cdf = np.asarray(scores["cdf"], float)
    del scores

    with np.load(RUN_DIR / "posterior.npz") as z:
        held = np.asarray(z["heldout"], bool)
        kept_shape = list(z["kept/pred_loc"].shape[:2])
        loc_rhat = chunked_rhat(z["kept/pred_loc"])
    gc.collect()

    frame = pd.read_parquet(DS_ROWS, columns=["listing_id", "building"])
    held_lids = frame["listing_id"].to_numpy()[held].astype(str)
    ads_df = dkr.ads_over(held_lids, dkr.places(cdf), cdf, loc_rhat)
    del loc_rhat, cdf, held_lids
    gc.collect()

    with np.load(RUN_DIR / "posterior.npz") as z:
        bld_rhat = chunked_rhat(z["kept/bld"])
    gc.collect()

    blds = pd.read_parquet(BLDS_PATH)
    # Match order of buildings in posterior (`drift_diagnostics.levels` sorts unique buildings)
    uniq_blds = pd.Index(np.unique(frame["building"].astype(str).to_numpy()))
    assert len(uniq_blds) == len(bld_rhat), (
        f"building count mismatch: {len(uniq_blds)} vs {len(bld_rhat)}"
    )
    b_map = blds.set_index(blds["building"].astype(str))
    levels = pd.DataFrame(
        {
            "zone": b_map["zone"].reindex(uniq_blds).fillna("unknown").to_numpy(),
            "level": b_map["level"].reindex(uniq_blds).fillna(0.0).to_numpy(float),
        },
        index=uniq_blds,
    )
    tr_cnt = (
        frame.loc[~held, "building"]
        .astype(str)
        .value_counts()
        .reindex(uniq_blds)
        .fillna(0)
        .to_numpy(int)
    )
    ho_cnt = (
        frame.loc[held, "building"]
        .astype(str)
        .value_counts()
        .reindex(uniq_blds)
        .fillna(0)
        .to_numpy(int)
    )
    listed = dkr.buildings_listed(levels, bld_rhat, tr_cnt, ho_cnt)
    high = (levels.level.to_numpy() > dkr.FAR_LEVEL) & (ho_cnt > 0)
    with_ads = listed.scored_ads > 0

    out = {
        "run": RUN_DIR.name,
        "bounds": {
            "rhat": dkr.RHAT,
            "far_level": dkr.FAR_LEVEL,
            "few_ads": dkr.FEW_ADS,
        },
        "kept_draws": kept_shape,
        "counts": {
            "scored_ads": int(held.sum()),
            "ads_rhat_over": len(ads_df),
            "buildings": len(levels),
            "buildings_rhat_over": int(listed.rhat_over.sum()),
            "buildings_rhat_over_with_scored_ads": int(
                (listed.rhat_over & with_ads).sum()
            ),
            "buildings_far_thin": int(listed.far_thin.sum()),
            "buildings_far_thin_with_scored_ads": int(
                (listed.far_thin & with_ads).sum()
            ),
            "scored_ads_in_far_thin_buildings": int(
                listed.scored_ads[listed.far_thin].sum()
            ),
            "buildings_level_over_far_with_scored_ads": int(high.sum()),
            "scored_ads_in_buildings_level_over_far": int(ho_cnt[high].sum()),
        },
        "ads_top20": json.loads(ads_df.head(20).to_json(orient="records")),
        "buildings_top30": json.loads(listed.head(30).to_json(orient="records")),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["counts"], indent=2))
    if len(ads_df):
        print("\nTop 10 ads with pred_loc R-hat > 1.05:")
        print(ads_df.head(10).to_string(index=False))
    if len(listed):
        print("\nTop 15 listed buildings (rhat > 1.05 or |level| > 0.5 & train < 10):")
        print(listed.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
