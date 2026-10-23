"""The stabilized-text discount split by building age, tax-bill registration and period.

    python stabilized_split.py OUT_DIR [REPS]

This runs the Design section of docs/notes/stabilized-split-predictions-2026-10-23.md. It reads
the ads of the v36 dense NYC dataset, leaves out furnished, short-term and shared-space ads, and
regresses log latest ask on the rent-stabilized text flag, alone or interacted with a split, with
fixed effects for building, calendar month of the latest-ask day and bedrooms by full baths:

1. pooled: the flag alone;
2. age: flag by year-built bin (before 1974, 1974 to 2007, 2008 on, unknown);
3. taxbill: Manhattan rows only, flag by stabilized units on the lot's DOF tax bill (none, some);
4. age_period: flag by year-built bin by latest-ask day before or after 2019-06-14 (HSTPA).

The fixed effects are absorbed exactly. The script demeans every column within building, then
handles the month and cell dummies, which number about two hundred, through their Gram matrix
after the building demeaning. Each flag regressor costs a few bincounts, so a permutation
replicate refits all four specifications in a second or two. Standard errors are clustered by
building and by ISO week of the latest-ask day (Cameron, Gelbach and Miller: V_b + V_w - V_bw,
each with a G/(G-1) factor). The permutation null shuffles the flag among a building's ads,
REPS times (default 200), and refits.

It writes results.json and table.md to OUT_DIR. Coefficients are in percent, 100 (exp(b) - 1);
differences are percent-point differences of those.
"""

import json
import sys
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp

DATASET = (
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc"
)
REGISTRY = (
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
)
AGE = "/data1/apartments/external/building-age/20261021-3a64aa22/age.parquet"
RENTSTAB = "/data1/apartments/external/rentstab/20261008-b487c8a/rentstab.parquet"
HSTPA = pd.Timestamp("2019-06-14")
AGE_BINS = ("pre1974", "1974-2007", "2008on", "unknown")
TAX_BINS = ("none", "some")
PERIODS = ("pre", "post")
Q = (2.5, 50, 95, 97.5)


def codes(values):
    """Dense integer codes 0..k-1 of an array of labels."""
    return np.unique(values, return_inverse=True)[1].ravel()


def demean(v, g, n):
    """Each column of v less its mean within the groups g (counts n)."""
    v = np.asarray(v, float)
    if v.ndim == 1:
        return v - (np.bincount(g, v, len(n)) / n)[g]
    return np.column_stack([demean(c, g, n) for c in v.T])


class Absorb:
    """OLS of y on few regressors X plus building, month and cell fixed effects.

    Frisch-Waugh in two steps: demean y, X and the month and cell dummies Z within building,
    then partial Z out through G = Z~'Z~ = Z'Z - A' diag(1/n_b) A, with A the building by Z
    count matrix. Z has a rank deficit of two after the building demeaning, so G goes through a
    pseudo-inverse, which leaves the fitted values unchanged.
    """

    def __init__(self, y, bld, month, cell):
        self.b = codes(bld)
        self.nb = np.bincount(self.b).astype(float)
        m, c = codes(month), codes(cell)
        k = m.max() + 1
        cols = np.concatenate([m, k + c])
        rows = np.concatenate([np.arange(len(m))] * 2)
        self.Z = sp.csr_matrix((np.ones(len(cols)), (rows, cols)))
        nbz = sp.csr_matrix(
            (np.ones(len(cols)), (np.concatenate([self.b] * 2), cols)),
            shape=(len(self.nb), self.Z.shape[1]),
        )
        zz = (self.Z.T @ self.Z).toarray()
        G = zz - (nbz.T @ sp.diags(1 / self.nb) @ nbz).toarray()
        self.Gp = np.linalg.pinv(G, rcond=1e-10, hermitian=True)
        self.y = demean(y, self.b, self.nb)
        self.zy = self.Z.T @ self.y

    def beta(self, X):
        """Coefficients on X, with the pieces fit() reuses."""
        Xt = demean(X, self.b, self.nb)
        zx = np.asarray(self.Z.T @ Xt)
        H = Xt.T @ Xt - zx.T @ self.Gp @ zx
        g = Xt.T @ self.y - zx.T @ self.Gp @ self.zy
        return np.linalg.solve(H, g), Xt, zx, H

    def fit(self, X, clusters):
        """Coefficients and the two-way clustered covariance (CGM)."""
        b, Xt, zx, H = self.beta(X)
        Xr = Xt - demean(self.Z @ (self.Gp @ zx), self.b, self.nb)
        gamma = self.Gp @ (self.zy - zx @ b)
        e = self.y - Xt @ b - demean(self.Z @ gamma, self.b, self.nb)
        Hi = np.linalg.inv(H)
        V = cgm(Xr * e[:, None], Hi, clusters)
        return b, V


def cluster_meat(scores, g):
    """Sum over clusters g of s_g s_g', times G/(G-1)."""
    g = codes(g)
    s = np.column_stack([np.bincount(g, c) for c in scores.T])
    G = len(s)
    return G / (G - 1) * s.T @ s


def cgm(scores, Hi, clusters):
    """Cameron-Gelbach-Miller two-way covariance from per-row scores x_i e_i."""
    a, w = clusters
    both = a.astype(np.int64) * (w.max() + 1) + w
    meat = (
        cluster_meat(scores, a) + cluster_meat(scores, w) - cluster_meat(scores, both)
    )
    return Hi @ meat @ Hi


def pct(b):
    return 100 * np.expm1(b)


def load():
    """The estimating rows with their flag, fixed-effect keys and split labels."""
    cols = [
        "building",
        "latest_ask",
        "latest_day",
        "bedrooms",
        "full_baths",
        "furnished",
        "short_term",
        "shared_space",
        "rent_stabilized",
    ]
    f = pd.read_parquet(f"{DATASET}/rows.parquet", columns=cols)
    f = f[~(f.furnished | f.short_term | f.shared_space)].reset_index(drop=True)
    day = pd.to_datetime(f.latest_day)
    iso = day.dt.isocalendar()
    reg = pd.read_parquet(REGISTRY, columns=["building", "bbl"]).set_index("building")
    age = pd.read_parquet(AGE, columns=["building", "year_built"]).set_index("building")
    out = pd.DataFrame(
        {
            "building": f.building.to_numpy(),
            "y": np.log(f.latest_ask.to_numpy()),
            "flag": f.rent_stabilized.to_numpy().astype(float),
            "month": (day.dt.year * 12 + day.dt.month).to_numpy(),
            "week": (iso.year * 100 + iso.week).to_numpy().astype(int),
            "cell": (f.bedrooms.astype(int) * 10 + f.full_baths).to_numpy(),
            "post": (day >= HSTPA).to_numpy(),
            "year": day.dt.year.to_numpy().astype(np.int64),
            "bbl": f.building.map(reg.bbl).to_numpy(),
        }
    )
    yb = f.building.map(age.year_built).to_numpy()
    out["age"] = np.select(
        [np.isnan(yb), yb < 1974, yb < 2008],
        ["unknown", "pre1974", "1974-2007"],
        "2008on",
    )
    out["manhattan"] = out.bbl.str[0].eq("1").to_numpy()
    out["tax"] = taxbill(out)
    return out


def taxbill(rows):
    """Per row: "some" or "none" stabilized units on its lot's bill in the ad's year, or the
    nearest year the lot has on file; "" off Manhattan. A Manhattan lot missing from the file
    counts as none."""
    rs = pd.read_parquet(RENTSTAB).sort_values("year")
    man = rows[rows.manhattan][["bbl", "year"]].reset_index()
    hit = pd.merge_asof(
        man.sort_values("year"), rs, on="year", by="bbl", direction="nearest"
    )
    units = hit.set_index("index").units.reindex(man["index"]).fillna(0)
    tax = np.full(len(rows), "", dtype=object)
    tax[man["index"].to_numpy()] = np.where(units.to_numpy() > 0, "some", "none")
    return tax


SPECS = {
    "pooled": (None, ["all"]),
    "age": (None, list(AGE_BINS)),
    "taxbill": ("manhattan", list(TAX_BINS)),
    "age_period": (None, [f"{a} x {p}" for a in AGE_BINS for p in PERIODS]),
}
# (spec, minuend cell, subtrahend cell) for the differences the predictions name.
DIFFS = [
    ("age", "pre1974", "2008on"),
    ("taxbill", "some", "none"),
    ("age_period", "pre1974 x post", "pre1974 x pre"),
    ("age_period", "2008on x post", "2008on x pre"),
]


def labels(rows, spec):
    """Per row: the cell its flag falls in under a specification."""
    if spec == "pooled":
        return np.full(len(rows), "all", dtype=object)
    if spec == "age":
        return rows.age.to_numpy()
    if spec == "taxbill":
        return rows.tax.to_numpy()
    return (rows.age + np.where(rows.post, " x post", " x pre")).to_numpy()


def design(flag, lab, cells):
    """Flag interacted with each cell's indicator."""
    return np.column_stack([flag * lab[c] for c in cells])


def counts(rows, cells, lab):
    """Ads, flagged ads and flagged ads in buildings with no flag contrast, per cell."""
    by = rows.groupby("building").flag
    mixed = (by.transform("min") < by.transform("max")).to_numpy()
    out = {}
    for c in cells:
        m = lab[c]
        out[c] = dict(
            ads=int(m.sum()),
            buildings=int(rows.building[m].nunique()),
            flagged=int(rows.flag[m].sum()),
            flagged_no_contrast=int((rows.flag.to_numpy()[m] * ~mixed[m]).sum()),
        )
    return out


def main():
    out_dir, reps = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 200
    t0 = time.time()
    rows = load()
    res = {
        "dataset": DATASET,
        "rows": len(rows),
        "flagged": int(rows.flag.sum()),
        "manhattan_rows": int(rows.manhattan.sum()),
        "manhattan_rows_lot_not_in_taxbill_file": int(
            (
                rows.manhattan
                & ~rows.bbl.isin(set(pd.read_parquet(RENTSTAB, columns=["bbl"]).bbl))
            ).sum()
        ),
        "rows_no_year_built": int((rows.age == "unknown").sum()),
        "specs": {},
        "diffs": {},
    }
    fits, perm_x = {}, {}
    for spec, (subset, cells) in SPECS.items():
        r = rows[rows[subset]].reset_index(drop=True) if subset else rows
        lab = labels(r, spec)
        lab = {c: lab == c for c in cells}
        cells = [c for c in cells if lab[c].any()]
        ab = Absorb(r.y.to_numpy(), r.building, r.month, r.cell)
        b, V = ab.fit(
            design(r.flag.to_numpy(), lab, cells), (ab.b, codes(r.week.to_numpy()))
        )
        fits[spec] = (cells, b, V)
        perm_x[spec] = (ab, lab, cells, subset)
        se = np.sqrt(np.diag(V))
        res["specs"][spec] = {
            "rows": len(r),
            "cells": {
                c: dict(
                    b=b[i],
                    se=se[i],
                    pct=pct(b[i]),
                    ci95=[pct(b[i] - 1.96 * se[i]), pct(b[i] + 1.96 * se[i])],
                )
                for i, c in enumerate(cells)
            },
            "counts": counts(r, cells, lab),
        }
        print(spec, f"{time.time() - t0:.0f}s", flush=True)
    for spec, a, z in DIFFS:
        cells, b, V = fits[spec]
        i, j = cells.index(a), cells.index(z)
        c = np.zeros(len(b))
        c[i], c[j] = 1, -1
        se = float(np.sqrt(c @ V @ c))
        d = b[i] - b[j]
        res["diffs"][f"{spec}: {a} - {z}"] = dict(
            log_points=100 * d,
            se_log_points=100 * se,
            z=d / se,
            pct_points=pct(b[i]) - pct(b[j]),
        )
    res["fit_seconds"] = time.time() - t0

    # Permutation null: shuffle the flag among each building's ads.
    rng = np.random.default_rng(20261023)
    bld = codes(rows.building.to_numpy())
    by_bld = np.argsort(bld, kind="stable")
    flag = rows.flag.to_numpy()
    man = rows.manhattan.to_numpy()
    null = {s: [] for s in SPECS}
    t1 = time.time()
    for _ in range(reps):
        order = np.lexsort((rng.random(len(bld)), bld))
        fp = np.empty_like(flag)
        fp[by_bld] = flag[order]
        for spec, (ab, lab, cells, subset) in perm_x.items():
            f = fp[man] if subset else fp
            null[spec].append(pct(ab.beta(design(f, lab, cells))[0]))
    res["perm_reps"] = reps
    res["perm_seconds"] = time.time() - t1
    for spec in SPECS:
        n = np.array(null[spec])
        for i, c in enumerate(fits[spec][0]):
            cell = res["specs"][spec]["cells"][c]
            cell["null_pct"] = dict(zip(map(str, Q), np.percentile(n[:, i], Q)))
            cell["null_share_below"] = float((n[:, i] < cell["pct"]).mean())
    for spec, a, z in DIFFS:
        cells = fits[spec][0]
        n = np.array(null[spec])
        nd = n[:, cells.index(a)] - n[:, cells.index(z)]
        d = res["diffs"][f"{spec}: {a} - {z}"]
        d["null_pct_points"] = dict(zip(map(str, Q), np.percentile(nd, Q)))
        d["null_share_below"] = float((nd < d["pct_points"]).mean())
    res["seconds"] = time.time() - t0

    with open(f"{out_dir}/results.json", "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    lines = [
        "| spec | cell | ads | flagged | flagged, no contrast | % | 95% CI | null 2.5/50/97.5 | null share below |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for spec, s in res["specs"].items():
        for name, c in s["cells"].items():
            k, q = s["counts"][name], c["null_pct"]
            lines.append(
                f"| {spec} | {name} | {k['ads']} | {k['flagged']} | {k['flagged_no_contrast']} "
                f"| {c['pct']:.2f} | {c['ci95'][0]:.2f} to {c['ci95'][1]:.2f} "
                f"| {q['2.5']:.2f} / {q['50']:.2f} / {q['97.5']:.2f} | {c['null_share_below']:.3f} |"
            )
    lines += [
        "",
        "| difference | pct points | log points (SE) | z | null 2.5/50/97.5 | null share below |",
        "|---|---|---|---|---|---|",
    ]
    for name, d in res["diffs"].items():
        q = d["null_pct_points"]
        lines.append(
            f"| {name} | {d['pct_points']:.2f} | {d['log_points']:.2f} ({d['se_log_points']:.2f}) "
            f"| {d['z']:.2f} | {q['2.5']:.2f} / {q['50']:.2f} / {q['97.5']:.2f} "
            f"| {d['null_share_below']:.3f} |"
        )
    with open(f"{out_dir}/table.md", "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"total {res['seconds']:.0f}s, permutations {res['perm_seconds']:.0f}s")


if __name__ == "__main__":
    main()
