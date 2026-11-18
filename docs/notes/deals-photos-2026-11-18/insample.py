"""In-sample distance of every training ad's log ask from the population mean of a drift fit.

    systemd-run --user --scope -q -p MemoryMax=9G env JAX_PLATFORMS=cpu PYTHONPATH=frontier/src \
        /data1/apartments/venvs/bridge-frontier/bin/python docs/notes/deals-photos-2026-11-18/insample.py

The fit is `drift-building-b0-latest-67d14e17-b9` (`rentfrontier.drift_building`). Its row
mean is

    x beta + L(t) + level of the building + path of the building at the row's quarter + u

with u the unit's own level, which the sampler integrates out. The run keeps the draws of
beta, L, the location waves and the buildings' levels. It keeps neither the buildings'
quarterly paths nor anything for a training row.

The script works in two steps.

1. `static_part` rebuilds the design of every row of the run's dataset with
   `drift.design`, as `b0.main_run` did, and takes x beta + L(t) + the building's level at
   the posterior means of the kept draws. That sum is linear in the kept quantities, so
   the means give its posterior mean. The arrays are cached under `OUT`, because the design
   takes several minutes. The design's matrix is 3.8 GB in float64 and the design modules
   stack it several times over, so `lean_stacks` has numpy stack any array of a million
   rows or more in float32 while the design is built. The coding of the features is the
   repo's, and x beta moves by about 1e-6.

2. `paths` estimates what the run did not keep. With the kept quantities and the scales at
   their posterior means, a training row's remainder is

       e = path of the building at the quarter + s of the unit + d of the unit at the date
           + Student-t noise

   with the path an AR(1) process over quarters, s a Normal level and d an OU process.
   Each of the three is a Gaussian Markov chain, so the estimate comes from a sparse
   linear system over the paths' cells, the units' s and the d at every ad's date. The
   Student-t noise enters by EM: each round weighs a row by
   (nu + 1) / (nu + (remainder / sigma)^2) and solves the system again. The held-out rows
   sit in the system as nodes with no observation, so the solution also gives the
   location the run kept for them (`pred_loc`), and the script compares the two.

The estimate of step 2 is a posterior mode at fixed scales. The run's own mean averages
over the draws of the scales and of the noise weights, so the two differ, and the printed
comparison on the held-out rows measures by how much.

The output has a row for every training ad:

- `listing_id`, `building`, `unit_id`, `latest_day`, `group` (the noise group), `y`;
- `static`: x beta + L(t) + the building's level;
- `bld_path`: the estimated path of the building at the ad's quarter;
- `pop` = `static` + `bld_path`, `resid` = `y` - `pop`;
- `z` = `resid` / sqrt(unit_sd^2 + sigma_group^2), at the posterior means;
- `unit_resid`, `unit_n`: the mean of `resid` over the unit's training ads and their
  number, with a unit the model's (building and `unit_id`, an ad with no `unit_id` alone);
- `within` = `resid` - `unit_resid`;
- `unit_level`: the estimated s + d of the unit at the ad's date.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import cg

RUN = Path("/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9")
OUT = Path("/data1/apartments/tmp/deals-photos-2026-11-18")
CACHE = OUT / "insample-static.npz"
EM_ROUNDS = 30
PER_YEAR = 4  # the buildings' steps a year (`drift.groups_of`)


def kept_mean(z, name):
    """The mean over chains and kept draws of the run's kept array `name`."""
    v = z["kept/" + name]
    return v.reshape(-1, *v.shape[2:]).mean(axis=0, dtype=np.float64)


@contextlib.contextmanager
def lean_stacks(rows=1_000_000):
    """While open, `np.column_stack` and `np.hstack` build a numeric array of `rows` rows
    or more column by column in float32. Every other call goes to numpy's own function."""
    own = np.column_stack, np.hstack

    def lean(orig, columns):
        def stack(arrays, *args, **kw):
            arrays = [np.asarray(v) for v in arrays]
            big = (
                not args
                and not kw
                and arrays
                and all(len(v) >= rows and v.dtype.kind in "fiub" for v in arrays)
                and all(v.ndim == 2 or (columns and v.ndim == 1) for v in arrays)
            )
            if not big:
                return orig(arrays, *args, **kw)
            widths = [1 if v.ndim == 1 else v.shape[1] for v in arrays]
            out = np.empty((len(arrays[0]), sum(widths)), np.float32)
            at = 0
            for v, w in zip(arrays, widths):
                out[:, at : at + w] = v.reshape(len(v), w)
                at += w
            return out

        return stack

    np.column_stack, np.hstack = lean(own[0], True), lean(own[1], False)
    try:
        yield
    finally:
        np.column_stack, np.hstack = own


def static_part() -> dict:
    """Every dataset row's x beta + L(t) + building level at the posterior means, with the
    row's building, unit, time in years, noise group and y, from the design the fit built."""
    if CACHE.exists():
        return dict(np.load(CACHE))
    from rentfrontier import (
        b0,
        building_zones_floor_asof,
        drift,
        drift_building,
        drift_score,
        splits,
    )

    record = json.loads((RUN / "result.json").read_text())
    z = np.load(RUN / "posterior.npz")
    held = z["heldout"]
    frame = b0.load_frame(drift_score.dataset_dir(RUN))
    assert np.array_equal(splits.SPLITS[record["split"]](frame), held), (
        "the split moved"
    )
    building_zones_floor_asof.SPLIT = record["split"]
    with lean_stacks():
        d = drift_building.design(frame)
    del frame
    assert list(d.names) == [str(n) for n in z["names"]], "the design's columns moved"
    now = drift_building.run_record(d)
    for k in sorted(set(now) & set(record)):
        if k not in ("unit", "local") and str(now[k]) != str(record[k]):
            print(
                f"record differs at {k}: {str(now[k])[:300]} / {str(record[k])[:300]}"
            )
    # The waves are centred on the training rows' buildings (`building_zones.wave_matrix`),
    # which reads only the design's sites and surfaces.
    train = dataclasses.replace(d, site=d.site[~held])
    waves, _ = drift.wave_matrix(train)
    level = waves @ kept_mean(z, "gp_w") + kept_mean(z, "bld")
    L = kept_mean(z, "L")
    beta = kept_mean(z, "beta")
    xb = np.concatenate(
        [d.x[a : a + 100_000] @ beta for a in range(0, len(d.y), 100_000)]
    )
    static = xb + (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1] + level[d.site]
    out = dict(
        static=static,
        site=d.site,
        unit=d.unit,
        years=drift.years(d),
        group=d.group,
        y=d.y,
        held=held,
    )
    np.savez(CACHE, **out)
    return out


def chain(group, t, corr, var):
    """The prior precision of Gaussian Markov chains, as a sparse matrix over the nodes.
    Nodes are sorted by `group` and then `t`, and each group is a stationary chain with
    variance `var` and correlation `corr(gap)` between neighbours `gap` apart in `t`."""
    n = len(group)
    link = np.flatnonzero(group[1:] == group[:-1])
    r = corr((t[1:] - t[:-1])[link])
    w = 1.0 / (var * (1.0 - r * r))
    diag = np.full(n, 1.0 / var)
    # A linked pair adds r^2 w to its first node's precision and w - 1 / var to its
    # second's, since the second's own term is the innovation's and not the stationary one.
    np.add.at(diag, link, r * r * w)
    np.add.at(diag, link + 1, w - 1.0 / var)
    off = sp.coo_matrix((-r * w, (link, link + 1)), shape=(n, n))
    return (sp.diags(diag) + off + off.T).tocsr()


def nodes(a, b):
    """The distinct pairs of (a, b) sorted by a then b, as the two columns, and each
    row's place among them."""
    order = np.lexsort((b, a))
    a_, b_ = a[order], b[order]
    first = np.r_[True, (a_[1:] != a_[:-1]) | (b_[1:] != b_[:-1])]
    place = np.empty(len(a), np.int64)
    place[order] = np.cumsum(first) - 1
    return a_[first], b_[first], place


def paths(s: dict, z) -> dict:
    """The EM estimate of each row's building path and unit level (see the module
    docstring), for every row whose unit has a training row, and the path alone for the
    rest."""
    ss, sd, tau = (float(kept_mean(z, k)) for k in ("unit_sd", "drift_sd", "drift_tau"))
    a_sd, rho = (float(kept_mean(z, k)) for k in ("building_ar_sd", "building_ar_rho"))
    sigma, nu = kept_mean(z, "sigma"), float(kept_mean(z, "nu"))
    print(
        f"scales: unit_sd {ss:.4f} drift_sd {sd:.4f} drift_tau {tau:.2f} "
        f"path sd {a_sd:.4f} rho {rho:.3f} sigma {sigma.round(4)} nu {nu:.3f}"
    )
    train = ~s["held"]
    step = np.floor(s["years"] * PER_YEAR).astype(np.int64)
    c_site, c_step, cell = nodes(s["site"], step)
    known = s["unit"] >= 0
    n_cells, n_units = len(c_site), int(s["unit"].max()) + 1
    d_unit, d_t, dn = nodes(s["unit"][known], s["years"][known])
    prior = sp.block_diag(
        [
            chain(c_site, c_step.astype(float), lambda g: rho**g, a_sd**2),
            sp.diags(np.full(n_units, 1.0 / ss**2)),
            chain(d_unit, d_t, lambda g: np.exp(-g / tau), sd**2),
        ],
        format="csr",
    )
    # Each row reads its cell, its unit's s and its unit's d at its date.
    rows = len(s["y"])
    place = np.flatnonzero(known)
    H = sp.coo_matrix(
        (
            np.ones(rows + 2 * len(place)),
            (
                np.r_[np.arange(rows), place, place],
                np.r_[cell, n_cells + s["unit"][known], n_cells + n_units + dn],
            ),
        ),
        shape=(rows, prior.shape[0]),
    ).tocsr()
    Ht = H[train]
    e = (s["y"] - s["static"])[train]
    sig = sigma[s["group"][train]]
    lam = np.ones(len(e))
    x = np.zeros(prior.shape[0])
    for k in range(EM_ROUNDS):
        c = lam / sig**2
        P = (prior + Ht.T @ sp.diags(c) @ Ht).tocsr()
        inv = 1.0 / P.diagonal()
        x_new, info = cg(
            P, Ht.T @ (c * e), x0=x, M=sp.diags(inv), rtol=1e-8, maxiter=5000
        )
        move = float(np.abs(x_new - x).max())
        x = x_new
        lam = (nu + 1.0) / (nu + ((e - Ht @ x) / sig) ** 2)
        print(f"EM round {k + 1}: cg info {info}, largest move {move:.2e}", flush=True)
        if move < 1e-5:
            break
    path = x[:n_cells][cell]
    return dict(path=path, unit_level=H @ x - path)


def main():
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    s = static_part()
    print(f"static part ready, {time.perf_counter() - t0:.0f}s", flush=True)
    z = np.load(RUN / "posterior.npz")
    est = paths(s, z)
    held, train = s["held"], ~s["held"]
    pop = s["static"] + est["path"]

    # The run's kept location of the held-out rows against this script's.
    loc = kept_mean(z, "pred_loc")
    assert np.allclose(z["kept/pred_y"], s["y"][held]), "the held-out rows' y moved"
    new = s["unit"][held] < 0
    gap = loc - pop[held]
    print(f"held-out rows: {held.sum()}, of units with no training row: {new.sum()}")
    if new.any():
        print(
            f"  those rows, pred_loc - pop: max abs {np.abs(gap[new]).max():.2e}, "
            f"rms {np.sqrt(np.mean(gap[new] ** 2)):.2e}"
        )
        print(
            "  those rows, pred_loc - static: max abs "
            f"{np.abs(loc - s['static'][held])[new].max():.2e}"
        )
    full = gap - est["unit_level"][held]
    print(
        f"  all held-out rows, pred_loc - (pop + unit level): rms "
        f"{np.sqrt(np.mean(full**2)):.4f}, median abs {np.median(np.abs(full)):.4f}, "
        f"99% abs {np.quantile(np.abs(full), 0.99):.4f}, max abs {np.abs(full).max():.4f}"
    )
    print(
        "  the same without the path or the unit level: rms "
        f"{np.sqrt(np.mean((loc - s['static'][held]) ** 2)):.4f}"
    )

    resid = (s["y"] - pop)[train]
    unit = s["unit"][train]
    unit_n = np.bincount(unit)
    unit_resid = np.bincount(unit, weights=resid) / unit_n
    hu = s["unit"][held]
    old = hu >= 0
    print(
        "  held-out rows of units with training rows, corr(pred_loc - pop, unit_resid): "
        f"{np.corrcoef(gap[old], unit_resid[hu[old]])[0, 1]:.4f}"
    )

    sigma = kept_mean(z, "sigma")
    scale = np.sqrt(float(kept_mean(z, "unit_sd")) ** 2 + sigma[s["group"][train]] ** 2)
    from rentfrontier import drift_score

    frame = pd.read_parquet(
        drift_score.dataset_dir(RUN) / "rows.parquet",
        columns=["listing_id", "building", "unit_id", "latest_day"],
    )[train].reset_index(drop=True)
    frame["group"] = s["group"][train]
    frame["y"] = s["y"][train]
    frame["static"] = s["static"][train]
    frame["bld_path"] = est["path"][train]
    frame["pop"] = pop[train]
    frame["resid"] = resid
    frame["z"] = resid / scale
    frame["unit_resid"] = unit_resid[unit]
    frame["unit_n"] = unit_n[unit]
    frame["within"] = resid - unit_resid[unit]
    frame["unit_level"] = est["unit_level"][train]
    frame.to_parquet(OUT / "insample.parquet", index=False)
    qs = [0.01, 0.05, 0.5, 0.95, 0.99]
    print(f"training rows: {len(frame)}")
    print("z quantiles 1/5/50/95/99%:", frame.z.quantile(qs).round(3).tolist())
    units3 = unit_resid[unit_n >= 3]
    print(
        f"unit_resid over {len(units3)} units with 3 or more training ads:",
        np.quantile(units3, qs).round(4).tolist(),
    )
    print(f"wrote {OUT / 'insample.parquet'}, {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
