"""Robustness of the as-of increment over C's own columns to suspect lot matches.

The new-building check (#723) flags rows in buildings with 101+ scored rows
whose lot has no residential units on record (1,088 rows, 5 buildings), which
are probably matched to the wrong tax lot. This script reruns the control step
of held_data_ceiling.py (WLS and LightGBM, no coordinates) three ways:

    all rows      as before
    excluded      the flagged rows dropped before folding and fitting
    PLUTO masked  the flagged rows kept, with their PLUTO columns (C's own and
                  the pluto family) and the stabilized share set to missing

For each it reports the increment of own + as-of over own alone on the
row-weighted board miss and on the building-weighted miss (each row weighs
1 / its building's rows, as in newbuilding.building_weighted), with 90%
lot-cluster bootstrap intervals.

    python held_data_ceiling_lotcheck.py PER_ROW_FILE

Writes lotcheck.json beside the other ceiling outputs.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import held_data_ceiling as hc  # noqa: E402
from rentfrontier import features  # noqa: E402


def wmedian(v, w):
    order = np.argsort(v)
    cw = np.cumsum(w[order])
    return v[order][np.searchsorted(cw, 0.5 * cw[-1])]


def main(per_row_file):
    _, frame, heldout = hc._load_frame()
    base = features.build(hc.BASE, frame, ~heldout)
    own_names = list(base.names)
    own = pd.DataFrame(base.values, columns=own_names, index=frame.audit_id)
    per = pd.read_parquet(per_row_file)
    per = per[per.rung == "new building"].reset_index(drop=True)
    flag = ((per.row_bin == "101+") & (per.unitsres == 0)).to_numpy()
    print(
        f"flagged rows {flag.sum()}, buildings {per.building[flag].nunique()}",
        flush=True,
    )
    table = pd.read_parquet(hc.OUT / "features.parquet").set_index("audit_id")
    fam = json.loads((hc.OUT / "families.json").read_text())
    asof = [c for c, f in fam.items() if f in hc.AS_OF]
    x_own_all = own.loc[per.audit_id].to_numpy(float)
    x_asof_all = table.loc[per.audit_id, asof].to_numpy(float)
    pluto = [c for c, f in fam.items() if f == "pluto"]
    own_mask = [own_names.index(c.split(":", 1)[1]) for c in pluto]
    asof_mask = [asof.index(c) for c in pluto + ["stabilized share"]]

    result = {"flagged_rows": int(flag.sum())}
    for variant in ("all rows", "excluded", "PLUTO masked"):
        keep = ~flag if variant == "excluded" else np.ones(len(per), bool)
        p = per[keep].reset_index(drop=True)
        x_own, x_asof = x_own_all[keep].copy(), x_asof_all[keep].copy()
        if variant == "PLUTO masked":
            x_own[np.ix_(flag, own_mask)] = np.nan
            x_asof[np.ix_(flag, asof_mask)] = np.nan
        y, med = p.y.to_numpy(), p["median"].to_numpy()
        r = y - med
        lots = p.bbl.where(p.bbl.notna() & (p.bbl != "")).to_numpy()
        folds, groups = hc.lot_folds(
            p.building.to_numpy(), lots, np.random.default_rng(hc.SEED)
        )
        _, b_idx, b_n = np.unique(p.building, return_inverse=True, return_counts=True)
        w_b = 1.0 / b_n[b_idx]
        zero = np.zeros(len(r))
        both = np.column_stack([x_own, x_asof])
        fits = {
            "wls": (
                hc.wls_oof(r, zero, x_own, folds),
                hc.wls_oof(r, zero, both, folds),
            ),
            "lightgbm": (
                hc.gbm_oof(r, zero, x_own, folds, groups),
                hc.gbm_oof(r, zero, both, folds, groups),
            ),
        }

        def row_miss(q, i):
            return 100 * np.median(np.abs(np.exp(med[i] + q[i] - y[i]) - 1))

        def bld_miss(q, i):
            return 100 * wmedian(np.abs(np.exp(med[i] + q[i] - y[i]) - 1), w_b[i])

        out = {
            "rows": int(len(r)),
            "board_miss_row": row_miss(zero, np.arange(len(r))),
            "board_miss_building": bld_miss(zero, np.arange(len(r))),
        }
        for model, (p_own, p_both) in fits.items():
            for weighting, miss in (("row", row_miss), ("building", bld_miss)):
                for label, a, b in (
                    ("own", p_own, zero),
                    ("increment", p_both, p_own),
                ):
                    d = hc.boot(
                        lambda i: miss(a, i) - miss(b, i),
                        groups,
                        np.random.default_rng(6),
                        200,
                    )
                    out[f"{label} / {model} / {weighting}"] = d
                    print(
                        f"{variant:13s} {label:9s} {model:8s} {weighting:8s} "
                        f"{d[0]:+.3f} pp [{d[1]:+.3f}, {d[2]:+.3f}]",
                        flush=True,
                    )
        result[variant] = out
    (hc.OUT / "lotcheck.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
