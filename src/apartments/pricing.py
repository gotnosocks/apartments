"""Interpretable, chronological asking-rent baseline and dollar-valued search.

Standard-library implementation. Associations are not causal amenity valuations.
The encoder, category vocabulary, and imputation are learned on training rows only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping

VERSION = "interpretable-asking-rent-v1"
NUMERIC = ("bedrooms", "bathrooms", "square_feet", "listed_floor", "physical_floor")
CATEGORICAL = ("building_id", "laundry_type", "doorman_type", "hvac_type", "pet_rules")
EXPOSURES = {"window_exposures": ("north", "east", "south", "west"),
             "view_exposures": ("street", "courtyard", "park", "water", "open", "garden", "city", "skyline")}
ALIASES = {"rent": ("asking_rent", "base_rent", "price"),
           "observed_at": ("collected_at", "date"),
           "building_id": ("building_slug", "building"),
           "listed_floor": ("advertised_floor",),
           "physical_floor": ("floors_above_ground", "floor_above_ground"),
           "pet_rules": ("pet_policy",)}
LIMITATIONS = [
    "Targets advertised asking rent, not signed leases or net-effective rent.",
    "Coefficients are conditional associations, not causal willingness to pay.",
    "Building effects and building-wide amenities can be confounded; ridge selects a decomposition.",
    "Unknown amenities remain unknown; absence of evidence is not evidence of absence.",
    "Prediction ranges are heuristic training-residual ranges, not calibrated confidence intervals.",
    "Chronological holdout measures later observations, including previously seen units; not new-unit generalization.",
    "The latest capture per unit/month defines the sample; no duration weighting or stale-listing correction.",
    "Linear time extrapolation and monthly seasonality require multiple years and broad coverage to separate.",
]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _numeric_feature(name: str, value: Any) -> float | None:
    result = _number(value)
    if result is not None and name in ("bedrooms", "bathrooms", "square_feet"):
        if result < 0 or (result == 0 and name != "bedrooms"):
            return None
    return result


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result = datetime.fromtimestamp(value, UTC)
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def _boolean(value: Any) -> float | None:
    if value is True or value == 1 or str(value).lower() in ("true", "yes"):
        return 1.0
    if value is False or value == 0 or str(value).lower() in ("false", "no"):
        return 0.0
    return None


def _normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(record)
    for key, aliases in ALIASES.items():
        if row.get(key) is None:
            row[key] = next((row[a] for a in aliases if row.get(a) is not None), None)
    return row


def _tokens(value: Any) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("/", ",").split(",")
    if not isinstance(value, (list, tuple, set)):
        return None
    if any(x is None or not isinstance(x, str) or not x.strip() for x in value):
        return None
    tokens = {x.strip().lower() for x in value}
    if tokens & {"unknown", "unspecified"}:
        return None
    return tokens


def _exposure(value: Any, field: str, level: str) -> float | None:
    """Mappings are partial tri-state evidence; lists assert a complete set."""
    if isinstance(value, Mapping):
        if set(value) - set(EXPOSURES[field]):
            return None
        return _boolean(value.get(level))
    tokens = _tokens(value)
    if tokens is None or tokens - set(EXPOSURES[field]):
        return None
    return float(level in tokens)


def _category(value: Any) -> str:
    if value is None:
        return "__unknown__"
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    normalized = str(value).strip().lower()
    return "__unknown__" if normalized in ("", "unknown", "unspecified", "__unknown__", "not known", "n/a") else normalized


def _prepare(records: Iterable[Mapping[str, Any]]) -> tuple[list[dict], dict]:
    monthly: dict[tuple[str, str], dict] = {}
    exclusions: Counter = Counter()
    input_count = 0
    for record in records:
        input_count += 1
        row = _normalize(record)
        flagged = next((name for name in ("furnished", "short_term", "concession") if _boolean(row.get(name)) == 1.0), None)
        if flagged:
            exclusions["excluded_" + flagged] += 1
            continue
        rent = _number(row.get("rent"))
        if rent is None or rent <= 0:
            exclusions["invalid_rent"] += 1
            continue
        if not row.get("unit_id"):
            exclusions["missing_unit_id"] += 1
            continue
        try:
            observed = _timestamp(row.get("observed_at"))
        except (ValueError, TypeError, OverflowError, OSError):
            exclusions["invalid_observation_time"] += 1
            continue
        row.update(rent=rent, observed_at=observed.isoformat(), unit_id=str(row["unit_id"]))
        key = (row["unit_id"], observed.strftime("%Y-%m"))
        previous = monthly.get(key)
        if previous is not None:
            exclusions["superseded_unit_month_capture"] += 1
            if row["observed_at"] == previous["observed_at"]:
                # Contradictory measurements at an identical clock need a source correction.
                fields = ("rent", *NUMERIC, *CATEGORICAL, "elevator", *EXPOSURES)
                if any(row.get(k) != previous.get(k) for k in fields):
                    raise ValueError(f"Conflicting simultaneous observations for unit {row['unit_id']}")
                # Equivalent modeled facts can have different provenance; choose
                # deterministically so input ordering cannot change the artifact.
                chosen = min((row, previous), key=lambda r: json.dumps(r, sort_keys=True, default=str))
                monthly[key] = chosen
            if row["observed_at"] <= previous["observed_at"]:
                continue
        monthly[key] = row
    rows = sorted(monthly.values(), key=lambda r: (r["observed_at"], r["unit_id"]))
    return rows, {"input_rows": input_count, "retained_unit_months": len(rows),
                  "exclusions": dict(exclusions), "selection_rule": "latest-observation-per-unit-utc-month"}


def _raw_features(row: Mapping[str, Any], epoch: str) -> dict[str, float | None]:
    result = {name: _numeric_feature(name, row.get(name)) for name in NUMERIC}
    # A unit label or advertised floor cannot establish physical height.
    elevator = _boolean(row.get("elevator"))
    result["elevator"] = elevator
    physical = result["physical_floor"]
    result["physical_floor_x_elevator"] = physical * elevator if physical is not None and elevator is not None else None
    result["floor_label_gap"] = result["listed_floor"] - physical if physical is not None and result["listed_floor"] is not None else None
    observed = _timestamp(row.get("observed_at"))
    result["trend_years"] = (observed - _timestamp(epoch)).total_seconds() / (365.25 * 86400)
    phase = 2 * math.pi * (observed.month - 1) / 12
    result["season_sin"] = math.sin(phase)
    result["season_cos"] = math.cos(phase)
    for name, levels in EXPOSURES.items():
        for level in levels:
            result[f"{name}.{level}"] = _exposure(row.get(name), name, level)
    return result


def _fit_encoder(train: list[dict]) -> dict:
    epoch = train[0]["observed_at"]
    raw = [_raw_features(row, epoch) for row in train]
    numeric = {}
    time_span_days = (_timestamp(train[-1]["observed_at"]) - _timestamp(epoch)).total_seconds() / 86400
    calendar_months = {r["observed_at"][:7] for r in train}
    seasonal_months = {r["observed_at"][5:7] for r in train}
    for name in raw[0]:
        values = [r[name] for r in raw if r[name] is not None]
        center = statistics.mean(values) if values else 0.0
        scale = statistics.pstdev(values) if len(values) > 1 else 1.0
        numeric[name] = {"center": center, "scale": scale if scale > 1e-12 else 1.0,
                         "known_rows": len(values), "missing_rows": len(train)-len(values),
                         "unique_values": len(set(values)), "min": min(values) if values else None,
                         "max": max(values) if values else None, "enabled": True}
        reason = None
        if name == "trend_years" and time_span_days < 90:
            reason = "Trend frozen: fewer than 90 days of training coverage"
        elif name in ("season_sin", "season_cos") and (len(calendar_months) < 12 or len(seasonal_months) < 12):
            reason = "Seasonality frozen: fewer than 12 distinct calendar months covering all months of year"
        if reason:
            numeric[name].update(enabled=False, support_warning=reason)
    categories = {name: sorted({_category(r.get(name)) for r in train}) for name in CATEGORICAL}
    features = ["intercept"]
    for name in numeric:
        features.extend([name, name + ".unknown"])
    for name, levels in categories.items():
        features.extend(f"{name}={level}" for level in levels)
    return {"epoch": epoch, "numeric": numeric, "categories": categories, "features": features}


def _encode(row: Mapping[str, Any], encoder: dict) -> dict[int, float]:
    raw = _raw_features(row, encoder["epoch"])
    values = {"intercept": 1.0}
    for name, settings in encoder["numeric"].items():
        if not settings.get("enabled", True):
            continue
        value = raw[name]
        values[name] = (value - settings["center"]) / settings["scale"] if value is not None else 0.0
        values[name + ".unknown"] = float(value is None)
    for name, levels in encoder["categories"].items():
        category = _category(row.get(name))
        if category in levels:
            values[f"{name}={category}"] = 1.0
    return {i: values[name] for i, name in enumerate(encoder["features"]) if values.get(name, 0.0) != 0.0}


def _ridge(matrix: list[dict[int, float]], target: list[float], width: int, penalty: float) -> tuple[list[float], int, bool]:
    """Sparse coordinate descent; storage scales with nonzero features, not buildings squared."""
    columns: list[list[tuple[int, float]]] = [[] for _ in range(width)]
    for i, row in enumerate(matrix):
        for j, value in row.items():
            columns[j].append((i, value))
    # Constant features carry no identified information and otherwise create
    # redundant intercepts that slow coordinate descent considerably.
    for j in range(1, width):
        if len(columns[j]) == len(target) and len({x for _, x in columns[j]}) == 1:
            columns[j] = []
    beta = [0.0] * width
    beta[0] = statistics.mean(target)
    residual = [value - beta[0] for value in target]
    denominators = [sum(x*x for _, x in column) + (0 if j == 0 else penalty)
                    for j, column in enumerate(columns)]
    for iteration in range(1, 2001):
        maximum = 0.0
        for j, column in enumerate(columns):
            if denominators[j] == 0:
                continue
            change = (sum(x * residual[i] for i, x in column) - (0 if j == 0 else penalty * beta[j])) / denominators[j]
            beta[j] += change
            for i, x in column:
                residual[i] -= x * change
            maximum = max(maximum, abs(change))
        if maximum < 1e-8:
            return beta, iteration, True
    return beta, iteration, False


@dataclass
class PricingModel:
    encoder: dict
    coefficients: list[float]
    report: dict
    residual_log_std: float

    def predict(self, record: Mapping[str, Any]) -> dict:
        row = _normalize(record)
        encoded = _encode(row, self.encoder)
        log_rent = sum(self.coefficients[i] * value for i, value in encoded.items())
        if not math.isfinite(log_rent) or abs(log_rent) > 700:
            raise ValueError("Prediction outside numerical range; inspect extrapolated features")
        unseen = sorted(name for name, levels in self.encoder["categories"].items() if _category(row.get(name)) not in levels)
        prediction = math.exp(log_rent)
        spread = 1.645 * self.residual_log_std
        return {"predicted_rent": prediction, "log_rent": log_rent,
                "heuristic_low": math.exp(max(-700, log_rent - spread)),
                "heuristic_high": math.exp(min(700, log_rent + spread)),
                "unseen_categories": unseen,
                "prediction_kind": "conditional_median_asking_rent",
                "frozen_time_effects": sorted(name for name, settings in self.encoder["numeric"].items() if not settings.get("enabled", True))}

    def marginal_contributions(self, record: Mapping[str, Any], changes: Mapping[str, Any]) -> dict:
        """Evaluate a joint counterfactual, recomputing interactions (noncausal)."""
        base = _normalize(record)
        changed = dict(base)
        # Normalize aliases on the requested changes before merging into canonical row.
        for key, value in changes.items():
            canonical = next((name for name, aliases in ALIASES.items() if key in aliases), key)
            changed[canonical] = value
        warnings = []
        for key in changes:
            canonical = next((name for name, aliases in ALIASES.items() if key in aliases), key)
            feature_names = [canonical]
            if canonical == "observed_at":
                feature_names = ["trend_years", "season_sin", "season_cos"]
            if canonical in EXPOSURES:
                feature_names = [f"{canonical}.{level}" for level in EXPOSURES[canonical]]
            for feature in feature_names:
                support = self.encoder["numeric"].get(feature)
                if support is not None and not support.get("enabled", True):
                    warnings.append(support["support_warning"])
                elif support is not None and support["unique_values"] < 2:
                    warnings.append(f"{feature}: insufficient observed training variation; effect is not identified")
            if canonical in self.encoder["categories"]:
                levels = self.encoder["categories"][canonical]
                if len(levels) < 2:
                    warnings.append(f"{canonical}: insufficient training variation; effect is not identified")
                if _category(base.get(canonical)) not in levels or _category(changed.get(canonical)) not in levels:
                    warnings.append(f"{canonical}: unseen category; effect is not identified")
        before, after = self.predict(base)["predicted_rent"], self.predict(changed)["predicted_rent"]
        return {"baseline_rent": before, "changed_rent": after,
                "dollar_change": after - before, "percent_change": 100 * (after / before - 1),
                "changes": dict(changes), "warnings": warnings, "interpretation": "conditional association; not a causal estimate"}

    def decomposition(self, record: Mapping[str, Any]) -> dict[str, float]:
        encoded = _encode(_normalize(record), self.encoder)
        return {self.encoder["features"][i]: self.coefficients[i] * value for i, value in encoded.items()}

    def to_dict(self) -> dict:
        return {"version": VERSION, "encoder": self.encoder, "coefficients": self.coefficients,
                "report": self.report, "residual_log_std": self.residual_log_std}

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "PricingModel":
        data = json.loads(Path(path).read_text())
        if data.get("version") != VERSION:
            raise ValueError("Unsupported pricing artifact version")
        return cls(data["encoder"], data["coefficients"], data["report"], data["residual_log_std"])


def _metrics(model: PricingModel, rows: list[dict]) -> dict:
    if not rows:
        return {"rows": 0}
    predicted = [model.predict(row)["predicted_rent"] for row in rows]
    actual = [row["rent"] for row in rows]
    return {"rows": len(rows), "mae_dollars": statistics.mean(abs(a-p) for a,p in zip(actual,predicted)),
            "rmse_log": math.sqrt(statistics.mean((math.log(a)-math.log(p))**2 for a,p in zip(actual,predicted))),
            "median_absolute_percent_error": statistics.median(abs(a-p)/a * 100 for a,p in zip(actual,predicted))}


def fit_pricing_model(records: Iterable[Mapping[str, Any]], *, holdout_fraction: float = .2,
                      ridge: float = 1.0, min_train_rows: int = 10) -> PricingModel:
    """Fit on early UTC months and evaluate on later months; never refit on holdout.

    Requires at least two distinct months and min_train_rows after capture dedup.
    Set holdout_fraction=0 only for explicitly descriptive, unvalidated fitting.
    Hyperparameters are fixed inputs, not selected on the reported holdout.
    """
    if not 0 <= holdout_fraction < 1 or not math.isfinite(ridge) or ridge <= 0:
        raise ValueError("holdout_fraction must be in [0, 1) and ridge must be positive")
    if min_train_rows < 2:
        raise ValueError("min_train_rows must be at least 2")
    rows, selection = _prepare(records)
    months = sorted({r["observed_at"][:7] for r in rows})
    if holdout_fraction > 0 and len(months) < 2:
        raise ValueError("At least two observation months are required for chronological validation")
    split = min(len(months)-1, max(1, int(len(months) * (1-holdout_fraction))))
    cutoff = months[split] if holdout_fraction > 0 else None
    train = [r for r in rows if cutoff is None or r["observed_at"][:7] < cutoff]
    holdout = [r for r in rows if cutoff is not None and r["observed_at"][:7] >= cutoff]
    if len(train) < min_train_rows:
        raise ValueError(f"Need at least {min_train_rows} training unit-months; found {len(train)}")
    encoder = _fit_encoder(train)
    matrix = [_encode(row, encoder) for row in train]
    target = [math.log(row["rent"]) for row in train]
    beta, iterations, converged = _ridge(matrix, target, len(encoder["features"]), ridge)
    errors = [y - sum(beta[j]*x for j,x in row.items()) for y,row in zip(target,matrix)]
    model = PricingModel(encoder, beta, {}, math.sqrt(statistics.mean(e*e for e in errors)))
    train_units = {r["unit_id"] for r in train}
    train_buildings = {_category(r.get("building_id")) for r in train}
    baseline = statistics.median(r["rent"] for r in train)
    # Digest the analytical input used, including chronology and attributes. No wall clock in artifact.
    data_hash = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    model.report = {"version": VERSION, "selection": selection, "dataset_sha256": data_hash,
                    "ridge": ridge, "iterations": iterations, "converged": converged,
                    "train_start": train[0]["observed_at"], "train_end": train[-1]["observed_at"],
                    "holdout_start_month": cutoff, "holdout_end": holdout[-1]["observed_at"] if holdout else None,
                    "validation_mode": "chronological" if holdout else "descriptive_no_holdout",
                    "training_months": len({r["observed_at"][:7] for r in train}),
                    "training": _metrics(model, train), "holdout": _metrics(model, holdout),
                    "holdout_new_units": _metrics(model, [r for r in holdout if r["unit_id"] not in train_units]),
                    "holdout_new_buildings": _metrics(model, [r for r in holdout if _category(r.get("building_id")) not in train_buildings]),
                    "training_median_baseline_holdout_mae": statistics.mean(abs(r["rent"]-baseline) for r in holdout) if holdout else None,
                    "training_units": len(train_units), "training_buildings": len(train_buildings),
                    "feature_support": {"numeric": encoder["numeric"],
                        "categorical": {name: dict(Counter(_category(r.get(name)) for r in train)) for name in CATEGORICAL}},
                    "limitations": LIMITATIONS + (["No held-out validation: descriptive fit only."] if not holdout else [])
                    + (["Fewer than 24 training months: seasonality and trend are not well identified."]
                       if len({r["observed_at"][:7] for r in train}) < 24 else [])}
    return model


def rank_apartments(records: Iterable[Mapping[str, Any]], willingness_to_pay: Mapping[str, float], *,
                    unknown_policy: str = "exclude") -> list[dict]:
    """Rank by monthly dollar surplus and mark the preference-specific Pareto set.

    Numeric preference keys are per unit (bedrooms: $500 per bedroom), categorical
    keys are indicators (laundry_type=in_unit: $150/month). Exposure keys use dots
    (window_exposures.south: $100). Negative values express aversions. A unit
    dominates another iff rent is no higher and every signed preference benefit
    is no lower, with at least one strict inequality. Default excludes candidates
    missing any valued attribute; explicit 'zero' treats unknown as zero benefit.
    """
    if unknown_policy not in ("exclude", "zero"):
        raise ValueError("unknown_policy must be 'exclude' or 'zero'")
    weights = {}
    for key, value in willingness_to_pay.items():
        field = key.split("=", 1)[0].split(".", 1)[0]
        canonical = next((name for name, aliases in ALIASES.items() if field in aliases), field)
        key = canonical + key[len(field):]
        valid = (("=" in key and canonical in CATEGORICAL)
                 or (key in (*NUMERIC, "elevator"))
                 or ("." in key and canonical in EXPOSURES and key.split(".", 1)[1] in EXPOSURES[canonical]))
        if "=" in key and _category(key.split("=", 1)[1]) == "__unknown__":
            valid = False
        if not valid:
            raise ValueError(f"Unknown or unsupported preference feature: {key}")
        if key in weights:
            raise ValueError(f"Duplicate preference feature after alias normalization: {key}")
        weights[key] = _number(value)
    if any(value is None for value in weights.values()):
        raise ValueError("Willingness-to-pay values must be finite monthly dollar amounts")
    weights = {key: value for key, value in weights.items() if value != 0}
    result = []
    for record in records:
        row = _normalize(record)
        rent = _number(row.get("rent"))
        if rent is None or rent <= 0:
            raise ValueError("Candidate rent must be finite and positive")
        benefits, unknown = {}, []
        for key, weight in weights.items():
            if "=" in key:
                field, level = key.split("=", 1)
                category = _category(row.get(field))
                value = float(category == _category(level)) if category != "__unknown__" else None
            elif "." in key and key.split(".", 1)[0] in EXPOSURES:
                field, level = key.split(".", 1)
                value = _exposure(row.get(field), field, level)
            else:
                value = _boolean(row.get(key)) if key == "elevator" else _numeric_feature(key, row.get(key))
            if value is None:
                unknown.append(key)
            benefits[key] = weight * (value if value is not None else 0.0)
        eligible = not unknown or unknown_policy == "zero"
        result.append({"record": dict(record), "rent": rent, "monthly_benefits": benefits,
                       "unknown_preferences": unknown, "eligible": eligible,
                       "monthly_surplus": sum(benefits.values()) - rent if eligible else None,
                       "pareto_efficient": False})
    eligible = [r for r in result if r["eligible"]]
    for row in eligible:
        row["pareto_efficient"] = not any(
            other["rent"] <= row["rent"]
            and all(other["monthly_benefits"][k] >= row["monthly_benefits"][k] for k in weights)
            and (other["rent"] < row["rent"] or any(other["monthly_benefits"][k] > row["monthly_benefits"][k] for k in weights))
            for other in eligible if other is not row)
    return sorted(result, key=lambda r: (not r["eligible"], -(r["monthly_surplus"] or 0)))
