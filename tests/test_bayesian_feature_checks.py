"""Joint-draw reconstruction and bounded posterior discrepancy diagnostics."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from models import bayesian_feature_checks as m


@pytest.fixture
def posterior_case(tmp_path):
    rng = np.random.default_rng(812)
    data = pd.DataFrame(
        {
            "asking_rent": [3000.0, 4500.0, 8000.0],
            "audit_id": ["a", "b", "c"],
            "source_listing_id": ["11", "12", "13"],
            "unit_id": ["u1", "u0", "u1"],
            "building": ["b1", "b0", "b1"],
            "period": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
        }
    )
    time = SimpleNamespace(
        time_matrix=rng.normal(size=(3, 2)),
        time_center=np.array([0.1, 0.3]),
        linear_time=np.array([0.0, 1.0, 2.0]),
        linear_center=0.8,
        season_matrix=rng.normal(size=(12, 2)),
        season_weights=np.ones(12) / 12,
        buildings=["b0", "b1"],
        unit_ids=["u0", "u1"],
    )
    indices = {
        "period": np.array([0, 1, 2]),
        "season": np.array([0, 1, 2]),
        "building": np.array([1, 0, 1]),
        "unit": np.array([1, 0, 1]),
    }
    time.arrays = lambda frame: indices
    matrix = rng.normal(size=(3, 2))
    design = SimpleNamespace(
        time=time, features=["x", "z"], matrix=lambda frame: matrix
    )
    coordinates = {
        "chain": [10, 20],
        "draw": list(range(9)),
        "feature": design.features,
        "building": time.buildings,
        "unit": time.unit_ids,
        "trend_basis": [0, 1],
        "season_basis": [0, 1],
    }
    variables = {}
    for name, dims in m.VARIABLE_DIMS.items():
        shape = (2, 9) + tuple(len(coordinates[d]) for d in dims)
        values = rng.normal(size=shape) * 0.1
        if name == "alpha":
            values += 8
        if name in ("sigma", "sigma_unit"):
            values = abs(values) + 0.01
        variables[name] = (("chain", "draw", *dims), values)
    posterior = xr.Dataset(variables, coords=coordinates)
    path = tmp_path / "posterior.nc"
    posterior.to_netcdf(path, group="posterior", engine="h5netcdf")
    return path, posterior, design, data


def test_balanced_selection_boundaries_and_validation():
    selected = m.select_draws(4, 4000)
    assert len(selected) == 200
    for chain in range(4):
        indices = [d for c, d in selected if c == chain]
        assert len(set(indices)) == 50 and min(indices) >= 0 and max(indices) < 4000
        assert indices == list(range(40, 4000, 80))
    assert m.select_draws(2, 1) == [(0, 0), (1, 0)]
    for args in [(1, 100, 50), (4, 100, 51), (2, 0, 1), (2, 100, 0), (True, 100, 1)]:
        with pytest.raises(ValueError):
            m.select_draws(*args)


def test_lazy_joint_selection_and_reconstruction_matches_original_summary(
    posterior_case,
):
    from models.bayesian_feature_experiment import fitted_summary

    path, posterior, design, data = posterior_case
    samples, selection = m.load_draws(
        path, {"chains": 2, "draws": 9}, design, per_chain=3
    )
    assert [s["draw_index"] for s in selection] == [1, 4, 7] * 2
    assert [s["chain_coordinate"] for s in selection] == [10] * 3 + [20] * 3
    for name in m.VARIABLE_DIMS:
        expected = np.concatenate(
            [posterior[name].isel(chain=c, draw=[1, 4, 7]).values for c in range(2)]
        )
        np.testing.assert_array_equal(samples[name], expected)
    mu = m.reconstruct_mu(samples, design, data)
    # Independent pointwise formula detects draw-axis mixing and omitted components.
    for s in range(6):
        for i in range(3):
            d = design.time
            a = d.arrays(data)
            expected = (
                samples["alpha"][s]
                + design.matrix(data)[i] @ samples["beta"][s]
                + (d.time_matrix[i] - d.time_center) @ samples["trend_coefficients"][s]
                + samples["annual_drift"][s] * (d.linear_time[i] - d.linear_center)
                + (d.season_matrix[i] - d.season_weights @ d.season_matrix)
                @ samples["season_coefficients"][s]
                + samples["building_effect"][s, a["building"][i]]
                + samples["sigma_unit"][s] * samples["unit_z"][s, a["unit"][i]]
            )
            assert mu[s, i] == pytest.approx(expected, abs=1e-12)
    selected = posterior.isel(draw=[1, 4, 7])
    rows, _ = fitted_summary({"posterior": selected}, design, data)
    np.testing.assert_allclose(
        [r["fitted_rent"] for r in rows], np.exp(np.median(mu, axis=0)), atol=1e-9
    )
    np.testing.assert_allclose(
        [r["latent_rent_lower_95"] for r in rows],
        np.exp(np.quantile(mu, 0.025, axis=0)),
        atol=1e-9,
    )


def test_posterior_dimensions_and_coordinate_order_refused(posterior_case):
    path, posterior, design, _ = posterior_case
    with pytest.raises(ValueError, match="dimensions differ"):
        m.load_draws(path, {"chains": 2, "draws": 8}, design)
    design.features = ["z", "x"]
    with pytest.raises(ValueError, match="coordinate order"):
        m.load_draws(path, {"chains": 2, "draws": 9}, design)


def test_asymmetric_omission_detected_despite_matching_mean_absolute_error():
    rng = np.random.default_rng(42)
    replicated = rng.standard_t(5, size=(200, 2000)) * 0.07
    # Positive omitted-feature tail with matched mean absolute residual magnitude.
    observed = np.abs(replicated)
    result = m.compare_residuals(observed, replicated)
    assert (
        result["mean_absolute_log_residual"]["observed"]
        == result["mean_absolute_log_residual"]["replicated"]
    )
    assert (
        result["median_signed_log_residual"]["probability_replicated_greater_or_equal"]
        == 0
    )
    assert (
        result["signed_tail_balance_10pct"]["observed_minus_replicated"]["lower_95"]
        > 0.1
    )
    assert result["negative_tail_10pct"]["observed"]["upper_95"] == 0
    assert result["negative_tail_10pct"]["replicated"]["lower_95"] > 0
    # Fixed thresholds use reciprocal rent ratios, not symmetric dollar percentages.
    assert m.THRESHOLDS["10pct"] == pytest.approx(np.log(1.1))


def test_sparse_current_slices_are_explicitly_withheld():
    data = pd.DataFrame(
        {
            "bedrooms": [1] * 20 + [2] * 2,
            "unit_id": ["u" + str(i) for i in range(22)],
            "building": ["b" + str(i % 3) for i in range(22)],
            "analysis_price_basis": ["historical_initial_own_advertisement_ask"] * 20
            + ["current_capture_gross_ask"] * 2,
        }
    )
    included, omitted = m.slices(data)
    assert {v["slice"] for v, _ in included} == {
        "overall",
        "history",
        "bedrooms=1",
        "bedrooms=1/history",
    }
    assert next(v for v in omitted if v["slice"] == "current")["support"]["rows"] == 2


def test_rejected_fit_never_reads_posterior(monkeypatch, tmp_path):
    def reject(*args, **kwargs):
        raise ValueError("Unacceptable derived diagnostics")

    monkeypatch.setattr(m.report, "build_report", reject)
    monkeypatch.setattr(
        m, "load_draws", lambda *a, **k: pytest.fail("Read rejected posterior")
    )
    with pytest.raises(ValueError, match="derived diagnostics"):
        m.run(tmp_path / "experiment", tmp_path / "source", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_frozen_reconstruction_dependency_hashes_enforced():
    root = Path(m.__file__).resolve().parents[1]
    names = [
        "bayesian_feature_model.py",
        "bayesian_rent_model.py",
        "bayesian_feature_experiment.py",
        "amenity_rent_model.py",
        "minimal_rent_model.py",
        "pricing.py",
        "corrections.py",
        "research_pipeline.py",
    ]
    paths = [
        next(
            p
            for p in (root / "models" / name, root / "src" / "apartments" / name)
            if p.exists()
        )
        for name in names
    ]
    hashes = {p.name: m.digest(p) for p in paths}
    assert len(m.verify_implementation({"implementation_sha256": hashes})) == len(paths)
    hashes["bayesian_feature_model.py"] = "0" * 64
    with pytest.raises(ValueError, match="differs from frozen"):
        m.verify_implementation({"implementation_sha256": hashes})
