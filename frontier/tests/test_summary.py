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
        np.full((draws, 1), 0.05),
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


def test_row_tables_from_a_pool_match_the_tables_built_in_process():
    rng = np.random.default_rng(5)
    draws, n = 200, 4
    chunks = []
    for c in range(5):
        terms = {
            "market": np.log(3000) + rng.normal(0, 0.01, (draws, n)),
            "unit": rng.normal(0, 0.05, (draws, n)),
        }
        sub = pd.DataFrame(
            {
                "audit_id": [f"a{c}-{i}" for i in range(n)],
                "unit_id": ["u"] * n,
                "building": ["b"] * n,
                "period": pd.to_datetime(["2020-01-01"] * n),
                "asking_rent": np.full(n, 3500.0),
            },
            index=np.arange(c * n, (c + 1) * n),
        )
        chunks.append(
            (
                sub,
                terms,
                rng.normal(0, 0.5, (draws, n)),
                np.zeros(n),
                np.exp(sum(terms.values())),
                np.full((draws, 1), 0.05),
                np.full(draws, 5.0),
                ["market", "unit"],
                ["{}"] * n,
            )
        )
    tables = {}
    for workers in (1, 2):
        with summary.RowTables(workers) as t:
            for chunk in chunks:
                t.add(*chunk)
            tables[workers] = pd.concat(t.collect())
    pd.testing.assert_frame_equal(tables[1], tables[2])
    assert len(tables[2]) == 5 * n


def test_range_sample_rates_take_every_row_of_a_sparse_group():
    groups = np.r_[np.zeros(9000, int), np.ones(900, int), np.full(100, 2)]
    rate = summary.range_sample_rates(groups, 4, rows=1000, per_group=200)
    np.testing.assert_allclose(rate, [0.1, 200 / 900, 1.0, 1.0])


def test_the_range_sample_reproduces_the_rows_predictive_intervals():
    rng = np.random.default_rng(6)
    draws, n = 300, 40
    terms = {
        "market": np.log(3000) + rng.normal(0, 0.01, (draws, n)),
        "unit": rng.normal(0, 0.1, (draws, n)),
    }
    log_w = rng.normal(0, 0.5, (draws, n))
    sigma = np.exp(rng.normal(np.log(0.1), 0.3, (draws, n)))
    nu = np.full(draws, 4.0)
    ids = np.array([f"a{i}" for i in range(n)])
    group = np.r_[np.zeros(n - 5, int), np.ones(5, int)]
    sub = pd.DataFrame(
        {
            "audit_id": ids,
            "unit_id": ["u"] * n,
            "building": ["b"] * n,
            "period": pd.to_datetime(["2020-01-01"] * n),
            "asking_rent": np.full(n, 3500.0),
        }
    )
    table = summary.row_table(
        sub,
        terms,
        log_w,
        np.zeros(n),
        np.exp(sum(terms.values())),
        sigma,
        nu,
        ["market", "unit"],
        ["{}"] * n,
    )
    sample = summary.RangeSample(np.array([0.5, 1.0]))
    for part, in_fit in ((slice(0, 20), True), (slice(20, n), False)):
        sample.add(
            ids[part],
            group[part],
            in_fit,
            {k: v[:, part] for k, v in terms.items()},
            log_w[:, part],
            sigma[:, part],
        )
    got = sample.arrays(nu)
    picked = pd.Index(ids).get_indexer(got["audit_id"])
    # Every row of the group sampled at rate 1, and about half of the other.
    assert set(ids[-5:]) <= set(got["audit_id"]) and 5 < len(picked) < n
    np.testing.assert_array_equal(got["in_fit"], picked < 20)
    np.testing.assert_array_equal(got["group"], group[picked])
    assert got["total"].shape == (len(picked), draws) and got["nu"].shape == (draws,)
    pred = np.exp(
        summary.predictive_quantiles(
            got["total"].T.astype(float),
            got["sigma"].T.astype(float),
            got["nu"].astype(float),
            got["weights"].T.astype(float),
            [0.10, 0.90],
        )
    )
    np.testing.assert_allclose(pred[0], table.estimate_pred_lower_80[picked], rtol=1e-5)
    np.testing.assert_allclose(pred[1], table.estimate_pred_upper_80[picked], rtol=1e-5)
    # A sample that picked no row still saves arrays of the right shapes.
    none = summary.RangeSample(np.zeros(2)).arrays(nu)
    assert none["total"].shape == (0, draws) and none["audit_id"].shape == (0,)


def test_row_tables_drop_queued_chunks_on_an_error():
    with pytest.raises(ZeroDivisionError):
        with summary.RowTables(2) as t:
            1 / 0
    assert t.pool is None


def test_present_terms_leave_out_terms_a_design_does_not_have():
    config = model.MODELS["m0q-btrend"]
    names = summary.present_terms(config, ["bedrooms", "bedrooms", "size"], line=False)
    assert names == ["market", "bedrooms", "size", "building", "building_drift", "unit"]
    labels = {t["name"]: t["label"] for t in summary.terms_record(names)}
    assert labels["building_drift"] == "Building over time" and labels["size"] == "Size"
    text = {
        t["name"]: t["description"] for t in summary.terms_record(["neighbourhood"])
    }
    assert text["neighbourhood"] == summary.TERM_TEXT["neighbourhood"]
    three = summary.terms_record(
        ["neighbourhood"], ["West Village", "Greenwich Village"]
    )
    assert three[0]["description"].startswith(
        "Each neighbourhood against Chelsea (the West Village, Greenwich Village):"
    )
    four = summary.terms_record(
        ["neighbourhood"],
        ["West Village", "Greenwich Village", "Flatiron + Gramercy Park"],
    )
    assert "Greenwich Village, Flatiron + Gramercy Park):" in four[0]["description"]
    five = summary.terms_record(
        ["neighbourhood"],
        ["West Village", "Greenwich Village", "Flatiron", "Gramercy Park"],
    )
    assert (
        "(the West Village, Greenwich Village, Flatiron, Gramercy Park):"
        in (five[0]["description"])
    )


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
    assert record["data_rule_files"] == {}
    assert "buildings_fraction" not in record
    assert not (tmp_path / "s.tmp").exists()
    out["buildings_fraction"] = 0.04
    path = summary.write(out, tmp_path / "sample", "d" * 40, 1.0)
    record = json.loads((path / "complete.json").read_text())
    assert record["buildings_fraction"] == 0.04
    out["range_sample"] = {"audit_id": np.array(["a"]), "nu": np.ones(10)}
    path = summary.write(out, tmp_path / "ranges", "d" * 40, 1.0)
    record = json.loads((path / "complete.json").read_text())
    assert "range-sample.npz" in record["files"]
    assert np.load(path / "range-sample.npz")["audit_id"].tolist() == ["a"]
    out["noise"] = {"groups": {"0": {"lower": -1.0, "step": 1.0, "cdf": [0, 1]}}}
    out["range_atoms_fallback_chunks"] = 0
    path = summary.write(out, tmp_path / "atoms", "d" * 40, 1.0)
    record = json.loads((path / "complete.json").read_text())
    assert "noise.json" in record["files"] and record["range_atoms"] == 64
    assert record["range_atoms_fallback_chunks"] == 0
    assert json.loads((path / "noise.json").read_text()) == out["noise"]


def test_write_copies_the_row_dropping_rules_file(tmp_path, monkeypatch):
    rule_file = tmp_path / "q.jsonl"
    rule_file.write_text('{"audit_id": "c", "action": "x", "reason": "y"}\n')
    monkeypatch.setitem(summary.data.RULE_SOURCES, "quarantine-v1", rule_file)
    # A corrections file is hashed but not copied: it keeps every row.
    fixes = tmp_path / "c.jsonl"
    fixes.write_text('{"audit_id": "a", "action": "correct_bedrooms"}\n')
    monkeypatch.setitem(summary.data.RULE_SOURCES, "bedrooms-ad-v1", fixes)
    # unit-labels-v2's alias table is hashed but has no per-row decisions.
    aliases = tmp_path / "aliases.jsonl"
    aliases.write_text(
        '{"alias_group_id": "g", "unit_id": "u", "history_confirmed": true}\n'
    )
    monkeypatch.setitem(summary.data.RULE_SOURCES, "unit-labels-v2", aliases)
    monkeypatch.setattr(summary, "hardware", lambda: {"cpu": "test"})
    monkeypatch.setattr(summary, "loo_score", lambda run: None)
    rows = pd.DataFrame({"audit_id": ["a"], "in_fit": [True], "pareto_k": [0.2]})
    sources = {
        "quarantine-v1": {"sha256": summary.data.sha256(rule_file)},
        "bedrooms-ad-v1": {"sha256": summary.data.sha256(fixes)},
        "unit-labels-v2": {"sha256": summary.data.sha256(aliases)},
    }
    out = {
        "result": {
            "name": "r",
            "commit": "c" * 40,
            "dataset": "/d",
            "dataset_observations_sha256": "s",
            "data_rules": ["unit-labels-v2", "quarantine-v1", "bedrooms-ad-v1"],
            "data_rule_sources": sources,
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
    name = "data-rule-quarantine-v1.jsonl"
    assert record["data_rule_files"] == {"quarantine-v1": name}
    assert record["files"][name] == summary.data.sha256(rule_file)
    assert record["data_rule_sources"] == sources


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


def test_without_a_building_fraction_the_summary_takes_every_row_as_before():
    rng = np.random.default_rng(0)
    buildings = rng.integers(0, 300, 5000)
    heldout = rng.random(5000) < 0.2
    keep = summary.building_sample(buildings, None)
    train_idx, held_idx = summary.summary_rows(heldout, keep)
    assert keep.all()
    np.testing.assert_array_equal(train_idx, np.flatnonzero(~heldout))
    np.testing.assert_array_equal(held_idx, np.flatnonzero(heldout))
    np.testing.assert_array_equal(heldout[keep], heldout)


def test_building_samples_nest_keep_whole_buildings_and_match_the_fraction():
    rng = np.random.default_rng(1)
    buildings = rng.integers(0, 20_000, 200_000)
    samples = {f: summary.building_sample(buildings, f) for f in (0.01, 0.04, 0.16)}
    assert not (samples[0.01] & ~samples[0.04]).any()
    assert not (samples[0.04] & ~samples[0.16]).any()
    for fraction, keep in samples.items():
        kept = pd.Series(keep).groupby(buildings).agg(["min", "max"])
        assert (kept["min"] == kept["max"]).all()
        share = kept["min"].mean()
        assert abs(share - fraction) < 4 * math.sqrt(fraction / len(kept))
    # The sample depends on the building id alone, so a reordered frame keeps
    # the same buildings.
    order = rng.permutation(len(buildings))
    np.testing.assert_array_equal(
        summary.building_sample(buildings[order], 0.04), samples[0.04][order]
    )
    assert summary.building_sample(buildings, 1.0).all()
    with pytest.raises(ValueError):
        summary.building_sample(buildings, 0.0)


def test_the_building_sample_flags_are_checked_before_any_work(tmp_path):
    for argv in (
        ["r", "--buildings", "0.04"],
        ["r", "--out", str(tmp_path)],
        ["r", "--buildings", "1.5", "--out", str(tmp_path)],
        ["r", "--buildings", "0.04", "--out", str(summary.SUMMARIES / "r-sample")],
    ):
        with pytest.raises(SystemExit) as exit:
            summary.main(argv)
        assert exit.value.code == 2


def test_chunk_rows_bounds_the_batch():
    assert summary.chunk_rows(2200) == 1022
    assert summary.chunk_rows(100) == 1024 and summary.chunk_rows(100_000) == 256


def test_building_fact_groups_have_descriptions():
    names = ["building era", "building size", "building class", "building status"]
    for term in summary.terms_record(names):
        assert not term["description"].startswith("Listing attributes"), term


def test_new_unit_levels_draw_from_the_unit_prior():
    """Held-out rows of units with no rows in the fit get unit levels from the
    prior: zero-centred, with the draws' unit scale (Normal or Student-t)."""
    import jax

    draws = 4000
    params = {"unit_scale": np.full(draws, 0.05), "unit_nu": np.full(draws, 30.0)}
    for t_units in (False, True):
        levels = summary.new_unit_levels(
            params, 3, jax.random.PRNGKey(0), t_units=t_units
        )
        assert levels.shape == (draws, 3)
        assert abs(levels.mean()) < 0.005
        assert 0.045 < levels.std() < 0.056


def test_new_unit_levels_are_clipped_so_the_mean_is_finite():
    """A Student-t unit prior with a small nu draws levels far out in the
    tail; they are clipped at UNIT_CLIP unit scales, as the site's form does."""
    import jax

    assert summary.UNIT_CLIP == 40.0  # apartments.site.estimate.UNIT_CLIP
    params = {"unit_scale": np.full(4000, 0.05), "unit_nu": np.full(4000, 0.3)}
    levels = summary.new_unit_levels(params, 50, jax.random.PRNGKey(0), t_units=True)
    assert np.abs(levels).max() <= 0.05 * summary.UNIT_CLIP + 1e-12
    assert np.isfinite(np.exp(levels).mean())


def test_predictive_quantiles_invert_the_mixture_cdf():
    from scipy.special import stdtr

    rng = np.random.default_rng(0)
    draws, rows = 200, 5
    total = rng.normal(8.0, 0.05, (draws, rows))
    # Per-row noise scales, per-draw nu and unequal (PSIS-like) weights.
    sigma = rng.uniform(0.03, 0.08, (draws, rows))
    nu = rng.uniform(2.0, 30.0, draws)
    weights = rng.exponential(1.0, (draws, rows))
    weights /= weights.sum(0)
    q = summary.predictive_quantiles(total, sigma, nu, weights, [0.025, 0.5, 0.975])
    for i, p in enumerate([0.025, 0.5, 0.975]):
        cdf = (stdtr(nu[:, None], (q[i][None] - total) / sigma) * weights).sum(0)
        np.testing.assert_allclose(cdf, p, atol=1e-6)
    assert (q[0] < q[1]).all() and (q[1] < q[2]).all()


def test_predictive_quantiles_with_few_heavy_draws():
    """PSIS weights on a few draws far apart, with very different noise
    scales: the mixture CDF has plateaus where Newton alone can cycle."""
    from scipy.special import stdtr

    rng = np.random.default_rng(2)
    draws, rows = 400, 50
    total = rng.normal(7.7, 0.1, (draws, rows))
    sigma = rng.uniform(0.01, 0.3, (draws, rows))
    nu = rng.uniform(1.5, 30.0, draws)
    log_w = rng.normal(0.0, 1.0, (draws, rows))
    log_w[:3] += 12.0  # three draws hold almost all the weight
    total[:3] += np.array([[-0.3], [0.0], [0.4]])
    weights = np.exp(log_w - log_w.max(0))
    weights /= weights.sum(0)
    probabilities = [0.025, 0.1, 0.5, 0.9, 0.975]
    q = summary.predictive_quantiles(total, sigma, nu, weights, probabilities)
    for i, p in enumerate(probabilities):
        cdf = (stdtr(nu[:, None], (q[i][None] - total) / sigma) * weights).sum(0)
        np.testing.assert_allclose(cdf, p, atol=1e-6)


def fixed_step_quantiles(total, sigma, nu, weights, probabilities, iterations=10):
    """predictive_quantiles as it ran up to 2026-10-17: `iterations` Newton steps
    (ten by default) on every row, then 50 bisection steps on rows still off by
    more than 1e-7."""
    from scipy.special import gammaln, stdtr, stdtrit

    sigma = np.broadcast_to(sigma, total.shape)
    nu_ = nu[:, None]
    const = np.exp(gammaln((nu + 1) / 2) - gammaln(nu / 2)) / np.sqrt(nu * np.pi)
    wpdf = weights * const[:, None] / sigma
    out = np.empty((len(probabilities), total.shape[1]))
    for q, p in enumerate(probabilities):
        own = total + sigma * stdtrit(nu, p)[:, None]
        lo, hi = own.min(0), own.max(0)
        x = (own * weights).sum(0)
        for _ in range(iterations):
            z = (x[None] - total) / sigma
            f = (stdtr(nu_, z) * weights).sum(0) - p
            d = (wpdf * (1 + z * z / nu_) ** (-(nu_ + 1) / 2)).sum(0)
            lo, hi = np.where(f < 0, x, lo), np.where(f < 0, hi, x)
            step = x - f / np.maximum(d, 1e-300)
            inside = (step >= lo) & (step <= hi)
            x = np.where(inside, step, 0.5 * (lo + hi))
        z = (x[None] - total) / sigma
        f = (stdtr(nu_, z) * weights).sum(0) - p
        slow = np.flatnonzero(np.abs(f) > 1e-7)
        if len(slow):
            t, s_, w = total[:, slow], sigma[:, slow], weights[:, slow]
            a = np.where(f[slow] < 0, x[slow], lo[slow])
            b = np.where(f[slow] < 0, hi[slow], x[slow])
            for _ in range(50):
                m = 0.5 * (a + b)
                below = (stdtr(nu_, (m[None] - t) / s_) * w).sum(0) < p
                a, b = np.where(below, m, a), np.where(below, b, m)
            x[slow] = 0.5 * (a + b)
        out[q] = x
    return out


def bisected_rows(monkeypatch) -> list[int]:
    """Count the rows each call of summary._bisect finishes."""
    counts, bisect = [], summary._bisect

    def spy(total, *rest):
        counts.append(total.shape[1])
        return bisect(total, *rest)

    monkeypatch.setattr(summary, "_bisect", spy)
    return counts


def test_rows_that_stop_early_match_the_fixed_step_quantiles(monkeypatch):
    """Heavy-tailed draws far apart, as in the previous test but heavier: some
    rows need the bisection finish, and every row matches the fixed-step
    output well inside display precision."""
    rng = np.random.default_rng(3)
    draws, rows = 400, 300
    total = rng.normal(7.7, 0.1, (draws, rows))
    sigma = rng.uniform(0.005, 0.4, (draws, rows))
    nu = rng.uniform(1.05, 4.0, draws)
    log_w = rng.normal(0.0, 1.0, (draws, rows))
    log_w[:2] += 14.0
    total[:2] += np.array([[-0.8], [0.8]])
    weights = np.exp(log_w - log_w.max(0))
    weights /= weights.sum(0)
    probabilities = [0.025, 0.1, 0.9, 0.975]
    counts = bisected_rows(monkeypatch)
    q = summary.predictive_quantiles(total, sigma, nu, weights, probabilities)
    # Some rows need the bisection finish, and most stop on Newton steps.
    assert sum(counts) > 0 and max(counts) < rows // 4
    expected = fixed_step_quantiles(total, sigma, nu, weights, probabilities)
    np.testing.assert_allclose(q, expected, rtol=0, atol=1e-9)


def test_every_row_gets_the_bisection_finish_with_no_newton_steps(monkeypatch):
    """With no Newton steps every row's CDF stays off at the starting point,
    and the bisection finish still brings each one to its quantile."""
    from scipy.special import stdtr

    rng = np.random.default_rng(4)
    draws, rows = 200, 20
    total = rng.normal(8.0, 0.2, (draws, rows))
    sigma = rng.uniform(0.02, 0.2, (draws, rows))
    nu = rng.uniform(2.0, 10.0, draws)
    weights = np.full((draws, rows), 1.0 / draws)
    counts = bisected_rows(monkeypatch)
    q = summary.predictive_quantiles(total, sigma, nu, weights, [0.1], iterations=0)
    assert counts == [rows]
    cdf = (stdtr(nu[:, None], (q[0][None] - total) / sigma) * weights).sum(0)
    np.testing.assert_allclose(cdf, 0.1, atol=1e-9)


def test_predictive_bounds_agree_with_pit():
    """row_table's predictive bounds invert the distribution pit evaluates: an
    ask below the 80% range's lower bound has pit < 0.10, above its upper bound
    pit > 0.90 (and the same for the 95% range at 0.025 and 0.975)."""
    rng = np.random.default_rng(1)
    draws, rows = 300, 400
    total = rng.normal(8.3, 0.03, (draws, 1)) + rng.normal(0.0, 0.02, (1, rows))
    asks = np.exp(total.mean(0) + rng.standard_t(4, rows) * 0.08)
    sub = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(rows)],
            "unit_id": [f"u{i}" for i in range(rows)],
            "building": ["b"] * rows,
            "period": pd.to_datetime(["2024-05-01"] * rows),
            "asking_rent": asks,
        }
    )
    sigma = np.full((draws, 1), 0.05)
    nu = np.full(draws, 5.0)
    table = summary.row_table(
        sub,
        {"market": total},
        np.zeros((draws, rows)),
        np.full(rows, np.nan),
        np.exp(total),
        sigma,
        nu,
        [],
        [""] * rows,
    )
    pit, ask = table.pit.to_numpy(), table.asking_rent.to_numpy()
    for name, lo, hi in summary.PREDICTIVE:
        low, high = (
            table[f"estimate_pred_lower_{name}"],
            table[f"estimate_pred_upper_{name}"],
        )
        clear = (np.abs(pit - lo) > 1e-3) & (np.abs(pit - hi) > 1e-3)
        np.testing.assert_array_equal((pit < lo)[clear], (ask < low)[clear])
        np.testing.assert_array_equal((pit > hi)[clear], (ask > high)[clear])
    inside = (ask >= table.estimate_pred_lower_80) & (
        ask <= table.estimate_pred_upper_80
    )
    assert 0.6 < inside.mean() < 0.95


def test_summary_reports_the_median_and_the_95_interval():
    # A skewed draw set: the mean (2.8) is far from the median (1.0).
    x = np.array([[0.0], [1.0], [1.0], [1.0], [11.0]])
    mid, lo, hi = summary._summary(x)
    assert mid[0] == pytest.approx(1.0)
    assert lo[0] == pytest.approx(np.quantile(x[:, 0], 0.025))
    assert hi[0] == pytest.approx(np.quantile(x[:, 0], 0.975))


def site_ranges():
    """apartments.site.ranges, loaded by its path: the site's environments
    have no rentfrontier and this one has no apartments package."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "src" / "apartments" / "site" / "ranges.py"
    spec = importlib.util.spec_from_file_location("site_ranges", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ranges_from_atoms_match_the_exact_predictive_intervals(tmp_path):
    """The site's ranges from 64 atoms and the group's noise table, against
    predictive_quantiles on the same draws, with a per-group sigma, per-draw
    nu and unequal weights."""
    ranges = site_ranges()
    assert ranges.ATOMS == summary.RANGE_ATOMS
    rng = np.random.default_rng(7)
    draws, rows, n_groups = 1000, 12, 3
    groups = np.arange(rows) % n_groups
    sigma = rng.uniform(0.04, 0.12, (draws, n_groups)) * np.array([1.0, 1.5, 3.0])
    nu = rng.uniform(3.0, 30.0, draws)
    total = rng.normal(8.0, 0.06, (draws, rows))
    weights = rng.exponential(1.0, (draws, rows)) ** 0.3
    weights /= weights.sum(0)
    noise = summary.noise_tables(sigma, nu)
    (tmp_path / "noise.json").write_text(json.dumps(noise))
    tables = ranges.load_noise(tmp_path / "noise.json")
    atoms = summary.range_atoms(total, weights).T.astype(np.float32)
    probabilities = [p for _, lo, hi in ranges.RANGES for p in (lo, hi)]
    exact = summary.predictive_quantiles(
        total, sigma[:, groups], nu, weights, probabilities
    )
    # The Monte Carlo yardstick: half the gap between the exact bounds on the
    # even and the odd draws.
    halves = [
        summary.predictive_quantiles(
            total[h::2], sigma[h::2, groups], nu[h::2], weights[h::2], probabilities
        )
        for h in (0, 1)
    ]
    yardstick = np.abs(halves[0] - halves[1]) / 2
    error = np.empty_like(exact)
    for i in range(rows):
        got = ranges.likely_ask(atoms[i].tolist(), tables[int(groups[i])])
        for q, (name, _, _) in enumerate(ranges.RANGES):
            error[2 * q, i] = math.log(got[f"pred_lower_{name}"]) - exact[2 * q, i]
            error[2 * q + 1, i] = (
                math.log(got[f"pred_upper_{name}"]) - exact[2 * q + 1, i]
            )
    assert np.median(np.abs(error)) < np.median(yardstick)
    # Within 0.06 of the group's median scale: the Monte Carlo error of a 97.5%
    # bound from 1000 draws is near 0.08 of it.
    assert (np.abs(error) < 0.06 * np.median(sigma, 0)[groups]).all()


def test_the_row_table_writes_atoms_in_place_of_the_intervals():
    rng = np.random.default_rng(8)
    draws, n = 300, 4
    terms = {"market": np.log(3000) + rng.normal(0, 0.05, (draws, n))}
    sub = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(n)],
            "unit_id": ["u"] * n,
            "building": ["b"] * n,
            "period": pd.to_datetime(["2020-01-01"] * n),
            "asking_rent": np.full(n, 3500.0),
        }
    )
    args = (
        sub,
        terms,
        np.zeros((draws, n)),
        np.zeros(n),
        np.exp(terms["market"]),
        np.full((draws, 1), 0.05),
        np.full(draws, 5.0),
        ["market"],
        ["{}"] * n,
    )
    exact = summary.row_table(*args)
    table = summary.row_table(*args, np.array([0, 1, 0, 1]))
    assert not any(c.startswith("estimate_pred_") for c in table)
    assert table.noise_group.tolist() == [0, 1, 0, 1]
    atoms = np.stack(table.estimate_atoms)
    assert atoms.shape == (n, summary.RANGE_ATOMS) and atoms.dtype == np.float32
    assert (np.diff(atoms, axis=1) >= 0).all()
    np.testing.assert_allclose(
        np.median(atoms, 1), np.log(exact.estimate_median), atol=0.01
    )
    shared = [c for c in exact if c in table]
    pd.testing.assert_frame_equal(exact[shared], table[shared])


def test_noise_tables_are_the_mixture_cdf_on_the_grid():
    from scipy.special import stdtr

    rng = np.random.default_rng(9)
    sigma = rng.uniform(0.05, 0.1, (200, 2))
    nu = rng.uniform(2.0, 20.0, 200)
    noise = summary.noise_tables(sigma, nu, grid=101)
    for g in (0, 1):
        t = noise["groups"][str(g)]
        e = t["lower"] + t["step"] * np.arange(101)
        assert abs(e[50]) < 1e-12 and len(t["cdf"]) == 101
        want = stdtr(nu[None], e[:, None] / sigma[None, :, g]).mean(1)
        np.testing.assert_allclose(t["cdf"], want, atol=1e-9)
