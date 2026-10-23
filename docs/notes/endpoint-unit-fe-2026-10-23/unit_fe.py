"""Unit fixed-effects OLS on Sol's audited endpoints: the regression of
docs/notes/endpoint-unit-fe-predictions-2026-10-23.md.

    python unit_fe.py [OUT_DIR]

OUT_DIR defaults to /data1/apartments/tmp/conference-followups/unit-fe, where counts.py wrote
endpoint_design.parquet: the 123,828 endpoint ads with their fit 4 design columns. I read each
ad's latest ask from the model rows and fit, on the endpoint rows,

    log latest_ask = unit effect + month effect + x b + e,

with the month of each row's own latest_day. Alternating projections absorb both sets of
effects. The columns x are every design column that changes within at least one unit, all in
one regression.

Standard errors are two-way clustered by unit and by the ISO week of each row's own latest_day
(Cameron, Gelbach and Miller 2011), with the larger one-way variance where the two-way one comes
out negative. A week cluster gathers the first and second endpoints dated in that week, from
any unit.

I fit twice: on all pairs, and without the units whose later endpoint fit 4's latest split
holds out. I write results.json and tables.md to OUT_DIR.
"""

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
    else "/data1/apartments/tmp/conference-followups/unit-fe"
)
MODEL = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
COUNTS = json.loads((OUT / "counts.json").read_text())
NAMES = [n for n, t in COUNTS["terms"].items() if t["units_changing"] > 0]
PREDICTED = [
    "unit:laundry_in_unit",
    "unit:laundry_in_building",
    "unit:dishwasher",
    "unit:log_size_rel",
    "unit:size_imputed",
    "unit:size_unknown",
    "flag:shared_space",
    "flag:rent_stabilized",
    "bld:altered_2000_on",
    "unit:walkup_floor_unknown",
]
ELASTICITY = {"unit:log_size_rel"}

E = pd.read_parquet(OUT / "endpoint_design.parquet")
ask = pd.read_parquet(MODEL, columns=["listing_id", "latest_ask"])
ask = ask.assign(listing_id=ask.listing_id.astype(str)).set_index("listing_id")
E["latest_ask"] = E.listing_id.astype(str).map(ask.latest_ask)
del ask
assert E.latest_ask.gt(0).all()
day = pd.to_datetime(E.latest_day)
iso = day.dt.isocalendar()
E["month"] = day.dt.to_period("M").astype(str)
E["week"] = iso.year.astype(str) + "-" + iso.week.astype(str)


def code(s):
    return pd.factorize(s)[0]


def demean(M, groups, tol=1e-10, itmax=5000):
    """Residualize the columns of M on the fixed effects in `groups` by alternating
    projections, sweeping out each factor's group means in turn until the largest change
    falls below tol."""
    M = M - M.mean(axis=0)
    counts = [np.bincount(g) for g in groups]
    for it in range(itmax):
        change = 0.0
        for g, n in zip(groups, counts, strict=True):
            means = np.stack(
                [np.bincount(g, M[:, j]) / n for j in range(M.shape[1])], axis=1
            )
            change = max(change, float(np.abs(means).max()))
            M -= means[g]
        if change < tol:
            return M, it + 1
    raise RuntimeError("alternating projections did not converge")


def fit(F):
    """The unit and month fixed-effects fit on the rows of F, with two-way clustered
    standard errors by unit and by own week."""
    unit, month, week = code(F.unit_id), code(F.month), code(F.week)
    X = F[NAMES].to_numpy(float)
    y = np.log(F.latest_ask.to_numpy(float))
    D, its = demean(np.column_stack([X, y]), [unit, month])
    x, yy = D[:, :-1], D[:, -1]
    keep = x.std(axis=0) > 1e-8
    names = [n for n, k in zip(NAMES, keep, strict=True) if k]
    x = x[:, keep]
    A = np.linalg.inv(x.T @ x)
    beta = A @ (x.T @ yy)
    score = x * (yy - x @ beta)[:, None]
    nw = int(week.max()) + 1
    V = {}
    for dim, ids in {
        "unit": unit,
        "week": week,
        "unit_week": unit.astype(np.int64) * nw + week,
    }.items():
        u, inv = np.unique(ids, return_inverse=True)
        S = np.zeros((len(u), x.shape[1]))
        np.add.at(S, inv, score)
        V[dim] = A @ (len(u) / (len(u) - 1) * (S.T @ S)) @ A
    two = V["unit"] + V["week"] - V["unit_week"]
    se = np.sqrt(
        np.where(
            np.diag(two) > 0,
            np.diag(two),
            np.maximum(np.diag(V["unit"]), np.diag(V["week"])),
        )
    )
    one_way = {d: np.sqrt(np.diag(V[d])) for d in ("unit", "week")}
    pair = F.sort_values(["unit_id", "endpoint"])
    first, last = (pair[pair.endpoint == k].set_index("unit_id") for k in (0, 1))
    changing = (last[names] - first[names].reindex(last.index)).abs().gt(1e-9).sum()
    terms = {}
    for i, n in enumerate(names):
        b, s = beta[i], se[i]
        lo, hi = b - 1.96 * s, b + 1.96 * s
        if n in ELASTICITY:
            est = [round(float(v), 4) for v in (b, lo, hi)]
        else:
            est = [round(100 * float(np.expm1(v)), 2) for v in (b, lo, hi)]
        terms[n] = dict(
            estimate=est,
            scale="elasticity" if n in ELASTICITY else "percent",
            log_coef=round(float(b), 5),
            se_two_way=round(float(s), 5),
            se_unit=round(float(one_way["unit"][i]), 5),
            se_week=round(float(one_way["week"][i]), 5),
            units_changing=int(changing[n]),
        )
    return dict(
        rows=int(len(F)),
        units=int(unit.max() + 1),
        months=int(month.max() + 1),
        weeks=int(week.max() + 1),
        iterations=its,
        dropped_columns=[n for n, k in zip(NAMES, keep, strict=True) if not k],
        terms=terms,
    )


held_units = set(E.unit_id[E.fit4_held_out])
runs = {
    "all_pairs": fit(E),
    "without_fit4_held_out_units": fit(E[~E.unit_id.isin(held_units)]),
}
moves = {
    n: round(
        runs["without_fit4_held_out_units"]["terms"][n]["estimate"][0]
        - runs["all_pairs"]["terms"][n]["estimate"][0],
        4,
    )
    for n in PREDICTED
}
out = dict(
    inputs=dict(
        endpoints=str(OUT / "endpoint_design.parquet"),
        model_rows=MODEL,
        counts=str(OUT / "counts.json"),
    ),
    target="log latest_ask",
    fixed_effects=["unit", "calendar month of own latest_day"],
    clusters="two-way: unit and ISO week of own latest_day",
    columns=NAMES,
    runs=runs,
    held_out_check_moves=moves,
    seconds=round(time.time() - T0, 1),
)
(OUT / "results.json").write_text(json.dumps(out, indent=1))

lines = ["# Unit fixed-effects OLS on audited endpoints", ""]
for k, r in runs.items():
    lines += [
        f"## {k}: {r['rows']} rows, {r['units']} units, {r['weeks']} weeks",
        "",
        "| column | units changing | estimate | 95% interval | se unit / week / two-way |",
        "|---|---:|---:|---|---|",
    ]
    for n, t in r["terms"].items():
        b, lo, hi = t["estimate"]
        lines.append(
            f"| {n} | {t['units_changing']} | {b} | {lo} to {hi} | "
            f"{t['se_unit']} / {t['se_week']} / {t['se_two_way']} |"
        )
    lines.append("")
(OUT / "tables.md").write_text("\n".join(lines))
print("\n".join(lines))
print(json.dumps(moves), f"{out['seconds']}s")
