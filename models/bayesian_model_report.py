"""Build a standalone, mobile-friendly report of Bayesian rental experiments."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xarray as xr


COLORS = ["#225f89", "#d67e32", "#537f5a", "#995d9f"]


def read_json(path):
    return json.loads(Path(path).read_text())


def table(frame):
    return (
        '<div class="table-scroll">'
        + frame.to_html(index=False, escape=True, border=0)
        + "</div>"
    )


def percent(value):
    return f"{value:.1f}%"


def plot(figure, first=False, height=390):
    figure.update_layout(
        template="plotly_white",
        font=dict(family="system-ui", size=13),
        margin=dict(l=55, r=22, t=35, b=55),
        height=height,
        legend=dict(orientation="h", y=-0.23),
        hovermode="x unified",
    )
    return figure.to_html(
        full_html=False,
        include_plotlyjs=True if first else False,
        config={"responsive": True, "displaylogo": False},
    )


def experiment_table(directories):
    records = []
    for directory in directories:
        for path in sorted(Path(directory).rglob("results.json")):
            result = read_json(path)
            if "diagnostics" not in result or "all" not in result.get("scores", {}):
                continue
            settings, diagnostics, score = (
                result["settings"],
                result["diagnostics"],
                result["scores"]["all"],
            )
            records.append(
                {
                    "Experiment": path.parent.name,
                    "Units": "No" if settings["no_units"] else "Yes",
                    "Growth term": "Yes" if settings.get("linear_drift") else "No",
                    "Size": "No" if settings["no_size"] else "Yes",
                    "Residuals": settings["likelihood"].replace("_", " "),
                    "Median error": percent(score["median_absolute_percent_error"]),
                    "80% coverage": percent(score["coverage_80"]),
                    "Log score": f"{score['mean_log_predictive_density']:.3f}",
                    "Max R-hat": f"{diagnostics['max_rhat']:.4f}",
                    "Min ESS": f"{diagnostics['min_ess_bulk']:.0f}",
                    "Divergences": diagnostics["divergences"],
                    "Diagnostics": (
                        "Pass" if diagnostics["acceptable"] else "Not accepted"
                    ),
                }
            )
    return pd.DataFrame(records)


def paired_comparisons(directories):
    records = []
    for directory in directories:
        for path in sorted(Path(directory).glob("comparison-*.json")):
            result = read_json(path)
            gain = result["log_predictive_density_difference"]
            records.append(
                {
                    "Candidate": result["candidate"],
                    "Reference": result["reference"],
                    "Log-score gain": f"{gain['estimate']:.3f}",
                    "95% bootstrap interval": f"[{gain['lower_95']:.3f}, {gain['upper_95']:.3f}]",
                }
            )
    return pd.DataFrame(records)


def trace_plot(directory):
    names = [
        "alpha",
        "annual_drift",
        "sigma",
        "sigma_unit",
        "trend_scale",
        "season_scale",
    ]
    with xr.open_datatree(directory / "posterior.nc", engine="h5netcdf") as tree:
        posterior = tree["posterior"].to_dataset()
        names = [name for name in names if name in posterior]
        figure = make_subplots(
            rows=len(names), cols=1, subplot_titles=names, vertical_spacing=0.09
        )
        for row, name in enumerate(names, 1):
            values = posterior[name].transpose("chain", "draw").values
            stride = max(1, values.shape[1] // 500)
            for chain in range(len(values)):
                figure.add_trace(
                    go.Scatter(
                        x=np.arange(0, values.shape[1], stride),
                        y=values[chain, ::stride],
                        name=f"Chain {chain + 1}",
                        line=dict(color=COLORS[chain % len(COLORS)], width=1),
                        opacity=0.65,
                        showlegend=row == 1,
                    ),
                    row=row,
                    col=1,
                )
    return plot(figure, height=230 * len(names))


def growth_table(directory):
    with xr.open_datatree(directory / "posterior.nc", engine="h5netcdf") as tree:
        posterior = tree["posterior"].to_dataset()
        trend = posterior["trend"].values.reshape(-1, posterior.sizes["period"])
        periods = pd.DatetimeIndex(posterior.period.values)
        records = []
        for months in [12, 24, 60]:
            if len(periods) <= months:
                continue
            changes = 100 * np.expm1(trend[:, -1] - trend[:, -1 - months])
            lower, median, upper = np.quantile(changes, [0.025, 0.5, 0.975])
            records.append(
                {
                    "Period": f"{periods[-1 - months]:%b %Y}–{periods[-1]:%b %Y}",
                    "Adjusted change": percent(median),
                    "95% credible interval": f"{lower:.1f}% to {upper:.1f}%",
                }
            )
    return pd.DataFrame(records)


def build(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    baseline = read_json(args.baseline / "results.json")
    coverage = baseline["coverage"]
    comparison = experiment_table(args.experiments)
    sections = []
    selected = (
        read_json(args.selected_fit / "results.json") if args.selected_fit else None
    )
    tested = read_json(args.test_fit / "results.json") if args.test_fit else None
    if selected and not selected["diagnostics"]["acceptable"]:
        raise ValueError("Cannot present an unaccepted fit as the selected posterior")
    if (
        selected
        and selected["settings"]["training_rows"] != coverage["model_observations"]
    ):
        raise ValueError("The selected report fit must use the full retained dataset")
    if selected and selected["settings"]["input_sha256"] != baseline["training_sha256"]:
        raise ValueError(
            "The selected report fit must use the same frozen input as the baseline"
        )
    if tested and not tested["diagnostics"]["acceptable"]:
        raise ValueError("Cannot present an unaccepted test fit as final validation")
    if selected and tested:
        for key in [
            "input_sha256",
            "no_units",
            "no_size",
            "likelihood",
            "linear_drift",
        ]:
            if selected["settings"].get(key) != tested["settings"].get(key):
                raise ValueError(
                    f"Full and test fits must use the same configuration: {key}"
                )
    sections.append(
        '<p class="eyebrow">Chelsea · local modeling study · September 18, 2026</p>'
    )
    sections.append("<h1>Bayesian asking-rent model</h1>")
    if selected:
        sections.append(
            '<p class="lead">A hierarchical model of asking prices with uncertainty for the market trend, '
            "housing attributes, and individual homes. Incremental bedroom effects are retained.</p>"
        )
    else:
        sections.append(
            '<p class="lead">Model experiments and diagnostic findings. No final full-data Bayesian fit has yet '
            "been selected for this report; the existing robust point model remains the reference.</p>"
        )
    sections.append(
        f'<div class="cards"><div><strong>{coverage["model_observations"]:,}</strong>unit-month observations</div>'
        f"<div><strong>{coverage['units']:,}</strong>canonical units</div>"
        f"<div><strong>{coverage['retained_percent']:.1f}%</strong>of listing IDs retained</div>"
        f"<div><strong>{coverage['missing_sqft_observations'] / coverage['model_observations']:.1%}</strong>missing size, kept</div></div>"
    )
    if tested:
        point_error = baseline["temporal_validation"]["scores"]["model"][
            "median_absolute_percent_error"
        ]
        bayes_score = tested["scores"]["all"]
        bayes_error = bayes_score["median_absolute_percent_error"]
        outcome = (
            "The existing robust point model remains the prediction benchmark. "
            if bayes_error > point_error
            else "The Bayesian model improved median prediction error in this final test. "
        )
        sections.append(
            '<div class="finding"><strong>What the final test tells us</strong><p>'
            + outcome
            + f"Bayesian median error was {bayes_error:.1f}% versus {point_error:.1f}% on 2026 observations. "
            + f"The nominal 80% and 95% prediction intervals covered {bayes_score['coverage_80']:.1f}% "
            + f"and {bayes_score['coverage_95']:.1f}%. "
            + "The accepted posterior is useful for studying uncertainty and attribute associations, "
            "but passing sampling checks does not establish forecast accuracy. The model was selected "
            "on 2025 results and was not retuned against this test.</p></div>"
        )
    sections.append(
        "<h2>What was compared</h2><p>Models use the same cleaned input, with comparisons on 2025 "
        "after training through 2024. Ablations remove unit identity, remove square footage, or replace "
        "robust Student-t residuals with normal residuals. Lower median error is better; higher "
        "held-out log predictive density is better. An 80% prediction interval should cover about "
        "80% of held-out observations.</p>"
    )
    accepted = (
        comparison[comparison.Diagnostics.eq("Pass")] if len(comparison) else comparison
    )
    sections.append(
        table(accepted) if len(accepted) else "<p>No accepted experiments yet.</p>"
    )
    if len(comparison) and len(accepted) != len(comparison):
        sections.append(
            "<details><summary>Exploratory fits that did not pass diagnostics</summary>"
            + table(comparison[comparison.Diagnostics.ne("Pass")])
            + "</details>"
        )
    sections.append(
        '<p class="note">Results marked “Not accepted” are exploratory and are not eligible for final '
        "inference. Log scores are densities on the log-rent scale. Different sampler "
        "parameterizations can describe the same statistical model.</p>"
    )
    paired = paired_comparisons(args.experiments)
    if len(paired):
        sections.append(
            "<details><summary>How much do the retained features help?</summary>"
            "<p>Positive log-score gains favor the candidate. These paired intervals resample whole "
            "buildings, preserving related observations within each building. They describe uncertainty "
            "in this validation-year comparison; they are not posterior intervals or guarantees for future years.</p>"
            + table(paired)
            + "</details>"
        )
    first_plot = True
    if tested:
        old = baseline["temporal_validation"]["scores"]["model"]
        new = tested["scores"]["all"]
        sections.append(
            "<h2>Final retrospective test: 2026</h2><p>January–August 2026 prices were withheld from "
            "this fit. Model choices were made using the earlier comparison period. This evaluates "
            "future dates with archived attributes, not a strict historical as-of-date forecast.</p>"
        )
        records = []
        for name, score in [
            ("Robust point model", old),
            ("Selected Bayesian model", new),
        ]:
            records.append(
                {
                    "Model": name,
                    "Observations": score["observations"],
                    "Median error": percent(score["median_absolute_percent_error"]),
                    "Within 20%": percent(score["within_20_percent"]),
                    "Median bias": percent(score["median_signed_percent_error"]),
                    "80% coverage": (
                        percent(score["coverage_80"]) if "coverage_80" in score else "—"
                    ),
                    "95% coverage": (
                        percent(score["coverage_95"]) if "coverage_95" in score else "—"
                    ),
                }
            )
        sections.append(table(pd.DataFrame(records)))
        if "seen_units" in tested["scores"] and "unseen_units" in tested["scores"]:
            sections.append(
                "<p>Bayesian median error: "
                f"{tested['scores']['seen_units']['median_absolute_percent_error']:.1f}% for previously observed homes; "
                f"{tested['scores']['unseen_units']['median_absolute_percent_error']:.1f}% for new homes.</p>"
            )
        predictions = pd.read_parquet(args.test_fit / "validation.parquet")
        monthly_bias = predictions.groupby("period").apply(
            lambda group: 100 * np.median(group.predicted_rent / group.asking_rent - 1),
            include_groups=False,
        )
        sections.append(
            f"<p>Median signed error changed from {monthly_bias.iloc[0]:.1f}% in "
            f"{monthly_bias.index[0]:%B} to {monthly_bias.iloc[-1]:.1f}% in {monthly_bias.index[-1]:%B}. "
            "Negative values mean underprediction. This pattern points to the extrapolated time trend "
            "as a priority for future work; it does not by itself establish the cause.</p>"
        )
        monthly = predictions.groupby("period").apply(
            lambda group: pd.Series(
                {
                    "Observed median": group.asking_rent.median(),
                    "Predicted median": group.predicted_rent.median(),
                }
            ),
            include_groups=False,
        )
        figure = go.Figure()
        for name, color in zip(monthly.columns, COLORS):
            figure.add_trace(
                go.Scatter(
                    x=monthly.index,
                    y=monthly[name],
                    name=name,
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )
        figure.update_yaxes(title="Monthly median asking rent · dollars")
        sections.append(
            "<details><summary>Test-period price levels</summary><p>Observed and predicted "
            "medians for the same held-out homes each month. Changing listing composition "
            "affects both series; this is a forecast check, not the adjusted market index.</p>"
            + plot(figure, first=first_plot)
            + "</details>"
        )
        first_plot = False
    holdout_path = getattr(args, "holdout_fit", None)
    if holdout_path:
        holdout = read_json(holdout_path / "results.json")
        if (
            not holdout["diagnostics"]["acceptable"]
            or not holdout["settings"]["holdout_units"]
        ):
            raise ValueError(
                "The whole-unit check requires an accepted held-out-unit fit"
            )
        if selected:
            for key in [
                "input_sha256",
                "no_units",
                "no_size",
                "likelihood",
                "linear_drift",
            ]:
                if selected["settings"].get(key) != holdout["settings"].get(key):
                    raise ValueError(f"Full and held-out-unit fits must match: {key}")
        score = holdout["scores"]["all"]
        sections.append(
            "<h2>Exploratory check: entirely unseen homes</h2>"
            f"<p>Holding out complete histories for 20% of units gives {score['observations']:,} test observations: "
            f"median error {score['median_absolute_percent_error']:.1f}%, "
            f"80% interval coverage {score['coverage_80']:.1f}%, and "
            f"95% coverage {score['coverage_95']:.1f}%. "
            "The model learns market periods from other homes. This is an exploratory generalization check: "
            "the earlier 2025 model comparison can include these units, so the 2026 temporal test above "
            "remains the separate final evaluation.</p>"
        )
    if selected:
        index = pd.read_parquet(args.selected_fit / "index.parquet")
        old_index = pd.read_parquet(args.baseline / "rent_index.parquet")
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=index.period,
                y=index.index_upper_95,
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=index.period,
                y=index.index_lower_95,
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(34,95,137,.16)",
                name="95% credible interval",
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=index.period,
                y=index.index_median,
                name="Bayesian trend",
                line=dict(color=COLORS[0]),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=old_index.period,
                y=old_index.smooth_index,
                name="Robust point trend",
                line=dict(color=COLORS[1], dash="dot"),
            )
        )
        figure.update_yaxes(title="Index · January 2022 = 100")
        sections.append(
            "<h2>Adjusted asking-rent trend</h2><p>The final fit uses all retained dates. The band "
            "describes uncertainty in the shared trend, not the price range for an individual home. "
            "Effects adjust for recorded attributes and building/unit composition.</p>"
        )
        sections.append(plot(figure, first=first_plot))
        first_plot = False
        sections.append(table(growth_table(args.selected_fit)))
        sections.append(
            '<p class="note">These are posterior trend changes fitted to observed dates, '
            "not forecasts. Intervals condition on the model and retained source records.</p>"
        )
        coefficients = pd.read_parquet(args.selected_fit / "coefficients.parquet")
        labels = {
            "bedrooms_gt_0": "Studio → 1 bedroom",
            "bedrooms_gt_1": "1 → 2 bedrooms",
            "bedrooms_gt_2": "2 → 3 bedrooms",
            "bedrooms_gt_3": "3 → 4 bedrooms",
            "bedrooms_gt_4": "4 → 5 bedrooms",
            "bathrooms_above_one": "One additional bathroom",
            "log_size_within_bedrooms": "10% greater reported area",
            "size_missing": "Size unreported",
        }
        area = coefficients.term.eq("log_size_within_bedrooms")
        for column in ["median_percent", "lower_95_percent", "upper_95_percent"]:
            coefficients.loc[area, column] = 100 * np.expm1(
                np.log1p(coefficients.loc[area, column] / 100) * np.log(1.1)
            )
        coefficients["Effect"] = coefficients.term.map(labels).fillna(coefficients.term)
        display = coefficients[
            ["Effect", "median_percent", "lower_95_percent", "upper_95_percent"]
        ].copy()
        for column in display.columns[1:]:
            display[column] = display[column].map(percent)
        display.columns = ["Effect", "Median", "95% lower", "95% upper"]
        sections.append(
            "<h2>Incremental attribute effects</h2><p>A two-bedroom home includes both the "
            "studio-to-one-bedroom and one-to-two-bedroom effects; effects multiply on the rent scale. "
            "These are conditional associations, not renovation valuations. Size uses each bedroom "
            "group’s reference area; bedroom contrasts are not fixed-area causal effects.</p>"
        )
        sections.append(table(display))
        diagnostics = selected["diagnostics"]
        sections.append("<h2>Sampling checks</h2>")
        sections.append(
            f"<p>Four chains. Maximum R-hat {diagnostics['max_rhat']:.4f}; minimum bulk ESS "
            f"{diagnostics['min_ess_bulk']:.0f}; minimum tail ESS {diagnostics['min_ess_tail']:.0f}; "
            f"{diagnostics['divergences']} divergences. Runtime {selected['runtime_seconds'] / 60:.1f} minutes.</p>"
        )
        sections.append(
            "<details><summary>Inspect chain traces</summary>"
            + trace_plot(args.selected_fit)
            + "</details>"
        )
    sections.append(
        "<h2>Data and interpretation</h2><p>Each advertisement contributes its own first active asking price "
        "and its own recorded attributes. Repeated captures count once; multiple ads for the same canonical "
        "unit in one month become one observation. Explicit concessions, furnished and very short-term "
        "offers, invalid layouts/prices, and conflicting unit-month layouts are excluded. Missing area remains "
        "usable. Review annotations are not inputs.</p><p>These are nominal asking rents, not signed leases. "
        "Canonical URLs are source-declared identities. Unit effects capture persistent differences, while "
        "unrecorded renovations and changing condition remain unresolved. Intervals depend on these modeling "
        "assumptions; a completed sampler does not establish that every source record is correct.</p>"
    )
    sections.append(
        "<h2>Repository maintenance</h2><p>Transform finalization now uses named validation helpers and rejects "
        "unexpected Parquet files, missing or mismatched checkpoints, and inconsistent row counts before "
        "publishing a completion marker. Added regression tests cover damaged outputs and recovery. The local "
        "transform path and reproducibility instructions are documented. Raw data and review decisions remain intact.</p>"
    )
    sections.append(
        "<details><summary>Reproducibility and diagnostic criteria</summary><p>Model sources, input hashes, "
        "posterior draws, predictions, sampler settings, and artifact hashes are retained with each run. "
        "Acceptance requires R-hat below 1.01, bulk and tail ESS at least 400, zero divergences, finite "
        "diagnostics, and E-BFMI at least 0.3. See "
        '<a href="https://mc-stan.org/learn-stan/diagnostics-warnings.html">Stan’s diagnostic guidance</a>.</p>'
    )
    for label, path in [
        ("Baseline", args.baseline),
        ("Selected full fit", args.selected_fit),
        ("2026 test fit", args.test_fit),
    ]:
        if path:
            sections.append(f"<p>{label}: <code>{html.escape(str(path))}</code></p>")
    sections.append("</details>")
    style = """body{margin:0;background:#f3f5f6;color:#20303b;font:16px/1.6 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:40px 24px 70px}h1{font-size:clamp(2rem,5vw,3.3rem);line-height:1.12;letter-spacing:-.04em;margin:10px 0 20px}h2{margin-top:44px;font-size:1.5rem;letter-spacing:-.02em}.eyebrow{color:#54717e;font-size:.83rem;text-transform:uppercase;letter-spacing:.11em}.lead{font-size:1.15rem;max-width:800px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:32px 0}.cards>div{padding:18px;background:white;border:1px solid #dce3e6;border-radius:10px;color:#59717f;font-size:.86rem}.cards strong{display:block;color:#20303b;font-size:1.9rem;line-height:1.3}.table-scroll{overflow:auto;background:white;border:1px solid #dce3e6;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:.86rem;text-align:left}th,td{padding:11px 13px;border-bottom:1px solid #e6ecef;white-space:nowrap}th{background:#edf2f5;font-weight:600}.note{font-size:.9rem;color:#5c707a}details{margin:22px 0;padding:16px 20px;background:white;border:1px solid #dce3e6;border-radius:8px}summary{cursor:pointer;font-weight:600}code{font-size:.8rem;overflow-wrap:anywhere}a{color:#225f89}.plotly-graph-div{border:1px solid #dce3e6;border-radius:8px;overflow:hidden} @media(max-width:640px){main{padding:24px 14px 50px}.cards{grid-template-columns:repeat(2,1fr);gap:10px}.cards strong{font-size:1.6rem}h2{margin-top:32px}.table-scroll{margin:0 -2px}}"""
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chelsea Bayesian rent model</title><style>'
        + style
        + ".finding{background:#fff6e7;border-left:4px solid #d67e32;padding:18px 22px;margin:24px 0}.finding p{margin:8px 0 0}"
        + "</style></head><body><main>"
        + "".join(sections)
        + "</main><script>document.querySelectorAll('details').forEach(function(d){d.addEventListener('toggle',function(){if(d.open&&window.Plotly){d.querySelectorAll('.plotly-graph-div').forEach(function(g){Plotly.Plots.resize(g);});}});});</script></body></html>"
    )
    (output / "report.html").write_text(document)
    return output / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", nargs="+", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--selected-fit", type=Path)
    parser.add_argument("--test-fit", type=Path)
    parser.add_argument("--holdout-fit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    print(build(parser.parse_args()))


if __name__ == "__main__":
    main()
