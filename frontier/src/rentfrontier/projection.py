"""Projection of a rich reference fit onto cheaper model structures.

    python -m rentfrontier.projection [--reference m8-drift-desc-v1-rows-b7c196f]

Projection predictive selection (Piironen, Paasiniemi and Vehtari 2020),
first version: a *mean projection*. The reference's posterior-mean fitted
log rent mu_ref over the row split's training rows is the target. Each
candidate structure is fit to that target (not to the data) by penalized
least squares, with each term's penalty sigma^2 / tau^2 taken from the
reference's own estimated scales (tau: building, walk, unit, slope and
curve scales; sigma: its noise scale). Random walks (the market trend, the
bedroom-group curves, the per-building walk) are parameterized by their
independent steps, so the penalty is the walk prior.

Scores, per candidate:
- loss: log density the projection loses against the reference on the
  training rows, both scored with the reference's Student-t noise
  (sigma, nu). Zero means the cheaper structure reproduces the reference's
  predictions; the number is in the same units as ELPD.
- captured: share of the reference's fitted variation (Var mu_ref) the
  projection reproduces.

Limits of this version: one projection of the posterior mean (not one per
draw), Gaussian ridge penalties for Student-t unit effects, and in-sample
scoring. It ranks structures by how much of the reference's description
they can hold; the candidates it favours are then fit natively and scored
with PSIS-LOO.

Writes /data1/apartments/frontier/projection/<reference>-<commit>/result.json.
Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

from . import data, explain, features, model, splits
from .run import git, hardware

PROJECTION_ROOT = data.OUTPUT_ROOT / "projection"
REFERENCE = "m8-drift-desc-v1-rows-b7c196f"
FEATURE_SLOPES = ("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3")


@dataclass(frozen=True)
class Structure:
    """Which terms a candidate has (the fields mirror `model.ModelConfig`)."""

    name: str
    features: str = "base-v1"
    trend_knot_months: int = 1
    bedroom_time: bool = False
    building_walk: bool = False
    bedroom_slope: bool = False
    feature_slopes: bool = False
    units: bool = True
    unit_drift: bool = False
    native: str | None = None  # model name of a native fit with this structure


def _with(base: Structure, name, **kw):
    return Structure(**{**asdict(base), "name": name, "native": None, **kw})


M0 = Structure("m0", native="m0-base")
M1 = _with(M0, "m1", building_walk=True)
CANDIDATES = [
    M0,
    _with(M0, "m0 + desc", features="desc-v1"),
    _with(M0, "m0 quarterly", trend_knot_months=3),
    _with(M0, "m0 + bedroom slope", bedroom_slope=True),
    _with(M0, "m0 + bedroom slope + desc", bedroom_slope=True, features="desc-v1"),
    _with(M0, "m0 + feature slopes", feature_slopes=True),
    _with(
        M0,
        "m0 + bedroom and feature slopes + desc",
        bedroom_slope=True,
        feature_slopes=True,
        features="desc-v1",
    ),
    _with(M0, "m0 + unit drift", unit_drift=True),
    _with(M0, "m0 without units", units=False),
    Structure("m1", building_walk=True, native="m1-walk"),
    _with(M1, "m1 + desc", features="desc-v1"),
    _with(
        M1, "m1 + bedroom slope (m5-nocurves)", bedroom_slope=True, trend_knot_months=3
    ),
    Structure(
        "m5-nocurves",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        native="m5-nocurves",
    ),
    Structure(
        "m5-quarterly",
        building_walk=True,
        bedroom_slope=True,
        bedroom_time=True,
        trend_knot_months=3,
        native="m5-quarterly",
    ),
    Structure(
        "m6",
        building_walk=True,
        bedroom_slope=True,
        bedroom_time=True,
        trend_knot_months=3,
        feature_slopes=True,
        native="m6-slopes",
    ),
    Structure(
        "m6 + desc",
        features="desc-v1",
        building_walk=True,
        bedroom_slope=True,
        bedroom_time=True,
        trend_knot_months=3,
        feature_slopes=True,
    ),
    Structure(
        "m6 without curves + desc",
        features="desc-v1",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        feature_slopes=True,
    ),
    Structure(
        "m8 without curves + desc",
        features="desc-v1",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        feature_slopes=True,
        unit_drift=True,
    ),
    Structure(
        "m5-nocurves + desc",
        features="desc-v1",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
    ),
    Structure(
        "m8 structure + desc",
        features="desc-v1",
        building_walk=True,
        bedroom_slope=True,
        bedroom_time=True,
        trend_knot_months=3,
        feature_slopes=True,
        unit_drift=True,
        native="m8-drift",
    ),
]


def walk_knots(index, n_groups, position, frac, n_knots, rows, tau):
    """Per-group random walks over knots (knot 0 pinned at 0), as knot values.

    A row at knot k with weight frac on knot k+1 reads (1 - frac) v_k +
    frac v_{k+1}. The walk prior is a first-difference penalty
    sum_k (v_k - v_{k-1})^2 / tau^2, banded within each group."""
    m = n_knots - 1  # free knots 1..n_knots-1
    r, c, v = [], [], []
    for knot, w in ((position, 1.0 - frac), (position + 1, frac)):
        ok = (knot >= 1) & (knot <= m) & (w != 0)
        idx = np.flatnonzero(ok)
        r.append(idx)
        c.append(index[idx] * m + knot[idx] - 1)
        v.append(np.broadcast_to(w, (rows,))[idx])
    z = sp.csr_matrix(
        (np.concatenate(v), (np.concatenate(r), np.concatenate(c))),
        shape=(rows, n_groups * m),
    )
    diff = sp.eye(m, format="csr") - sp.eye(m, k=-1, format="csr")
    pen = sp.kron(sp.identity(n_groups), (diff.T @ diff) / tau**2, format="csr")
    return z, pen


def indicator(index, n, rows, values=None):
    v = np.ones(rows) if values is None else values
    return sp.csr_matrix((v, (np.arange(rows), index)), shape=(rows, n))


def design(s: Structure, a, x, names, n_months, n_build, n_units, scales):
    """Sparse columns and the prior's penalty matrix (inverse prior covariance)."""
    rows = len(a.y)
    blocks, pens = [], []

    def add(block, tau=None, pen=None):
        blocks.append(block)
        pens.append(pen if pen is not None else sp.identity(block.shape[1]) / tau**2)

    add(sp.csr_matrix(np.ones((rows, 1))), 10.0)
    add(sp.csr_matrix(x), 0.5)
    k = s.trend_knot_months
    n_knots = int(np.ceil((n_months - 1) / k)) + 1
    zt, pt = walk_knots(
        np.zeros(rows, int),
        1,
        a.month // k,
        (a.month % k) / k,
        n_knots,
        rows,
        # The reference's walk scale is per step of its own knot spacing; a
        # random walk's variance per step grows with the step length.
        scales["trend_scale"] * math.sqrt(k / scales["trend_knot_months"]),
    )
    add(zt, pen=pt)
    add(indicator(a.calendar, 12, rows), scales["season_scale"])
    if s.bedroom_time:
        kb = 3
        nb = int(np.ceil((n_months - 1) / kb)) + 1
        others = a.bed_group != 1  # 1-bedroom is the reference curve
        zb, pb = walk_knots(
            np.where(others, a.bed_group, 0),
            4,
            a.month // kb,
            (a.month % kb) / kb,
            nb,
            rows,
            scales["bedroom_time_scale"],
        )
        add(sp.diags(others.astype(float)) @ zb, pen=pb)
    add(indicator(a.building, n_build, rows), scales["building_scale"])
    if s.building_walk:
        zw, pw = walk_knots(
            a.building,
            n_build,
            a.knot,
            a.knot_frac,
            model.n_knots(n_months),
            rows,
            scales["walk_scale"],
        )
        add(zw, pen=pw)
    if s.bedroom_slope:
        add(
            indicator(a.building, n_build, rows, a.beds_centered),
            scales["bedroom_slope_scale"],
        )
    if s.feature_slopes:
        for j, fname in enumerate(FEATURE_SLOPES):
            add(
                indicator(a.building, n_build, rows, x[:, names.index(fname)]),
                scales["fslope_scales"][j],
            )
    if s.units:
        add(indicator(a.unit, n_units, rows), scales["unit_scale"])
    if s.unit_drift:
        add(indicator(a.unit, n_units, rows, a.unit_time), scales["unit_drift_scale"])
    return sp.hstack(blocks).tocsc(), sp.block_diag(pens, format="csc")


def t_logpdf(r, nu, sigma):
    from scipy.special import gammaln

    z = r / sigma
    return (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
        - 0.5 * np.log(nu * math.pi)
        - np.log(sigma)
        - (nu + 1) / 2 * np.log1p(z * z / nu)
    )


def project(reference: str, candidates=CANDIDATES):
    _, result, kept = explain.load_run(reference)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    heldout = splits.SPLITS[result["split"]](frame)
    frame = data.apply_rules(frame, result.get("data_rules", ()))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    names = [str(n) for n in feats.names]
    # Posterior-mean fitted log rent (offset removed), in row chunks to bound memory.
    parts = []
    train_idx = np.flatnonzero(~heldout)
    for chunk in np.array_split(train_idx, max(1, len(train_idx) // 6000)):
        mask = np.zeros(len(frame), dtype=bool)
        mask[chunk] = True
        a = model.row_arrays(prep, frame, mask)
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            model.walk_spacing(config),
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            [names.index(n) for n in config.feature_slopes],
        )
        parts.append(sum(terms.values()).mean(0) - prep.offset)
    mu_ref = np.concatenate(parts)
    y = prep.train.y
    sigma, nu = float(kept["sigma"].mean()), float(kept["nu"].mean())
    scales = {
        k: float(kept[k].mean())
        for k in (
            "trend_scale",
            "season_scale",
            "bedroom_time_scale",
            "building_scale",
            "walk_scale",
            "bedroom_slope_scale",
            "unit_scale",
            "unit_drift_scale",
        )
        if k in kept
    }
    scales["fslope_scales"] = kept["fslope_scales"].mean(0).tolist()
    scales["trend_knot_months"] = config.trend_knot_months
    elpd_ref = float(t_logpdf(y - mu_ref, nu, sigma).sum())
    base_x = features.build("base-v1", frame, ~heldout)
    xs = {
        "desc-v1": feats.values[~heldout],
        "base-v1": base_x.values[~heldout],
    }
    xnames = {"desc-v1": names, "base-v1": [str(n) for n in base_x.names]}
    var_ref = float(np.var(mu_ref))
    out = []
    for s in candidates:
        t0 = time.perf_counter()
        z, pen = design(
            s,
            prep.train,
            xs[s.features],
            xnames[s.features],
            len(prep.periods),
            len(prep.buildings),
            len(prep.units),
            scales,
        )
        # Posterior mode of the structure fit to mu_ref with the reference's
        # noise scale: (z'z + sigma^2 P) b = z' mu_ref.
        # Conjugate gradients with a Jacobi preconditioner: only sparse
        # products, no factorization fill (building walks couple to units).
        system = (z.T @ z + sigma**2 * pen).tocsr()
        precond = sp.diags(1.0 / system.diagonal())
        b, info = cg(system, z.T @ mu_ref, M=precond, rtol=1e-10, maxiter=20000)
        if info != 0:
            raise RuntimeError(f"CG did not converge for {s.name} (info {info})")
        m = z @ b
        loss = elpd_ref - float(t_logpdf(y - m, nu, sigma).sum())
        out.append(
            {
                **asdict(s),
                "columns": int(z.shape[1]),
                "loss": loss,
                "captured": 1.0 - float(np.var(mu_ref - m)) / var_ref,
                "rms_log_diff": float(np.sqrt(np.mean((mu_ref - m) ** 2))),
                "seconds": time.perf_counter() - t0,
            }
        )
        print(
            f"{s.name:44s} loss {loss:9.1f}  captured {100 * out[-1]['captured']:6.2f}%  "
            f"({out[-1]['columns']} columns, {out[-1]['seconds']:.0f} s)",
            flush=True,
        )
    return {
        "reference": reference,
        "reference_commit": result["commit"],
        "rows": len(y),
        "reference_elpd_in_sample": elpd_ref,
        "noise": {"sigma": sigma, "nu": nu},
        "scales": scales,
        "candidates": out,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reference", default=REFERENCE)
    parser.add_argument(
        "--dev", action="store_true", help="allow a dirty tree; print only"
    )
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty and not args.dev:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    t0 = time.perf_counter()
    record = project(args.reference)
    record.update(
        commit=commit,
        dirty=bool(dirty),
        seconds=time.perf_counter() - t0,
        hardware=hardware(),
    )
    if args.dev:
        return
    out_dir = PROJECTION_ROOT / f"{args.reference}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(record, indent=2))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
