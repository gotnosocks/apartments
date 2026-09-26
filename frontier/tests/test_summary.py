import json
import math

import numpy as np
import pandas as pd
import pytest
from rentfrontier import loo, model, summary
from scipy import stats

jax = pytest.importorskip("jax")
jax.config.update("jax_enable_x64", True)


def toy_units(rng, n_units=25):
    sizes = rng.integers(1, 5, n_units)
    return np.repeat(np.arange(n_units), sizes)


@pytest.mark.parametrize("t_units", [False, True])
def test_loglik_is_loo_integrated_loglik(t_units):
    rng = np.random.default_rng(1)
    unit = toy_units(rng)
    n, draws = len(unit), 6
    y = rng.normal(0, 0.1, n)
    rest = rng.normal(0, 0.02, (draws, n))
    params = {
        "nu": rng.uniform(2, 8, draws),
        "sigma": rng.uniform(0.03, 0.08, draws),
        "unit_scale": rng.uniform(0.05, 0.15, draws),
        "unit_nu": rng.uniform(2, 6, draws),
    }
    expected = loo.integrated_loglik(
        y, rest, unit, unit.max() + 1, np.zeros(n), params, t_units=t_units, drift=False
    )
    got, level = summary.loo_unit_levels(
        y, rest, unit, unit.max() + 1, params, jax.random.PRNGKey(0), t_units=t_units
    )
    np.testing.assert_allclose(got, np.asarray(expected), rtol=1e-12, atol=1e-12)
    assert level.shape == (draws, n) and np.isfinite(level).all()


def test_level_draws_follow_the_conditional_given_the_units_other_rows():
    """Gaussian noise and levels: a | y_{u,-i} is normal with known moments."""
    tau, sigma, draws = 0.1, 0.05, 20_000
    y = np.array([0.12, 0.08, 0.15, -0.05])
    unit = np.array([0, 0, 0, 1])  # unit 1 has one row: its level is the prior
    params = {
        "nu": np.full(draws, 1e8),
        "sigma": np.full(draws, sigma),
        "unit_scale": np.full(draws, tau),
    }
    _, level = summary.loo_unit_levels(
        y, np.zeros((draws, 4)), unit, 2, params, jax.random.PRNGKey(3), t_units=False
    )
    for i in range(3):
        others = np.delete(y[:3], i)
        var = 1 / (1 / tau**2 + len(others) / sigma**2)
        mean = var * others.sum() / sigma**2
        assert abs(level[:, i].mean() - mean) < 4 * math.sqrt(var / draws)
        assert level[:, i].std() == pytest.approx(math.sqrt(var), rel=0.03)
    assert abs(level[:, 3].mean()) < 4 * tau / math.sqrt(draws)
    assert level[:, 3].std() == pytest.approx(tau, rel=0.03)


def test_leave_own_row_out_estimate_matches_exact_loo_on_a_conjugate_model():
    """y_ij = m + a_j + e_ij, Gaussian a and e, flat-ish prior on m: the
    posterior of m + a_u(i) given y_-i is normal and exact."""
    rng = np.random.default_rng(0)
    tau, sigma, prior_sd = 0.1, 0.05, 1.0
    unit = toy_units(rng)
    n, n_units = len(unit), unit.max() + 1
    y = 0.3 + rng.normal(0, tau, n_units)[unit] + rng.normal(0, sigma, n)
    # Latent (m, a_1..a_J); design rows pick m and the row's unit.
    x = np.zeros((n, 1 + n_units))
    x[:, 0] = 1.0
    x[np.arange(n), 1 + unit] = 1.0
    prior_prec = np.diag([1 / prior_sd**2] + [1 / tau**2] * n_units)
    # Exact posterior draws of m given all rows (the fit's kept draws).
    cov_given_m = sigma**2 * np.eye(n) + tau**2 * (unit[:, None] == unit[None, :])
    inv = np.linalg.inv(cov_given_m)
    post_var = 1 / (1 / prior_sd**2 + inv.sum())
    post_mean = post_var * (inv @ y).sum()
    draws = 8000
    m = rng.normal(post_mean, math.sqrt(post_var), draws)
    params = {
        "nu": np.full(draws, 1e8),
        "sigma": np.full(draws, sigma),
        "unit_scale": np.full(draws, tau),
    }
    loglik, level = summary.loo_unit_levels(
        y,
        np.broadcast_to(m[:, None], (draws, n)),
        unit,
        n_units,
        params,
        jax.random.PRNGKey(7),
        t_units=False,
    )
    log_w, k = summary.psis_log_weights(loglik)
    assert np.all(k < 0.7)
    weights = summary.normalized_weights(log_w)
    mu = m[:, None] + level
    got_mean = (weights * mu).sum(0)
    got_q = summary.weighted_quantiles(mu, weights)
    for i in range(n):
        keep = np.arange(n) != i
        cov = np.linalg.inv(prior_prec + x[keep].T @ x[keep] / sigma**2)
        mean = cov @ x[keep].T @ y[keep] / sigma**2
        exact_mean, exact_sd = x[i] @ mean, math.sqrt(x[i] @ cov @ x[i])
        assert abs(got_mean[i] - exact_mean) < 0.08 * exact_sd, i
        exact_q = stats.norm.ppf(summary.PROBABILITIES, exact_mean, exact_sd)
        np.testing.assert_allclose(got_q[:, i], exact_q, atol=0.15 * exact_sd)


def test_weighted_quantiles_with_equal_weights_are_the_inverted_cdf():
    rng = np.random.default_rng(2)
    values = rng.normal(size=(999, 5))
    weights = np.full_like(values, 1 / 999)
    got = summary.weighted_quantiles(values, weights, (0.025, 0.5, 0.975))
    expected = np.quantile(values, (0.025, 0.5, 0.975), axis=0, method="inverted_cdf")
    np.testing.assert_allclose(got, expected)


def test_row_table_contributions_add_up_to_the_estimate():
    rng = np.random.default_rng(4)
    draws, n = 400, 6
    terms = {
        "market": np.log(3000) + rng.normal(0, 0.01, (draws, n)),
        "bedrooms": rng.normal(0.2, 0.02, (draws, n)),
        "building": rng.normal(-0.1, 0.05, (draws, n)),
        "unit": rng.normal(0, 0.05, (draws, n)),
    }
    sub = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(n)],
            "unit_id": ["u"] * n,
            "building": ["b"] * n,
            "period": pd.to_datetime(["2020-01-01"] * n),
            "asking_rent": np.full(n, 3500.0),
        }
    )
    log_w = rng.normal(0, 0.5, (draws, n))
    table = summary.row_table(
        sub,
        terms,
        log_w,
        np.zeros(n),
        np.exp(sum(terms.values())),
        np.full(draws, 0.05),
        np.full(draws, 5.0),
        ["market", "bedrooms", "building", "unit"],
        ["{}"] * n,
    )
    parts = table[["market_usd", "bedrooms_usd", "building_usd", "unit_usd"]].sum(
        axis=1
    )
    np.testing.assert_allclose(parts, table.estimate, rtol=1e-10)
    np.testing.assert_allclose(table.residual_usd, 3500.0 - table.estimate)
    assert (table.estimate_lower_95 < table.estimate_median).all()
    assert (table.estimate_median < table.estimate_upper_95).all()
    assert table.pit.between(0, 1).all()


def test_present_terms_leave_out_terms_a_design_does_not_have():
    config = model.MODELS["m0q-btrend"]
    names = summary.present_terms(config, ["bedrooms", "bedrooms", "size"], line=False)
    assert names == ["market", "bedrooms", "size", "building", "building_drift", "unit"]
    labels = {t["name"]: t["label"] for t in summary.terms_record(names)}
    assert labels["building_drift"] == "Building over time" and labels["size"] == "Size"


def test_write_records_every_file_and_renames_last(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "hardware", lambda: {"cpu": "test"})
    monkeypatch.setattr(summary, "loo_score", lambda run: None)
    rows = pd.DataFrame(
        {"audit_id": ["a", "b"], "in_fit": [True, False], "pareto_k": [0.2, np.nan]}
    )
    out = {
        "result": {
            "name": "r",
            "commit": "c" * 40,
            "dataset": "/d",
            "dataset_observations_sha256": "s",
            "feature_set": "f",
            "model": {"name": "m"},
            "split": "rows",
            "seconds": {"fit_total": 1.0},
            "hardware": {"cpu": "x", "gpu": None},
        },
        "gate": {"passes": True},
        "draws": 10,
        "names": ["market"],
        "rows": rows,
        "market": pd.DataFrame({"period": ["2020-01-01"]}),
        "buildings": pd.DataFrame({"building": ["b"]}),
        "coefficients": pd.DataFrame({"feature": ["x"]}),
        "k_threshold": 0.7,
    }
    path = summary.write(out, tmp_path / "s", "d" * 40, 1.0)
    record = json.loads((path / "complete.json").read_text())
    assert set(record["files"]) == {
        "rows.parquet",
        "market.parquet",
        "buildings.parquet",
        "coefficients.parquet",
        "terms.json",
    }
    assert record["rows"] == 2 and record["rows_in_fit"] == 1
    assert not (tmp_path / "s.tmp").exists()


def _result(**changes):
    result = {
        "split": "rows",
        "feature_set": "unitdesc-v1",
        "feature_sources": {"registry": {"path": "/old/path", "sha256": "abc"}},
    }
    result.update(changes)
    return result


def test_check_run_hashes_the_files_the_feature_set_reads_now(monkeypatch):
    now = {"registry": {"path": "/new/path", "sha256": "abc"}}
    monkeypatch.setattr(summary.run_module, "feature_sources", lambda fs: now)
    summary.check_run(_result())  # same content at a new path is fine
    now["registry"]["sha256"] = "changed"
    with pytest.raises(SystemExit, match="feature source registry differs"):
        summary.check_run(_result())
    monkeypatch.setattr(summary.run_module, "feature_sources", lambda fs: {})
    with pytest.raises(SystemExit, match="feature source registry differs"):
        summary.check_run(_result())


def test_check_run_refuses_the_unit_split(monkeypatch):
    monkeypatch.setattr(summary.run_module, "feature_sources", lambda fs: {})
    summary.check_run(_result(split="all", feature_sources={}))
    with pytest.raises(SystemExit, match="units-split runs are not summarized"):
        summary.check_run(_result(split="units", feature_sources={}))


def test_verify_run_refuses_differing_rows_and_indexes(tmp_path):
    from types import SimpleNamespace

    frame = pd.DataFrame({"audit_id": ["a", "b", "c"]})
    frame.attrs["source_sha256"] = "d"
    heldout = np.array([False, True, False])
    np.savez(tmp_path / "heldout.npz", audit_id=np.array(["b"], dtype=object))
    prep = SimpleNamespace(units=np.array(["u1", "u2"]), buildings=np.array(["b1"]))
    result = {"dataset_observations_sha256": "d"}
    args = (result, frame, heldout, prep, tmp_path)
    summary.verify_run(*args, prep.units, prep.buildings)
    with pytest.raises(SystemExit, match="dataset differs"):
        summary.verify_run(
            {"dataset_observations_sha256": "x"}, *args[1:], prep.units, prep.buildings
        )
    with pytest.raises(SystemExit, match="held-out rows differ"):
        summary.verify_run(
            result, frame, ~heldout, prep, tmp_path, prep.units, prep.buildings
        )
    with pytest.raises(SystemExit, match="units or buildings differ"):
        summary.verify_run(*args, np.array(["u1"]), prep.buildings)


def test_chunk_rows_bounds_the_batch():
    assert summary.chunk_rows(2200) == 1022
    assert summary.chunk_rows(100) == 1024 and summary.chunk_rows(100_000) == 256
