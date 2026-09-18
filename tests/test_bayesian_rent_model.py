import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "bayesian_model", Path(__file__).parents[1] / "models/bayesian_rent_model.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def data():
    return pd.DataFrame(
        {
            "unit_id": ["u1", "u2", "u3", "u1", "u2", "u3"],
            "building": ["b1", "b1", "b2"] * 2,
            "period": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-02-01",
                    "2020-03-01",
                    "2022-01-01",
                    "2022-02-01",
                    "2022-03-01",
                ]
            ),
            "bedrooms": [0.0, 1.0, 2.0, 0.0, 1.0, 2.0],
            "bathrooms": [1.0, 1.0, 2.0] * 2,
            "square_feet": [np.nan, 700.0, 1100.0] * 2,
            "asking_rent": [2000.0, 3000.0, 4000.0] * 2,
            "listing_ids": ["[]"] * 6,
        }
    )


def test_bayesian_design_incremental_train_only_and_anchor():
    train = data()
    design = m.Design(train, "2023-12-01")
    assert np.array_equal(
        design.raw_features(train)[:3, :5],
        [[0, 0, 0, 0, 0], [1, 0, 0, 0, 0], [1, 1, 0, 0, 0]],
    )
    assert np.allclose(design.time_matrix[design.anchor], 0)
    assert np.allclose(design.season_matrix.sum(axis=0), 0)
    test = train.iloc[:1].copy()
    test["unit_id"] = "new"
    test["building"] = "new"
    test["period"] = pd.Timestamp("2023-01-01")
    assert (
        design.arrays(test)["unit"][0] == -1
        and design.arrays(test)["building"][0] == -1
    )
    before = design.feature_means.copy()
    test["square_feet"] = 10000
    design.arrays(test)
    assert np.array_equal(before, design.feature_means)


def test_model_ablations_and_finite_log_density():
    train = data()
    for units, size in [(True, True), (False, True), (True, False)]:
        design = m.Design(train, "2023-12-01", units=units, size=size)
        model = m.build_model(train, design)
        assert ("unit_z" in model.named_vars) == units
        assert len(design.features) == (8 if size else 6)
        assert np.isfinite(model.compile_logp()(model.initial_point()))


def test_building_only_still_identifies_previously_seen_units():
    train = data()
    design = m.Design(train, "2023-12-01", units=False)
    assert design.arrays(train)["unit"].min() >= 0
    assert "unit_z" not in m.build_model(train, design).named_vars


def test_unseen_group_predictions_share_effects_and_add_uncertainty():
    import xarray as xr

    train = data()
    design = m.Design(train, "2023-12-01")
    chains, draws = 4, 500
    shape = (chains, draws)
    posterior = xr.Dataset(
        {
            "alpha": (("chain", "draw"), np.full(shape, np.log(3000))),
            "beta": (
                ("chain", "draw", "feature"),
                np.zeros((*shape, len(design.features))),
            ),
            "trend": (
                ("chain", "draw", "period"),
                np.zeros((*shape, len(design.periods))),
            ),
            "season": (("chain", "draw", "month"), np.zeros((*shape, 12))),
            "sigma": (("chain", "draw"), np.full(shape, 0.05)),
            "sigma_building": (("chain", "draw"), np.full(shape, 0.20)),
            "building_z": (
                ("chain", "draw", "building"),
                np.zeros((*shape, len(design.buildings))),
            ),
            "sigma_unit": (("chain", "draw"), np.full(shape, 0.30)),
            "unit_z": (
                ("chain", "draw", "unit"),
                np.zeros((*shape, len(design.unit_ids))),
            ),
        }
    )
    rows = pd.concat([train.iloc[[0]]] * 3, ignore_index=True)
    rows.loc[1:, "unit_id"] = "new-unit"
    rows.loc[1:, "building"] = "new-building"
    result = m.predict_table({"posterior": posterior}, design, rows, "student_t")
    assert result.seen_unit.tolist() == [True, False, False]
    assert np.isclose(result.predicted_rent.iloc[0], 3000)
    assert result.predicted_rent.iloc[1] == result.predicted_rent.iloc[2]
    width = result.upper_95 - result.lower_95
    assert width.iloc[1] > 3 * width.iloc[0]
    assert np.isfinite(result.log_predictive_density).all()


def test_nonfinite_sampler_diagnostics_never_pass(monkeypatch):
    import xarray as xr

    rng = np.random.default_rng(4)
    shape = (4, 200)
    inference = {
        "posterior": xr.Dataset({"alpha": (("chain", "draw"), rng.normal(size=shape))}),
        "sample_stats": xr.DataTree(
            xr.Dataset(
                {
                    "energy": (("chain", "draw"), rng.normal(size=shape)),
                    "diverging": (("chain", "draw"), np.zeros(shape, dtype=bool)),
                    "maxdepth_reached": (
                        ("chain", "draw"),
                        np.zeros(shape, dtype=bool),
                    ),
                }
            )
        ),
    }
    summary = pd.DataFrame(
        {"r_hat": [1.0, np.nan], "ess_bulk": [700.0, 800.0], "ess_tail": [700.0, 800.0]}
    )
    monkeypatch.setattr(m.az, "summary", lambda *args, **kwargs: summary)
    result, _ = m.diagnostics(inference)
    assert result["nonfinite_diagnostics"] == 1
    assert not result["acceptable"]


def test_trend_cannot_duplicate_a_pure_seasonal_pattern():
    periods = pd.date_range("2010-01-01", "2026-08-01", freq="MS")
    trend, anchor = m.time_basis(periods)
    seasonal = m.scipy.linalg.null_space(np.ones((1, 12)))[periods.month - 1]
    combined = np.column_stack([np.ones(len(periods)), trend, seasonal])
    assert np.linalg.matrix_rank(combined) == combined.shape[1]
    assert np.allclose(trend[anchor], 0)


def test_likelihood_rotation_preserves_the_trend_prior_covariance():
    train = data()
    design = m.Design(train, "2023-12-01")
    original, _ = m.time_basis(design.periods)
    transformed = design.time_matrix * design.time_prior_scales
    assert np.allclose(original @ original.T, transformed @ transformed.T)


def test_saved_design_reuses_exact_training_transforms(tmp_path):
    train = data()
    original = m.Design(train, "2023-12-01")
    original.save(tmp_path / "design.json")
    loaded = m.Design.load(tmp_path / "design.json")
    future = train.iloc[:2].copy()
    future["period"] = pd.Timestamp("2023-11-01")
    future.loc[future.index[0], "unit_id"] = "unknown"
    future.loc[future.index[1], "square_feet"] = np.nan
    for name, values in original.arrays(future).items():
        assert np.array_equal(values, loaded.arrays(future)[name])
    assert np.array_equal(original.time_matrix, loaded.time_matrix)
    assert np.array_equal(original.time_center, loaded.time_center)


def test_linear_drift_is_separate_from_spline_and_seasonality(tmp_path):
    train = data()
    design = m.Design(train, "2023-12-01", linear_drift=True)
    seasonal = design.season_matrix[design.periods.month - 1]
    combined = np.column_stack(
        [np.ones(len(design.periods)), design.time_matrix, design.linear_time, seasonal]
    )
    assert np.linalg.matrix_rank(combined) == combined.shape[1]
    model = m.build_model(train, design)
    assert "annual_drift" in model.named_vars
    assert np.isfinite(model.compile_logp()(model.initial_point()))
    design.save(tmp_path / "design.json")
    loaded = m.Design.load(tmp_path / "design.json")
    assert np.array_equal(loaded.linear_time, design.linear_time)
    assert loaded.linear_center == design.linear_center


def test_chunked_diagnostics_match_full_parameter_diagnostics():
    import xarray as xr

    rng = np.random.default_rng(81)
    shape = (4, 100)
    tree = xr.DataTree.from_dict(
        {
            "/posterior": xr.Dataset(
                {"unit_z": (("chain", "draw", "unit"), rng.normal(size=(*shape, 520)))},
                coords={"unit": np.arange(520)},
            ),
            "/sample_stats": xr.Dataset(
                {
                    "energy": (("chain", "draw"), rng.normal(size=shape)),
                    "diverging": (("chain", "draw"), np.zeros(shape, dtype=bool)),
                    "maxdepth_reached": (
                        ("chain", "draw"),
                        np.zeros(shape, dtype=bool),
                    ),
                }
            ),
        }
    )
    expected = m.az.summary(
        tree, var_names=["unit_z"], kind="diagnostics", round_to="none"
    ).sort_index()
    _, actual = m.diagnostics(tree)
    pd.testing.assert_frame_equal(actual.sort_index(), expected)


def test_drift_and_nonlinear_time_are_orthogonal_on_training_dates():
    train = data()
    design = m.Design(train, "2023-12-01", linear_drift=True)
    periods = design.periods.get_indexer(train.period)
    centered_linear = design.linear_time[periods] - design.linear_center
    centered_spline = design.time_matrix[periods] - design.time_center
    assert np.allclose(centered_linear @ centered_spline, 0, atol=1e-10)
