"""Predictive scores for the rows a drift run predicted (`rentfrontier.drift`).

    python -m rentfrontier.drift_score RUN [--out FILE.npz] [--runs DIR]

A drift run keeps, for every row outside its training rows and every kept draw, the row's
location `pred_loc` (x beta + L(t) + eta + the mean of its unit's level u) and the sd of u,
`pred_unit_sd`. Given a draw, the row's log rent is

    y = pred_loc + pred_unit_sd z + sigma_group t,   z ~ Normal(0, 1),  t ~ StudentT(nu),

so its predictive density is the average over draws of a Student-t smoothed by a Normal. I
integrate z with Gauss-Hermite quadrature. For each row the output holds
- `elpd`: the log predictive density at the row's own y;
- `cdf`: the predictive probability of a log rent below the row's y. For an ad on the market
  this is the share of the model's distribution under the ask, so a low value marks an ask
  that is low for the apartment;
- `q`: the predictive quantiles at `quantiles`, and `pred`, the predictive median;
- `unit_sd`: the mean over draws of the sd of u, which is small for a unit with recent ads
  and sqrt(ss^2 + sd^2) for a unit with none;
- `y` and `group`, and, when the run's dataset is on disk, each row's `listing`, `building`
  and `week` as `docs/notes/conference-followups-2026-10-22/score.py` writes them.

The scores read only the run's posterior.npz, so they need no design and little memory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.special import gammaln, logsumexp

Q = (0.025, 0.05, 0.1, 0.25, 0.75, 0.9, 0.95, 0.975)
NODES = 21
SAMPLES = 4
CHUNK = 2000


def _hermite(nodes: int):
    """Nodes and weights for an average over a standard Normal."""
    x, w = np.polynomial.hermite_e.hermegauss(nodes)
    return x, w / w.sum()


def score_rows(loc, usd, sigma, nu, y, seed=0, nodes=NODES, samples=SAMPLES) -> dict:
    """Scores for a block of rows: `loc` and `usd` (draws, rows), `sigma` (draws, rows) the
    noise scale of each row's group, `nu` (draws,), `y` (rows,)."""
    x, w = _hermite(nodes)
    loc, usd, sigma = (np.asarray(v, float) for v in (loc, usd, sigma))
    nu_ = np.asarray(nu, float)[:, None, None]
    z = (y[None, :, None] - loc[:, :, None] - usd[:, :, None] * x) / sigma[:, :, None]
    lp = (
        gammaln((nu_ + 1) / 2)
        - gammaln(nu_ / 2)
        - 0.5 * np.log(nu_ * np.pi)
        - np.log(sigma[:, :, None])
        - (nu_ + 1) / 2 * np.log1p(z * z / nu_)
    )
    per_draw = logsumexp(lp, axis=2, b=w)
    elpd = logsumexp(per_draw, axis=0) - np.log(loc.shape[0])
    cdf = (stats.t.cdf(z, nu_) * w).sum(axis=2).mean(axis=0)
    rng = np.random.default_rng(seed)
    shape = (samples, *loc.shape)
    rep = (
        loc
        + usd * rng.standard_normal(shape)
        + sigma * rng.standard_t(np.broadcast_to(nu_[:, :, 0], loc.shape), size=shape)
    ).reshape(-1, loc.shape[1])
    q = np.quantile(rep, Q, axis=0).T
    return dict(
        elpd=elpd,
        cdf=cdf,
        q=q.astype(np.float32),
        pred=np.median(rep, axis=0),
        unit_sd=usd.mean(axis=0),
    )


def score_run(run_dir: Path, seed: int = 0) -> dict:
    """Scores for every row the run at `run_dir` predicted."""
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
    for a in range(0, len(y), CHUNK):
        sl = slice(a, a + CHUNK)
        part = score_rows(
            loc[:, sl], usd[:, sl], sig[:, group[sl]], nu, y[sl], seed + a
        )
        for k, v in part.items():
            out[k].append(v)
    res = {k: np.concatenate(v) for k, v in out.items()}
    res |= dict(y=y, group=group, quantiles=np.array(Q), heldout=z["heldout"])
    result = run_dir / "result.json"
    dataset = (
        Path(json.loads(result.read_text())["dataset"]) if result.exists() else None
    )
    if dataset is not None and (dataset / "rows.parquet").exists():
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
    p.add_argument("--runs", default="/data1/apartments/frontier/runs")
    args = p.parse_args(argv)
    run_dir = Path(args.runs) / args.run
    res = score_run(run_dir)
    out = Path(args.out) if args.out else run_dir / "pred_scores.npz"
    np.savez_compressed(out, **res)
    print(json.dumps(summary(res), indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
