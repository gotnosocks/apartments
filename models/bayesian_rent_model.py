"""Local Bayesian asking-rent experiments using frozen canonical-unit model inputs.

Incremental bedroom effects, smooth time, seasonality, hierarchical buildings and
optional units, with posterior prediction for unseen groups and future periods.
"""

from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")
import numpy as np
import pandas as pd
import scipy.linalg
import scipy.interpolate
from scipy.special import logsumexp
from scipy.stats import t as student_t, norm
import pymc as pm
import pytensor.tensor as pt
import arviz as az


def file_hash(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def emit(phase, **data):
    print(
        json.dumps(
            {"phase": phase, "utc": pd.Timestamp.now(tz="UTC").isoformat(), **data},
            default=str,
        ),
        flush=True,
    )


def time_basis(periods, spacing=3, separate_linear=False):
    """Whitened, proper cubic-spline curvature prior, anchored at January 2022."""
    n = len(periods)
    if n < 24:
        raise ValueError(
            "Need at least 24 monthly periods to separate trend and seasonality"
        )
    knots = np.r_[
        np.repeat(0.0, 4),
        np.arange(spacing, n - 1, spacing),
        np.repeat(float(n - 1), 4),
    ]
    spline = scipy.interpolate.BSpline.design_matrix(
        np.arange(n, dtype=float), knots, 3
    ).toarray()
    k = spline.shape[1]
    q = scipy.linalg.null_space(np.ones((1, k)))
    d2 = np.diff(np.eye(k), n=2, axis=0)
    precision = q.T @ (d2.T @ d2 + 0.01 * np.eye(k)) @ q
    anchor = int(np.clip(periods.searchsorted(pd.Timestamp("2022-01-01")), 0, n - 1))
    centered = (spline - spline[anchor]) @ q
    transform = scipy.linalg.solve_triangular(
        np.linalg.cholesky(precision), centered.T, lower=True
    ).T
    # Quarterly splines can exactly reproduce three repeating annual patterns.
    # Condition those pure seasonal coefficient directions to zero, leaving
    # seasonality to its explicit contrasts and an identifiable trend basis.
    seasonal = scipy.linalg.null_space(np.ones((1, 12)))[periods.month - 1]
    nuisance = [np.ones(n), seasonal]
    if separate_linear:
        nuisance.append((np.arange(n) - anchor) / 12.0)
    seasonal_space = scipy.linalg.orth(np.column_stack(nuisance))
    residual = transform - seasonal_space @ (seasonal_space.T @ transform)
    alias = scipy.linalg.null_space(residual)
    if alias.shape[1]:
        transform = transform @ scipy.linalg.null_space(alias.T)
    return transform, anchor


class Design:
    def __init__(self, train, end, *, size=True, units=True, linear_drift=False):
        self.size = size
        self.units = units
        self.linear_drift = linear_drift
        self.basis_version = "season-separated-rotated-v4"
        self.group_parameterization = "centered-zero-sum-building-v1"
        self.periods = pd.date_range(
            train.period.min(), pd.Timestamp(end).to_period("M").start_time, freq="MS"
        )
        raw_time, self.anchor = time_basis(self.periods, separate_linear=linear_drift)
        self.linear_time = (np.arange(len(self.periods)) - self.anchor) / 12.0
        period_index = self.periods.get_indexer(pd.DatetimeIndex(train.period))
        counts = np.bincount(period_index, minlength=len(self.periods))
        if linear_drift:
            # Define drift as the training-weighted linear time component.
            # Removing only exact linear duplication leaves near-collinear
            # nonlinear curves; this projection gives the slope a clear meaning.
            linear_design = np.column_stack(
                [np.ones(len(self.periods)), self.linear_time]
            )
            projection = np.linalg.lstsq(
                linear_design * np.sqrt(counts[:, None]),
                raw_time * np.sqrt(counts[:, None]),
                rcond=None,
            )[0]
            raw_time = raw_time - linear_design @ projection
            raw_time = raw_time - raw_time[self.anchor]
        # Rotate into training-likelihood directions and scale them. The prior
        # covariance is unchanged: each new coefficient gets the matching scale.
        _, singular_values, rotation = np.linalg.svd(
            raw_time * np.sqrt(counts[:, None]), full_matrices=False
        )
        self.time_prior_scales = np.maximum(singular_values, 1.0)
        self.time_matrix = (raw_time @ rotation.T) / self.time_prior_scales
        self.time_center = np.average(self.time_matrix, axis=0, weights=counts)
        self.linear_center = float(np.average(self.linear_time, weights=counts))
        self.season_weights = np.bincount(
            train.period.dt.month.to_numpy() - 1, minlength=12
        ) / len(train)
        self.season_matrix = scipy.linalg.null_space(np.ones((1, 12)))
        self.buildings = sorted(train.building.unique())
        self.unit_ids = sorted(train.unit_id.unique())
        self.size_medians = {
            str(int(b)): float(v)
            for b, v in train.groupby("bedrooms").square_feet.median().dropna().items()
        }
        self.size_default = (
            float(train.square_feet.median())
            if train.square_feet.notna().any()
            else 700.0
        )
        self.features = [
            *[f"bedrooms_gt_{i}" for i in range(5)],
            "bathrooms_above_one",
        ] + (["log_size_within_bedrooms", "size_missing"] if size else [])
        self.feature_means = self.raw_features(train).mean(axis=0)

    def raw_features(self, data):
        cols = [data.bedrooms.gt(i).to_numpy(dtype=float) for i in range(5)]
        cols.append(data.bathrooms.to_numpy(dtype=float) - 1)
        if self.size:
            area = data.square_feet.to_numpy(dtype=float)
            median = data.bedrooms.map(
                lambda b: self.size_medians.get(str(int(b)), self.size_default)
            ).to_numpy()
            present = np.isfinite(area)
            cols.extend(
                [
                    np.log(np.where(present, area, median) / median),
                    (~present).astype(float),
                ]
            )
        return np.column_stack(cols)

    def arrays(self, data):
        periods = self.periods.get_indexer(pd.DatetimeIndex(data.period))
        if (periods < 0).any():
            raise ValueError("Prediction period is outside the fitted horizon")
        building = (
            data.building.map({b: i for i, b in enumerate(self.buildings)})
            .fillna(-1)
            .to_numpy(dtype=int)
        )
        unit = (
            data.unit_id.map({u: i for i, u in enumerate(self.unit_ids)})
            .fillna(-1)
            .to_numpy(dtype=int)
        )
        return {
            "x": self.raw_features(data) - self.feature_means,
            "period": periods,
            "season": data.period.dt.month.to_numpy() - 1,
            "building": building,
            "unit": unit,
        }

    def save(self, path):
        meta = {
            k: v
            for k, v in self.__dict__.items()
            if k
            not in {
                "linear_time",
                "time_matrix",
                "season_matrix",
                "periods",
                "feature_means",
                "time_prior_scales",
                "time_center",
                "season_weights",
            }
        }
        meta.update(
            periods=self.periods.strftime("%Y-%m-%d").tolist(),
            feature_means=self.feature_means.tolist(),
            linear_time=self.linear_time.tolist(),
            time_prior_scales=self.time_prior_scales.tolist(),
            time_center=self.time_center.tolist(),
            season_weights=self.season_weights.tolist(),
        )
        Path(path).write_text(json.dumps(meta, indent=2))
        np.savez_compressed(
            Path(path).with_suffix(".npz"),
            time_matrix=self.time_matrix,
            season_matrix=self.season_matrix,
        )

    @classmethod
    def load(cls, path):
        """Reload the exact fitted design without re-estimating training scales."""
        design = cls.__new__(cls)
        for key, value in json.loads(Path(path).read_text()).items():
            setattr(design, key, value)
        design.periods = pd.DatetimeIndex(pd.to_datetime(design.periods))
        for key in [
            "feature_means",
            "linear_time",
            "time_prior_scales",
            "time_center",
            "season_weights",
        ]:
            setattr(design, key, np.asarray(getattr(design, key), dtype=float))
        with np.load(Path(path).with_suffix(".npz"), allow_pickle=False) as arrays:
            design.time_matrix = arrays["time_matrix"].copy()
            design.season_matrix = arrays["season_matrix"].copy()
        return design


def build_model(train, design, likelihood="student_t", centered_time=True):
    a = design.arrays(train)
    coords = {
        "feature": design.features,
        "period": design.periods.strftime("%Y-%m-%d").tolist(),
        "trend_basis": np.arange(design.time_matrix.shape[1]),
        "season_basis": np.arange(11),
        "month": np.arange(1, 13),
        "building": design.buildings,
        "observation": np.arange(len(train)),
    }
    if design.units:
        coords["unit"] = design.unit_ids
    with pm.Model(coords=coords) as model:
        alpha = pm.Normal("alpha", np.log(4500), 0.8)
        means = np.array(
            [0.20, 0.18, 0.15, 0.10, 0.10, 0.10] + ([0.35, 0.0] if design.size else [])
        )
        scales = np.array([0.25] * 5 + [0.20] + ([0.30, 0.20] if design.size else []))
        beta = pm.Normal("beta", means, scales, dims="feature")
        trend_scale = pm.HalfNormal("trend_scale", 0.15)
        trend_coefficients = (
            pm.Normal(
                "trend_coefficients",
                0,
                trend_scale * design.time_prior_scales,
                dims="trend_basis",
            )
            if centered_time
            else trend_scale
            * design.time_prior_scales
            * pm.Normal("trend_z", 0, 1, dims="trend_basis")
        )
        drift = pm.Normal("annual_drift", 0.03, 0.05) if design.linear_drift else 0.0
        trend = pm.Deterministic(
            "trend",
            pt.dot(design.time_matrix, trend_coefficients) + drift * design.linear_time,
            dims="period",
        )
        season_scale = pm.HalfNormal("season_scale", 0.10)
        season_coefficients = (
            pm.Normal("season_coefficients", 0, season_scale, dims="season_basis")
            if centered_time
            else season_scale * pm.Normal("season_z", 0, 1, dims="season_basis")
        )
        season = pm.Deterministic(
            "season", pt.dot(design.season_matrix, season_coefficients), dims="month"
        )
        sigma_building = pm.HalfNormal("sigma_building", 0.35)
        building_effect = pm.ZeroSumNormal(
            "building_effect", sigma=sigma_building, dims="building"
        )
        building_z = pm.Deterministic(
            "building_z", building_effect / sigma_building, dims="building"
        )
        intercept = pm.Deterministic(
            "intercept",
            alpha
            - drift * design.linear_center
            - pt.dot(design.time_center, trend_coefficients)
            - pt.dot(design.season_weights, season),
        )
        mu = (
            intercept
            + pt.dot(a["x"], beta)
            + trend[a["period"]]
            + season[a["season"]]
            + building_effect[a["building"]]
        )
        if design.units:
            sigma_unit = pm.HalfNormal("sigma_unit", 0.25)
            unit_z = pm.Normal("unit_z", 0, 1, dims="unit")
            mu = mu + sigma_unit * unit_z[a["unit"]]
        sigma = pm.HalfNormal("sigma", 0.25)
        if likelihood == "student_t":
            pm.StudentT(
                "log_rent",
                nu=5,
                mu=mu,
                sigma=sigma,
                observed=np.log(train.asking_rent),
                dims="observation",
            )
        elif likelihood == "normal":
            pm.Normal(
                "log_rent",
                mu=mu,
                sigma=sigma,
                observed=np.log(train.asking_rent),
                dims="observation",
            )
        else:
            raise ValueError("Unknown likelihood")
    return model


def posterior_dataset(inference):
    node = inference["posterior"]
    return node.to_dataset() if hasattr(node, "to_dataset") else node


def sample_values(posterior, name):
    return (
        posterior[name].stack(sample=("chain", "draw")).transpose("sample", ...).values
    )


def diagnostics(inference):
    posterior = posterior_dataset(inference)
    names = [name for name in posterior.data_vars if name not in {"trend", "season"}]
    # Ranking all 20,000+ unit traces at once allocates several full-size
    # temporary arrays. Chunk only the parameter axis; every chain/draw remains.
    summaries = []
    for name in names:
        variable = posterior[[name]]
        dimensions = [
            dim for dim in posterior[name].dims if dim not in {"chain", "draw"}
        ]
        if len(dimensions) == 1 and variable.sizes[dimensions[0]] > 512:
            dim = dimensions[0]
            pieces = (
                variable.isel({dim: slice(start, start + 512)})
                for start in range(0, variable.sizes[dim], 512)
            )
        else:
            pieces = [variable]
        summaries.extend(
            az.summary(piece, kind="diagnostics", round_to="none") for piece in pieces
        )
    summary = pd.concat(summaries)
    stats = inference["sample_stats"].to_dataset()
    rhat = summary["r_hat"]
    ess = summary["ess_bulk"]
    tail = summary["ess_tail"]
    result = {
        "max_rhat": float(rhat.max()),
        "rhat_over_1_01": int((rhat > 1.01).sum()),
        "min_ess_bulk": float(ess.min()),
        "median_ess_bulk": float(ess.median()),
        "min_ess_tail": float(tail.min()),
        "divergences": int(stats["diverging"].sum().item()),
        "parameters": len(summary),
    }
    for name in ["tree_depth", "depth", "n_steps"]:
        if name in stats:
            result["max_" + name] = float(stats[name].max().item())
    result["worst_rhat"] = (
        summary.sort_values("r_hat", ascending=False)
        .head(12)
        .reset_index()
        .to_dict(orient="records")
    )
    energy = stats["energy"].transpose("chain", "draw").values
    bfmi = np.mean(np.diff(energy, axis=1) ** 2, axis=1) / np.var(energy, axis=1)
    result["bfmi_per_chain"] = bfmi.tolist()
    result["min_bfmi"] = float(bfmi.min())
    result["maxdepth_reached"] = int(stats["maxdepth_reached"].sum().item())
    result["nonfinite_diagnostics"] = int(
        (~np.isfinite(summary[["r_hat", "ess_bulk", "ess_tail"]])).sum().sum()
    )
    result["acceptable"] = (
        result["max_rhat"] < 1.01
        and result["min_ess_bulk"] >= 400
        and result["min_ess_tail"] >= 400
        and result["divergences"] == 0
        and result["min_bfmi"] >= 0.3
        and result["nonfinite_diagnostics"] == 0
    )
    return result, summary


def predict_table(inference, design, data, likelihood, seed=8821, limit_draws=2000):
    posterior = posterior_dataset(inference)
    rng = np.random.default_rng(seed)
    total = posterior.sizes["chain"] * posterior.sizes["draw"]
    selected = np.linspace(0, total - 1, min(total, limit_draws), dtype=int)

    def values(name):
        return sample_values(posterior, name)[selected]

    alpha = values("intercept" if "intercept" in posterior else "alpha")
    beta = values("beta")
    trend = values("trend")
    season = values("season")
    sigma = values("sigma")
    sb = values("sigma_building")
    bz = values("building_z")
    su = values("sigma_unit") if design.units else np.zeros(len(alpha))
    uz = values("unit_z") if design.units else None
    a = design.arrays(data)
    # Shared new-group draws preserve repeated-unit dependence within each draw.
    unknown_buildings = sorted(data.loc[a["building"] < 0, "building"].unique())
    unknown_units = (
        sorted(data.loc[a["unit"] < 0, "unit_id"].unique()) if design.units else []
    )
    nb = {b: rng.normal(size=len(alpha)) * sb for b in unknown_buildings}
    nu = {u: rng.normal(size=len(alpha)) * su for u in unknown_units}
    output = []
    for start in range(0, len(data), 512):
        end = min(start + 512, len(data))
        part = data.iloc[start:end]
        mu = (
            alpha[:, None]
            + beta @ a["x"][start:end].T
            + trend[:, a["period"][start:end]]
            + season[:, a["season"][start:end]]
        )
        for j, row in enumerate(part.itertuples()):
            bi = a["building"][start + j]
            ui = a["unit"][start + j]
            mu[:, j] += sb * bz[:, bi] if bi >= 0 else nb[row.building]
            if design.units:
                mu[:, j] += su * uz[:, ui] if ui >= 0 else nu[row.unit_id]
        noise = (
            rng.standard_t(5, size=mu.shape)
            if likelihood == "student_t"
            else rng.normal(size=mu.shape)
        ) * sigma[:, None]
        y = np.log(part.asking_rent.to_numpy())
        density = (
            student_t.logpdf(y[None, :], df=5, loc=mu, scale=sigma[:, None])
            if likelihood == "student_t"
            else norm.logpdf(y[None, :], loc=mu, scale=sigma[:, None])
        )
        point = np.exp(np.median(mu, axis=0))
        quantiles = np.exp(
            np.quantile(mu + noise, [0.025, 0.10, 0.50, 0.90, 0.975], axis=0)
        )
        frame = part[
            ["unit_id", "building", "period", "bedrooms", "asking_rent", "listing_ids"]
        ].copy()
        frame["predicted_rent"] = point
        for name, vals in zip(
            ["lower_95", "lower_80", "predictive_median", "upper_80", "upper_95"],
            quantiles,
        ):
            frame[name] = vals
        frame["log_predictive_density"] = logsumexp(density, axis=0) - np.log(
            len(alpha)
        )
        frame["seen_unit"] = a["unit"][start:end] >= 0
        frame["seen_building"] = a["building"][start:end] >= 0
        output.append(frame)
    return pd.concat(output, ignore_index=True)


def score(predictions):
    y = predictions.asking_rent.to_numpy()
    pred = predictions.predicted_rent.to_numpy()
    error = np.abs(pred / y - 1) * 100
    return {
        "observations": len(y),
        "median_absolute_percent_error": float(np.median(error)),
        "mean_absolute_percent_error": float(np.mean(error)),
        "log_rmse": float(np.sqrt(np.mean(np.log(pred / y) ** 2))),
        "median_signed_percent_error": float(np.median((pred / y - 1) * 100)),
        "within_20_percent": float(np.mean(error <= 20) * 100),
        "coverage_80": float(
            np.mean((y >= predictions.lower_80) & (y <= predictions.upper_80)) * 100
        ),
        "coverage_95": float(
            np.mean((y >= predictions.lower_95) & (y <= predictions.upper_95)) * 100
        ),
        "median_interval_80_width_percent": float(
            np.median((predictions.upper_80 - predictions.lower_80) / y * 100)
        ),
        "mean_log_predictive_density": float(predictions.log_predictive_density.mean()),
    }


def run(args):
    started = time.monotonic()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    data = pd.read_parquet(args.input)
    data = data[data.period <= pd.Timestamp(args.predict_end)].copy()
    if args.max_units:
        units = sorted(
            data.unit_id.unique(), key=lambda u: hashlib.sha256(u.encode()).hexdigest()
        )[: args.max_units]
        data = data[data.unit_id.isin(units)]
    if args.holdout_units:
        held = {
            u
            for u in data.unit_id.unique()
            if int(hashlib.sha256(u.encode()).hexdigest()[:8], 16) % 5 == 0
        }
        train = data[
            (data.period <= pd.Timestamp(args.train_end)) & (~data.unit_id.isin(held))
        ].copy()
        test = data[data.unit_id.isin(held)].copy()
    else:
        train = data[data.period <= pd.Timestamp(args.train_end)].copy()
        test = data[data.period > pd.Timestamp(args.train_end)].copy()
    if train.empty:
        raise ValueError("No training rows")
    design = Design(
        train,
        args.predict_end,
        size=not args.no_size,
        units=not args.no_units,
        linear_drift=args.linear_drift,
    )
    design.save(output / "design.json")
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    settings.update(
        training_rows=len(train),
        evaluation_rows=len(test),
        training_units=train.unit_id.nunique(),
        training_buildings=train.building.nunique(),
        input_sha256=file_hash(args.input),
        source_sha256=file_hash(__file__),
    )
    (output / "settings.json").write_text(json.dumps(settings, indent=2))
    emit("building", **settings)
    model = build_model(
        train, design, args.likelihood, centered_time=not args.noncentered_time
    )
    with model:
        prior = pm.sample_prior_predictive(
            draws=80,
            random_seed=312,
            var_names=["alpha", "beta", "sigma", "trend", "season"],
            return_inferencedata=True,
        )
        prior.to_netcdf(output / "prior.nc", engine="h5netcdf")
        emit("sampling", elapsed_seconds=time.monotonic() - started)
        inference = pm.sample(
            draws=args.draws,
            tune=args.tune,
            chains=args.chains,
            cores=min(args.chains, 4),
            nuts_sampler="nutpie",
            backend="numba",
            target_accept=args.target_accept,
            nuts={"adaptation": args.adaptation},
            random_seed=150130,
            progressbar=False,
            return_inferencedata=True,
            idata_kwargs={"log_likelihood": False},
            compute_convergence_checks=False,
        )
    emit("sampled", elapsed_seconds=time.monotonic() - started)
    inference.to_netcdf(output / "posterior.nc", engine="h5netcdf")
    diag, summary = diagnostics(inference)
    summary.to_parquet(output / "parameter_diagnostics.parquet")
    (output / "diagnostics.json").write_text(json.dumps(diag, indent=2))
    results = {"settings": settings, "diagnostics": diag, "scores": {}}
    if not test.empty:
        predictions = predict_table(inference, design, test, args.likelihood)
        predictions.to_parquet(output / "validation.parquet", index=False)
        results["scores"]["all"] = score(predictions)
        for key, mask in [
            ("seen_units", predictions.seen_unit),
            ("unseen_units", ~predictions.seen_unit),
        ]:
            if mask.any():
                results["scores"][key] = score(predictions[mask])
    posterior = posterior_dataset(inference)
    trend = sample_values(posterior, "trend")
    idx = 100 * np.exp(trend)
    pd.DataFrame(
        {
            "period": design.periods,
            "index_median": np.median(idx, axis=0),
            "index_lower_95": np.quantile(idx, 0.025, axis=0),
            "index_upper_95": np.quantile(idx, 0.975, axis=0),
        }
    ).to_parquet(output / "index.parquet", index=False)
    beta = sample_values(posterior, "beta")
    effects = 100 * np.expm1(beta)
    pd.DataFrame(
        {
            "term": design.features,
            "median_percent": np.median(effects, axis=0),
            "lower_95_percent": np.quantile(effects, 0.025, axis=0),
            "upper_95_percent": np.quantile(effects, 0.975, axis=0),
        }
    ).to_parquet(output / "coefficients.parquet", index=False)
    results["runtime_seconds"] = time.monotonic() - started
    results["versions"] = {
        x: importlib.metadata.version(x)
        for x in ["pymc", "pytensor", "nutpie", "arviz", "numpy", "scipy"]
    }
    (output / "results.json").write_text(json.dumps(results, indent=2))
    manifest = {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "complete.json").write_text(
        json.dumps(
            {
                "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "diagnostics_acceptable": diag["acceptable"],
                "artifacts_sha256": manifest,
            },
            indent=2,
        )
    )
    emit(
        "complete",
        runtime_seconds=results["runtime_seconds"],
        diagnostics=diag,
        scores=results["scores"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-end", default="2024-12-01")
    parser.add_argument("--predict-end", default="2025-12-01")
    parser.add_argument("--draws", type=int, default=600)
    parser.add_argument("--tune", type=int, default=800)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--target-accept", type=float, default=0.92)
    parser.add_argument(
        "--linear-drift",
        action="store_true",
        help="Separately regularized long-run annual drift",
    )
    parser.add_argument("--no-units", action="store_true")
    parser.add_argument("--no-size", action="store_true")
    parser.add_argument(
        "--likelihood", choices=["student_t", "normal"], default="student_t"
    )
    parser.add_argument(
        "--adaptation",
        choices=["diag", "low_rank"],
        default="diag",
        help="Nutpie mass-matrix adaptation; low_rank is experimental",
    )
    parser.add_argument(
        "--holdout-units",
        action="store_true",
        help="Withhold a deterministic 20% of whole units across all dates",
    )
    parser.add_argument(
        "--noncentered-time",
        action="store_true",
        help="Alternative sampler parameterization; same prior",
    )
    parser.add_argument(
        "--max-units",
        type=int,
        default=0,
        help="Deterministic pilot subset; zero uses all units",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
