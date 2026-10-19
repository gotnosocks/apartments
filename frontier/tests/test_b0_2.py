import json

import numpy as np
import pytest

from rentfrontier import b0, b0_2
from test_b0 import frame_of

pytest.importorskip("numpyro")


def test_ladder_sums_every_step_at_or_below_the_cell():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    d = b0_2.design(frame)
    assert "bed>=2&full>=3" in d.names
    assert d.count["bed>=2&full>=3"] == int(
        ((frame.bedrooms >= 2) & (frame.full_baths >= 3)).sum()
    )
    ladder = [j for j, n in enumerate(d.names) if n.startswith(("bed>=", "full>="))]
    rng = np.random.default_rng(0)
    beta = np.zeros(len(d.names))
    beta[ladder] = rng.normal(0, 0.3, len(ladder))
    cells = b0_2.cell_log_premiums(beta, d.names)
    known = ~np.isnan(frame.full_baths.to_numpy())
    beds = np.minimum(frame.bedrooms.to_numpy().astype(int), b0_2.BEDS)
    full = np.clip(np.nan_to_num(frame.full_baths.to_numpy(), nan=1), 1, b0_2.BATHS)
    want = np.array([cells[(b, int(f))] for b, f in zip(beds, full)])
    assert np.allclose((d.x @ beta)[known], want[known])


def test_model_log_density_matches_b0_2_written_out():
    """The NumPyro model's joint density at a point equals B0.2 written out by hand, up to
    the constant of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = b0_2.design(frame)
    priors = b0_2.Priors()
    fixed, inter = b0_2.split_index(d.names)
    rng = np.random.default_rng(0)
    main = rng.normal(0, 0.1, len(fixed))
    main[0] = np.log(2500)
    steps = rng.normal(0, 0.05, len(inter))
    z = rng.standard_t(2, d.weeks)
    point = {
        "main": main,
        "s_int": 0.07,
        "inter_z": steps / 0.07,
        "g": 0.0005,
        "tau": 0.002,
        "nu_t": 1.5,
        "nu": 5.0,
        "sigma": truth["sigma"],
        "z": z,
    }
    got, _ = log_density(b0_2.model(d, priors), (), {}, point)

    m_fix, s_fix = b0_2.prior_arrays(priors, d.names)
    beta = np.zeros(len(d.names))
    beta[fixed], beta[inter] = main, steps
    L = np.concatenate([[0.0], np.cumsum(0.0005 + 0.002 * z)])
    mu = d.x @ beta + (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    want = (
        stats.norm.logpdf(main, m_fix, s_fix).sum()
        + np.log(2) + stats.norm.logpdf(0.07, 0, priors.s_int)
        + stats.norm.logpdf(steps / 0.07, 0, 1).sum()
        + stats.norm.logpdf(0.0005, *priors.g)
        + np.log(tau_rate) - tau_rate * 0.002
        + stats.gamma.logpdf(1.5, priors.nu_t[0], scale=1 / priors.nu_t[1])
        + stats.gamma.logpdf(5.0, priors.nu[0], scale=1 / priors.nu[1])
        + (np.log(2) + stats.norm.logpdf(truth["sigma"], 0, priors.sigma)).sum()
        + stats.t.logpdf(z, 1.5).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )  # fmt: skip
    assert float(got) == pytest.approx(float(want), rel=1e-9)


def test_run_and_score(tmp_path, monkeypatch):
    from rentfrontier import loo
    from rentfrontier import run as runmod

    frame, _ = frame_of(n=1500, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(loo, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "b0.2", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "b02-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "b02-test" / "result.json").read_text())
    assert result["sampler"] == "b0.2" and result["line"] == "baseline-blackjax"
    assert "s_int" in result["diagnostics"]["per_quantity"]
    assert "h" not in result["diagnostics"]["per_quantity"]
    assert result["model"]["priors"]["tau_u"] == b0_2.Priors.tau_u
    record, pointwise = b0.score("b02-test", "b0.2", b0_2)
    assert record["model"] == "b0.2"
    assert np.isfinite(record["elpd_loo"])
    assert set(record["summary"]["cells"]) >= {"0bed_1bath", "5bed_4bath"}
    assert record["summary"]["cells"]["0bed_1bath"]["median"] == 0.0
    assert [r["n"] for r in record["scorecard"]] == list(range(1, 9))
    assert pointwise["heldout_quantiles"].shape == (result["sizes"]["heldout"], 5)
