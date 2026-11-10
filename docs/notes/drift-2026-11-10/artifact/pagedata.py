"""Turn the extract of the scored runs into the explainer page's data file.

python docs/notes/drift-2026-11-10/artifact/pagedata.py EXTRACT.json PAGE.json \
    [--more FITS.json] [--market-day 2026-11-09]

EXTRACT.json is what `../artifact-data/extract.py` writes on thelio. `--more` names a JSON
list of further rows for the page's table of fits (earlier rounds that missed the gate), in
the page's own shape. The page itself is `page.html`, and `build.py` puts PAGE.json into it.

The two residual checks at the top of the page come from the note of 2026-11-10 and are
written out here, since no fit reproduces them.
"""

import argparse
import datetime
import json
import math
from pathlib import Path

# Share of the leftover variance that two ads of one unit have in common, by years between
# them, in the residuals of a model with no unit term (the note's first table).
UNIT_CORR = [
    (0.25, 139671, 0.663),
    (0.75, 113489, 0.558),
    (1.5, 338499, 0.487),
    (2.5, 291301, 0.419),
    (4, 424084, 0.327),
    (6.5, 344356, 0.255),
    (9.5, 133319, 0.206),
]
# Correlation of the residuals of two ads of different units of one building, by the time
# between them, with a constant effect per unit taken out (the note's second check).
BUILDING_CORR = [
    ("under 3 mo", "<3m", 0.26),
    ("3 to 6 mo", "3-6m", 0.13),
    ("6 to 12 mo", "6-12m", 0.075),
    ("1 to 2 years", "1-2y", 0.016),
    ("2 to 3", "2-3y", -0.014),
    ("3 to 5", "3-5y", -0.044),
    ("5 to 8", "5-8y", -0.064),
    ("8 and over", "8y+", -0.064),
]
GAPS = (
    ("<0.25", "under 3 mo", "<3m"),
    ("0.25-0.5", "3 to 6 mo", "3-6m"),
    ("0.5-1", "6 to 12 mo", "6-12m"),
    ("1-2", "1 to 2 years", "1-2y"),
    ("2-4", "2 to 4", "2-4y"),
    ("4-8", "4 to 8", "4-8y"),
    ("8+", "8 and over", "8y+"),
)
MODELS = {
    "drift": ("Drift", "each apartment's own level, drifting"),
    "drift-building": ("Drift + building", "plus a path for each building"),
    "drift-local": ("Drift + building + area", "plus a path for each area"),
}
REFS = (
    ("fit8", "fit8", "Fit 8", "no memory of the apartment", True),
    ("ks_a", "ks", "Kitchen sink", "plus every feature on hand", True),
    ("fit4", "fit4", "Fit 4", "a fixed level per apartment (did not converge)", False),
)
SPLITS = {"latest": "held-out ads", "market": "the market"}


def day_label(day: str) -> str:
    d = datetime.date.fromisoformat(day)
    return f"{d:%B} {d.day}, {d.year}"


def corr_fit() -> dict:
    """The least-squares a + b exp(-gap / tau) through UNIT_CORR, weighted by pairs."""
    best = None
    for k in range(40, 1200):
        tau = k / 100
        e = [math.exp(-g / tau) for g, _, _ in UNIT_CORR]
        w = [p for _, p, _ in UNIT_CORR]
        r = [v for _, _, v in UNIT_CORR]
        sw = sum(w)
        me = sum(a * b for a, b in zip(w, e)) / sw
        mr = sum(a * b for a, b in zip(w, r)) / sw
        see = sum(a * (x - me) ** 2 for a, x in zip(w, e))
        b = sum(a * (x - me) * (y - mr) for a, x, y in zip(w, e, r)) / see
        a = mr - b * me
        sse = sum(c * (y - a - b * x) ** 2 for c, x, y in zip(w, e, r))
        if best is None or sse < best[0]:
            best = (sse, a, b, tau)
    return {"a": best[1], "b": best[2], "tau": best[3]}


def pct(v: float) -> str:
    return f"{100 * math.expm1(v):.1f}%"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("extract")
    p.add_argument("out")
    p.add_argument("--more")
    p.add_argument("--market-day", default="2026-11-09")
    a = p.parse_args()
    X = json.loads(Path(a.extract).read_text())
    runs = {r["fit"]: r for r in X["runs"]}
    model = {k: r["model"] for k, r in runs.items()}
    win_fit = X["winner"]["fit"]
    win = model[win_fit]
    tr = runs[win_fit]["traced_mean_p5_p95"]
    mean = lambda k: tr[k][0] if k in tr else None  # noqa: E731
    latest = [k for k, r in runs.items() if r["split"] == "latest" and k in X["scores"]]

    scores = [
        {"name": name, "label": label, "note": note, "elpd": X["scores"][k]["elpd"]}
        | {"gate": gate, "new": False}
        for k, name, label, note, gate in REFS
        if k in X["scores"]
    ]
    for k in sorted(latest, key=lambda k: X["scores"][k]["elpd"]):
        s = X["scores"][k]
        scores.append(
            {
                "name": model[k],
                "label": MODELS[model[k]][0],
                "note": MODELS[model[k]][1]
                + ("" if runs[k]["gate"]["passes"] else " (missed the gate)"),
                "elpd": s["elpd"],
                "gate": runs[k]["gate"]["passes"],
                "new": True,
                "rows": s["rows"],
                "median_abs_error": s["median_abs_error"],
                "coverage": s["coverage"],
            }
        )
    sw = next(s for s in scores if s["name"] == win)
    by = {s["name"]: s for s in scores}
    # A newer model that scores higher than the winner and missed the gate: the page says
    # so where it shows what the winner cannot see.
    ahead = [
        k for k in latest if X["scores"][k]["elpd"] > sw["elpd"] and model[k] != win
    ]
    beyond = None
    if ahead:
        k = max(ahead, key=lambda k: X["scores"][k]["elpd"])
        g = runs[k]["gate"]
        beyond = {
            "name": model[k],
            "gain": X["scores"][k]["elpd"] - sw["elpd"],
            "max_rhat": g["max_rhat"],
            "min_ess": g["min_ess"],
            "caption": f"A model that adds {MODELS[model[k]][1][5:]} scores "
            f"<b>{X['scores'][k]['elpd'] - sw['elpd']:,.0f}</b> higher on the same held-out "
            "ads. Its fit missed the project's convergence gate (worst R-hat "
            f"{g['max_rhat']:.3f}, where the gate allows 1.01), so nothing on this page "
            "is built on it.",
        }

    names = {"ks_a": "ks", "fit4": "fit4"} | {k: model[k] for k in latest}
    gap_models = {}
    for k, rows in X["by_gap"].items():
        got = {r["gap_years"]: r for r in rows}
        if all(g in got for g, _, _ in GAPS):
            gap_models[names[k]] = {
                "mae": [got[g]["median_abs_error"] for g, _, _ in GAPS],
                "width80": [got[g]["width80"] for g, _, _ in GAPS],
            }
    compare = [
        n for n in ("ks", *sorted(MODELS, key=len)) if n in gap_models and n in by
    ]
    gw = gap_models[win]

    bt, mk = X["backtest"], X["market"]
    rows = []
    for r in bt["by_first_ask_place"]:
        lo = round(10 * float(r["place"].split(" to ")[0]))
        rows.append(
            {
                "lower_than": f"{90 - 10 * lo}% to {100 - 10 * lo}%",
                "short": f"{90 - 10 * lo}+",
                "ads": r["ads"],
                "median_days_on_market": r["median_days_on_market"],
                "share_cut": r["share_cut"],
            }
        )
    top = [
        {
            "hood": r["neighbourhood"],
            "bedrooms": r["bedrooms"],
            "ask": r["ask"],
            "model_median": r["model_median"],
            "model_lo80": r["model_lo80"],
            "model_hi80": r["model_hi80"],
            "below_share": r["below_share"],
            "unit_ads": r["unit_ads"],
        }
        for r in mk["lowest"]
        if r.get("neighbourhood")
    ]
    # The opening example: a low ask of an apartment the model has seen, not so low that
    # it reads as a typing error.
    hero = next(
        (r for r in top if r["unit_ads"] and r["ask"] > 0.7 * r["model_median"]), top[0]
    )
    hist = mk["below_share_bins"]
    even = sum(hist) / len(hist)
    walk = X.get("walk")
    fits = []
    for k, r in runs.items():
        label = MODELS[r["model"]][0] + ", "
        label += "backtest" if k == "backtest" else SPLITS.get(r["split"], r["split"])
        fits.append(
            {
                "name": r["model"],
                "label": label,
                "train": r["rows_trained"],
                "predicted": r["rows_predicted"],
                "rhat": r["gate"]["max_rhat"],
                "ess": r["gate"]["min_ess"],
                "gate": r["gate"]["passes"],
                "elpd": X["scores"][k]["elpd"] if k in X["scores"] else None,
                "cost": r["cost_usd"] or 0.0,
            }
        )
    if a.more:
        fits = json.loads(Path(a.more).read_text()) + fits
    total = runs["market"]["rows_trained"] + runs["market"]["rows_predicted"]
    ks, fit4 = by["ks"]["elpd"], by["fit4"]["elpd"]
    sigma = [tr[k][0] for k in sorted(tr) if k.startswith("sigma[")]
    bld = [tr[k][0] for k in sorted(tr) if k.startswith("bld_sd[")]
    D = {
        "winner": win,
        "meta": {
            "scoring_day_label": day_label(a.market_day),
            "coefficients": sum(k.startswith("beta[") for k in tr),
            "weeks": 4 * (len(walk["week_start"]) - 1) + 1 if walk else 620,
            "buildings": 68000,
            "units": 935000,
            "sub": f"A model of asking rents fitted to {total / 1e6:.1f} million New York "
            "City rental ads, and what it says about the ads on the market now.",
            "source": "Every number on this page comes from the fits listed below. The "
            "code, the predictions written before each fit and the full record are in "
            "the repository under docs/notes/drift-2026-11-10.md.",
            "fitnote": "The gate is the project's: split R-hat at most 1.01 and bulk ESS "
            "above 400 on every scalar and coefficient. Only a fit that passes is "
            "published.",
        },
        "hero": {k: hero[k] for k in ("hood", "bedrooms", "ask", "below_share")}
        | {
            "median": hero["model_median"],
            "lo80": hero["model_lo80"],
            "hi80": hero["model_hi80"],
        },
        "hyp": {
            "building_sd": sum(bld) / len(bld),
            "unit_sd": mean("unit_sd"),
            "drift_sd": mean("drift_sd"),
            "drift_tau": mean("drift_tau"),
            "building_ar_sd": mean("building_ar_sd"),
            "building_ar_rho": mean("building_ar_rho"),
            "nbhd_ar_sd": mean("nbhd_ar_sd"),
            "nbhd_ar_rho": mean("nbhd_ar_rho"),
            "sigma_mid": sorted(sigma)[len(sigma) // 2 - 1],
        },
        "unit_corr": [{"mid": m, "pairs": n, "r": r} for m, n, r in UNIT_CORR],
        "corr_fit": corr_fit(),
        "building_corr": [
            {"label": lab, "short": s, "r": r} for lab, s, r in BUILDING_CORR
        ],
        "scores": scores,
        "by_gap": {
            "labels": [lab for _, lab, _ in GAPS],
            "short": [s for _, _, s in GAPS],
            "models": gap_models,
        },
        "gap_compare": compare,
        "pit": {model[k]: v for k, v in X["pit"].items()},
        "sample": {
            "y": [round(math.log(r[0]), 4) for r in X["sample"]["rows"]],
            "med": [round(math.log(r[1]), 4) for r in X["sample"]["rows"]],
        },
        "units": [
            {
                "hood": u["neighbourhood"],
                "bedrooms": u["bedrooms"],
                "ads": [
                    {"day": d["day"], "ask": d["ask"], "held": d["held_out"]}
                    for d in u["ads"]
                ],
                "q": list(u["held_quantiles_dollars"].values()),
                "cdf": u["held_cdf"],
            }
            for u in X["units"]
        ],
        "backtest": {
            "as_of_label": day_label(bt["scoring_day"]),
            "ads": bt["ads_with_first_ask"],
            "rows": rows,
        },
        "market": {
            "ads": mk["ads"],
            "hist": hist,
            "width_new": mk["median_width80_pct"]["without_training_ad"],
            "top": top,
        },
        "score_caption": f"The scoreboard, on the same {sw['rows']:,} held-out ads. "
        f"{sw['label']} scores <b>{sw['elpd'] - ks:,.0f}</b> above the kitchen sink, "
        "the best earlier model that converged, and "
        f"{sw['elpd'] - fit4:,.0f} above fit 4, which had a fixed level per apartment "
        "and did not converge."
        + (
            f" The building's path alone is worth {sw['elpd'] - by['drift']['elpd']:,.0f}."
            if win != "drift" and "drift" in by
            else ""
        ),
        "gap_caption": "The kitchen sink misses by about the same amount however "
        f"lately the apartment was listed. {sw['label']} misses by "
        f"<b>{pct(gw['mae'][0])}</b> when the last ad is under three months old and "
        f"{pct(gw['mae'][-1])} when it is over eight years old, and it is ahead at "
        "every age.",
        "market_caption": f"The bar on the left holds the {hist[0]:,} asks that are "
        f"lower than 95% of their range, where level bars would put {even:,.0f}."
        if hist[0] > even
        else f"The bar on the left holds the {hist[0]:,} asks that are lower than 95% "
        f"of their range. Level bars would put {even:,.0f} there: asks on the market "
        "run high against the model, which is fitted to final asks.",
        "fits": fits,
    }
    if beyond:
        D["next"] = beyond
    if walk:
        D["walk"] = {
            "dates": walk["week_start"],
            "mean": walk["mean"],
            "lo": walk["p5"],
            "hi": walk["p95"],
        }
    Path(a.out).write_text(json.dumps(D, separators=(",", ":")))
    print(f"winner {win}, {len(scores)} scores, {len(fits)} fits to {a.out}")


if __name__ == "__main__":
    main()
