import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import bayesian_feature_experiment_v2 as m


@pytest.mark.parametrize("version", sorted(m.DATASET_VERSIONS))
def test_load_preserves_review_flags_and_current_membership(tmp_path, version):
    row = {
        "audit_id": "a",
        "unit_id": "u",
        "building": "b",
        "period": "2026-09-01",
        "asking_rent": 5000.0,
        "square_feet": None,
        "analysis_price_basis": "current_capture_gross_ask",
        "bathrooms": 1.0,
        "reported_full_bathrooms": 1,
        "reported_half_bathrooms": 0,
        "bathroom_count_evidence": {
            "flags": ["reviewed_external_shared_bathroom_or_toilet_access"]
        },
    }
    publish_bundle(
        tmp_path, {"observations.jsonl": canonical(row) + "\n"}, {"version": version}
    )
    data, manifest = m.load_data(tmp_path)
    assert manifest["version"] == version
    assert (
        len(data) == 1
        and data.iloc[0].analysis_price_basis == "current_capture_gross_ask"
    )
    assert data.reported_full_bathrooms.tolist() == [1]
    assert not m.feature.bathroom_values(data)[2].any()


class BathDesign:
    features = ["full2", "full3", "shortfall", "half1", "half2"]

    def matrix(self, data):
        f = data.reported_full_bathrooms.to_numpy()
        h = data.reported_half_bathrooms.to_numpy()
        return np.column_stack(
            [f > 1, f > 2, np.maximum(data.bedrooms - f, 0), h > 0, h > 1]
        ).astype(float)


def bath_data():
    return pd.DataFrame(
        {
            "bedrooms": [2] * 5,
            "reported_full_bathrooms": [1, 2, 3, 1, 1],
            "reported_half_bathrooms": [0, 0, 0, 1, 2],
            "bathrooms": [1.0, 2.0, 3.0, 1.5, 2.0],
            "bathroom_count_evidence": [{"flags": []} for _ in range(5)],
            "unit_id": list("abcde"),
            "building": ["b"] * 5,
        }
    )


def test_supported_joint_directions_and_second_half_bath_increment():
    data = bath_data()
    design = BathDesign()
    directions = m.contrast_directions(design, data)
    np.testing.assert_array_equal(
        directions["bed2:net_minus1_to0_minus_0to1"], [1, -1, -1, 0, 0]
    )
    np.testing.assert_array_equal(directions["bed2:full1:half1_to_2"], [0, 0, 0, 0, 1])
    assert all(name.startswith("bed2:") for name in directions)
    beta = np.array([[0.2, 0.1, -0.05, 0.07, 0.03], [0.3, 0.2, -0.04, 0.08, 0.04]])
    rows = m.half_bath_contrasts(design, data, beta)
    second = next(
        r
        for r in rows
        if r["bedrooms"] == 2 and r["full_bathrooms"] == 1 and r["before_half"] == 1
    )
    assert second["supported_endpoints"] and second["encoded_contrast"]
    assert second["log_effect"]["median"] == pytest.approx(0.035)
    assert second["support_after"] == {"rows": 1, "units": 1, "buildings": 1}
    data.at[4, "bathroom_count_evidence"] = {"flags": ["not_usable"]}
    assert "bed2:full1:half1_to_2" not in m.contrast_directions(design, data)


def test_diagnostics_cover_actual_unit_effects_and_correlated_balance(monkeypatch):
    data = bath_data()
    design = BathDesign()
    z = np.arange(8).reshape(2, 4) / 100
    beta = np.zeros((2, 4, 5))
    beta[:, :, 0] = z + 0.3
    beta[:, :, 1] = z
    scale = np.arange(1, 9).reshape(2, 4) / 10
    unit_z = np.full((2, 4, 2), [1.0, -2.0])
    posterior = xr.Dataset(
        {
            "beta": (("chain", "draw", "feature"), beta),
            "sigma_unit": (("chain", "draw"), scale),
            "unit_z": (("chain", "draw", "unit"), unit_z),
        },
        coords={"feature": design.features, "unit": ["u", "v"]},
    )
    captured = {}

    def diagnostics(inference):
        captured.update(inference)
        return {"acceptable": True}, pd.DataFrame()

    monkeypatch.setattr(m.base, "diagnostics", diagnostics)
    m.derived_diagnostics(
        {"posterior": posterior, "sample_stats": "same stats"}, design, data
    )
    result = captured["posterior"]
    np.testing.assert_allclose(result.unit_effect, scale[:, :, None] * unit_z)
    np.testing.assert_allclose(
        result.bathroom_contrast.sel(contrast="bed2:net_minus1_to0_minus_0to1"), 0.3
    )
    assert captured["sample_stats"] == "same stats"


def test_failed_derived_diagnostics_withhold_convergence_even_when_parameters_pass(
    tmp_path, monkeypatch
):
    design = SimpleNamespace(
        features=["f"],
        support={},
        time=SimpleNamespace(buildings=["b"], unit_ids=["u"]),
    )
    monkeypatch.setattr(
        m.base,
        "diagnostics",
        lambda _: ({"acceptable": True, "maxdepth_reached": 0}, pd.DataFrame()),
    )
    monkeypatch.setattr(
        m, "derived_diagnostics", lambda *a: ({"acceptable": False}, pd.DataFrame())
    )
    samples = {
        "beta": np.zeros((4, 1)),
        "building_effect": np.zeros((4, 1)),
        "sigma_unit": np.ones(4),
        "unit_z": np.zeros((4, 1)),
    }
    monkeypatch.setattr(
        m.reports, "fitted_summary", lambda *a: ([{"residual_log": 0.1}], samples)
    )
    monkeypatch.setattr(m.reports, "bathroom_contrasts", lambda *a: {"balance": []})
    monkeypatch.setattr(m, "half_bath_contrasts", lambda *a: [])
    result = m.write_reports(tmp_path, None, design, None, "p")
    assert result["status"] == "diagnostic_only_do_not_interpret_intervals"


def test_completed_v2_run_replays_without_resampling_and_rejects_changed_protocol(
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
        lambda _: (
            data,
            {
                "version": "reviewed-bathroom-counts-projection-v1",
                "files": {"observations.jsonl": "source-hash"},
            },
        ),
    )

    def stop(*args):
        raise RuntimeError("stop before sampling")

    monkeypatch.setattr(m.feature, "FeatureDesign", stop)
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
    m.sampler.publish_fit(fit, version=m.VERSION, protocol_hash=protocol)
    assert m.run(args) == summary
    args.draws += 1
    with pytest.raises(ValueError):
        m.run(args)
