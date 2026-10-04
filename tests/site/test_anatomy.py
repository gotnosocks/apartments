import ast
from pathlib import Path

from apartments.site import anatomy

MODEL_PY = Path(__file__).parents[2] / "frontier/src/rentfrontier/model.py"


def model_config_fields() -> dict:
    """ModelConfig's fields and their default source text, read from the
    source (the site's venv has no JAX to import it)."""
    tree = ast.parse(MODEL_PY.read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ModelConfig"
    )
    return {
        n.target.id: ast.literal_eval(n.value)
        for n in cls.body
        if isinstance(n, ast.AnnAssign)
    }


def test_every_model_config_field_is_described():
    fields = model_config_fields()
    known = (
        set(anatomy.DEFAULTS) | set(anatomy.PRIOR_FIELDS) | set(anatomy.SAMPLING_FIELDS)
    )
    missing = sorted(set(fields) - known)
    assert not missing, f"describe these ModelConfig fields in anatomy.py: {missing}"
    for name, default in fields.items():
        if name in anatomy.DEFAULTS:
            assert anatomy.DEFAULTS[name] == (
                tuple(default) if isinstance(default, tuple) else default
            ), name
        if name in anatomy.PRIOR_FIELDS:
            assert anatomy.PRIOR_FIELDS[name] == default, name


SERVED = {
    "name": "m7-nocurves-bathfloor",
    "building_walk": True,
    "bedroom_slope": True,
    "feature_slopes": ["bathrooms=2", "log_floor"],
    "trend_knot_months": 3,
    "unit_t": True,
    "beta_sd": 0.5,
}
SIZES = {
    "rows": 77904,
    "features": 97,
    "months": 201,
    "buildings": 2296,
    "units": 35217,
}


def test_describe_reads_the_parts_and_counts():
    a = anatomy.describe(SERVED, SIZES)
    present = [p.key for p in a.present]
    assert present == [
        "intercept",
        "trend",
        "season",
        "building",
        "walk",
        "bedroom_slope",
        "feature_slopes",
        "unit",
        "features",
        "noise",
    ]
    parts = {p.key: p for p in a.parts}
    # 201 months at quarterly knots: 68 knots, 67 steps and their scale.
    assert parts["trend"].count == 68 and parts["trend"].setting == "quarterly"
    # 2,296 buildings x 34 half-year steps, and the walk's scale.
    assert parts["walk"].count == 2296 * 34 + 1
    assert parts["feature_slopes"].setting == "a second full bath and a higher floor"
    assert parts["unit"].count == 35217 + 2  # the scale and the estimated nu
    assert a.parameters == sum(p.count for p in a.present)
    assert a.other == [] and a.sampling == []


def test_equation_has_one_line_per_level_with_terms():
    lines = anatomy.describe(SERVED, SIZES).equation()
    assert [label for label, _ in lines] == [
        "",
        "Market",
        "Building",
        "Apartment",
        "Listing",
    ]
    market = "".join(lines[1][1])
    assert market.startswith('<math display="inline"><mrow><mi>α</mi></mrow></math>')
    assert "&lt;" not in market  # MathML, not escaped text
    assert all("<mo>+</mo>" in t for t in lines[2][1])  # every later term adds


def test_old_records_and_pymc_screens():
    # A record from before a field existed had its default.
    old = anatomy.describe({"name": "m0-base", "beta_sd": 0.5})
    assert [p.key for p in old.present] == [
        "intercept",
        "trend",
        "season",
        "building",
        "unit",
        "features",
        "noise",
    ]
    assert anatomy.describe({"name": "nuts-bslope"}) is None  # the board's stand-in
    assert anatomy.describe({"name": "L3-season", "backend": "pymc"}) is None
    assert anatomy.describe(None) is None


def test_unknown_options_and_sampling_coordinates_are_listed():
    a = anatomy.describe(
        {
            **SERVED,
            "new_option": True,
            "coordinates": ["unit_totals"],
            "noncentered": ["unit"],
        }
    )
    assert a.other == [("new_option", "true")]
    assert a.sampling == ["unit_totals", "unit"]


def test_differences_from_another_design():
    served = anatomy.describe(SERVED)
    other = anatomy.describe(
        {
            **SERVED,
            "building_walk": False,
            "line_effects": True,
            "unit_t": False,
            "season_harmonics": 2,
            "feature_slopes": ["log_sqft_vs_bedroom_median", "bathrooms=2"],
        }
    )
    assert anatomy.differences(other, served) == [
        "calendar season: 2 Fourier pairs, not 12 month effects",
        "drops building drift over time",
        "adds each building's own price for size beyond the typical for the bedroom count",
        "drops each building's own price for a higher floor",
        "adds line premium (lines of ≥ 2 apartments)",
        "apartment premium: Normal, not heavy-tailed",
    ]
    assert anatomy.differences(served, served) == []


def test_learned_feature_scales_and_the_zero_sum_season():
    served = anatomy.describe(SERVED, SIZES)
    locscale = anatomy.describe(
        {**SERVED, "learned_feature_groups": ["location"]}, SIZES
    )
    features = next(p for p in locscale.parts if p.key == "features")
    assert features.setting == "97 features, location shrinkage learned"
    assert "λ_g" in features.prior
    assert anatomy.differences(locscale, served) == [
        "features with a learned prior scale: location, not none"
    ]
    # build_model's zero-sum season takes precedence over harmonics.
    both = anatomy.describe(
        {**SERVED, "season_harmonics": 2, "coordinates": ["season_zerosum"]}
    )
    season = next(p for p in both.parts if p.key == "season")
    assert season.setting == "12 month effects"


def test_daily_season():
    daily = anatomy.describe({**SERVED, "season_harmonics": 2, "season_daily": True})
    season = next(p for p in daily.parts if p.key == "season")
    assert season.setting == "2 Fourier pairs at each listing's date"
    assert season.short == "2 Fourier, daily" and "<mi>d</mi>" in season.math
    monthly = anatomy.describe({**SERVED, "season_harmonics": 2})
    assert anatomy.differences(daily, monthly) == [
        "calendar season: 2 Fourier pairs at each listing's date, not 2 Fourier pairs"
    ]


def test_noise_differences_read_plainly():
    served = anatomy.describe({**SERVED, "noise_by_bedrooms": True})
    plain = anatomy.describe({**SERVED, "nu_fixed": 5.0})
    assert anatomy.differences(plain, served) == [
        "what's left: one scale for every ask, not one per bedroom count",
        "what's left: ν = 5, not ν fitted",
    ]


def test_symbols_are_the_ones_the_equation_uses():
    a = anatomy.describe({**SERVED, "season_harmonics": 2, "season_daily": True})
    names = [s for s, _ in a.symbols]
    assert names == ["B(i)", "U(i)", "m(i)", "tᵢ", "dᵢ"]
    with_curves = anatomy.describe({**SERVED, "bedroom_time": True})
    assert ("g(i)", "bedroom group") in with_curves.symbols
    assert ("c(i)", "calendar month") in with_curves.symbols
