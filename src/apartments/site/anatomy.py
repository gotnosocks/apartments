"""A model design's structure from its recorded config: parts, equation, diagram.

Every fit's run record stores the `rentfrontier.model.ModelConfig` it was fit
with (the research data carries it as an entry's `model`, the served bundle as
its provenance's). `describe` reads that dict into the parts of the log-rent
equation, each with a plain sentence, its prior and its number of parameters;
the templates draw the equation (MathML, rendered by the browser without
script), a plate diagram (HTML and CSS) and a table from them. `differences`
says how one design differs from another.

The site does not import rentfrontier (its venv has no JAX), so the meaning of
each config field is written down here. tests/site/test_anatomy.py reads
ModelConfig's fields from the source and fails when one is neither described
here nor listed as a prior or sampling setting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from markupsafe import Markup, escape

# ModelConfig's defaults for the fields that change what a model says. Older
# run records predate some fields; a missing field had its default.
DEFAULTS = {
    "trend": True,
    "season": True,
    "features": True,
    "buildings": True,
    "units": True,
    "market_drift": False,
    "season_harmonics": 0,
    "noise_by_bedrooms": False,
    "building_walk": False,
    "walk_knot_months": 6,
    "walk_t": False,
    "walk_nu_fixed": None,
    "walk_min_rows_per_knot": 0.0,
    "walk_anchor_data": False,
    "walk_zero_sum": False,
    "line_effects": False,
    "line_min_units": 2,
    "building_trend": False,
    "bedroom_time": False,
    "bedroom_slope": False,
    "feature_slopes": (),
    "learned_feature_groups": (),
    "trend_knot_months": 1,
    "bedroom_time_knot_months": 1,
    "nu_fixed": None,
    "unit_t": False,
    "unit_nu_fixed": None,
    "unit_drift": False,
}
# Prior scales: shown in each part's prior, not parts of their own.
PRIOR_FIELDS = {
    "market_drift_sd": 0.1,
    "beta_sd": 0.5,
    "trend_scale_sd": 0.05,
    "season_scale_sd": 0.05,
    "building_scale_sd": 0.5,
    "unit_scale_sd": 0.2,
    "noise_scale_sd": 0.2,
    "walk_scale_sd": 0.1,
    "line_scale_sd": 0.1,
    "building_trend_scale_sd": 0.05,
    "bedroom_time_scale_sd": 0.02,
    "bedroom_slope_scale_sd": 0.1,
    "feature_slope_scale_sd": 0.1,
    "unit_drift_scale_sd": 0.05,
}
# How a sampler moves, not what the model says (ModelConfig's comments).
SAMPLING_FIELDS = ("name", "noncentered", "coordinates")

LEVELS = (
    ("market", "Market", "every listing, each month"),
    ("building", "Building", "one value per building"),
    ("unit", "Apartment", "one value per apartment"),
    ("listing", "Listing", "each ask"),
)

COLUMNS = {
    "market_drift": "Steady drift",
    "trend": "Trend",
    "season": "Season",
    "bedroom_time": "Trend by bedrooms",
    "building": "Premium",
    "walk": "Drift over time",
    "building_trend": "Trend",
    "bedroom_slope": "Price per bedroom",
    "feature_slopes": "Own feature prices",
    "line": "Line premium",
    "unit": "Premium",
    "unit_drift": "Trend",
    "features": "Features",
    "noise": "What's left",
}

# Feature columns that designs give per-building slopes, in words.
FEATURE_SHORT = {
    "bathrooms=2": "2nd bath",
    "bathrooms=3": "3rd bath",
    "log_floor": "floor",
    "log_sqft_vs_bedroom_median": "size",
}
FEATURE_WORDS = {
    "bathrooms=2": "a second full bath",
    "bathrooms=3": "a third full bath",
    "log_floor": "floor height",
    "log_sqft_vs_bedroom_median": "size beyond the typical for the bedroom count",
}


@dataclass
class Part:
    key: str
    level: str
    label: str
    present: bool
    setting: str = ""
    plain: str = ""
    prior: str = ""
    count: int | None = None
    math: Markup = field(default_factory=Markup)
    # The features of per-building slopes, in words.
    words: list[str] = field(default_factory=list)
    # A few words for the design matrix's cell ("" for a plain yes).
    short: str = ""

    @property
    def column(self) -> str:
        """The design matrix's column heading, under its level's."""
        return COLUMNS.get(self.key, self.label)

    @property
    def formula(self) -> Markup:
        """The term as a MathML element of its own."""
        return _math(self.math) if self.math else Markup("")


@dataclass
class Anatomy:
    name: str
    parts: list[Part]
    # Fields this module does not know, with non-default values: [(name, value)].
    other: list[tuple[str, str]] = field(default_factory=list)
    # Sampling coordinates and non-centred sites, which change how the sampler
    # moves but not the model.
    sampling: list[str] = field(default_factory=list)
    sizes: dict = field(default_factory=dict)

    @property
    def present(self) -> list[Part]:
        return [p for p in self.parts if p.present]

    def level(self, key: str) -> list[Part]:
        return [p for p in self.parts if p.level == key]

    @property
    def parameters(self) -> int | None:
        counts = [p.count for p in self.present]
        if not counts or any(c is None for c in counts):
            return None
        return sum(counts)

    def equation(self) -> list[tuple[str, list[Markup]]]:
        """The equation's lines: [(level label, [MathML term])], the left-hand
        side first and one line per level with terms. Each term (with its
        leading +) is a math element of its own, so a narrow screen wraps a
        line between terms."""
        lines = [("", [_math(_lhs(), _mo("="))])]
        first = True
        for key, label, _ in LEVELS:
            terms = [p.math for p in self.level(key) if p.present and p.math]
            if not terms:
                continue
            body = []
            for i, t in enumerate(terms):
                body.append(_math(_mo("+"), t) if i or not first else _math(t))
            first = False
            lines.append((label, body))
        return lines


# --- MathML ---------------------------------------------------------------


def _mi(s: str, normal: bool = False) -> Markup:
    variant = ' mathvariant="normal"' if normal else ""
    return Markup(f"<mi{variant}>{escape(s)}</mi>")


def _mo(s: str) -> Markup:
    return Markup(f"<mo>{escape(s)}</mo>")


def _mn(s) -> Markup:
    return Markup(f"<mn>{escape(s)}</mn>")


def _row(*xs) -> Markup:
    return Markup("<mrow>" + "".join(str(x) for x in xs) + "</mrow>")


def _sub(base, sub) -> Markup:
    return Markup(f"<msub>{base}{sub}</msub>")


def _subsup(base, sub, sup) -> Markup:
    return Markup(f"<msubsup>{base}{sub}{sup}</msubsup>")


def _bar(x) -> Markup:
    return Markup(f'<mover accent="true">{x}<mo>¯</mo></mover>')


def _math(*xs) -> Markup:
    return Markup('<math display="inline">') + _row(*xs) + Markup("</math>")


def _of(fn: str) -> Markup:
    """B(i): the row's building, unit, month, ..."""
    return _row(_mi(fn), _mo("("), _mi("i"), _mo(")"))


def _t() -> Markup:
    return _sub(_mi("t"), _mi("i"))


def _lhs() -> Markup:
    return _row(
        _mi("log", normal=True),
        Markup('<mspace width="0.2em"></mspace>'),
        _sub(_mi("r"), _mi("i")),
    )


def _since(level: str) -> Markup:
    """(t_i - t̄_B(i)): years since the building's or unit's mean date."""
    return _row(_mo("("), _t(), _mo("−"), _sub(_bar(_mi("t")), _of(level)), _mo(")"))


# --- Parts -----------------------------------------------------------------


def _knots(n_months: int | None, spacing: int) -> int | None:
    if n_months is None:
        return None
    return math.ceil((n_months - 1) / spacing) + 1


def _every(months: int) -> str:
    return {1: "monthly", 3: "quarterly", 6: "half-yearly", 12: "yearly"}.get(
        months, f"every {months} months"
    )


def _num(x) -> str:
    if isinstance(x, bool):
        return str(x).lower()
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def _times(n, k=1, plus=0):
    return None if n is None else n * k + plus


def describe(model: dict | None, sizes: dict | None = None) -> Anatomy | None:
    """The parts of the design `model` (a run record's ModelConfig dict), with
    parameter counts from `sizes` (rows, features, months, buildings, units).
    None when the record has no design to read (the old PyMC screens)."""
    if (
        not isinstance(model, dict)
        or model.get("backend")
        or "name" not in model
        # The board names a PyMC screen's model and records nothing else.
        or not set(model) & (set(DEFAULTS) | set(PRIOR_FIELDS))
    ):
        return None
    c = {**DEFAULTS, **PRIOR_FIELDS, **model}
    sizes = sizes or {}
    months, buildings, units = (
        sizes.get("months"),
        sizes.get("buildings"),
        sizes.get("units"),
    )
    n_features = sizes.get("features")
    parts: list[Part] = []

    def add(key, level, label, present, **kw):
        parts.append(Part(key, level, label, bool(present), **kw))

    # Market.
    add(
        "intercept",
        "market",
        "Overall level",
        True,
        plain="A starting point: the typical ask across every listing.",
        prior="α ~ Normal(0, 1)",
        count=1,
        math=_mi("α"),
    )
    add(
        "market_drift",
        "market",
        "Steady market drift",
        c["market_drift"],
        setting="per year",
        plain="The whole market rises or falls at one steady rate per year.",
        prior=f"δ ~ Normal(0, {_num(c['market_drift_sd'])})",
        count=1,
        math=_row(_mi("δ"), _mo("⁢"), _t()),
    )
    tk = c["trend_knot_months"]
    trend_knots = _knots(months, tk)
    add(
        "trend",
        "market",
        "Market trend",
        c["trend"],
        setting=_every(tk),
        plain=(
            "The whole market's rent level over time, free to wander up and down"
            + ("" if tk == 1 else f", set {_every(tk)} and smooth in between")
            + "."
        ),
        prior=(
            "τ is a random walk: each step ~ Normal(0, σ_τ), "
            f"σ_τ ~ HalfNormal({_num(c['trend_scale_sd'])})"
        ),
        # (knots - 1) steps and their scale.
        count=trend_knots,
        math=_sub(_mi("τ"), _of("m")),
    )
    harmonics = c["season_harmonics"] or 0
    add(
        "season",
        "market",
        "Calendar season",
        c["season"],
        setting=(
            f"{harmonics} Fourier pair{'s' if harmonics != 1 else ''}"
            if harmonics
            else "12 month effects"
        ),
        plain=(
            "Some calendar months are pricier than others (summer more than winter), "
            "the same pattern every year"
            + (", drawn as a smooth yearly wave" if harmonics else "")
            + "."
        ),
        prior=(
            f"s_c = Σ_k a_k sin(2πkc/12) + b_k cos(2πkc/12), a_k, b_k ~ Normal(0, σ_s / k), "
            f"σ_s ~ HalfNormal({_num(c['season_scale_sd'])})"
            if harmonics
            else f"s_c ~ Normal(0, σ_s), σ_s ~ HalfNormal({_num(c['season_scale_sd'])})"
        ),
        count=(2 * harmonics if harmonics else 12) + 1,
        math=_sub(_mi("s"), _of("c")),
    )
    btk = c["bedroom_time_knot_months"]
    add(
        "bedroom_time",
        "market",
        "Market trend by bedrooms",
        c["bedroom_time"],
        setting=_every(btk),
        plain=(
            "Studios, two- and three-bedrooms each follow their own market path, "
            "relative to one-bedrooms."
        ),
        prior=(
            "each group's path is a random walk: step ~ Normal(0, σ_g), "
            f"σ_g ~ HalfNormal({_num(c['bedroom_time_scale_sd'])})"
        ),
        # Three paths of (knots - 1) steps, and their scale.
        count=_times(_knots(months, btk), 3, plus=-2),
        math=_sub(_mi("c"), _row(_of("g"), _mo(","), _of("m"))),
    )

    # Building.
    add(
        "building",
        "building",
        "Building premium",
        c["buildings"],
        plain=(
            "Each building's own premium or discount over what its listings' "
            "features explain: its location, management and finishes."
        ),
        prior=f"b ~ Normal(0, σ_b), σ_b ~ HalfNormal({_num(c['building_scale_sd'])})",
        count=_times(buildings, plus=1),
        math=_sub(_mi("b"), _of("B")),
    )
    wk = c["walk_knot_months"]
    walk_bits = [f"{wk}-month steps"]
    if c["walk_t"]:
        walk_bits.append(
            "heavy-tailed steps"
            + (f" (ν = {_num(c['walk_nu_fixed'])})" if c["walk_nu_fixed"] else "")
        )
    if c["walk_zero_sum"]:
        walk_bits.append("zero-sum across buildings")
    if c["walk_min_rows_per_knot"]:
        walk_bits.append(
            f"buildings with ≥ {_num(c['walk_min_rows_per_knot'])} asks per step"
        )
    if c["walk_anchor_data"]:
        walk_bits.append("anchored where observed")
    walk_plain = (
        "Each building's premium can drift over time, so a building can become "
        f"relatively pricier or cheaper; it changes every {wk} months, smoothly in between."
    )
    if c["walk_t"]:
        walk_plain += (
            " Most buildings move a little and a few jump (a renovation, a lease-up)."
        )
    if c["walk_zero_sum"]:
        walk_plain += " At every moment the drifts average to zero, so market-wide moves stay in the market trend."
    if c["walk_min_rows_per_knot"]:
        walk_plain += " Buildings with too few asks follow the market."
    walk_knots = _knots(months, wk)
    add(
        "walk",
        "building",
        "Building drift over time",
        c["building_walk"],
        setting=", ".join(walk_bits),
        plain=walk_plain,
        prior=(
            "w_B is a random walk: each step ~ "
            + ("Student-t(ν_w, 0, σ_w)" if c["walk_t"] else "Normal(0, σ_w)")
            + f", σ_w ~ HalfNormal({_num(c['walk_scale_sd'])})"
            + (
                ", ν_w ~ Gamma(2, 0.1)"
                if c["walk_t"] and not c["walk_nu_fixed"]
                else ""
            )
        ),
        count=None
        if buildings is None or walk_knots is None
        else buildings * (walk_knots - 1)
        + 1
        + (1 if c["walk_t"] and not c["walk_nu_fixed"] else 0),
        math=_row(_sub(_mi("w"), _of("B")), _mo("("), _t(), _mo(")")),
    )
    add(
        "building_trend",
        "building",
        "Building trend",
        c["building_trend"],
        setting="per year",
        plain="Each building gets steadily pricier or cheaper at its own rate per year.",
        prior=f"γ ~ Normal(0, σ_γ), σ_γ ~ HalfNormal({_num(c['building_trend_scale_sd'])})",
        count=_times(buildings, plus=1),
        math=_row(_sub(_mi("γ"), _of("B")), _mo("⁢"), _since("B")),
    )
    add(
        "bedroom_slope",
        "building",
        "Building's price per bedroom",
        c["bedroom_slope"],
        plain="Each building has its own price for an extra bedroom, around the market's.",
        prior=f"κ ~ Normal(0, σ_κ), σ_κ ~ HalfNormal({_num(c['bedroom_slope_scale_sd'])})",
        count=_times(buildings, plus=1),
        math=_row(
            _sub(_mi("κ"), _of("B")),
            _mo("⁢"),
            _row(
                _mo("("),
                _sub(_mi("beds", normal=True), _mi("i")),
                _mo("−"),
                _mn(1),
                _mo(")"),
            ),
        ),
    )
    slopes = list(c["feature_slopes"] or ())
    words = [FEATURE_WORDS.get(s, s) for s in slopes]
    add(
        "feature_slopes",
        "building",
        "Building's own feature prices",
        slopes,
        setting=_join(words),
        plain=(
            "Each building has its own price for "
            + _join(words)
            + ", around the market's."
            if words
            else "Each building has its own price for some features."
        ),
        prior=(
            "θ_B,j ~ Normal(0, σ_j), each σ_j ~ "
            f"HalfNormal({_num(c['feature_slope_scale_sd'])})"
        ),
        count=None if buildings is None else (buildings + 1) * len(slopes),
        words=words,
        math=_row(
            _subsup(_mi("θ"), _of("B"), _mo("⊤")),
            _sub(_mi("x"), _row(_mi("i"), _mo(","), _mi("S"))),
        ),
    )

    # Apartment.
    min_units = c["line_min_units"]
    add(
        "line",
        "unit",
        "Line premium",
        c["line_effects"],
        setting=f"lines of ≥ {min_units} apartments",
        plain=(
            "Apartments stacked in the same line (4C, 7C, 12C) share a premium, so an "
            "apartment listed once borrows from its neighbours above and below."
        ),
        prior=f"ℓ ~ Normal(0, σ_ℓ), σ_ℓ ~ HalfNormal({_num(c['line_scale_sd'])})",
        count=None,
        math=_sub(_mi("ℓ"), _of("L")),
    )
    add(
        "unit",
        "unit",
        "Apartment premium",
        c["units"],
        setting="heavy-tailed" if c["unit_t"] else "Normal",
        plain=(
            "Each apartment's own premium over its building and features, learned from "
            "its other listings"
            + (
                ": most sit close to the prediction and a few far from it."
                if c["unit_t"]
                else "."
            )
        ),
        prior=(
            ("u ~ Student-t(ν_u, 0, σ_u)" if c["unit_t"] else "u ~ Normal(0, σ_u)")
            + f", σ_u ~ HalfNormal({_num(c['unit_scale_sd'])})"
            + (
                f", ν_u = {_num(c['unit_nu_fixed'])}"
                if c["unit_t"] and c["unit_nu_fixed"]
                else ", ν_u ~ Gamma(2, 0.1)"
                if c["unit_t"]
                else ""
            )
        ),
        count=_times(
            units, plus=1 + (1 if c["unit_t"] and not c["unit_nu_fixed"] else 0)
        ),
        math=_sub(_mi("u"), _of("U")),
    )
    add(
        "unit_drift",
        "unit",
        "Apartment trend",
        c["unit_drift"],
        setting="per year",
        plain="Each apartment's premium can drift steadily over the years.",
        prior=f"d ~ Normal(0, σ_d), σ_d ~ HalfNormal({_num(c['unit_drift_scale_sd'])})",
        count=_times(units, plus=1),
        math=_row(_sub(_mi("d"), _of("U")), _mo("⁢"), _since("U")),
    )

    # Listing.
    learned = list(c["learned_feature_groups"] or ())
    add(
        "features",
        "listing",
        "Listing features",
        c["features"],
        setting=f"{n_features} features" if n_features else "",
        plain=(
            "What the listing says about the apartment and its building (bedrooms, baths, "
            "size, floor, doorman, laundry and so on), each with one price shared by every "
            "building"
            + (
                f"; the {_join(learned)} features' prices are shrunk together by a strength the data choose"
                if learned
                else ""
            )
            + "."
        ),
        prior=(
            f"β_j ~ Normal(0, {_num(c['beta_sd'])} · s_j), s_j the feature's own scale"
            + (
                f"; for {_join(learned)}: β_j ~ Normal(0, λ · s_j), λ ~ HalfNormal({_num(c['beta_sd'])})"
                if learned
                else ""
            )
        ),
        count=None if n_features is None else n_features + len(learned),
        math=_row(_subsup(_mi("x"), _mi("i"), _mo("⊤")), _mi("β")),
    )
    nu = c["nu_fixed"]
    by_beds = c["noise_by_bedrooms"]
    add(
        "noise",
        "listing",
        "What's left",
        True,
        setting=(
            ("Student-t" + (f", ν = {_num(nu)}" if nu else ""))
            + (", one scale per bedroom count" if by_beds else "")
        ),
        plain=(
            "Each ask's own scatter around the model: mostly small, with occasional big "
            "surprises (heavy tails)"
            + ("; larger apartments' asks scatter more" if by_beds else "")
            + "."
        ),
        prior=(
            "ε_i ~ Student-t(ν, 0, "
            + ("σ_g(i)" if by_beds else "σ")
            + f"), σ ~ HalfNormal({_num(c['noise_scale_sd'])}), "
            + (f"ν = {_num(nu)}" if nu else "ν ~ Gamma(2, 0.1)")
        ),
        count=(4 if by_beds else 1) + (0 if nu else 1),
        math=_sub(_mi("ε"), _mi("i")),
    )

    short = {
        "trend": _every(tk),
        "season": f"{harmonics} Fourier" if harmonics else "12 months",
        "bedroom_time": _every(btk),
        "walk": ", ".join(
            [f"{wk} mo"]
            + (["heavy-tailed"] if c["walk_t"] else [])
            + (["zero-sum"] if c["walk_zero_sum"] else [])
            + (
                [f"≥ {_num(c['walk_min_rows_per_knot'])}/step"]
                if c["walk_min_rows_per_knot"]
                else []
            )
            + (["anchored"] if c["walk_anchor_data"] else [])
        ),
        "feature_slopes": ", ".join(FEATURE_SHORT.get(f, f) for f in slopes),
        "line": f"≥ {min_units} units",
        "unit": "heavy-tailed" if c["unit_t"] else "",
        "features": str(n_features) if n_features else "",
        "noise": ("ν = " + _num(nu) if nu else "ν fitted")
        + (", by bedrooms" if by_beds else ""),
    }
    for p in parts:
        p.short = short.get(p.key, "")

    known = set(DEFAULTS) | set(PRIOR_FIELDS) | set(SAMPLING_FIELDS)
    other = [
        (k, _num(v) if not isinstance(v, (list, tuple)) else ", ".join(map(str, v)))
        for k, v in model.items()
        if k not in known and v not in (None, False, 0, [], (), "")
    ]
    sampling = [*model.get("coordinates", ()), *model.get("noncentered", ())]
    return Anatomy(model["name"], parts, other, list(sampling), dict(sizes))


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _words(p: Part) -> list[str]:
    return p.words


def differences(a: Anatomy, b: Anatomy) -> list[str]:
    """How design `a` differs from `b`, in short phrases ("adds building drift
    over time", "season: 2 Fourier pairs, not 12 month effects")."""
    out = []
    theirs = {p.key: p for p in b.parts}
    for p in a.parts:
        q = theirs.get(p.key)
        if q is None:
            continue
        if p.key == "feature_slopes" and p.present and q.present:
            added = [w for w in _words(p) if w not in _words(q)]
            dropped = [w for w in _words(q) if w not in _words(p)]
            if added:
                out.append(f"adds each building's own price for {_join(added)}")
            if dropped:
                out.append(f"drops each building's own price for {_join(dropped)}")
            continue
        if p.present and not q.present:
            out.append(
                f"adds {p.label.lower()}" + (f" ({p.setting})" if p.setting else "")
            )
        elif q.present and not p.present:
            out.append(f"drops {q.label.lower()}")
        elif p.present and p.setting != q.setting and p.key != "features":
            out.append(
                f"{p.label.lower()}: {p.setting or 'plain'}, not {q.setting or 'plain'}"
            )
    mine, yours = dict(a.other), dict(b.other)
    for k in sorted(set(mine) | set(yours)):
        if mine.get(k) != yours.get(k):
            out.append(f"{k} = {mine.get(k, 'off')}, not {yours.get(k, 'off')}")
    return out
