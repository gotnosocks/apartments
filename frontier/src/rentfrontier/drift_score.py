"""Predictive scores for the rows a drift run predicted (`rentfrontier.drift`).

    python -m rentfrontier.drift_score RUN [--out FILE.npz] [--runs DIR]

A drift run keeps, for every row outside its training rows and every kept draw, the row's
location `pred_loc` (x beta + L(t) + eta + the mean of its unit's level u) and the sd of u,
`pred_unit_sd`. Given a draw, the row's log rent is

    y = pred_loc + pred_unit_sd z + sigma_group t,   z ~ Normal(0, 1),  t ~ StudentT(nu),

so its predictive density is the average over draws of a Student-t smoothed by a Normal. The
Student-t is a scale mixture of Normals: with lam ~ Gamma(nu / 2, rate nu / 2),

    y | lam ~ Normal(pred_loc, pred_unit_sd^2 + sigma_group^2 / lam),

and I integrate lam on a grid in log lam (`mixture`). The integrand is smooth in log lam
whatever the ratio of the two scales, where a quadrature over z loses the Student-t's peak
once the unit sd is a few times sigma. For each row the output holds
- `elpd`: the log predictive density at the row's own y;
- `cdf`: the predictive probability of a log rent below the row's y. For an ad on the market
  this is the share of the model's distribution under the ask, so a low value marks an ask
  that is low for the apartment;
- `q`: the predictive quantiles at `quantiles`, and `pred`, the predictive median;
- `unit_sd`: the mean over draws of the sd of u, which is small for a unit with recent ads
  and sqrt(ss^2 + sd^2) for a unit with none;
- `y` and `group`, and, when the run's dataset is on disk, each row's `listing`, `building`
  and `day`.

The scores read only the run's posterior.npz, so they need no design. A block of `CHUNK` rows
takes about 1 GB for 800 kept draws.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp, ndtr

from . import run as run_module

Q = (0.025, 0.05, 0.1, 0.25, 0.75, 0.9, 0.95, 0.975)
NODES = 96
SAMPLES = 4
CHUNK = 250


def mixture(nu, nodes: int = NODES):
    """A grid for the Student-t's mixing scale: for each nu, `lam` and the log weights
    `logw`, both (len(nu), nodes), with sum(exp(logw) f(lam)) the mean of f over
    Gamma(nu / 2, rate nu / 2). The grid is even in x = log lam, where the density is
    exp(a x - a e^x) with a = nu / 2, and the trapezoid rule on it converges fast. The
    grid starts where the density is exp(-30) of its peak, moved down by the shift a row 60
    sigma from its location gives the integrand's peak (to lam near a / (a + 1800)), and ends
    past the upper tail's exp(-a e^x)."""
    a = np.asarray(nu, float)[:, None] / 2
    lo = -(1.0 + 30.0 / a) - np.log1p(1800.0 / a)
    hi = np.log(1.0 + 12.0 / np.sqrt(a) + 30.0 / a)
    x = lo + (hi - lo) * np.linspace(0.0, 1.0, nodes)[None, :]
    logw = a * x - a * np.exp(x)
    logw = logw - logsumexp(logw, axis=1, keepdims=True)
    return np.exp(x), logw


def _density(y, loc, usd, sigma, lam, logw):
    """The log density and the cdf at `y` (rows,) of each draw's mixture, (draws, rows)."""
    var = usd[:, :, None] ** 2 + sigma[:, :, None] ** 2 / lam[:, None, :]
    dev = y[None, :, None] - loc[:, :, None]
    lp = logw[:, None, :] - 0.5 * (np.log(2 * np.pi * var) + dev * dev / var)
    cdf = (np.exp(logw)[:, None, :] * ndtr(dev / np.sqrt(var))).sum(axis=2)
    return logsumexp(lp, axis=2), cdf


def score_rows(
    loc, usd, sigma, nu, y, seed=0, nodes=NODES, samples=SAMPLES, at=None
) -> dict:
    """Scores for a block of rows: `loc` and `usd` (draws, rows), `sigma` (draws, rows) the
    noise scale of each row's group, `nu` (draws,), `y` (rows,). With `at` (rows,), also
    `cdf_at`, the predictive probability of a log rent below `at`."""
    loc, usd, sigma = (np.asarray(v, float) for v in (loc, usd, sigma))
    y = np.asarray(y, float)
    nu_ = np.asarray(nu, float)[:, None, None]
    lam, logw = mixture(nu, nodes)
    per_draw, cdf = _density(y, loc, usd, sigma, lam, logw)
    elpd = logsumexp(per_draw, axis=0) - np.log(loc.shape[0])
    cdf = cdf.mean(axis=0)
    rng = np.random.default_rng(seed)
    shape = (samples, *loc.shape)
    rep = (
        loc
        + usd * rng.standard_normal(shape)
        + sigma * rng.standard_t(np.broadcast_to(nu_[:, :, 0], loc.shape), size=shape)
    ).reshape(-1, loc.shape[1])
    q = np.quantile(rep, Q, axis=0).T
    out = dict(
        elpd=elpd,
        cdf=cdf,
        q=q.astype(np.float32),
        pred=np.median(rep, axis=0),
        unit_sd=usd.mean(axis=0),
    )
    if at is not None:
        at = np.asarray(at, float)
        out["cdf_at"] = _density(at, loc, usd, sigma, lam, logw)[1].mean(axis=0)
    return out


def score_run(run_dir: Path, seed: int = 0, at=None) -> dict:
    """Scores for every row the run at `run_dir` predicted. `at` (rows,) asks for `cdf_at`,
    the predictive probability of a log rent below each row's value."""
    z = np.load(run_dir / "posterior.npz")
    if "kept/pred_loc" not in z:
        raise SystemExit(f"{run_dir} predicted no rows")
    flat = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:])  # noqa: E731
    loc, usd, sig, nu = (
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma"),
        flat("nu"),
    )
    y, group = z["kept/pred_y"], z["kept/pred_group"]
    out = {k: [] for k in ("elpd", "cdf", "q", "pred", "unit_sd")}
    if at is not None:
        out["cdf_at"] = []
        at = np.asarray(at, float)
    for a in range(0, len(y), CHUNK):
        sl = slice(a, a + CHUNK)
        part = score_rows(
            loc[:, sl],
            usd[:, sl],
            sig[:, group[sl]],
            nu,
            y[sl],
            seed + a,
            at=None if at is None else at[sl],
        )
        for k, v in part.items():
            out[k].append(v)
    res = {k: np.concatenate(v) for k, v in out.items()}
    res |= dict(y=y, group=group, quantiles=np.array(Q), heldout=z["heldout"])
    dataset = dataset_dir(run_dir)
    if dataset is not None:
        import pandas as pd

        frame = pd.read_parquet(
            dataset / "rows.parquet", columns=["listing_id", "building", "latest_day"]
        )[z["heldout"]]
        res |= dict(
            listing=frame.listing_id.astype(str).to_numpy().astype("U"),
            building=frame.building.astype(str).to_numpy().astype("U"),
            day=frame.latest_day.astype(str).to_numpy().astype("U"),
        )
    return res


def dataset_dir(run_dir: Path) -> Path | None:
    """The folder of the run's dataset: the path its `result.json` names or, for a fit that
    ran on another machine, the dataset of that name in this machine's datasets folder. None
    when neither holds a `rows.parquet`."""
    result = run_dir / "result.json"
    if not result.exists():
        return None
    named = Path(json.loads(result.read_text())["dataset"])
    for folder in (named, run_module.RUNS.parent / "datasets" / named.name):
        if (folder / "rows.parquet").exists():
            return folder
    return None


def summary(res: dict) -> dict:
    """The run's headline scores: total elpd, RMSE and bias of the predictive median, and
    the central intervals' coverage."""
    y, q = res["y"], res["q"]
    cover = {
        "50": float(np.mean((y >= q[:, 3]) & (y <= q[:, 4]))),
        "80": float(np.mean((y >= q[:, 2]) & (y <= q[:, 5]))),
        "90": float(np.mean((y >= q[:, 1]) & (y <= q[:, 6]))),
        "95": float(np.mean((y >= q[:, 0]) & (y <= q[:, 7]))),
    }
    err = y - res["pred"]
    return {
        "rows": int(len(y)),
        "elpd": float(res["elpd"].sum()),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "median_abs_error": float(np.median(np.abs(err))),
        "bias": float(np.mean(err)),
        "coverage": cover,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run")
    p.add_argument("--out")
    p.add_argument("--runs", default=str(run_module.RUNS))
    args = p.parse_args(argv)
    run_dir = Path(args.runs) / args.run
    res = score_run(run_dir)
    out = Path(args.out) if args.out else run_dir / "pred_scores.npz"
    np.savez_compressed(out, **res)
    print(json.dumps(summary(res), indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
