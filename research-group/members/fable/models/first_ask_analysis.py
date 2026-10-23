"""Frozen post-fit analysis of the first-ask floor fit (first_ask_analysis.md), on the common
held-out rows with a first ask, from the per-draw exports in first_ask_draws/{base,firstask}.

    python first_ask_analysis.py

Each export holds, per row and per thinned draw s (the same 200 draws in both), the model's mean
log rent at the first-ask date (mu_first) and at the base last-ask date (mu_last), and the log
response the run was fitted to (y). From them:

1. d = log latest ask (base y) - log first ask (first-ask y), and e_s = log first ask -
   mu_first_s. Both are demeaned within price_at year-month cells, then each draw gets an OLS
   slope with a building-clustered (CR1) sandwich variance. The slope's posterior is a working
   model-plus-sampling uncertainty calculation: for each draw I sample MIX_PER_DRAW values of
   slope_s + N(0, var_s), seeded, and pool them. The across-draw spread of slope_s comes beside
   it. Samples:
   - primary: drops ads with |d| > 0.5 and base latest_day at most 3 days after price_at;
   - no exclusion; changed ads only (d != 0, within the primary sample);
   - drift-adjusted: d_adj_s = d - (mu_last_s - mu_first_s), with the first-ask run's means;
   - secondary: e_s from the base run's mu_first.
2. Lagged past-only peer IV. The instrument is reaction_iv_lagged.py's z_l, built the same way:
   other units' walk-adjusted first-ask deviations from their previous ad, first asks 90 to 455
   days before the ad's own, last move before it, at least 5 peers. The regressor is the model
   residual e_s in place of dev_u, the outcome is d, and the sample is the primary sample.
3. P(cut) = P(d < 0) by decile of the posterior-mean first-ask residual (first-ask run).
4. Held-out coverage per run, on its own response at its own date, by simulating Student-t noise
   with each draw's nu and sigma of the row's noise group (b0.design's group, bedrooms capped
   at 3), PER_DRAW times a draw, seeded per block as b0.predictive_block seeds.
5. A seeded sample of SAMPLE_N rows with the two log asks and each run's predictive median and
   80% bounds, written to first_ask_analysis_sample.csv.
"""

from __future__ import annotations

import glob
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
EXPORT = HERE / "first_ask_draws"
OUT = HERE / "first_ask_analysis_results.json"
SAMPLE_OUT = HERE / "first_ask_analysis_sample.csv"
RUNS = Path("/data1/apartments/frontier/runs")
BASE_ROWS = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc/rows.parquet"
)
OBS = "/data1/apartments/frontier/cache/observations-aecf9b7724d3208a-v2.parquet"
SEED = 20261023
MIX_PER_DRAW = 100
PER_DRAW = 10
BLOCK = 5000
SAMPLE_N = 2000
QS = np.array([0.025, 0.05, 0.1, 0.5, 0.9, 0.95, 0.975])


def load_export(tag: str):
    m = json.loads((EXPORT / tag / "manifest.json").read_text())
    parts = [np.load(f) for f in sorted(glob.glob(str(EXPORT / tag / "chunk_*.npz")))]
    out = {k: np.concatenate([p[k] for p in parts], axis=-1) for k in ("row", "y")}
    for k in ("mu_first", "mu_last"):
        out[k] = np.concatenate([p[k] for p in parts], axis=1)
    return m, out


def demean(v: np.ndarray, cell: np.ndarray, n: int) -> np.ndarray:
    """v (rows,) or (draws, rows) minus its mean within each cell."""
    cnt = np.bincount(cell, minlength=n)
    if v.ndim == 1:
        return v - (np.bincount(cell, v, n) / np.maximum(cnt, 1))[cell]
    out = np.empty_like(v)
    for s in range(len(v)):
        out[s] = v[s] - (np.bincount(cell, v[s], n) / np.maximum(cnt, 1))[cell]
    return out


def codes(v) -> tuple[np.ndarray, int]:
    c, u = pd.factorize(pd.Series(v))
    return c.astype(np.int64), len(u)


def cluster_slope(y, x, z, cl, ncl):
    """Per-draw slope sum(z y) / sum(z x) with CR1 building-clustered variance; z = x gives
    OLS. y, x and z are demeaned, each (rows,) or (draws, rows)."""
    y2, x2, z2 = np.atleast_2d(y), np.atleast_2d(x), np.atleast_2d(z)
    S = max(len(y2), len(x2), len(z2))
    b, v = np.empty(S), np.empty(S)
    G = len(np.unique(cl))
    for s in range(S):
        ys, xs, zs = y2[s % len(y2)], x2[s % len(x2)], z2[s % len(z2)]
        q = zs @ xs
        b[s] = (zs @ ys) / q
        u = ys - b[s] * xs
        g = np.bincount(cl, zs * u, ncl)
        v[s] = G / (G - 1) * (g @ g) / q**2
    return b, v


def mixture(b, v, rng) -> dict:
    sims = (b[:, None] + rng.standard_normal((len(b), MIX_PER_DRAW)) * np.sqrt(v)[:, None]).ravel()
    q = lambda a: [float(t) for t in np.quantile(a, [0.05, 0.5, 0.95])]  # noqa: E731
    return {
        "median": q(sims)[1],
        "q05_q95": [q(sims)[0], q(sims)[2]],
        "across_draw_median": float(np.median(b)),
        "across_draw_q05_q95": [q(b)[0], q(b)[2]],
        "mean_sampling_se": float(np.sqrt(v.mean())),
    }


def regress(d, e, mask, ym, cl, rng, z=None):
    """Year-month demeaned slope of d on e over `mask`, per draw, with its mixture. With z,
    the IV slope and the first stage."""
    cells, nc = codes(ym[mask])
    bcl, nb = codes(cl[mask])
    dd = demean(d[..., mask] if d.ndim == 2 else d[mask], cells, nc)
    ee = demean(e[:, mask], cells, nc)
    out = {"rows": int(mask.sum()), "buildings": nb}
    if z is None:
        b, v = cluster_slope(dd, ee, ee, bcl, nb)
        return out | mixture(b, v, rng), b
    zz = demean(z[mask], cells, nc)
    b, v = cluster_slope(dd, ee, zz, bcl, nb)
    f1, v1 = cluster_slope(ee, zz, zz, bcl, nb)
    F = f1**2 / v1
    em = demean(e[:, mask].mean(0), cells, nc)
    bm, vm = cluster_slope(dd, em, zz, bcl, nb)
    fm, vfm = cluster_slope(em, zz, zz, bcl, nb)
    bo, _ = cluster_slope(dd, ee, ee, bcl, nb)
    return out | mixture(b, v, rng) | {
        "first_stage_F_median_across_draws": float(np.median(F)),
        "first_stage_F_range": [float(F.min()), float(F.max())],
        "first_stage_coef_median": float(np.median(f1)),
        "posterior_mean_residual_iv": {
            "slope": float(bm[0]),
            "se": float(np.sqrt(vm[0])),
            "first_stage_F": float(fm[0] ** 2 / vfm[0]),
        },
        "ols_same_rows_median": float(np.median(bo)),
    }, b


def lagged_instrument(rows: pd.DataFrame) -> np.ndarray:
    """reaction_iv_lagged.py's lagged past-only peer instrument z_l for each of `rows`
    (listing_id, building, unit_id, d0), NaN without 5 peers. Tables j, u and t are that
    script's, unchanged; the instrument is joined to these rows in place of t's own."""
    z = np.load(RUNS / "building-zones-floor-b0-latest-6b5a5b4a-dense-w1000/posterior.npz")
    L = np.median(z["kept/L"].reshape(-1, z["kept/L"].shape[-1]), axis=0)
    walk = pd.DataFrame({"week": np.arange(len(L)), "L": L})
    c = duckdb.connect()
    c.sql("SET memory_limit='1500MB'; SET threads=2")
    c.register("walk", walk)
    c.register("h", rows)
    c.sql(f"""create temp table j as
      select r.listing_id, r.building, r.unit_id, r.bedrooms, r.rent_stabilized,
             r.price_at::date d0, r.latest_day d1, r.latest_ask, o.asking_rent first_ask,
             ln(r.latest_ask / o.asking_rent) dy, date_diff('day', r.price_at::date, r.latest_day) dlast,
             ln(o.asking_rent) - wa.L lf_adj, ln(r.latest_ask) - wb.L ll_adj
      from read_parquet('{BASE_ROWS}') r
      join (select source_listing_id, asking_rent from read_parquet('{OBS}')) o
        on r.listing_id = o.source_listing_id
      join walk wa on wa.week = greatest(0, least({len(L) - 1}, date_diff('day', date '2013-12-02', r.price_at::date) // 7))
      join walk wb on wb.week = greatest(0, least({len(L) - 1}, date_diff('day', date '2013-12-02', r.latest_day) // 7))
      where o.asking_rent > 0""")
    c.sql("""create temp table u as
      select a.*, a.lf_adj - b.ll_adj dev_u, date_diff('day', b.d1, a.d0) gap
      from j a join j b on a.unit_id = b.unit_id and b.d0 < a.d0 and a.bedrooms = b.bedrooms
      qualify row_number() over (partition by a.listing_id order by b.d0 desc) = 1""")
    c.sql("create temp table t as select * from u where gap between 0 and 1095 and not (dlast <= 3 and abs(dy) > 0.005)")
    zl = c.sql("""select a.listing_id, avg(b.dev_u) z_l, count(*) n_l
      from h a join t b on a.building = b.building and a.unit_id <> b.unit_id
        and b.d0 >= a.d0 - interval 455 days and b.d0 <= a.d0 - interval 90 days and b.d1 < a.d0
      group by a.listing_id having count(*) >= 5""").df()
    c.close()
    return rows.listing_id.map(zl.set_index("listing_id").z_l).to_numpy(float)


def predictive(y, mu, group, nu, sigma, seed):
    """Coverage of y by the 80/90/95% predictive intervals, each row's predictive quantiles
    QS, and the pooled predictive residual's q10 and q90 around the posterior-mean mu."""
    n = len(y)
    qv = np.empty((n, len(QS)))
    pooled = []
    rng0 = np.random.default_rng(seed)
    for lo in range(0, n, BLOCK):
        hi = min(lo + BLOCK, n)
        rng = np.random.default_rng([seed, lo])
        m = mu[:, lo:hi].astype(float)
        sims = rng.standard_t(np.broadcast_to(nu[None, :, None], (PER_DRAW, *m.shape)))
        sims *= sigma[:, group[lo:hi]][None]
        sims += m[None]
        sims = sims.reshape(-1, hi - lo)
        qv[lo:hi] = np.quantile(sims, QS, axis=0).T
        r = sims - m.mean(0)[None]
        pooled.append(r[rng0.integers(0, len(r), (20, hi - lo)), np.arange(hi - lo)[None, :]].ravel())
    pooled = np.concatenate(pooled)
    cov = {
        "80": float(((y >= qv[:, 2]) & (y <= qv[:, 4])).mean()),
        "90": float(((y >= qv[:, 1]) & (y <= qv[:, 5])).mean()),
        "95": float(((y >= qv[:, 0]) & (y <= qv[:, 6])).mean()),
    }
    p10, p90 = np.quantile(pooled, [0.1, 0.9])
    return cov, qv, {
        "pooled_predictive_residual_q10": float(p10),
        "pooled_predictive_residual_q90": float(p90),
        "pooled_q90_minus_q10": float(p90 - p10),
        "mean_row_interval_q90_minus_q10": float((qv[:, 4] - qv[:, 2]).mean()),
    }


def main():
    t0 = time.perf_counter()
    rng = np.random.default_rng(SEED)
    mb, base = load_export("base")
    mf, fa = load_export("firstask")
    assert np.array_equal(base["row"], fa["row"])
    assert mb["draw_indices"] == mf["draw_indices"]
    rowsel = base["row"]
    frame = pd.read_parquet(
        BASE_ROWS,
        columns=["listing_id", "building", "unit_id", "price_at", "latest_day",
                 "latest_ask", "bedrooms"],
    ).iloc[rowsel].reset_index(drop=True)
    d0 = pd.to_datetime(frame.price_at, utc=True).dt.tz_localize(None).dt.normalize()
    d1 = pd.to_datetime(frame.latest_day)
    ym = (d0.dt.year * 100 + d0.dt.month).to_numpy()
    cl = frame.building.astype(str).to_numpy()
    y_first, y_last = fa["y"], base["y"]
    assert np.allclose(y_last, np.log(frame.latest_ask.to_numpy()))
    d = y_last - y_first
    days = (d1 - d0).dt.days.to_numpy()
    typo = (np.abs(d) > 0.5) & (days <= 3)
    primary = ~typo
    res = {
        "label": "working model-plus-sampling uncertainty calculation: per-draw OLS/IV slopes "
        "with building-clustered CR1 variance, mixed over the 200 draws",
        "rows": int(len(d)),
        "draws": len(mb["draw_indices"]),
        "mix_per_draw": MIX_PER_DRAW,
        "seed": SEED,
        "primary_dropped_typo": int(typo.sum()),
        "primary_dropped_share": float(typo.mean()),
        "changed_ads_in_primary": int((primary & (d != 0)).sum()),
    }

    # 1. Reaction slopes.
    yf32 = y_first.astype(np.float32)[None, :]
    e_fa = yf32 - fa["mu_first"]
    e_base = yf32 - base["mu_first"]
    slopes = {}
    slopes["primary"], b_primary = regress(d, e_fa, primary, ym, cl, rng)
    slopes["no_exclusion"], _ = regress(d, e_fa, np.ones_like(primary), ym, cl, rng)
    slopes["changed_only"], _ = regress(d, e_fa, primary & (d != 0), ym, cl, rng)
    d_adj = d.astype(np.float32)[None, :] - (fa["mu_last"] - fa["mu_first"])
    slopes["drift_adjusted"], b_adj = regress(d_adj, e_fa, primary, ym, cl, rng)
    diff = b_adj - b_primary
    slopes["drift_adjusted"]["minus_raw_median"] = float(np.median(diff))
    slopes["drift_adjusted"]["minus_raw_q05_q95"] = [float(v) for v in np.quantile(diff, [0.05, 0.95])]
    slopes["primary_base_run_residual"], _ = regress(d, e_base, primary, ym, cl, rng)
    del e_base, d_adj
    res["slopes"] = slopes
    print("slopes", json.dumps(slopes, indent=1), flush=True)

    # 2. Lagged peer IV.
    z = lagged_instrument(
        pd.DataFrame({
            "listing_id": frame.listing_id,
            "building": frame.building,
            "unit_id": frame.unit_id,
            "d0": d0.dt.date,
        })
    )
    has = primary & ~np.isnan(z)
    res["iv"], _ = regress(d, e_fa, has, ym, cl, rng, z=np.nan_to_num(z))
    res["iv"]["changes_from_reaction_iv_lagged"] = (
        "regressor is the first-ask run's model residual e_s (per draw) in place of dev_u; "
        "outcome is d from the base and first-ask datasets; sample is the primary sample of "
        "common held-out first-ask ads with z_l (the instrument rows need not be in that "
        "script's table t); z_l itself is built exactly as there, from peers in t"
    )
    print("iv", json.dumps(res["iv"], indent=1), flush=True)

    # 3. P(cut) by decile of the posterior-mean first-ask residual.
    em = e_fa.mean(0)
    pc = {}
    for label, m in (("primary", primary), ("no_exclusion", np.ones_like(primary))):
        dec = pd.qcut(em[m], 10, labels=False)
        cut = d[m] < 0
        pc[label] = {
            "by_decile": [float(cut[dec == k].mean()) for k in range(10)],
            "bottom": float(cut[dec == 0].mean()),
            "top": float(cut[dec == 9].mean()),
        }
    res["p_cut"] = pc
    del e_fa

    # 4. Coverage and the predictive spread, each run on its own response at its own date.
    beds = np.clip(np.round(frame.bedrooms.to_numpy(float)), 0, None)
    group = np.minimum(beds, 3).astype(np.int32)  # as b0.design
    cover, quant = {}, {}
    for tag, m, ex, own in (("base", mb, base, "mu_last"), ("firstask", mf, fa, "mu_first")):
        with np.load(RUNS / m["run"] / "posterior.npz") as zz:
            idx = np.asarray(m["draw_indices"])
            nu = zz["kept/nu"].reshape(-1)[idx].astype(float)
            sigma = zz["kept/sigma"].reshape(-1, 4)[idx].astype(float)
        cov, qv, spread = predictive(ex["y"], ex[own], group, nu, sigma, SEED)
        r = ex["y"] - ex[own].mean(0)
        q10, q90 = np.quantile(r, [0.1, 0.9])
        cover[tag] = {"coverage": cov, "observed_residual_q10_q90": [float(q10), float(q90)],
                      "observed_q90_minus_q10": float(q90 - q10)} | spread
        quant[tag] = qv
    res["coverage"] = cover
    res["ratios_new_over_base"] = {
        "observed_q90_minus_q10": cover["firstask"]["observed_q90_minus_q10"]
        / cover["base"]["observed_q90_minus_q10"],
        "pooled_predictive_q90_minus_q10": cover["firstask"]["pooled_q90_minus_q10"]
        / cover["base"]["pooled_q90_minus_q10"],
    }
    print("coverage", json.dumps(cover, indent=1), flush=True)

    # 5. The sample of rows.
    pick = np.sort(np.random.default_rng(SEED).choice(len(d), SAMPLE_N, replace=False))
    pd.DataFrame({
        "log_first_ask": y_first[pick],
        "log_latest_ask": y_last[pick],
        "base_pred_median_last_date": quant["base"][pick, 3],
        "base_pred_q10_last_date": quant["base"][pick, 2],
        "base_pred_q90_last_date": quant["base"][pick, 4],
        "firstask_pred_median_first_date": quant["firstask"][pick, 3],
        "firstask_pred_q10_first_date": quant["firstask"][pick, 2],
        "firstask_pred_q90_first_date": quant["firstask"][pick, 4],
    }).to_csv(SAMPLE_OUT, index=False)
    res["sample_file"] = str(SAMPLE_OUT)
    res["seconds"] = time.perf_counter() - t0
    OUT.write_text(json.dumps(res, indent=1))
    print("wrote", OUT, f"{res['seconds']:.0f}s")


if __name__ == "__main__":
    main()
