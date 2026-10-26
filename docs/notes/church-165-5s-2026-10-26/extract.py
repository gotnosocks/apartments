"""Term-by-term pricing of unit 5S at 165 Church Street from the served fit's saved draws.

    python extract.py draws OUT_DIR     read the draws for 5S and a typical row (~10 min, 3 GB)
    python extract.py json OUT_DIR RAW_JSON DATA_JSON

The served fit is the m7 all-scraped run (RUN below). Its summary bundle holds each row's
encoded columns (`inputs`) and the design's indexes (`design-parts.npz`), so I rebuild the
two rows' model arrays from those and skip the 6 GB design. I then read every kept draw of
the terms the two rows use, one block of draws at a time (`rentfrontier.draws.read`), and
split each draw's log rent into the named terms of `rentfrontier.explain.log_terms`.

The typical row is the in-fit Manhattan row of the same month with the median fitted rent.
Its terms sit beside 5S's so each term reads as a difference from typical.

Two predictive distributions come out of the `json` step:

1. in-sample: the fit's own unit level for 5S plus Student-t noise at the row's scale
2. new unit: a unit level drawn from the unit prior in place of 5S's own, as the site
   prices an apartment the fit never saw

The bundle's PSIS-LOO interval goes in beside them. As a check, the `draws` step compares
its mean fitted rent against the bundle's and stops on a mismatch.
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import draws, explain, model

RUN = (
    "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope"
    "-slopemin3-unitnu4-all-scraped-v1-rows-e694a775-a40"
)
RUN_DIR = Path("/data1/apartments/frontier/runs") / RUN
BUNDLE = Path("/data1/apartments/frontier/summaries") / f"{RUN}-6d3f401"
SITE = Path("/data1/apartments/site/current/site.sqlite")
FOCUS = "4a3dee9d212a3163d75a9523848fc3d6ee1babd06a8feffaeab55fd556b96e5e"
DATASET = Path(
    "/data1/apartments/frontier/datasets/all-scraped-analysis-20261016-5f07157"
)
CHAINS = 2
KEYS = (
    "alpha",
    "trend",
    "season",
    "season_daily_coef",
    "beta",
    "bedroom_time",
    "building",
    "walk",
    "bedroom_slope",
    "fslope",
    "unit",
    "sigma",
    "nu",
    "unit_scale",
    "unit_nu",
    "area_time_scale",
    "line_scale",
    "building_trend_scale",
    "unit_drift",
)
ROW_COLUMNS = [
    "audit_id",
    "unit_id",
    "building",
    "period",
    "asking_rent",
    "in_fit",
    "unit_fit_rows",
    "fitted_rent",
    "estimate_median",
    "estimate_pred_lower_80",
    "estimate_pred_upper_80",
    "estimate_pred_lower_95",
    "estimate_pred_upper_95",
    "pit",
    "inputs",
]


def bundle_rows(period):
    # a batch at a time: the whole file's inputs column alone overruns the 3 GB scope
    out = []
    source = pq.ParquetFile(BUNDLE / "rows.parquet")
    for batch in source.iter_batches(
        batch_size=50_000, columns=ROW_COLUMNS + usd_columns()
    ):
        frame = batch.to_pandas()
        out.append(frame[frame.period == period])
    return pd.concat(out, ignore_index=True)


def usd_columns():
    terms = json.loads((BUNDLE / "terms.json").read_text())
    return [f"{t['name']}_usd" for t in terms]


def typical_row(rows):
    """The in-fit Manhattan row of the month with the median fitted rent."""
    with sqlite3.connect(SITE) as db:
        bbl = dict(db.execute("select id, bbl from buildings").fetchall())
    manhattan = rows.building.map(bbl).fillna("").str.startswith("1")
    pool = rows[manhattan & rows.in_fit].sort_values("fitted_rent")
    return pool.iloc[(len(pool) - 1) // 2], len(pool)


def price_dates(audit_ids):
    """Each row's price date from the fit's dataset (the season reads it)."""
    want, found = set(audit_ids), {}
    with open(DATASET / "observations.jsonl") as fh:
        for line in fh:
            if any(a in line for a in want):
                obs = json.loads(line)
                if obs["audit_id"] in want:
                    found[obs["audit_id"]] = obs["price_at"]
    return [found[a] for a in audit_ids]


def arrays(rows, parts, post_units, names, offset):
    periods = pd.DatetimeIndex(parts["periods"])
    period = pd.DatetimeIndex(pd.to_datetime(rows.period))
    month = (
        (period.year - periods[0].year) * 12 + period.month - periods[0].month
    ).to_numpy()
    x = np.zeros((len(rows), len(names)))
    for i, raw in enumerate(rows.inputs):
        for k, v in json.loads(raw).items():
            x[i, names.index(k)] = v
    beds = rows.bedrooms.to_numpy()
    at = pd.to_datetime(rows.price_at, utc=True)
    seconds = (at.dt.hour * 3600 + at.dt.minute * 60 + at.dt.second).to_numpy()
    days = np.where(at.dt.is_leap_year, 366.0, 365.0)
    n = len(rows)
    return model.Arrays(
        y=np.log(rows.asking_rent.to_numpy()) - offset,
        x=x,
        month=month.astype(np.int32),
        calendar=(period.month.to_numpy() - 1).astype(np.int32),
        # the draws are read for these rows' buildings and units only, in this order
        building=np.arange(n, dtype=np.int32),
        unit=np.arange(n, dtype=np.int32),
        knot=(month // model.KNOT_MONTHS).astype(np.int32),
        knot_frac=(month % model.KNOT_MONTHS) / model.KNOT_MONTHS,
        bed_group=np.minimum(np.clip(np.round(beds), 0, 3), 3).astype(np.int32),
        beds_centered=np.clip(np.round(beds), 0, 4) - 1.0,
        unit_time=np.zeros(n),
        year_frac=(at.dt.dayofyear.to_numpy() - 1 + seconds / 86400) / days,
        year=(period.year - periods[0].year).to_numpy().astype(np.int32),
    )


def bedrooms_of(x, names):
    """Bedroom count from the bedroom dummies (1 when none is set)."""
    for col, beds in (
        ("bedrooms=0", 0),
        ("bedrooms=2", 2),
        ("bedrooms=3", 3),
        ("bedrooms=4", 4),
        ("bedrooms=5+", 5),
    ):
        if x[names.index(col)]:
            return beds
    return 1


def step_draws(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    result = json.loads((RUN_DIR / "result.json").read_text())
    config = model.MODELS[result["model"]["name"]]
    parts = np.load(BUNDLE / "design-parts.npz", allow_pickle=True)
    meta = json.loads(str(parts["meta"]))
    names, groups, offset = meta["names"], meta["groups"], meta["offset"]
    post = np.load(RUN_DIR / "posterior.npz", allow_pickle=True)
    post_units, post_buildings = post["units"], post["buildings"]
    if list(post["feature_names"]) != names:
        raise SystemExit("feature names differ between the bundle and the draws")

    focus_rows = bundle_rows("2025-04-01")
    focus = focus_rows[focus_rows.audit_id == FOCUS].iloc[0]
    typical, pool = typical_row(focus_rows)
    rows = pd.DataFrame([focus, typical]).reset_index(drop=True)
    rows["price_at"] = price_dates(rows.audit_id)
    xs = [json.loads(r) for r in rows.inputs]
    rows["bedrooms"] = [
        bedrooms_of(np.array([x.get(k, 0.0) for k in names]), names) for x in xs
    ]
    b_idx = pd.Index(post_buildings).get_indexer(rows.building)
    u_idx = pd.Index(post_units).get_indexer(rows.unit_id)
    if (b_idx < 0).any() or (u_idx < 0).any():
        raise SystemExit("a row's building or unit is missing from the draws")
    a = arrays(rows, parts, post_units, names, offset)

    take = {
        "building": lambda v: v[:, b_idx].copy(),
        "bedroom_slope": lambda v: v[:, b_idx].copy(),
        "walk": lambda v: v[:, b_idx, :].copy(),
        "fslope": lambda v: v[:, b_idx, :].copy(),
        "unit": lambda v: v[:, u_idx].copy(),
    }
    kept = draws.read(RUN_DIR / "posterior.npz", keys=KEYS, take=take, block=10)
    fslope_index = [names.index(n) for n in config.feature_slopes]
    terms = explain.log_terms(
        kept,
        a,
        groups,
        model.walk_spacing(config),
        config.bedroom_time,
        config.bedroom_slope,
        offset,
        fslope_index,
    )
    dollars, fitted = explain.decompose(terms)

    # The bundle's fitted rent is the in-sample mean over the same draws. Its dollar
    # parts are weighted toward leaving the row out, so they differ from these.
    for i, row in rows.iterrows():
        if abs(fitted[:, i].mean() / row.fitted_rent - 1) > 1e-3:
            raise SystemExit(
                f"row {i}: fitted {fitted[:, i].mean()} vs {row.fitted_rent}"
            )

    columns = {
        names[j]: kept["beta"][:, j : j + 1] * a.x[:, j][None]
        for j in np.flatnonzero(np.any(a.x != 0, axis=0))
    }
    w = kept["walk"]
    np.savez(
        out_dir / "draws.npz",
        term_names=np.array(list(terms)),
        terms=np.stack([terms[k] for k in terms]),
        dollar_names=np.array(list(dollars)),
        dollars=np.stack([dollars[k] for k in dollars]),
        column_names=np.array(list(columns)),
        columns=np.stack([columns[k] for k in columns]) if columns else np.zeros((0,)),
        offset=offset,
        alpha=kept["alpha"],
        trend=kept["trend"],
        season_daily_coef=kept["season_daily_coef"],
        bedroom_time=kept["bedroom_time"][:, a.bed_group, :],
        walk=w,
        sigma=kept["sigma"],
        nu=kept["nu"],
        unit_scale=kept["unit_scale"],
        unit_nu=kept["unit_nu"],
        noise_group=model.noise_group(kept["sigma"].shape[1], a),
        month=a.month,
        year_frac=a.year_frac,
        periods=parts["periods"],
        walk_spacing=model.walk_spacing(config),
    )
    rows.drop(columns=["inputs"]).assign(
        x=[json.dumps(x) for x in xs], typical_pool=pool
    ).to_json(out_dir / "rows.json", orient="records", indent=1)
    print("draws written; checks passed", fitted.mean(0))


def q(v, ps=(2.5, 10, 50, 90, 97.5)):
    return dict(
        zip(["p2_5", "p10", "p50", "p90", "p97_5"], np.percentile(v, ps).tolist())
    )


def summarize(v, thin, keep_draws=True):
    """Median, 10/90 and 2.5/97.5 in log points (x100), multipliers, chain medians."""
    chains = v.reshape(CHAINS, -1)
    sd = float(v.std())
    meds = np.median(chains, axis=1)
    return {
        "log": q(v),
        "sd": sd,
        "multiplier": {k: float(np.exp(x)) for k, x in q(v).items()},
        "chain_medians": meds.tolist(),
        "chain_spread_over_sd": float(np.ptp(meds) / sd) if sd > 0 else 0.0,
        "chains_disagree": bool(sd > 0 and np.ptp(meds) > sd),
        **({"draws": np.round(v[thin], 4).tolist()} if keep_draws and sd > 0 else {}),
    }


def predictive(total, unit_own, sigma, nu, unit_scale, unit_nu, rng, reps=20):
    """(in-sample, new-unit) predictive draws of the ask in dollars."""
    d = len(total)
    t = rng.standard_t(np.repeat(nu, reps)).reshape(d, reps)
    noise = sigma[:, None] * t
    own = np.exp(total[:, None] + noise)
    z = np.clip(
        rng.standard_t(np.repeat(np.maximum(unit_nu, 1e-3), reps)).reshape(d, reps),
        -40,
        40,
    )
    new = np.exp((total - unit_own)[:, None] + unit_scale[:, None] * z + noise)
    return own.ravel(), new.ravel()


def dist(v, ask):
    return {
        "median": float(np.median(v)),
        "p10": float(np.percentile(v, 10)),
        "p90": float(np.percentile(v, 90)),
        "p2_5": float(np.percentile(v, 2.5)),
        "p97_5": float(np.percentile(v, 97.5)),
        "pit_of_ask": float(np.mean(v < ask)),
    }


def step_json(out_dir, raw_json, data_json):
    z = np.load(out_dir / "draws.npz", allow_pickle=True)
    rows = json.loads((out_dir / "rows.json").read_text())
    rng = np.random.default_rng(20261026)
    d = z["terms"].shape[1]
    thin = np.linspace(0, d - 1, 200).round().astype(int)
    term_names = list(z["term_names"])
    terms, dollars = z["terms"], z["dollars"]
    dollar_names = list(z["dollar_names"])
    total = terms.sum(0)
    sigma = z["sigma"][:, z["noise_group"]]
    ask = rows[0]["asking_rent"]

    # the market term split into its own parts
    market_parts = {
        "offset": np.full(d, float(z["offset"])),
        "intercept": z["alpha"],
        "trend": z["trend"][:, z["month"][0]],
        "season": z["season_daily_coef"]
        @ model.day_basis(z["year_frac"][:1], z["season_daily_coef"].shape[1] // 2).T[
            :, 0
        ],
    }
    out_terms = []
    for i, k in enumerate(term_names):
        f, t = terms[i, :, 0], terms[i, :, 1]
        usd = dollars[dollar_names.index(k)]
        out_terms.append(
            {
                "term": k,
                "focus": summarize(f, thin),
                "typical": summarize(t, thin, keep_draws=False),
                "difference": summarize(f - t, thin),
                "lmdi_usd": {
                    "focus": q(usd[:, 0]),
                    "typical": q(usd[:, 1]),
                },
            }
        )
    out_terms.sort(key=lambda r: -abs(r["difference"]["log"]["p50"]))
    columns = [
        {
            "column": str(name),
            "focus": summarize(z["columns"][j, :, 0], thin),
            "typical": summarize(z["columns"][j, :, 1], thin, keep_draws=False),
        }
        for j, name in enumerate(z["column_names"])
    ]
    own, new = predictive(
        total[:, 0],
        terms[term_names.index("unit"), :, 0],
        sigma[:, 0],
        z["nu"],
        z["unit_scale"],
        z["unit_nu"],
        rng,
    )
    pick = rng.choice(len(new), 400, replace=False)

    # the same apartment priced in every month, its columns held at the listing's
    periods = pd.DatetimeIndex(z["periods"])
    spacing = int(z["walk_spacing"])
    m0 = z["month"][0]
    fixed = total[:, 0] - (
        z["trend"][:, m0]
        + z["bedroom_time"][:, 0, m0]
        + terms[term_names.index("building_drift"), :, 0]
    )
    path = []
    for m in range(len(periods)):
        if periods[m].year < 2014:
            continue
        knot, frac = m // spacing, (m % spacing) / spacing
        walk = (1 - frac) * z["walk"][:, 0, knot] + frac * z["walk"][
            :, 0, min(knot + 1, z["walk"].shape[2] - 1)
        ]
        season = (
            z["season_daily_coef"]
            @ model.day_basis(
                np.array([(periods[m].month - 0.5) / 12]),
                z["season_daily_coef"].shape[1] // 2,
            ).T[:, 0]
            - market_parts["season"]
        )
        mu = fixed + z["trend"][:, m] + z["bedroom_time"][:, 0, m] + walk + season
        p_own, p_new = predictive(
            mu,
            terms[term_names.index("unit"), :, 0],
            sigma[:, 0],
            z["nu"],
            z["unit_scale"],
            z["unit_nu"],
            rng,
            reps=4,
        )
        path.append(
            {
                "month": str(periods[m].date()),
                "fitted_median": round(float(np.median(np.exp(mu)))),
                "own": {
                    k: round(v)
                    for k, v in dist(p_own, ask).items()
                    if k != "pit_of_ask"
                },
                "new_unit": {
                    k: round(v)
                    for k, v in dist(p_new, ask).items()
                    if k != "pit_of_ask"
                },
            }
        )
    raw = json.loads(Path(raw_json).read_text()) if raw_json else {}
    focus, typical = rows
    data = {
        "run": RUN,
        "bundle": str(BUNDLE),
        "why_this_fit": "the served model on the live site build (site/current build.json), "
        "with 5S's listing in its training rows",
        "draws": int(d),
        "chains": CHAINS,
        "focus_row": {k: v for k, v in focus.items() if k != "typical_pool"},
        "typical_row": typical,
        "units": "log points are natural-log units; multiply by 100 for percent-ish points",
        "fitted": {
            "focus": q(np.exp(total[:, 0])),
            "typical": q(np.exp(total[:, 1])),
            "focus_log_total": summarize(total[:, 0], thin),
        },
        "market_parts": {k: summarize(v, thin) for k, v in market_parts.items()},
        "terms": out_terms,
        "columns": columns,
        "noise": {
            "sigma": summarize(sigma[:, 0], thin),
            "nu": summarize(z["nu"], thin),
            "unit_scale": summarize(z["unit_scale"], thin),
            "unit_nu": float(np.median(z["unit_nu"])),
        },
        "predictive": {
            "ask": ask,
            "in_sample": dist(own, ask),
            "new_unit": dist(new, ask),
            "psis_loo_bundle": {
                "median": focus["estimate_median"],
                "p10": focus["estimate_pred_lower_80"],
                "p90": focus["estimate_pred_upper_80"],
                "p2_5": focus["estimate_pred_lower_95"],
                "p97_5": focus["estimate_pred_upper_95"],
                "pit_of_ask": focus["pit"],
            },
            "new_unit_draws": np.round(new[pick]).tolist(),
            "in_sample_draws": np.round(own[pick]).tolist(),
        },
        "monthly_path": path,
        "raw": raw,
    }
    Path(data_json).write_text(json.dumps(data, separators=(",", ":")))
    print(Path(data_json).stat().st_size, "bytes")


if __name__ == "__main__":
    step, out = sys.argv[1], Path(sys.argv[2])
    if step == "draws":
        step_draws(out)
    else:
        step_json(out, sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4])
