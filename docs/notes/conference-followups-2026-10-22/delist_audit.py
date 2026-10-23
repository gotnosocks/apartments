"""First ask against last ask: steps 2 and 3 of docs/notes/delist-audit-predictions-2026-10-23.md.

    python delist_audit.py [OUT_DIR]

OUT_DIR defaults to /data1/apartments/tmp/conference-followups/delist. I write results.json
there, and tables.md with the same numbers as short markdown tables. The relist counts of
step 1 and the relist and fast-delist reruns of step 4 belong to Fable's analysis, so this
script leaves them out and keeps only the share of units with a single listing.

Sources:

- First ask: `asking_rent` from the observations cache, kept where positive, deduplicated on
  source_listing_id and joined on listing_id, as in Fable's first_ask_dataset.py. It is dated
  by the row's own `price_at`.
- Last ask: the model row's `latest_ask`, dated by its `latest_day`.
- Days on market: off_day minus on_day from the pipeline's ads file for the b3ddebf build.
  Ads with no off_day are still up, and I leave them out of step 2.
- Cuts and raises: listing-outcomes (latest snapshot, Manhattan crawls only), without its
  still-listed rows.
- Floor, laundry and doorman: the pipeline rows; dishwasher: the unit-features snapshot.

Step 2 runs twice: on the model rows with an outcomes history (its first and final ask, its
cut count), and on every model row with an observed first ask (the ratio only, no cut count).

Step 3 fits within-building OLS on log first ask and log last ask for the same rows. The
sample is the model rows with both asks, a last-to-first ratio between 0.5 and 2, and no
furnished, short-term or shared-space flag. Each target's design has:

- fixed effects for building, the calendar month of that target's own date, and full baths,
  absorbed by alternating projections. Bedroom steps (bed>=1 .. bed>=5, as in b0) can't be
  estimated beside bedroom-by-bath fixed effects, so I fit them with bath fixed effects and
  check the other coefficients in a second fit with bedroom-by-bath fixed effects;
- floor: physical_floor, else listed_floor, capped at 40, with an indicator where neither is
  known (floor set to 0 there);
- in-unit laundry, dishwasher, doorman full-time, part-time and virtual against everything
  else, and rent_stabilized.

Standard errors are two-way clustered by building and by the ISO week of each target's own
date (Cameron, Gelbach and Miller). For the difference between targets I treat the two fits
as one stacked regression: a week cluster collects the first-ask rows posted that week and
the last-ask rows dated that week, so the interval accounts for the correlation between fits.
A third fit repeats step 3 on the Manhattan outcomes rows with the outcomes first and final
asks, as a check on the first-ask source.
"""

import glob
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

T0 = time.time()
OUT = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/data1/apartments/tmp/conference-followups/delist"
)
OUTCOMES = sorted(
    glob.glob("/data1/apartments/external/listing-outcomes/*/listing-outcomes.parquet")
)[-1]
ROWS = "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
OBS = "/data1/apartments/frontier/cache/observations-aecf9b7724d3208a-v2.parquet"
MODEL = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
UNIT_FEATURES = sorted(
    glob.glob("/data1/apartments/external/unit-features/*/unit_features.parquet")
)[-1]
FLOOR_CAP = 40
BED_STEPS = (1, 2, 3, 4, 5)

out = {
    "inputs": dict(
        outcomes=OUTCOMES,
        rows=ROWS,
        ads=ADS,
        observations=OBS,
        model=MODEL,
        unit_features=UNIT_FEATURES,
    )
}

# ---- Model rows with both asks and their attributes --------------------------------------
m = pd.read_parquet(
    MODEL,
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "latest_ask",
        "latest_day",
        "bedrooms",
        "full_baths",
        "rent_stabilized",
        "furnished",
        "short_term",
        "shared_space",
    ],
)
obs = pd.read_parquet(OBS, columns=["source_listing_id", "asking_rent"])
obs = obs[obs.asking_rent > 0].drop_duplicates("source_listing_id")
m["obs_first"] = m.listing_id.map(obs.set_index("source_listing_id").asking_rent)
del obs
rows = pd.read_parquet(
    ROWS,
    columns=[
        "listing_id",
        "unit_id",
        "laundry_type",
        "doorman_type",
        "physical_floor",
        "listed_floor",
    ],
)
assert rows.listing_id.is_unique
per_unit = rows.groupby("unit_id").size()
out["units"] = dict(
    pipeline_listings=int(len(rows)),
    units=int(len(per_unit)),
    share_units_single_listing=round(float((per_unit == 1).mean()), 4),
)
m = m.merge(rows.drop(columns="unit_id"), on="listing_id", how="left")
del rows
ads = pd.read_parquet(ADS, columns=["listing_id", "on_day", "off_day"])
ads["days"] = (pd.to_datetime(ads.off_day) - pd.to_datetime(ads.on_day)).dt.days
m["days"] = m.listing_id.map(ads.set_index("listing_id").days)
del ads
oc = pd.read_parquet(
    OUTCOMES,
    columns=[
        "listing_id",
        "first_ask",
        "final_ask",
        "n_cuts",
        "n_raises",
        "still_listed",
    ],
)
m = m.merge(oc, on="listing_id", how="left")
del oc
uf = pd.read_parquet(UNIT_FEATURES, columns=["listing_id", "dishwasher"])
m["dishwasher"] = m.listing_id.map(uf.set_index("listing_id").dishwasher)
del uf
m["first_day"] = pd.to_datetime(m.price_at).dt.tz_localize(None).dt.normalize()
m["last_day"] = pd.to_datetime(m.latest_day)
done = m.final_ask.notna() & ~m.still_listed.fillna(False).astype(bool)
out["coverage"] = dict(
    model_rows=int(len(m)),
    with_observed_first_ask=int(m.obs_first.notna().sum()),
    with_outcomes_history=int(m.final_ask.notna().sum()),
    with_finished_outcomes_history=int(done.sum()),
    with_ads_days_on_market=int(m.days.notna().sum()),
    dishwasher_matched=int(m.dishwasher.notna().sum()),
    observed_first_equals_outcomes_first=round(
        float(np.isclose(m.obs_first[done], m.first_ask[done]).mean()), 4
    ),
    latest_ask_equals_outcomes_final=round(
        float(np.isclose(m.latest_ask[done], m.final_ask[done]).mean()), 4
    ),
)
print(json.dumps(out["coverage"]), f"{time.time() - T0:.0f}s", flush=True)

# ---- Step 2: ask paths -------------------------------------------------------------------
BINS = ([-0.5, 13.5, 30.5, 60.5, 1e9], ["<14", "14-30", "31-60", ">60"])


def paths(f, cuts):
    d = dict(
        n=int(len(f)),
        median_ratio=round(float(f.ratio.median()), 4),
        mean_log_ratio_pct=round(100 * float(np.log(f.ratio).mean()), 3),
        share_ratio_eq_1=round(float(np.isclose(f.ratio, 1).mean()), 4),
        share_final_below_first=round(float((f.ratio < 1 - 1e-9).mean()), 4),
    )
    if cuts:
        c = f[f.n_cuts > 0]
        d |= dict(
            share_any_cut=round(float((f.n_cuts > 0).mean()), 4),
            share_any_raise=round(float((f.n_raises > 0).mean()), 4),
            median_cut_pct_among_cut=round(100 * float(1 - c.ratio.median()), 2),
        )
    return d


def step2(f, cuts):
    f = f.assign(bin=pd.cut(f.days, BINS[0], labels=BINS[1]))
    return {
        "all": paths(f, cuts),
        "days_on_market_missing": int(f.days.isna().sum()),
        **{str(k): paths(g, cuts) for k, g in f.groupby("bin", observed=True)},
    }


s2 = m[done & m.first_ask.gt(0) & m.final_ask.gt(0)]
s2 = s2.assign(ratio=s2.final_ask / s2.first_ask)
wide = m[m.obs_first.notna() & m.latest_ask.gt(0) & m.days.notna()]
wide = wide.assign(ratio=wide.latest_ask / wide.obs_first)
out["step2"] = {
    "outcomes_rows": step2(s2, True),
    "observed_first_vs_latest_ask_ended_ads": step2(wide, False),
}
del s2, wide

# ---- Step 3: within-building OLS on both targets -----------------------------------------
flags = m[["furnished", "short_term", "shared_space"]].fillna(False).any(axis=1)
fl = m.physical_floor.where(m.physical_floor.notna(), m.listed_floor)
beds = np.clip(np.round(m.bedrooms.to_numpy(float)), 0, None)
dm = m.doorman_type.fillna("")
X = {f"bed>={k}": (beds >= k).astype(float) for k in BED_STEPS}
X |= {
    "floor": np.minimum(np.clip(fl.fillna(0).to_numpy(float), 0, None), FLOOR_CAP),
    "floor_unknown": fl.isna().to_numpy(float),
    "in_unit_laundry": (m.laundry_type == "in_unit").to_numpy(float),
    "dishwasher": m.dishwasher.fillna(0).to_numpy(float),
    "doorman_full": (dm == "full_time").to_numpy(float),
    "doorman_part": (dm == "part_time").to_numpy(float),
    "doorman_virtual": (dm == "virtual").to_numpy(float),
    "rent_stabilized": m.rent_stabilized.fillna(False).to_numpy(float),
}
NAMES = list(X)
REPORT = [n for n in NAMES if n != "floor_unknown"]
Xm = np.column_stack([X[n] for n in NAMES])
del X


def code(s):
    return pd.factorize(s)[0]


def week(day):
    iso = day.dt.isocalendar()
    return code(iso.year.astype(str) + "-" + iso.week.astype(str))


baths = m.full_baths.fillna(-1).astype(int).astype(str)
codes = {
    "building": code(m.building),
    "bath": code(baths),
    "bedbath": code(pd.Series(beds.astype(int).astype(str)) + "x" + baths.to_numpy()),
}
dating = {
    "first": dict(month=code(m.first_day.dt.to_period("M")), week=week(m.first_day)),
    "last": dict(month=code(m.last_day.dt.to_period("M")), week=week(m.last_day)),
}


def demean(M, groups, tol=1e-8, itmax=1000):
    """Residualize the columns of M on the fixed effects in `groups` by alternating
    projections, sweeping out each factor's group means in turn until the largest change
    falls below tol."""
    M = M - M.mean(axis=0)
    counts = [np.bincount(g) for g in groups]
    for it in range(itmax):
        change = 0.0
        for g, n in zip(groups, counts, strict=True):
            for j in range(M.shape[1]):
                mean = np.bincount(g, M[:, j]) / n
                change = max(change, float(np.abs(mean).max()))
                M[:, j] -= mean[g]
        if change < tol:
            return M, it + 1
    raise RuntimeError("alternating projections did not converge")


def fit(mask, y_first, y_last, fe):
    """Both targets over `mask`, with building, own-date month and `fe` fixed effects, and the
    two-way clustered covariance of the stacked coefficients. Buildings with one row in the
    sample are dropped first, since a building effect fits them exactly."""
    b = codes["building"][mask]
    mask = mask.copy()
    mask[np.flatnonzero(mask)[np.bincount(b)[b] == 1]] = False
    cb = code(codes["building"][mask])
    fits, its = {}, {}
    for t, y in (("first", y_first[mask]), ("last", y_last[mask])):
        groups = [cb, code(dating[t]["month"][mask]), code(codes[fe][mask])]
        D, its[t] = demean(np.column_stack([Xm[mask], y]), groups)
        x, yy = D[:, :-1], D[:, -1]
        # A column the fixed effects absorb (the bedroom steps under bedroom-by-bath effects)
        # keeps only rounding noise after demeaning.
        raw = Xm[mask].std(axis=0)
        keep = x.std(axis=0) > 1e-6 * np.maximum(raw, 1e-12)
        if fe == "bedbath":
            keep &= np.array([not n.startswith("bed>=") for n in NAMES])
        x = x[:, keep]
        A = np.linalg.inv(x.T @ x)
        beta = A @ (x.T @ yy)
        fits[t] = dict(
            names=[n for n, k in zip(NAMES, keep, strict=True) if k],
            beta=beta,
            A=A,
            score=x * (yy - x @ beta)[:, None],
        )
    assert fits["first"]["names"] == fits["last"]["names"]
    names, k = fits["first"]["names"], len(fits["first"]["names"])
    w = {t: code(dating[t]["week"][mask]) for t in fits}
    nw = max(w["first"].max(), w["last"].max()) + 1
    # Cluster ids on a shared index space, so a cluster gathers scores from both targets.
    ids = {
        "building": {t: cb for t in fits},
        "week": w,
        "building_week": {t: cb.astype(np.int64) * nw + w[t] for t in fits},
    }
    Ab = np.zeros((2 * k, 2 * k))
    Ab[:k, :k], Ab[k:, k:] = fits["first"]["A"], fits["last"]["A"]
    V = {}
    for dim in ids:
        u, inv = np.unique(
            np.concatenate([ids[dim]["first"], ids[dim]["last"]]), return_inverse=True
        )
        G, n = len(u), int(mask.sum())
        S = np.zeros((G, 2 * k))
        np.add.at(S[:, :k], inv[:n], fits["first"]["score"])
        np.add.at(S[:, k:], inv[n:], fits["last"]["score"])
        V[dim] = Ab @ (G / (G - 1) * (S.T @ S)) @ Ab
    res = {}
    for i, nm in enumerate(names):
        b1, b2 = fits["first"]["beta"][i], fits["last"]["beta"][i]
        e1, e2 = np.zeros(2 * k), np.zeros(2 * k)
        e1[i], e2[k + i] = 1, 1
        s1, s2, sd = (se(V, c) for c in (e1, e2, e2 - e1))
        res[nm] = (b1, s1, b2, s2, b2 - b1, sd)
    return dict(
        n=int(mask.sum()),
        buildings=int(cb.max() + 1),
        iterations=its,
        coef=res,
    )


def se(V, c):
    """The two-way clustered standard error of c'beta. Where the two-way variance comes out
    negative, I fall back on the larger one-way variance (Cameron, Gelbach and Miller 2011)."""
    v = {d: float(c @ M @ c) for d, M in V.items()}
    two = v["building"] + v["week"] - v["building_week"]
    return float(np.sqrt(two if two > 0 else max(v["building"], v["week"])))


def pct(b, s):
    return [round(100 * float(np.expm1(v)), 2) for v in (b, b - 1.96 * s, b + 1.96 * s)]


def summarize(res):
    terms = {}
    for n in REPORT:
        if n not in res["coef"]:
            continue
        b1, s1, b2, s2, d, sd = res["coef"][n]
        f, l = pct(b1, s1), pct(b2, s2)
        terms[n] = dict(
            first_pct=f,
            last_pct=l,
            diff_pct_points=round(l[0] - f[0], 2),
            diff_log_points=[
                round(100 * float(v), 2) for v in (d, d - 1.96 * sd, d + 1.96 * sd)
            ],
            ratio=round(float(b2 / b1), 3) if abs(b1) > 1e-12 else None,
        )
    return dict(
        n=res["n"],
        buildings=res["buildings"],
        iterations=res["iterations"],
        terms=terms,
    )


base = ~flags.to_numpy() & m.bedrooms.notna().to_numpy()
ratio = (m.latest_ask / m.obs_first).to_numpy()
main = base & np.isfinite(ratio) & (ratio >= 0.5) & (ratio <= 2)
oc_ratio = (m.final_ask / m.first_ask).to_numpy()
manhattan = (
    base & done.to_numpy() & np.isfinite(oc_ratio) & (oc_ratio >= 0.5) & (oc_ratio <= 2)
)
log_obs, log_latest = np.log(m.obs_first.to_numpy()), np.log(m.latest_ask.to_numpy())
log_oc_first, log_oc_final = (
    np.log(m.first_ask.to_numpy()),
    np.log(m.final_ask.to_numpy()),
)
out["step3_sample"] = dict(
    model_rows_with_both_asks=int(np.isfinite(ratio).sum()),
    dropped_flagged=int((np.isfinite(ratio) & flags.to_numpy()).sum()),
    dropped_ratio_outside_half_to_double=int(
        (np.isfinite(ratio) & ~((ratio >= 0.5) & (ratio <= 2))).sum()
    ),
    kept=int(main.sum()),
)
del m
step3 = {}
for name, args in {
    "observed_first_vs_latest": (main, log_obs, log_latest, "bath"),
    "observed_first_vs_latest_bedbath_fe": (main, log_obs, log_latest, "bedbath"),
    "manhattan_outcomes_first_vs_final": (
        manhattan,
        log_oc_first,
        log_oc_final,
        "bath",
    ),
}.items():
    step3[name] = summarize(fit(*args))
    print(name, step3[name]["n"], f"{time.time() - T0:.0f}s", flush=True)
out["step3"] = step3
out["seconds"] = round(time.time() - T0, 1)

# ---- Write -------------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "results.json").write_text(json.dumps(out, indent=1, default=str))


def md(t):
    """A DataFrame as a markdown table (tabulate isn't in the venv)."""
    t = t.astype(str)
    head = "| | " + " | ".join(map(str, t.columns)) + " |"
    rule = "|" + "---|" * (len(t.columns) + 1)
    body = [
        "| " + str(i) + " | " + " | ".join(r) + " |"
        for i, r in zip(t.index, t.to_numpy(), strict=True)
    ]
    return "\n".join([head, rule, *body])


lines = ["# First ask against last ask", "", "## Coverage", ""]
lines += [md(pd.Series(out["coverage"]).to_frame("value")), ""]
for k, v in out["step2"].items():
    t = pd.DataFrame({b: s for b, s in v.items() if isinstance(s, dict)})
    lines += [f"## Step 2, {k}", "", md(t), ""]
for k, v in step3.items():
    t = pd.DataFrame(v["terms"]).T
    lines += [
        f"## Step 3, {k} (n={v['n']}, {v['buildings']} buildings)",
        "",
        "Premiums in percent as [estimate, 2.5%, 97.5%]; diff_log_points is last minus first.",
        "",
        md(t),
        "",
    ]
(OUT / "tables.md").write_text("\n".join(lines))
print(f"wrote {OUT}; {out['seconds']}s")
