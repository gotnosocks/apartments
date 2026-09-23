"""Posterior arithmetic and artifact integrity without stochastic sampling."""

from types import SimpleNamespace
import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle
from models import bayesian_feature_experiment as m


class ReconstructionTime:
    time_matrix = np.array([[0.2, -0.3], [0.7, 0.1]])
    time_center = np.array([0.1, -0.1])
    linear_time = np.array([-1.0, 1.0])
    linear_center = 0.25
    season_matrix = np.array([[1.0], [-1.0]])
    season_weights = np.array([0.75, 0.25])

    def arrays(self, data):
        return {
            name: data[name].to_numpy(int)
            for name in ("period", "season", "building", "unit")
        }


class ReconstructionDesign:
    time = ReconstructionTime()

    def matrix(self, data):
        return data[["x0", "x1"]].to_numpy(float)


def test_joint_posterior_reconstruction_matches_hand_calculation_across_blocks():
    n = 130  # Deliberately cross the runner's 128-observation block boundary.
    design = ReconstructionDesign()
    data = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(n)],
            "source_listing_id": np.arange(n) + 100,
            "unit_id": [f"u{i % 2}" for i in range(n)],
            "building": np.arange(n) % 2,
            "unit": np.arange(n) % 2,
            "season": np.arange(n) % 2,
            "period_index": np.arange(n) % 2,
            "period": pd.to_datetime(
                np.where(np.arange(n) % 2, "2022-02-01", "2022-01-01")
            ),
            "asking_rent": np.linspace(3500, 7000, n),
            "x0": np.linspace(-0.5, 0.5, n),
            "x1": 0.75,
        }
    )
    # Keep calendar dates for output while adapting array indexes for reconstruction.
    design.time = SimpleNamespace(
        **{
            k: getattr(ReconstructionTime, k)
            for k in (
                "time_matrix",
                "time_center",
                "linear_time",
                "linear_center",
                "season_matrix",
                "season_weights",
            )
        }
    )
    design.time.arrays = lambda frame: {
        "period": frame.period_index.to_numpy(int),
        **{name: frame[name].to_numpy(int) for name in ("season", "building", "unit")},
    }
    flat = {
        "alpha": np.log([4000.0, 4500.0, 5000.0, 5500.0]),
        "beta": np.array([[0.1, 0.2], [0.2, -0.1], [-0.1, 0.3], [0.4, 0.2]]),
        "trend_coefficients": np.array(
            [[0.03, 0.04], [0.06, -0.02], [-0.01, 0.08], [0.02, 0.01]]
        ),
        "annual_drift": np.array([0.01, 0.02, 0.03, 0.04]),
        "season_coefficients": np.array([[0.05], [0.02], [-0.03], [0.04]]),
        "building_effect": np.array(
            [[0.1, -0.1], [0.2, -0.2], [0.3, -0.3], [0.4, -0.4]]
        ),
        "sigma_unit": np.array([0.1, 0.2, 0.3, 0.4]),
        "unit_z": np.array([[1.0, -1.0], [2.0, -2.0], [-1.0, 1.0], [0.5, -0.5]]),
    }
    dims = {
        "beta": "feature",
        "trend_coefficients": "trend_basis",
        "season_coefficients": "season_basis",
        "building_effect": "building",
        "unit_z": "unit",
    }
    posterior = xr.Dataset(
        {
            name: (
                ("chain", "draw", dims[name]) if name in dims else ("chain", "draw"),
                values.reshape((2, 2) + values.shape[1:]),
            )
            for name, values in flat.items()
        }
    )
    result, samples = m.fitted_summary({"posterior": posterior}, design, data)
    assert len(result) == n
    for name, values in flat.items():
        np.testing.assert_array_equal(samples[name], values)
    for i in (0, 1, 127, 128, 129):
        r = data.iloc[i]
        period, season, building, unit = (
            int(r.period_index),
            int(r.season),
            int(r.building),
            int(r.unit),
        )
        d = design.time
        hand = np.array(
            [
                flat["alpha"][j]
                + flat["beta"][j, 0] * r.x0
                + flat["beta"][j, 1] * r.x1
                + np.sum(
                    flat["trend_coefficients"][j]
                    * (d.time_matrix[period] - d.time_center)
                )
                + flat["annual_drift"][j] * (d.linear_time[period] - d.linear_center)
                + flat["season_coefficients"][j, 0] * (d.season_matrix[season, 0] - 0.5)
                + flat["building_effect"][j, building]
                + flat["sigma_unit"][j] * flat["unit_z"][j, unit]
                for j in range(4)
            ]
        )
        lower, estimate, upper = np.exp(np.quantile(hand, [0.025, 0.5, 0.975]))
        assert result[i]["fitted_rent"] == pytest.approx(estimate)
        assert result[i]["latent_rent_lower_95"] == pytest.approx(lower)
        assert result[i]["latent_rent_upper_95"] == pytest.approx(upper)
        assert result[i]["residual_dollars"] == pytest.approx(r.asking_rent - estimate)
        assert result[i]["residual_log"] == pytest.approx(
            np.log(r.asking_rent / estimate)
        )
        assert result[i]["audit_id"] == f"a{i}"


class BathroomDesign:
    def matrix(self, data):
        full = data.reported_full_bathrooms.to_numpy()
        half = data.reported_half_bathrooms.to_numpy()
        return np.column_stack(
            [
                full > 1,
                full > 2,
                full > 3,
                full > 4,
                half > 0,
                np.maximum(data.bedrooms.to_numpy() - full, 0),
            ]
        )


def test_bathroom_balance_uses_joint_draws_not_independent_marginal_intervals():
    data = pd.DataFrame(
        {
            "bedrooms": [2] * 4,
            "reported_full_bathrooms": [1, 2, 3, 3],
            "reported_half_bathrooms": [0] * 4,
            "bathrooms": [1, 2, 3, 3],
            "bathroom_count_evidence": [{"flags": []}] * 3
            + [{"flags": ["shared_facility"]}],
            "unit_id": ["u1", "u2", "u3", "u4"],
            "building": ["b1", "b1", "b2", "b3"],
        }
    )
    z = np.linspace(-1, 1, 100)
    beta = np.zeros((100, 6))
    beta[:, 0], beta[:, 1], beta[:, 5] = z + 0.2, z, -0.1
    report = m.bathroom_contrasts(BathroomDesign(), data, beta)
    balance = next(r for r in report["balance"] if r["bedrooms"] == 2)
    # First increment z+.3 and second z are correlated perfectly. Their
    # difference is exactly .3 despite wide marginal intervals.
    assert balance["difference"]["lower_95"] == pytest.approx(0.3)
    assert balance["difference"]["median"] == pytest.approx(0.3)
    assert balance["difference"]["upper_95"] == pytest.approx(0.3)
    assert balance["probability_first_increment_larger"] == 1
    assert balance["support"] == [
        {"rows": 1, "units": 1, "buildings": 1},
        {"rows": 1, "units": 1, "buildings": 1},
        {"rows": 1, "units": 1, "buildings": 1},
    ]
    first = next(
        r
        for r in report["increments"]
        if r["bedrooms"] == 2 and r["before_full_half"] == (1, 0)
    )
    assert first["supported_endpoints"]
    expected = 100 * np.expm1(z + 0.3)
    assert first["percent_effect"]["median"] == pytest.approx(np.median(expected))
    assert first["percent_effect"]["lower_95"] == pytest.approx(
        np.quantile(expected, 0.025)
    )
    unsupported = next(r for r in report["increments"] if r["bedrooms"] == 1)
    assert not unsupported["supported_endpoints"]


def test_binary_fit_manifest_replay_and_tampering(tmp_path):
    (tmp_path / "posterior.nc").write_bytes(bytes(range(256)))
    (tmp_path / "summary.json").write_text(canonical({"status": "test"}) + "\n")
    m.publish_fit(tmp_path, "protocol-a")
    first = (tmp_path / "complete.json").read_bytes()
    manifest, files = _verified_bundle(tmp_path, retain={"posterior.nc"})
    assert files["posterior.nc"] == bytes(range(256))
    assert manifest["protocol_sha256"] == "protocol-a"
    m.publish_fit(tmp_path, "protocol-a")
    assert (tmp_path / "complete.json").read_bytes() == first
    (tmp_path / "posterior.nc").write_bytes(b"changed posterior")
    with pytest.raises(ValueError, match="integrity failure: posterior.nc"):
        _verified_bundle(tmp_path)


def test_completed_run_replays_without_sampling_and_rejects_binary_tampering(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "complete.json").write_text("{}\n")
    data = pd.DataFrame(
        {
            "unit_id": ["u"],
            "building": ["b"],
            "analysis_price_basis": ["current_capture_gross_ask"],
        }
    )
    monkeypatch.setattr(
        m,
        "load_data",
        lambda _: (data, {"files": {"observations.jsonl": "source-hash"}}),
    )

    def stop_design(*args):
        raise RuntimeError("stop before sampling")

    monkeypatch.setattr(m.feature, "FeatureDesign", stop_design)
    args = SimpleNamespace(
        output=tmp_path / "run",
        dataset=source_dir,
        spec="full_half_balance",
        draws=100,
        tune=100,
        chains=2,
        seed=1,
        target_accept=0.9,
        adaptation="diag",
        prior_multiplier=1.0,
    )
    with pytest.raises(RuntimeError, match="stop before sampling"):
        m.run(args)
    protocol = json.loads((args.output / "protocol" / "complete.json").read_text())[
        "protocol_sha256"
    ]
    fit = args.output / "fit"
    summary = {
        "status": "diagnostic_only_do_not_interpret_intervals",
        "protocol_sha256": protocol,
    }
    (fit / "summary.json").write_text(canonical(summary) + "\n")
    (fit / "posterior.nc").write_bytes(bytes(range(256)))
    m.publish_fit(fit, protocol)
    assert m.run(args) == summary
    original_manifest = (fit / "complete.json").read_bytes()
    wrong = json.loads(original_manifest)
    wrong["protocol_sha256"] = "different-protocol"
    (fit / "complete.json").write_text(canonical(wrong) + "\n")
    with pytest.raises(ValueError, match="Protocol mismatch"):
        m.run(args)
    (fit / "complete.json").write_bytes(original_manifest)
    (fit / "posterior.nc").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity failure: posterior.nc"):
        m.run(args)
