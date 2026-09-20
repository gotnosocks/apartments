"""Numerical project-health dashboard for collection, transformation, and modeling."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from apartments.project_evolution import (
    CATEGORIES,
    COLLECTION,
    METRIC_DEFINITIONS,
    MODELING,
    STATUSES,
    TRANSFORMATION,
    comparable_change,
    current_fit,
    current_selection,
    format_value,
    latest_observation,
    observations,
)

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(
    page_title="Project metrics",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #172033;
        --muted: #667085;
        --line: #e5e7eb;
    }
    .hero {
        padding: 1.5rem 1.7rem 1.35rem;
        border: 1px solid #dbeafe;
        border-radius: 18px;
        background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 58%, #ecfeff 100%);
        margin-bottom: 1.2rem;
    }
    .hero h1 { margin: 0 0 .35rem; color: var(--ink); letter-spacing: -.02em; }
    .hero p { margin: 0; color: #475467; max-width: 980px; font-size: 1.02rem; line-height: 1.55; }
    .stage-card {
        min-height: 120px;
        padding: 1rem 1.05rem;
        border: 1px solid var(--line);
        border-radius: 14px;
        background: white;
        box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
    }
    .stage-card h3 { margin: 0 0 .42rem; font-size: 1.02rem; color: var(--ink); }
    .stage-card p { margin: 0; color: var(--muted); line-height: 1.45; font-size: .91rem; }
    .stage-label {
        display: inline-block; padding: .16rem .48rem; border-radius: 999px;
        font-size: .72rem; font-weight: 700; letter-spacing: .04em;
        text-transform: uppercase; margin-bottom: .55rem;
    }
    .collection { background: #dbeafe; color: #1d4ed8; }
    .transformation { background: #ccfbf1; color: #0f766e; }
    .modeling { background: #fef3c7; color: #92400e; }
    .status { font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>Project metrics over time</h1>
      <p>
        Numerical health of the apartment pipeline from source collection through
        analytical transformation and Bayesian modeling. This page shows scale,
        missingness, conflicts, failures, uncertainty and compute cost alongside
        successful outcomes. A larger number is not automatically an improvement.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Metric filters")
    stage_choice = st.selectbox("Pipeline stage", ["All stages", *CATEGORIES])
    stage_filter = None if stage_choice == "All stages" else stage_choice
    importance_choice = st.selectbox("Metric group", ["All metrics", "Primary", "Risks and limits", "Context"])
    importance_filter = {
        "All metrics": None,
        "Primary": "primary",
        "Risks and limits": "risk",
        "Context": "context",
    }[importance_choice]
    include_research = st.checkbox(
        "Include research and interrupted runs",
        value=True,
        help="Unpromoted experiments and failed/partial runs are important project measurements and remain visible by default.",
    )
    st.divider()
    st.caption(
        "Use the app page navigation to open the rental explorer or Bayesian analysis. "
        "This dashboard is read-only and never scrapes or fits."
    )

status_filter = STATUSES if include_research else ("complete", "selected", "active", "warning")
all_observations = observations(stage=stage_filter, include_statuses=status_filter)
if not all_observations:
    st.info("No observations match the current filters.")
    st.stop()

min_day = min(item.day for item in all_observations)
max_day = max(item.day for item in all_observations)
with st.sidebar:
    selected_dates = st.date_input(
        "Observation dates",
        value=(min_day, max_day),
        min_value=min_day,
        max_value=max_day,
    )
if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
    start_day, end_day = selected_dates
else:
    start_day = end_day = selected_dates

visible_observations = [
    item for item in all_observations if start_day <= item.day <= end_day
]
visible_metric_ids = {
    item.metric_id
    for item in visible_observations
    if importance_filter is None or METRIC_DEFINITIONS[item.metric_id]["importance"] == importance_filter
}
visible_definitions = {
    metric_id: definition
    for metric_id, definition in METRIC_DEFINITIONS.items()
    if (stage_filter is None or definition["stage"] == stage_filter)
    and (importance_filter is None or definition["importance"] == importance_filter)
    and metric_id in visible_metric_ids
}

selection = current_selection(ROOT)
fit = current_fit(ROOT)
latest_floor = latest_observation("transform.floor_coverage_pct")
latest_conflicts = latest_observation("transform.conflicting_attribute_groups")
latest_raw = latest_observation("transform.listing_observations")

st.subheader("Current health snapshot")
health = st.columns(5)
health[0].metric(
    "Archived listing observations",
    format_value("transform.listing_observations", latest_raw.value if latest_raw else None),
    help="Granular source interpretation count; not a physical-unit census.",
)
if selection.get("available"):
    health[1].metric("Selected Bayesian rows", f"{selection.get('rows') or 0:,}")
    health[2].metric("Selected units / buildings", f"{selection.get('units') or 0:,} / {selection.get('buildings') or 0:,}")
else:
    health[1].metric("Selected Bayesian rows", "Unavailable")
    health[2].metric("Selected units / buildings", "Unavailable")
health[3].metric("Known listed-floor coverage", format_value("transform.floor_coverage_pct", latest_floor.value if latest_floor else None))
health[4].metric(
    "Maximum R-hat",
    f"{fit['max_rhat']:.4f}" if fit.get("available") and fit.get("max_rhat") is not None else "Unavailable",
    help="Near 1 is desirable; this is not a model-quality score by itself.",
)

if fit.get("available"):
    st.caption(
        f"Selected pointer: `{selection.get('experiment', 'unknown')}` · "
        f"{fit.get('retained_draws') or 0:,} retained draws · "
        f"{fit.get('divergences')} divergences · diagnostics acceptable={fit.get('acceptable')}"
    )
else:
    st.caption("The selected model pointer is readable, but lightweight fit diagnostics are unavailable.")

st.markdown("### Stage overview")
stage_columns = st.columns(3)
for column, category, heading, body, current in (
    (stage_columns[0], COLLECTION, "Capture", "Raw source requests, archive scale, duplicate behavior and coverage gaps.", "Canonical-only West Village collection is active."),
    (stage_columns[1], TRANSFORMATION, "Transform", "Input/output accounting, missingness, identity conflicts, temporal rules and reversible review overlays.", "Floor evidence and source revisions are tracked separately from the main fit."),
    (stage_columns[2], MODELING, "Fit and analyze", "Cohorts, validation, posterior diagnostics, residual behavior, uncertainty and computation.", "The expanded-floor PyMC fit is the selected main model."),
):
    css_class = {COLLECTION: "collection", TRANSFORMATION: "transformation", MODELING: "modeling"}[category]
    with column:
        st.markdown(
            f'<div class="stage-card"><span class="stage-label {css_class}">{escape(category)}</span>'
            f'<h3>{escape(heading)}</h3><p>{escape(body)}</p>'
            f'<p style="margin-top:.7rem"><strong>{escape(current)}</strong></p></div>',
            unsafe_allow_html=True,
        )

st.warning(
    "Important limitations remain visible: 966 historical 404 outcomes, 5,464 conflicting "
    "attribute groups, 66.3% square-footage missingness, unresolved advertisement/unit identities, "
    "and only 68.39% measured 95% interval coverage for new-building validation rows."
)


def status_text(value: str) -> str:
    return value.replace("_", " ").title()


def observation_value(metric_id: str, item) -> str:
    value = format_value(metric_id, item.value)
    if item.lower is not None and item.upper is not None:
        value += f" ({format_value(metric_id, item.lower)}–{format_value(metric_id, item.upper)})"
    return value


def change_text(metric_id: str) -> str:
    change = comparable_change(metric_id, include_statuses=status_filter)
    if not change.get("comparable"):
        return "—" if "latest" not in change else "Not comparable"
    delta = change["delta"]
    percent = change.get("percent")
    sign = "+" if delta > 0 else ""
    suffix = f" ({sign}{percent:.1f}%)" if percent is not None else ""
    return f"{sign}{format_value(metric_id, delta)}{suffix}"


def metric_table(metric_ids: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric_id in metric_ids:
        item = latest_observation(metric_id, include_statuses=status_filter)
        if item is None or not (start_day <= item.day <= end_day):
            continue
        definition = METRIC_DEFINITIONS[metric_id]
        rows.append(
            {
                "Metric": definition["label"],
                "Latest": observation_value(metric_id, item),
                "As of": item.day.isoformat(),
                "Version": item.version,
                "Status": status_text(item.status),
                "Change vs prior comparable": change_text(metric_id),
                "Direction": definition["direction"],
                "Caveat": definition["caveat"],
                "Evidence": " · ".join(item.source),
            }
        )
    return pd.DataFrame(rows)


# Every stage gets the same structure: all current metrics, one selectable
# trajectory, and the full dated observation ledger.  The table is deliberately
# not restricted to metrics with positive movement.
st.subheader("Stage metrics")
stage_tabs = st.tabs(list(CATEGORIES))
for tab, category in zip(stage_tabs, CATEGORIES):
    with tab:
        stage_metric_ids = [
            metric_id
            for metric_id, definition in visible_definitions.items()
            if definition["stage"] == category
        ]
        if not stage_metric_ids:
            st.info("No metrics match the current filters for this stage.")
            continue
        st.markdown(f"#### {category}: latest values and comparable movement")
        table = metric_table(stage_metric_ids)
        if table.empty:
            st.info("No observations match the selected date range.")
        else:
            st.dataframe(table, hide_index=True, width="stretch")

        chart_ids = [
            metric_id
            for metric_id in stage_metric_ids
            if any(item.metric_id == metric_id for item in visible_observations)
        ]
        if chart_ids:
            labels = {metric_id: METRIC_DEFINITIONS[metric_id]["label"] for metric_id in chart_ids}
            selected_metric = st.selectbox(
                "Plot a metric over time",
                chart_ids,
                format_func=labels.__getitem__,
                key=f"metric-plot-{category}",
            )
            points = [item for item in visible_observations if item.metric_id == selected_metric]
            frame = pd.DataFrame(
                [
                    {
                        "Date": item.day,
                        "Value": item.value,
                        "Version": item.version,
                        "Status": status_text(item.status),
                        "Note": item.note,
                    }
                    for item in points
                ]
            ).sort_values(["Date", "Version"])
            figure = px.line(
                frame,
                x="Date",
                y="Value",
                markers=True,
                color="Status",
                hover_name="Version",
                hover_data={"Date": "|%b %d, %Y", "Value": ":,.4f", "Status": True, "Note": True},
                height=350,
            )
            figure.update_layout(
                margin={"l": 10, "r": 20, "t": 20, "b": 10},
                xaxis_title="",
                yaxis_title=METRIC_DEFINITIONS[selected_metric]["unit"],
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend_title_text="",
            )
            figure.update_xaxes(showgrid=True, gridcolor="#eef2f6")
            st.plotly_chart(figure, width="stretch")
            definition = METRIC_DEFINITIONS[selected_metric]
            st.caption(
                f"{definition['direction'].title()} is not automatically better for this metric. "
                f"{definition['caveat']}"
            )

        with st.expander(f"All dated {category.lower()} observations"):
            ledger_rows = []
            for item in visible_observations:
                if item.metric_id not in stage_metric_ids:
                    continue
                definition = METRIC_DEFINITIONS[item.metric_id]
                ledger_rows.append(
                    {
                        "Metric": definition["label"],
                        "Date": item.day.isoformat(),
                        "Value": observation_value(item.metric_id, item),
                        "Version": item.version,
                        "Comparability key": item.comparability_key,
                        "Status": status_text(item.status),
                        "Note": item.note,
                        "Evidence": " · ".join(item.source),
                    }
                )
            st.dataframe(pd.DataFrame(ledger_rows), hide_index=True, width="stretch")

st.subheader("Metrics that are warnings, limits, or unresolved")
st.caption(
    "These are not failed progress indicators in every case. Some rose because the project "
    "measured a problem more accurately; they remain visible so the dashboard does not report only wins."
)
risk_ids = [
    metric_id
    for metric_id, definition in METRIC_DEFINITIONS.items()
    if definition["importance"] == "risk"
    and (stage_filter is None or definition["stage"] == stage_filter)
]
risk_table = metric_table(risk_ids)
if risk_table.empty:
    st.info("No warning metrics match the current filters.")
else:
    st.dataframe(risk_table, hide_index=True, width="stretch")

st.subheader("Cross-stage metric ledger")
ledger = []
for item in visible_observations:
    if item.metric_id not in visible_definitions:
        continue
    definition = METRIC_DEFINITIONS[item.metric_id]
    ledger.append(
        {
            "Stage": definition["stage"],
            "Metric": definition["label"],
            "Date": item.day.isoformat(),
            "Value": observation_value(item.metric_id, item),
            "Version": item.version,
            "Comparability key": item.comparability_key,
            "Status": status_text(item.status),
            "Evidence": " · ".join(item.source),
        }
    )
if ledger:
    st.dataframe(pd.DataFrame(ledger), hide_index=True, width="stretch")

st.subheader("How to interpret changes")
st.markdown(
    """
    - **Comparable change** is shown only when the latest two observations share a
      comparability key. A different source cohort, scope policy, or model
      specification is shown as **not comparable**, not as a misleading delta.
    - **Context metrics** such as row counts, parameter counts and retained draws
      describe the experiment. They are not quality scores.
    - **Risk metrics** include missingness, conflicts, 404s, unresolved identities,
      interval failures and interrupted work. They are intentionally not hidden.
    - Collection and interpretation time are different clocks. Dates on this page
      are report/artifact dates; they do not assert when an apartment attribute was
      historically effective.
    - Model residuals are in-sample review signals, and validation numbers are
      retrospective development results. Neither is a guarantee of availability,
      transaction rent, causal amenity value, or calibrated uncertainty.
    """
)

st.caption(
    "The metric ledger is curated from dated repository reports and lightweight saved model manifests. "
    "The page does not load posterior arrays, scrape StreetEasy, or modify analytical artifacts."
)
