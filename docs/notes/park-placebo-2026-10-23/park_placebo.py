"""Park frontage by line, by floor and against placebo frontages.

    PYTHONPATH=frontier/src python3 park_placebo.py GROUPS OUT_DIR [REPS]

This runs the Design section of docs/notes/park-placebo-predictions-2026-10-23.md. GROUPS is the
groups.parquet that counts.py writes: per ad, its line, floor, view marks and distances to parks
and placebo land. I join it by listing id to the v36 dense NYC rows for log latest ask, the
latest-ask day and bedrooms by full baths, and fit OLS with fixed effects absorbed exactly
(`Absorb`, as in conference-followups-2026-10-22/stabilized_split.py):

1. view: park-facing ads, building FE, the ad's view mark, floor bins as controls;
   view_line: ads with a parsed line in buildings holding both view and other lines, with the
   line's majority mark in place of the ad's;
2. view_near: fit 1 on the 40 to 200 m ring;
3. nonview_gap: non-view ads of park-facing and nearby buildings, 150 m cell FE, cells holding
   both kinds of building;
4. floor: park-facing and nearby ads, building FE, floor bins plus park-facing by floor bin;
   view_floor: park-facing ads, building FE, floor bins plus the view mark by floor bin;
5. prestige: all ads of park-facing and nearby buildings, cell FE, the front flag split into
   the prestige avenues and the rest (all_gap: the same with one front flag);
6. placebo_*: all ads of front and nearby buildings for each placebo kind, cell FE.

Every fit also has month and bedroom-by-bath FE. Floor bins are 0-2, 3-5, 6-10, 11-20, 21+ and
unknown. Standard errors are clustered by building and ISO week (Cameron, Gelbach and Miller).
Permutation nulls (REPS, default 200) move the view mark a unit at a time (1, 2): unit ids are
shuffled within the building, and each ad takes a mark drawn with replacement from the ads of the
unit its own unit maps to. They shuffle the line mark among a building's lines (view_line), or the front flag, with its prestige label,
among the buildings of a cell (3, 5, 6). Coefficients are in percent, 100 (exp(b) - 1).
"""

import json
import sys
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp

from rentfrontier import frontage

DATASET = (
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc"
)
REGISTRY = (
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
)
FRONT_M, NEAR_M, CELL_M = 40.0, 200.0, 150.0
FLOOR_BINS = ("0-2", "3-5", "6-10", "11-20", "21+", "unknown")
# the same avenue list as counts.py
PRESTIGE = (
    r"(?:^|-)(?:central-park-west|central-park-south|riverside-drive)(?:-new_york)?$"
    r"|(?:^|-)(?:5|fifth)-avenue-new_york$"
    r"|(?:^|-)prospect-park-west(?:-brooklyn)?$"
)
Q = (2.5, 5, 50, 95, 97.5)


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
    """OLS of y on few regressors X plus group, month and bedroom-by-bath fixed effects.

    Frisch-Waugh in two steps: demean within the group (a building or a 150 m cell), then
    partial the month and bedroom-by-bath dummies Z out through the pseudo-inverse of their
    Gram matrix after the group demeaning.
    """

    def __init__(self, y, grp, month, cell):
        self.b = codes(grp)
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
        Xt = demean(X, self.b, self.nb)
        zx = np.asarray(self.Z.T @ Xt)
        H = Xt.T @ Xt - zx.T @ self.Gp @ zx
        g = Xt.T @ self.y - zx.T @ self.Gp @ self.zy
        return np.linalg.lstsq(H, g, rcond=None)[0], Xt, zx, H

    def fit(self, X, clusters):
        b, Xt, zx, H = self.beta(X)
        Xr = Xt - demean(self.Z @ (self.Gp @ zx), self.b, self.nb)
        gamma = self.Gp @ (self.zy - zx @ b)
        e = self.y - Xt @ b - demean(self.Z @ gamma, self.b, self.nb)
        Hi = np.linalg.pinv(H)
        return b, cgm(Xr * e[:, None], Hi, clusters)


def cluster_meat(scores, g):
    g = codes(g)
    s = np.column_stack([np.bincount(g, c) for c in scores.T])
    G = len(s)
    return G / (G - 1) * s.T @ s


def cgm(scores, Hi, clusters):
    a, w = clusters
    both = a.astype(np.int64) * (w.max() + 1) + w
    meat = (
        cluster_meat(scores, a) + cluster_meat(scores, w) - cluster_meat(scores, both)
    )
    return Hi @ meat @ Hi


def pct(b):
    return 100 * np.expm1(b)


def load(groups):
    cols = [
        "listing_id",
        "building",
        "latest_ask",
        "latest_day",
        "bedrooms",
        "full_baths",
        "shared_space",
    ]
    f = pd.read_parquet(f"{DATASET}/rows.parquet", columns=cols)
    f = f[~f.shared_space.astype(bool)].drop(columns="shared_space")
    g = pd.read_parquet(groups).drop(columns=["building"])
    r = f.merge(g, on="listing_id", how="inner").reset_index(drop=True)
    day = pd.to_datetime(r.latest_day)
    iso = day.dt.isocalendar()
    r["y"] = np.log(r.latest_ask.to_numpy(float))
    r["month"] = (day.dt.year * 12 + day.dt.month).to_numpy()
    r["week"] = (iso.year * 100 + iso.week).to_numpy().astype(int)
    r["bedbath"] = (r.bedrooms.astype(int) * 10 + r.full_baths).to_numpy()
    r["building"] = r.building.astype(str)
    reg = pd.read_parquet(REGISTRY, columns=["building", "latitude", "longitude"])
    reg = reg.drop_duplicates("building").set_index("building")
    xy = frontage.metres(
        r.building.map(reg.longitude).to_numpy(float),
        r.building.map(reg.latitude).to_numpy(float),
    )
    ok = np.isfinite(xy).all(1)
    cx = np.where(ok, np.floor(xy[:, 0] / CELL_M), -1).astype(np.int64)
    cy = np.where(ok, np.floor(xy[:, 1] / CELL_M), -1).astype(np.int64)
    r["cell150"] = np.where(ok, cx * 1000003 + cy, -1)
    fl = r.floor.to_numpy(float)
    r["fbin"] = np.select(
        [np.isnan(fl), fl <= 2, fl <= 5, fl <= 10, fl <= 20],
        ["unknown", "0-2", "3-5", "6-10", "11-20"],
        "21+",
    )
    r["park_view"] = r.park_view.astype(bool)
    r["front"] = r.park_m < FRONT_M
    r["near"] = (r.park_m >= FRONT_M) & (r.park_m < NEAR_M)
    r["prestige"] = r.building.str.contains(PRESTIGE, regex=True)
    return r


def dummies(lab, cells):
    return np.column_stack([(lab == c).astype(float) for c in cells])


def quantiles(x):
    return dict(zip(map(str, Q), np.percentile(x, Q)))


def shuffle_within(values, groups, rng):
    """values permuted among the members of each group."""
    u = rng.random(len(values))
    order = np.lexsort((u, groups))
    srt = np.argsort(groups, kind="stable")
    out = np.empty_like(values)
    out[srt] = values[order]
    return out


class Spec:
    """One fit: rows, absorber, the regressors of interest (first k columns) and controls."""

    def __init__(self, name, r, grp, X, names, k, perm=None):
        self.name, self.r, self.X, self.names, self.k, self.perm = (
            name,
            r,
            X,
            names,
            k,
            perm,
        )
        self.ab = Absorb(r.y.to_numpy(), grp, r.month.to_numpy(), r.bedbath.to_numpy())
        self.cl = (codes(r.building.to_numpy()), codes(r.week.to_numpy()))

    def run(self):
        b, V = self.ab.fit(self.X, self.cl)
        self.b, self.V = b, V
        se = np.sqrt(np.diag(V))
        r = self.r
        out = {
            "ads": len(r),
            "buildings": int(r.building.nunique()),
            "terms": {
                n: dict(
                    b=float(b[i]),
                    se=float(se[i]),
                    pct=float(pct(b[i])),
                    ci95=[
                        float(pct(b[i] - 1.96 * se[i])),
                        float(pct(b[i] + 1.96 * se[i])),
                    ],
                )
                for i, n in enumerate(self.names[: self.k])
            },
        }
        return out

    def contrast(self, w):
        """A linear combination of the first k coefficients, in log points x100."""
        c = np.zeros(len(self.b))
        c[: len(w)] = w
        d = float(c @ self.b)
        se = float(np.sqrt(c @ self.V @ c))
        return dict(
            log_points=100 * d,
            se=100 * se,
            ci95=[100 * (d - 1.96 * se), 100 * (d + 1.96 * se)],
            z=d / se,
        )


def main():
    groups, out_dir = sys.argv[1], sys.argv[2]
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    rng = np.random.default_rng(20261023)
    t0 = time.time()
    r = load(groups)
    res = {"rows": len(r), "specs": {}, "contrasts": {}}
    fb = [c for c in FLOOR_BINS if c != "0-2"]
    specs = {}

    # 1 and 2: view mark within building, floor bins as controls
    for name, mask in (("view", r.front), ("view_near", r.near)):
        s = r[mask].reset_index(drop=True)
        X = np.column_stack([s.park_view.astype(float), dummies(s.fbin, fb)])
        specs[name] = Spec(
            name,
            s,
            s.building.to_numpy(),
            X,
            ["view"] + fb,
            1,
            perm=("units", s),
        )

    # 1, line version
    s = r[r.front & r.line.notna()].copy()
    s["bl"] = s.building + "|" + s.line.astype(str)
    lm = s.groupby("bl").park_view.mean() >= 0.5
    s["line_view"] = s.bl.map(lm).astype(float)
    both = s.groupby("building").line_view.agg(["min", "max"])
    keepb = both.index[(both["min"] == 0) & (both["max"] == 1)]
    s = s[s.building.isin(keepb)].reset_index(drop=True)
    X = np.column_stack([s.line_view, dummies(s.fbin, fb)])
    specs["view_line"] = Spec(
        "view_line",
        s,
        s.building.to_numpy(),
        X,
        ["line_view"] + fb,
        1,
        perm=("lines", s),
    )
    res["line_counts"] = dict(
        buildings=int(len(keepb)),
        lines=int(s.bl.nunique()),
        view_lines=int(s[s.line_view == 1].bl.nunique()),
        ads_view_lines=int((s.line_view == 1).sum()),
        ads_other_lines=int((s.line_view == 0).sum()),
    )

    def cells_with_both(s, flag):
        c = s.groupby("cell150")[flag].agg(["min", "max"])
        ok = c.index[(c["min"] == 0) & (c["max"] == 1) & (c.index != -1)]
        return s[s.cell150.isin(ok)].reset_index(drop=True)

    # 3: non-view ads across buildings, cell FE
    s = r[(r.front | r.near) & ~r.park_view].copy()
    s["f"] = s.front.astype(int)
    s = cells_with_both(s, "f")
    specs["nonview_gap"] = Spec(
        "nonview_gap",
        s,
        s.cell150.to_numpy(),
        s.f.to_numpy(float)[:, None],
        ["front"],
        1,
        perm=("buildings", s, ["front"]),
    )

    # 5: all ads, front flag pooled and split by prestige
    s = r[r.front | r.near].copy()
    s["f"] = s.front.astype(int)
    s = cells_with_both(s, "f")
    specs["all_gap"] = Spec(
        "all_gap",
        s,
        s.cell150.to_numpy(),
        s.f.to_numpy(float)[:, None],
        ["front"],
        1,
        perm=("buildings", s, ["front"]),
    )
    fp = (s.front & s.prestige).to_numpy(float)
    fo = (s.front & ~s.prestige).to_numpy(float)
    specs["prestige"] = Spec(
        "prestige",
        s,
        s.cell150.to_numpy(),
        np.column_stack([fp, fo]),
        ["front_prestige", "front_other"],
        2,
        perm=("buildings", s, ["front_prestige", "front_other"]),
    )

    # 4: floor gradient of the building flag and of the view mark
    s = r[r.front | r.near].reset_index(drop=True)
    inter = dummies(s.fbin, fb) * s.front.to_numpy(float)[:, None]
    specs["floor"] = Spec(
        "floor",
        s,
        s.building.to_numpy(),
        np.column_stack([inter, dummies(s.fbin, fb)]),
        [f"front x {c}" for c in fb] + fb,
        len(fb),
    )
    s = r[r.front].reset_index(drop=True)
    v = s.park_view.to_numpy(float)
    specs["view_floor"] = Spec(
        "view_floor",
        s,
        s.building.to_numpy(),
        np.column_stack([v, dummies(s.fbin, fb) * v[:, None], dummies(s.fbin, fb)]),
        ["view"] + [f"view x {c}" for c in fb] + fb,
        1 + len(fb),
    )

    # 6: placebo frontages, park-facing buildings left out
    for kind in ("rail", "cemetery", "highway"):
        d = r[f"{kind}_m"]
        s = r[~r.front & (d < NEAR_M)].copy()
        s["f"] = (s[f"{kind}_m"] < FRONT_M).astype(int)
        s = cells_with_both(s, "f")
        specs[f"placebo_{kind}"] = Spec(
            f"placebo_{kind}",
            s,
            s.cell150.to_numpy(),
            s.f.to_numpy(float)[:, None],
            ["front"],
            1,
            perm=("buildings", s, ["front"]),
        )

    for name, sp_ in specs.items():
        res["specs"][name] = sp_.run()
        print(name, res["specs"][name]["ads"], f"{time.time() - t0:.0f}s", flush=True)

    # contrasts: floors 11 and up against 0-2, weighted by park-facing ads in the two bins
    fr = r[r.front]
    w11 = np.array([(fr.fbin == "11-20").sum(), (fr.fbin == "21+").sum()], float)
    w11 /= w11.sum()
    i1, i2 = fb.index("11-20"), fb.index("21+")
    w = np.zeros(len(fb))
    w[i1], w[i2] = w11
    res["contrasts"]["front x floor 11+ minus 0-2"] = specs["floor"].contrast(w)
    w = np.zeros(1 + len(fb))
    w[1 + i1], w[1 + i2] = w11
    res["contrasts"]["view x floor 11+ minus 0-2"] = specs["view_floor"].contrast(w)
    res["contrasts"]["prestige minus other"] = specs["prestige"].contrast([1, -1])
    bp = specs["prestige"].b
    res["contrasts"]["other as share of prestige gap"] = dict(
        share=float(bp[1] / bp[0]), note="log coefficients, point estimate"
    )
    res["contrasts"]["view_line minus view (log points)"] = dict(
        log_points=100 * (specs["view_line"].b[0] - specs["view"].b[0])
    )
    res["contrasts"]["view minus view_near (log points)"] = dict(
        log_points=100 * (specs["view"].b[0] - specs["view_near"].b[0])
    )
    for kind in ("rail", "cemetery", "highway"):
        a, z = specs["all_gap"], specs[f"placebo_{kind}"]
        d = a.b[0] - z.b[0]
        se = np.sqrt(a.V[0, 0] + z.V[0, 0])
        res["contrasts"][f"park all_gap minus placebo_{kind}"] = dict(
            log_points=100 * d,
            se=100 * se,
            z=float(d / se),
            note="SEs combined as independent",
        )
    res["fit_seconds"] = time.time() - t0

    # permutation nulls
    t1 = time.time()
    null = {n: [] for n, s_ in specs.items() if s_.perm}
    prep = {}
    for n, s_ in specs.items():
        if not s_.perm:
            continue
        kind = s_.perm[0]
        if kind == "units":
            s = s_.perm[1]
            # a unit is its unit id, or the ad itself when the unit id is missing
            uid = s.unit_id.astype(str).where(
                s.unit_id.notna(), "ad:" + s.listing_id.astype(str)
            )
            key = s.building + "|" + uid
            u = codes(key.to_numpy())
            ub = s.groupby(u).building.first()
            order = np.argsort(u, kind="stable")
            cnt = np.bincount(u)
            start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
            prep[n] = (
                codes(ub.to_numpy()),
                u,
                s_.X[order, 0],
                start,
                cnt,
            )
        elif kind == "lines":
            s = s_.perm[1]
            lines = s.drop_duplicates("bl")[
                ["bl", "building", "line_view"]
            ].reset_index(drop=True)
            prep[n] = (
                codes(lines.building.to_numpy()),
                lines.line_view.to_numpy(float),
                pd.Index(lines.bl).get_indexer(s.bl),
            )
        elif kind == "buildings":
            s = s_.perm[1]
            cols = {"front": s.f.to_numpy(float)}
            if "front_prestige" in s_.perm[2]:
                cols = {
                    "front_prestige": (s.front & s.prestige).to_numpy(float),
                    "front_other": (s.front & ~s.prestige).to_numpy(float),
                }
            b = s.drop_duplicates("building").reset_index(drop=True)
            idx = pd.Index(b.building).get_indexer(s.building)
            first = s.drop_duplicates("building").index.to_numpy()
            vals = np.column_stack([cols[c][first] for c in s_.perm[2]])
            prep[n] = (codes(b.cell150.to_numpy()), vals, idx)
    for _ in range(reps):
        for n, s_ in specs.items():
            if not s_.perm:
                continue
            kind = s_.perm[0]
            if kind == "units":
                g, u, marks, start, cnt = prep[n]
                t = shuffle_within(np.arange(len(cnt)), g, rng)[u]
                pick = start[t] + (rng.random(len(u)) * cnt[t]).astype(int)
                X = s_.X.copy()
                X[:, 0] = marks[pick]
            elif kind == "lines":
                g, vals, idx = prep[n]
                X = s_.X.copy()
                X[:, 0] = shuffle_within(vals, g, rng)[idx]
            else:
                g, vals, idx = prep[n]
                perm = shuffle_within(np.arange(len(vals)), g, rng)
                X = s_.X.copy()
                X[:, : vals.shape[1]] = vals[perm][idx]
            null[n].append(pct(s_.ab.beta(X)[0][: s_.k]))
    res["perm_reps"] = reps
    res["perm_seconds"] = time.time() - t1
    for n, vals in null.items():
        vals = np.array(vals)
        for i, t in enumerate(specs[n].names[: specs[n].k]):
            term = res["specs"][n]["terms"][t]
            term["null_pct"] = quantiles(vals[:, i])
            term["null_share_below"] = float((vals[:, i] < term["pct"]).mean())
        if n == "prestige":
            dn = vals[:, 0] - vals[:, 1]
            c = res["contrasts"]["prestige minus other"]
            c["null_pct_points"] = quantiles(dn)
    res["seconds"] = time.time() - t0
    with open(f"{out_dir}/results.json", "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
