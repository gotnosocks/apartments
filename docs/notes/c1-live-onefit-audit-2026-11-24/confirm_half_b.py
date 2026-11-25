"""Unbiased Half-B confirmation & Student-t ELPD sizing of A1 + TODO candidate traits on `c1-live-of`."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import t as student_t

SEED = 20261124
OUT_DIR = Path(__file__).resolve().parent


def half_of_building(bld: str) -> str:
    h = hashlib.blake2b(f"{SEED}:{bld}".encode(), digest_size=8).digest()
    return "A" if (int.from_bytes(h, "little") & 1) == 0 else "B"


def main() -> None:
    ads = pd.read_parquet("/data1/apartments/site/diagnostics/ads.parquet")
    ads = ads[ads["source"] != "market"].copy()
    ads["half"] = ads["building"].astype(str).map(half_of_building)

    df_t = 4.0
    q90 = student_t.ppf(0.90, df_t)
    scale = (
        np.log(ads["model_hi80"].to_numpy(float))
        - np.log(ads["model_lo80"].to_numpy(float))
    ) / (2.0 * q90)
    resid = ads["gap"].to_numpy(float)
    valid = np.isfinite(scale) & (scale > 1e-4) & np.isfinite(resid)
    ads = ads[valid].reset_index(drop=True)
    scale = scale[valid]
    resid = resid[valid]
    is_a = (ads["half"] == "A").to_numpy()
    is_b = (ads["half"] == "B").to_numpy()
    bld_b = ads.loc[is_b, "building"].astype(str).to_numpy()

    day_dt = pd.to_datetime(ads["day"])
    prev_dt = pd.to_datetime(ads["prev_day"], errors="coerce")
    gap_days = (day_dt - prev_dt).dt.days.fillna(-1).to_numpy(float)
    sqft = ads["model_sqft"].fillna(1000.0).to_numpy(float)

    candidates = {
        "floor_unknown": ads["floor"].isna().to_numpy(float),
        "sparse_photos_le1": (ads["photos"].fillna(0) <= 1).to_numpy(float),
        "townhouse_units_le4": (ads["lot_units"].fillna(999) <= 4).to_numpy(float),
        "tenure_coop": (ads["tenure"] == "coop").to_numpy(float),
        "tenure_condo": (ads["tenure"] == "condo").to_numpy(float),
        "changed_bed": (
            ads["prev_bedrooms"].notna() & (ads["bedrooms"] != ads["prev_bedrooms"])
        ).to_numpy(float),
        "penthouse": (ads["penthouse"] == True).to_numpy(float),  # noqa: E712
        "u1_log_sqft_gt1k": np.maximum(0.0, np.log(np.maximum(sqft, 100.0) / 1000.0)),
        "top3_pred": (
            ads["model_median"] >= ads["model_median"].quantile(0.97)
        ).to_numpy(float),
        "floor_1": (ads["floor"] == 1).to_numpy(float),
        "baths_3p": (ads["full_baths"].fillna(0) >= 3).to_numpy(float),
        "gap_le_180d": ((gap_days >= 0) & (gap_days <= 180)).astype(float),
        "gap_gt_2yr": (gap_days > 730).astype(float),
        "months_free_gt0": (ads["months_free"].fillna(0) > 0).to_numpy(float),
        "walkup_high_f4p": (
            (ads["floor"].fillna(0) >= 4) & (ads["building_elevator"] == False)  # noqa: E712
        ).to_numpy(float),
        "low_fl_retail": (
            (ads["floor"].fillna(99) <= 2) & (ads["retail"] == True)  # noqa: E712
        ).to_numpy(float),
        "bld_thin_le5": (ads["building_ads"].fillna(0) <= 5).to_numpy(float),
        "bed_4p": (ads["bedrooms"].fillna(0) >= 4).to_numpy(float),
    }

    def ll(r, s, a, b, x):
        s2 = s * np.exp(a * x)
        return student_t.logpdf((r - b * x) / s2, df_t) - np.log(s2)

    base_ll_b = ll(resid[is_b], scale[is_b], 0.0, 0.0, np.zeros(is_b.sum()))
    print(
        f"Cross-fitted on Half A (n={is_a.sum():,}), scored on UNTOUCHED Half B (n={is_b.sum():,}), scaled x2:"
    )
    print(
        f"{'Candidate':22s} | {'Prev%':>6s} | {'Scale(A)':>8s} | {'Shift(A)':>8s} | {'Half-B dELPD':>12s} | {'Full Est +- SE':>18s} | {'z':>6s}"
    )
    print("-" * 98)
    rows = []
    for name, x in candidates.items():
        xa, xb = x[is_a], x[is_b]
        ra, rb = resid[is_a], resid[is_b]
        sa, sb = scale[is_a], scale[is_b]
        opt = minimize(
            lambda p: -ll(ra, sa, p[0], p[1], xa).sum(), [0.0, 0.0], method="BFGS"
        )
        a_hat, b_hat = float(opt.x[0]), float(opt.x[1])
        diff = ll(rb, sb, a_hat, b_hat, xb) - base_ll_b
        gsum = pd.Series(diff).groupby(bld_b).sum().to_numpy()
        d_b = float(diff.sum())
        se_b = float(np.sqrt(len(gsum) * np.var(gsum, ddof=1)))
        z = d_b / se_b if se_b > 0 else 0.0
        prev = float((x > 0).mean()) * 100.0
        rows.append(
            {
                "name": name,
                "prevalence_pct": prev,
                "scale_A": float(np.exp(a_hat)),
                "shift_A": b_hat,
                "half_b_delpd": d_b,
                "full_est_delpd": d_b * 2.0,
                "full_est_se": se_b * 2.0,
                "z": z,
            }
        )

    rows.sort(key=lambda r: -r["full_est_delpd"])
    for r in rows:
        print(
            f"{r['name']:22s} | {r['prevalence_pct']:5.1f}% | {r['scale_A']:7.3f}x | {r['shift_A']:+8.4f} | {r['half_b_delpd']:+12.1f} | {r['full_est_delpd']:+8.1f} +- {r['full_est_se']:5.1f} | {r['z']:+6.2f}"
        )
    (OUT_DIR / "half_b_confirmation.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
