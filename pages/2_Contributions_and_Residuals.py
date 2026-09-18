"""Read-only review of the verified descriptive asking-rent fit."""
from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from apartments.analysis_review import AnalysisWorkspace, bundle_signature

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/model/chelsea-reviewed-analysis-20260918-v3"
DEFAULT_RESIDUALS = ROOT / "data/model/chelsea-interior-reviewed-residuals-20260918"
DEFAULT_EVIDENCE = ROOT / "data/model/chelsea-analysis-descriptions-20260918"

st.set_page_config(page_title="Contributions and residuals", page_icon="🔎", layout="wide")
st.title("Chelsea — contributions and residuals")
st.caption("Review the saved fit, investigate unusual asking prices, and compare apartment features.")
st.info(
    "These are in-sample asking-rent diagnostics. A large residual is a reason to inspect "
    "the listing, its data, and missing features; it is not a bargain score. "
    "The saved current sample does not establish live availability."
)


@st.cache_resource(show_spinner=False)
def load_workspace(model: str, dataset: str, residuals: str, evidence: str | None, signature: str):
    del signature  # File metadata invalidates the verified workspace cache.
    return AnalysisWorkspace.load(model, dataset, residuals, evidence)


def display_name(value):
    return str(value).replace("_", " ")


def source_links(record):
    linked = False
    for label, key in (("Advertisement on StreetEasy", "advertisement_url"),
                       ("Unit on StreetEasy", "canonical_unit_url")):
        url = record.get(key)
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed and parsed.scheme == "https" and parsed.hostname in {"streeteasy.com", "www.streeteasy.com"}:
            st.link_button(label, url)
            linked = True
    if linked:
        st.caption("External listing pages may differ from the saved capture. See Source evidence for archived descriptions.")


def known_value(value):
    return value is not None and not (isinstance(value, float) and math.isnan(value))


with st.sidebar:
    st.header("Saved analysis")
    model_path = st.text_input("Model bundle", str(DEFAULT / "model"))
    dataset_path = st.text_input("Dataset bundle", str(DEFAULT / "dataset"))
    residual_path = st.text_input("Residual bundle", str(DEFAULT_RESIDUALS))
    evidence_path = st.text_input("Archived description bundle", str(DEFAULT_EVIDENCE),
                                  help="Optional verified description archive for this fitted cohort. Leave blank to disable.").strip() or None
    if st.button("Reload saved analysis"):
        load_workspace.clear()

try:
    signature = bundle_signature(model_path, dataset_path, residual_path, *([evidence_path] if evidence_path else []))
    with st.spinner("Verifying the saved analysis…"):
        workspace = load_workspace(model_path, dataset_path, residual_path, evidence_path, signature)
except (OSError, ValueError, KeyError, TypeError) as exc:
    st.error(f"The saved analysis could not be loaded: {exc}")
    st.caption("Choose matching model, dataset, and residual bundles. This page does not fit or scrape data.")
    st.stop()

residuals = pd.DataFrame(workspace.residuals)
if residuals.empty:
    st.info("The saved analysis contains no fitted observations.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fitted observations", f"{len(residuals):,}")
c2.metric("Units", f"{residuals.unit_id.nunique():,}")
c3.metric("Buildings", f"{residuals.building_id.nunique():,}")
c4.metric("Saved current observations", f"{residuals.current_capture.sum():,}")
with st.expander("Analysis coverage and provenance"):
    st.json(workspace.summary)

st.subheader("Find a listing to examine")
f1, f2, f3 = st.columns(3)
with f1:
    scope = st.selectbox("Observation scope", ["Saved current sample", "All fitted observations"])
with f2:
    building = st.selectbox("Building", [None, *sorted(residuals.building_id.unique())],
                            format_func=lambda value: "All buildings" if value is None else display_name(value))
with f3:
    order = st.selectbox("Review order", ["Largest absolute residual", "Ask above fitted rent", "Ask below fitted rent"])
one_per_unit = st.checkbox("Show one observation per unit", value=True)
search = st.text_input("Find advertisement ID or unit URL", help="Search within the selected observation scope and building before the row limit is applied.").strip()
view = residuals.copy()
if scope == "Saved current sample":
    view = view[view.current_capture]
if building is not None:
    view = view[view.building_id == building]
if search:
    search_columns = [column for column in ("source_listing_id", "canonical_unit_url", "unit_id") if column in view]
    matches = pd.Series(False, index=view.index)
    for column in search_columns:
        matches |= view[column].fillna("").astype(str).str.contains(search, case=False, regex=False)
    view = view[matches]
if order == "Ask above fitted rent":
    view = view[view.asking_minus_fitted > 0].sort_values(["asking_vs_fitted_percent", "audit_id"], ascending=[False, True])
elif order == "Ask below fitted rent":
    view = view[view.asking_minus_fitted < 0].sort_values(["asking_vs_fitted_percent", "audit_id"], ascending=[True, True])
else:
    view = view.sort_values(["absolute_log_residual", "audit_id"], ascending=[False, True])
if one_per_unit:
    view = view.drop_duplicates("unit_id")
if view.empty:
    st.info("No observations match these filters.")
    st.stop()

limit = st.selectbox("Maximum rows to review", [25, 100, 500], index=1)
review = view.head(limit)
st.caption(f"Showing {len(review):,} of {len(view):,} matching observations. Residual percentages use fitted rent as the denominator.")
columns = ["building_id", "source_listing_id", "period", "asking_rent", "fitted_rent", "asking_minus_fitted", "asking_vs_fitted_percent"]
st.dataframe(review[columns].rename(columns={
    "building_id": "Building", "source_listing_id": "Advertisement", "period": "Month",
    "asking_rent": "Asking rent ($)", "fitted_rent": "Fitted rent ($)",
    "asking_minus_fitted": "Ask − fit ($)", "asking_vs_fitted_percent": "Ask vs fit (%)",
}), hide_index=True, width="stretch")
labels = {row.audit_id: f"{display_name(row.building_id)} · ad {row.source_listing_id} · {row.period} · {row.asking_vs_fitted_percent:+.1f}%"
          for row in review.itertuples()}
audit_id = st.selectbox("Observation to inspect", list(labels), format_func=labels.__getitem__)
try:
    detail = workspace.detail(audit_id)
except (OSError, ValueError, KeyError, TypeError) as exc:
    st.error(f"The selected observation could not be verified: {exc}")
    st.stop()
record = detail["source_record"]
residual = detail["residual"]
st.subheader("Selected apartment")
a, b, c = st.columns(3)
a.metric("Advertised asking rent", f"${residual['asking_rent']:,.0f}")
b.metric("Fitted asking rent", f"${residual['fitted_rent']:,.0f}")
c.metric("Ask − fitted rent", f"${residual['asking_minus_fitted']:+,.0f}", f"{residual['asking_vs_fitted_percent']:+.1f}%", delta_color="off")
source_links({**record, **residual})
for warning in detail.get("warnings", []):
    st.warning(warning)

contributions_tab, contrast_tab, evidence_tab = st.tabs(["Contributions and history", "Change apartment features", "Source evidence"])
with contributions_tab:
    st.caption("These components sum to log fitted rent in the saved model's parameterization. They are not standalone dollar premiums or causal effects. Use feature changes to compare two specified apartments.")
    families = detail["log_contributions_by_family"]
    if "reference" in families:
        st.metric("Reference component (log rent)", f"{families['reference']:.6f}")
    family_frame = pd.DataFrame([{"Family": display_name(key), "Log contribution": value} for key, value in families.items() if key != "reference"])
    if not family_frame.empty:
        figure = go.Figure(go.Bar(x=family_frame["Log contribution"], y=family_frame.Family, orientation="h"))
        figure.update_layout(xaxis_title="Adjustment to reference log rent", yaxis_title=None,
                             height=max(300, 30 * len(family_frame)), margin={"t": 10, "b": 35})
        st.plotly_chart(figure, width="stretch")
    st.caption(f"Sum: {math.fsum(families.values()):.6f} log rent. Exponentiating the sum gives the fitted rent.")
    with st.expander("Exact model components"):
        st.json(detail["log_components"])
    st.subheader("This unit's fitted history")
    history = pd.DataFrame(detail["unit_history"])
    if not history.empty:
        history = history.sort_values(["period", "audit_id"])
        fig = go.Figure()
        for column, label in (("asking_rent", "Advertised ask"), ("fitted_rent", "Fitted rent")):
            fig.add_trace(go.Scatter(x=history.period, y=history[column], name=label, mode="lines+markers"))
        fig.update_layout(xaxis_title="Price month", yaxis_title="Monthly asking rent ($)", height=330)
        st.plotly_chart(fig, width="stretch")
        st.dataframe(history[["period", "source_listing_id", "asking_rent", "fitted_rent", "asking_vs_fitted_percent"]], hide_index=True, width="stretch")
    st.caption("History is retrospective: the price date can precede the capture of listing attributes. It does not establish which attributes were known at each historical date.")

with contrast_tab:
    st.caption("Compare conditional asking rents for the same apartment and date, keeping its building and unit effects fixed. Interactions are recomputed. This is an association in the fitted data, not a renovation return or personal willingness to pay.")
    fields = workspace.fields
    chosen = st.multiselect("Features to change together", list(fields),
                            format_func=lambda name: fields[name]["label"], key=f"fields:{audit_id}")
    if chosen:
        changes = {}
        with st.form(f"contrast:{audit_id}:{','.join(chosen)}"):
            for name in chosen:
                spec = fields[name]
                original = detail["feature_values"].get(name)
                label = spec["label"]
                st.caption(f"{label}: recorded value = {original if known_value(original) else 'unknown'}")
                key = f"change:{signature}:{audit_id}:{name}"
                if spec["kind"] == "category":
                    options = [None, *spec["options"]]
                    changes[name] = st.selectbox(label, options, index=options.index(original) if original in options else 0,
                                                format_func=lambda value: "Unknown" if value is None else display_name(value), key=key)
                elif spec["kind"] == "boolean":
                    options = [None, False, True]
                    changes[name] = st.selectbox(label, options, index=options.index(original) if original in options else 0,
                                                format_func=lambda value: "Unknown" if value is None else ("Yes" if value else "No"), key=key)
                else:
                    minimum, maximum = float(spec["minimum"]), float(spec["maximum"])
                    default = float(original) if known_value(original) else minimum
                    value = st.number_input(label, min_value=minimum, max_value=maximum,
                                            value=min(max(default, minimum), maximum), step=float(spec["step"]), key=key)
                    unknown = st.checkbox(f"{label} is unknown", value=not known_value(original), key=f"{key}:unknown")
                    changes[name] = None if unknown else value
            submitted = st.form_submit_button("Compare with recorded apartment")
        if submitted:
            try:
                result = workspace.contrast(audit_id, changes)
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"This feature comparison could not be computed: {exc}")
            else:
                st.caption("Submitted feature changes")
                st.json(changes)
                if result["show_estimate"]:
                    estimate = result["estimate"]
                    left, right = st.columns(2)
                    left.metric("Changed apartment: fitted rent", f"${estimate['changed_rent']:,.0f}")
                    right.metric("Change from recorded apartment", f"${estimate['dollar_change']:+,.0f}", f"{estimate['percent_change']:+.2f}%", delta_color="off")
                else:
                    st.warning("No supported feature-value estimate is available for this comparison.")
                    st.caption(display_name(result["status"]))
                for warning in result.get("warnings", []):
                    st.warning(warning)
                if result.get("support"):
                    st.write("Evidence supporting the comparison")
                    st.json(result["support"])
                with st.expander("Held fixed"):
                    st.write(result.get("held_fixed", []))
    else:
        st.info("Choose one or more features to compare jointly.")
    with st.expander("Feature coverage in the fitted dataset"):
        st.dataframe(pd.DataFrame(workspace.factor_support()), hide_index=True, width="stretch")

with evidence_tab:
    st.caption("Use these source records and timestamps to investigate missing features, ambiguous descriptions, and price-basis problems. This page does not modify the underlying evidence.")
    captures = detail.get("source_captures", [])
    if captures:
        st.subheader("Archived listing description")
        capture_index = st.selectbox("Saved capture", list(range(len(captures))),
            format_func=lambda index: f"Capture {captures[index].get('capture_id', index + 1)} · {captures[index].get('source_collected_at', 'collection time unavailable')}",
            key=f"source-capture:{audit_id}")
        capture = captures[capture_index]
        if capture.get("description"):
            st.text(capture["description"])
        else:
            st.info("This capture has no archived description text.")
        st.caption("Collection time is when the source was captured; interpretation time is when its description was recovered. Neither establishes when an apartment feature physically changed.")
        st.json({key: capture.get(key) for key in (
            "capture_id", "source_listing_id", "source_collected_at", "description_interpreted_at",
            "known_at", "body_sha256", "raw_listing_sha256", "source_path",
        )})
    else:
        st.info("No matching archived description is available for this observation in the selected bundle." if evidence_path
                else "Archived description review is disabled. Choose a description bundle to inspect saved text.")
    st.write("Observation provenance")
    st.json(detail["provenance"])
    with st.expander("Complete source record"):
        st.json(record)
    with st.expander("Saved residual record"):
        st.json(residual)
