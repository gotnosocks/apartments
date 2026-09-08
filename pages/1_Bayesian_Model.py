"""Streamlit view for the dynamic monthly Chelsea rent model."""
import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

MODEL_DIR = Path("data/model/monthly")
st.set_page_config(page_title="Chelsea rent model", page_icon="📈", layout="wide")
st.title("Chelsea — Bayesian asking-rent model")
st.caption("Monthly, composition-adjusted StreetEasy asking rents across all available archive buildings.")

@st.cache_data(show_spinner=False)
def load_outputs(directory: str, modified_ns: int):
    del modified_ns
    path = Path(directory)
    metadata = json.loads((path / "metadata.json").read_text())
    index = pd.read_parquet(path / "index.parquet")
    effects = pd.read_parquet(path / "building_effects.parquet")
    coefficients = pd.read_parquet(path / "coefficients.parquet")
    diagnostics = pd.read_parquet(path / "observation_diagnostics.parquet")
    index["period"] = pd.to_datetime(index["period"])
    diagnostics["period"] = pd.to_datetime(diagnostics["period"])
    return metadata, index, effects, coefficients, diagnostics

required = ["metadata.json", "index.parquet", "building_effects.parquet", "coefficients.parquet", "observation_diagnostics.parquet"]
missing = [name for name in required if not (MODEL_DIR / name).exists()]
if missing:
    st.info("Run the monthly model to create dashboard outputs: `./.venv/bin/python models/rent_model.py --frequency monthly`.")
    st.caption("All available history is used by default; this page does not start sampling.")
    st.stop()

metadata, index, effects, coefficients, diagnostics = load_outputs(str(MODEL_DIR), max((MODEL_DIR / name).stat().st_mtime_ns for name in required))
coverage = metadata.get("coverage", {})
c1, c2, c3, c4 = st.columns(4)
c1.metric("Buildings", f"{len(metadata.get('buildings', {})):,}")
c2.metric("Units", f"{metadata.get('units', 0):,}")
c3.metric("Observations", f"{metadata.get('observations', 0):,}")
c4.metric("Frequency", metadata.get("frequency", "monthly"))

st.subheader("Rent index")
fig = go.Figure()
fig.add_trace(go.Scatter(x=index.period, y=index.index_upper, line={"width": 0}, hoverinfo="skip", showlegend=False))
fig.add_trace(go.Scatter(x=index.period, y=index.index_lower, line={"width": 0}, fill="tonexty", fillcolor="rgba(22,77,180,.18)", name="95% credible interval"))
fig.add_trace(go.Scatter(x=index.period, y=index.index_median, line={"color": "#164db4", "width": 2}, name="Posterior median"))
fig.add_hline(y=100, line_dash="dot", line_color="gray")
fig.update_layout(xaxis_title="Month", yaxis_title=f"Index ({metadata.get('index_base_period', 'base')} = 100)", height=500, hovermode="x unified")
st.plotly_chart(fig, width="stretch")
st.caption(f"Index is rebased to {metadata.get('index_base_period')}. The bands describe model uncertainty, not complete market coverage.")
coverage_chart = go.Figure(go.Bar(x=index.period, y=index.units, name="Observed units"))
coverage_chart.update_layout(xaxis_title="Month", yaxis_title="Units with a price event", height=220)
st.plotly_chart(coverage_chart, width="stretch")

st.subheader("Coverage")
if coverage:
    st.dataframe(pd.DataFrame([{"metric": key, "value": str(value)} for key, value in coverage.items()]), width="stretch", hide_index=True)
else:
    st.write({"observations": metadata.get("observations"), "units": metadata.get("units"), "buildings": len(metadata.get("buildings", {}))})

st.subheader("Building effects")
st.caption("Percentage differences from the mean building effect after adjusting for listed controls. Sparse buildings are shrunk toward the population mean.")
st.dataframe(effects.sort_values("median", ascending=False), width="stretch", hide_index=True)

st.subheader("Model coefficients")
st.caption("Percent rent change per additional bedroom/bathroom, or per one standard deviation of log square footage. Missingness terms compare missing with recorded values. These are associations, not causal effects.")
st.dataframe(coefficients, width="stretch", hide_index=True)

validation = metadata.get("validation")
if validation:
    st.subheader("Withheld-price test")
    st.caption(validation.get("limitation", ""))
    if validation.get("max_rhat", 0) > 1.01 or validation.get("divergences", 0):
        st.warning("The withheld-price fit has a convergence warning; treat its metrics as provisional.")
    st.json(validation)

st.subheader("Observation diagnostics")
st.caption("These residuals use the fitted training data; see the separate withheld-price test for predictive performance.")
if not diagnostics.empty:
    selected = st.selectbox("Building", sorted(diagnostics.building_slug.unique()), format_func=lambda slug: metadata.get("buildings", {}).get(slug, slug))
    view = diagnostics[diagnostics.building_slug == selected].copy()
    scatter = go.Figure(go.Scattergl(x=view.fitted_rent, y=view.asking_rent, mode="markers", marker={"color": view.residual_percent, "colorscale": "RdBu_r", "size": 7}, text=view.unit))
    scatter.update_layout(xaxis_title="Fitted asking rent", yaxis_title="Observed asking rent", height=420)
    st.plotly_chart(scatter, width="stretch")
    view["period"] = view.period.dt.date
    st.dataframe(view.sort_values("period", ascending=False), width="stretch", hide_index=True)

st.subheader("Diagnostics and assumptions")
max_rhat = metadata.get("max_rhat")
divergences = metadata.get("divergences", 0)
if max_rhat is not None and max_rhat > 1.01:
    st.warning(f"Maximum R-hat is {max_rhat:.3f}; convergence is not yet reliable.")
if divergences:
    st.warning(f"The sampler reported {divergences:,} divergent transitions.")
st.json({"max_rhat": max_rhat, "min_ess_bulk": metadata.get("min_ess_bulk"), "divergences": divergences, "assumptions": metadata.get("assumptions", [])})
