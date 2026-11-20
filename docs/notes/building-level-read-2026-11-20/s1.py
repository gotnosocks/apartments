import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import pyarrow.parquet as pq
from rentfrontier import run as R, drift_score, drift_diagnostics

OUT = Path("/data1/apartments/tmp/po-bldmodes")
COLS = [
    "listing_id",
    "building",
    "unit_id",
    "neighbourhood",
    "latest_ask",
    "first_ask",
    "bedrooms",
    "full_baths",
    "half_baths",
    "latest_day",
    "first_day",
    "status",
    "shared_space",
    "income_restricted",
    "rent_stabilized",
    "bed_text",
]
allb = []
for tag, n in [("live", "6cd1f12b-range-m3"), ("back", "d9028c57-range-j")]:
    d = [p for p in R.RUNS.iterdir() if n in p.name and (p / "posterior.npz").exists()][
        0
    ]
    ds = drift_score.dataset_dir(d)
    rec = json.loads((d / "result.json").read_text())
    if tag == "live":
        print(
            pq.read_schema(
                json.loads((ds / "manifest.json").read_text())["build"]["ads"]["path"]
            ).names
        )
    z = np.load(d / "posterior.npz")
    print([(k, z[k].shape) for k in z.files if k.startswith("kept/")][:60])
    frame = pd.read_parquet(ds / "rows.parquet", columns=COLS)
    held = z["heldout"]
    names, why = drift_diagnostics.levels(d, rec, frame.building.astype(str).to_numpy())
    assert names is not None, why
    bld = z["kept/bld"].astype(float)
    diag = R.building_diagnostics(bld)
    cm = bld.mean(axis=1)  # chains x B
    names["rhat"] = diag["rhat"]
    names["ess"] = diag["ess"]
    names["c0"] = cm[0]
    names["c1"] = cm[1]
    names["c0sd"] = bld[0].std(axis=0)
    names["c1sd"] = bld[1].std(axis=0)
    b = frame.building.astype(str)
    names["n_train"] = (
        b[~held].value_counts().reindex(names.index).fillna(0).astype(int)
    )
    names["n_held"] = b[held].value_counts().reindex(names.index).fillna(0).astype(int)
    names["run"] = tag
    names.reset_index().to_parquet(OUT / f"levels_{tag}.parquet")
    frame["heldout"] = held
    sel = names[
        (names.rhat > 1.05) | ((names.level.abs() > 0.3) & (names.n_held > 0))
    ].index
    print(
        tag,
        "over1.05",
        (names.rhat > 1.05).sum(),
        "hi>.5 w held",
        ((names.level > 0.5) & (names.n_held > 0)).sum(),
        "ads",
        names.n_held[(names.level > 0.5)].sum(),
        "hi>.8 ads",
        names.n_held[names.level > 0.8].sum(),
        "lo<-.5 bld",
        ((names.level < -0.5) & (names.n_held > 0)).sum(),
        "ads",
        names.n_held[names.level < -0.5].sum(),
        "lo<-.8 ads",
        names.n_held[names.level < -0.8].sum(),
    )
    r = frame[b.isin(sel)].copy()
    r["run"] = tag
    r.to_parquet(OUT / f"rows_{tag}.parquet")
    # zone summary of levels and bld_sd
    print(names.groupby("zone")["level"].describe().round(3))
