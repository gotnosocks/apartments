"""Rescore a recorded run's held-out rows from its kept joint draws.

    JAX_PLATFORMS=cpu python -m rentfrontier.rescore <run-name>

No refit: the run's posterior.npz keeps one joint draw of every effect every
`keep_every` iterations (e.g. 16 chains x 20). For each kept draw this
rebuilds every held-out row's log predictor (`explain.log_terms`, the same
additive terms the app shows) and scores the row twice:

- exact: the current `collect.heldout_logpdf_given_mu` (unseen Student-t
  units with drift by 2-D quadrature, commit ad49968);
- approximate: the scoring used by runs before ad49968 (the drift folded
  into a widened unit scale), for a same-draw comparison.

The on-device score of the original run averages over every draw (e.g.
32,000); a kept-draw rescore averages over far fewer, so its Monte Carlo
error is larger. The "approximate" line checks the reconstruction: it should
match the recorded score to within that error. The exact-minus-approximate
difference on the same draws is the correction to the recorded score.

Writes /data1/apartments/frontier/rescores/<run>-<commit>/{result.json,
heldout.npz}. Refuses a dirty tree, like `run.py`.
"""

from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np

from . import data, explain, features, model, splits
from .run import REFERENCES, git, hardware, score

RESCORES = data.OUTPUT_ROOT / "rescores"
UNIT_TERMS = ("unit", "unit_drift")


def _approx_unseen_logpdf(p, test, mu, u):
    """Held-out density as scored before ad49968 (for comparison only)."""
    import jax.numpy as jnp
    from jax.scipy.special import logsumexp

    from .collect import GH_NODES, student_t_logpdf

    seen = test.unit >= 0
    drift_scale = p["unit_drift_scale"]
    unit_scale = jnp.sqrt(p["unit_scale"] ** 2 + (drift_scale * test.unit_time) ** 2)
    lp_seen = student_t_logpdf(test.y - mu - u, p["nu"], p["sigma"])
    x, w = (jnp.asarray(a, mu.dtype) for a in np.polynomial.hermite.hermgauss(GH_NODES))
    shifted = (
        test.y[:, None] - mu[:, None] - math.sqrt(2.0) * unit_scale[:, None] * x[None]
    )
    lp_new = logsumexp(
        student_t_logpdf(shifted, p["nu"], p["sigma"]) + jnp.log(w)[None], axis=1
    ) - 0.5 * math.log(math.pi)
    nu_u = p["unit_nu"]
    z = jnp.linspace(-40.0, 40.0, 801, dtype=mu.dtype)
    log_wz = student_t_logpdf(z, jnp.maximum(nu_u, 1e-3), 1.0) + math.log(0.1)
    shifted_t = test.y[:, None] - mu[:, None] - unit_scale[:, None] * z[None]
    lp_new_t = logsumexp(
        student_t_logpdf(shifted_t, p["nu"], p["sigma"]) + log_wz[None], axis=1
    )
    lp_new = jnp.where(nu_u > 0, lp_new_t, lp_new)
    return jnp.where(seen, lp_seen, lp_new)


def _pooled(lp):
    """(chains, per_chain, rows) per-draw densities -> pooled and per-chain lpd."""
    from scipy.special import logsumexp

    c, k, n = lp.shape
    lpd = logsumexp(lp.reshape(c * k, n), axis=0) - math.log(c * k)
    lpd_chain = logsumexp(lp, axis=1) - math.log(k)
    return lpd, lpd_chain


def rescore(name: str):
    import jax
    import jax.numpy as jnp

    jax.config.update("jax_enable_x64", True)
    from . import collect

    run_dir, result, kept = explain.load_run(name)
    chains, per_chain = np.load(run_dir / "posterior.npz", allow_pickle=True)[
        "kept/alpha"
    ].shape
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    heldout = splits.SPLITS[result["split"]](frame)
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    if not np.array_equal(
        prep.test_audit_id,
        np.load(run_dir / "heldout.npz", allow_pickle=True)["audit_id"],
    ):
        raise SystemExit("held-out rows differ from the run's recorded rows")
    test = prep.test
    terms = explain.log_terms(
        kept,
        test,
        feats.groups,
        config.building_walk,
        config.bedroom_time,
        config.bedroom_slope,
        prep.offset,
        [feats.names.index(n) for n in config.feature_slopes],
    )
    # y in Arrays is log rent minus the offset; `market` includes the offset.
    mu = sum(v for k, v in terms.items() if k not in UNIT_TERMS) - prep.offset
    u = sum(terms[k] for k in UNIT_TERMS if k in terms)
    names = ("nu", "sigma", "unit_scale", "unit_drift_scale", "unit_nu")
    scal = {k: kept[k] if k in kept else np.zeros(len(mu)) for k in names}
    test_j = test.map(jnp.asarray)

    @jax.jit
    def one(mu_d, u_d, s):
        exact = collect.heldout_logpdf_given_mu(s, test_j, mu_d, u_d, unseen=True)
        approx = _approx_unseen_logpdf(s, test_j, mu_d, u_d)
        return exact, approx

    exact, approx = [], []
    for d in range(len(mu)):
        e, a = one(mu[d], u[d], {k: v[d] for k, v in scal.items()})
        exact.append(np.asarray(e))
        approx.append(np.asarray(a))
    shape = (chains, per_chain, len(test.y))
    out = {}
    for label, lp in (("exact", exact), ("approximate", approx)):
        lpd, lpd_chain = _pooled(np.stack(lp).reshape(shape))
        out[label] = (
            lpd,
            lpd_chain,
            score(result["split"], prep.test_audit_id, lpd, lpd_chain),
        )
    diff = out["exact"][0] - out["approximate"][0]
    recorded = result["score"]
    return {
        "source_run": name,
        "source_commit": result["commit"],
        "split": result["split"],
        "draws": {"chains": chains, "per_chain": per_chain},
        "rows": len(test.y),
        "unseen_unit_rows": int((test.unit < 0).sum()),
        "recorded": {
            "elpd": recorded["elpd"],
            "delta_elpd": recorded.get("vs_promoted", {}).get("delta_elpd"),
            "delta_elpd_se": recorded.get("vs_promoted", {}).get("delta_elpd_se"),
            "draws": result["sampler_settings"]["chains"]
            * result["sampler_settings"]["draws"],
        },
        "approximate": out["approximate"][2],
        "exact": out["exact"][2],
        "exact_minus_approximate": {
            "elpd": float(diff.sum()),
            "se": float(diff.std(ddof=1) * math.sqrt(len(diff))),
            "unseen_rows_only": float(diff[test.unit < 0].sum()),
        },
        "exact_recorded_equivalent": {
            "note": "recorded dELPD + (exact - approximate) on the same kept draws",
            "delta_elpd": (recorded.get("vs_promoted", {}).get("delta_elpd") or 0.0)
            + float(diff.sum()),
        },
    }, out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out_dir = RESCORES / f"{args.run}-{commit[:7]}"
    if (out_dir / "result.json").exists():
        raise SystemExit(f"{out_dir} already has a result")
    t0 = time.perf_counter()
    record, out = rescore(args.run)
    record.update(
        commit=commit,
        dirty=False,
        seconds=time.perf_counter() - t0,
        hardware=hardware(),
        references={k: str(v) for k, v in REFERENCES.items()},
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "heldout.npz",
        audit_id=np.load(explain.RUNS / args.run / "heldout.npz", allow_pickle=True)[
            "audit_id"
        ],
        lpd=out["exact"][0],
        lpd_approximate=out["approximate"][0],
        lpd_chain=out["exact"][1].astype(np.float32),
    )
    (out_dir / "result.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
