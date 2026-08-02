import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

MODEL_DIR = Path("data/model")

st.set_page_config(page_title="West 15th Street Bayesian model", page_icon="📈", layout="wide")
st.title("West 15th Street — Bayesian rent model")
st.caption("Weekly composition-adjusted StreetEasy asking-rent analysis for The Sierra Chelsea, Stonehenge Gardens, and 101 W 15th.")


@st.cache_data(show_spinner=False)
def load_model_outputs(
    model_dir: str, modified_ns: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    del modified_ns
    path = Path(model_dir)
    index = pd.read_parquet(path / "index.parquet")
    index["period"] = pd.to_datetime(index["period"])
    bedroom_prices = pd.read_parquet(path / "bedroom_prices.parquet")
    bedroom_prices["period"] = pd.to_datetime(bedroom_prices["period"])
    floor_effects = pd.read_parquet(path / "floor_effects.parquet")
    observation_diagnostics = pd.read_parquet(path / "observation_diagnostics.parquet")
    observation_diagnostics["period"] = pd.to_datetime(observation_diagnostics["period"])
    metadata = json.loads((path / "metadata.json").read_text())
    return index, bedroom_prices, floor_effects, observation_diagnostics, metadata


st.subheader("Bayesian weekly local rent index")
with st.expander("Model explainer and equations", expanded=False):
    st.markdown(
        """
        ### Goal

        The model estimates a shared weekly rent level for three neighboring West 15th Street
        buildings while adjusting for building and apartment differences. It uses
        StreetEasy **asking rents**, not signed lease rents. Data before May 2019 is excluded.

        Every unit with a confirmed Blueground furnished period is excluded from the model,
        including its earlier history. For the remaining units, all events in the same calendar
        week are reduced to one median asking rent.

        ### Observation model

        Let $y_{i,t}$ be the logarithm of the median asking rent for unit $i$ in week $t$.
        A simplified version of the fitted model is:
        """
    )
    st.latex(
        r"y_{i,t} \sim \operatorname{StudentT}(\nu=5,\, \mu_{i,t},\, \sigma)"
    )
    st.latex(
        r"\mu_{i,t} = \alpha + B_t + \beta_H H_i + \beta_{101} Q_i"
        r" + \gamma_1 I(\mathrm{BR}_i\ge1) + \gamma_2 I(\mathrm{BR}_i\ge2)"
        r" + \gamma_3 I(\mathrm{BR}_i\ge3)"
        r" + \beta_S z(\log(\mathrm{sqft}_i)) + \beta_M M_i"
        r" + \beta_O C_i + \beta_K K_i + A_{f(i)} + u_i"
    )
    st.markdown(
        r"""
        Where:

        - $B_t$ is the shared local rent factor for week $t$.
        - $H_i$ and $Q_i$ identify Stonehenge Gardens and 101 W 15th; their coefficients are
          adjusted levels relative to Sierra.
        - $\gamma_1$ is the first-bedroom premium: one- and two-bedroom units both receive it.
        - $\gamma_2$ and $\gamma_3$ are incremental second- and third-bedroom premiums.
          The total three-bedroom versus studio effect is $\gamma_1+\gamma_2+\gamma_3$.
        - $z(\log(\mathrm{sqft}))$ is standardized log square footage.
        - $M_i$ indicates that square footage was missing and imputed from the bedroom group.
        - For Sierra, $C_i$ is the facing contrast: $-0.5$ for garden, $+0.5$ for skyline/street, and
          zero for K units that face both directions. Thus $\beta_O$ directly compares skyline
          with garden exposure.
        - $K_i$ identifies Sierra's K stack, estimating its both-facing deviation from the midpoint
          of the garden-only and skyline-only groups. Frontage is neutral for the other buildings.
        - $A_{f(i)}$ is a building-specific cumulative physical-floor effect. Sierra skips
          marketed floor 13, so marketed floor 14 is physical floor 13 and PH is physical floor 14.
        - $u_i$ is a unit-specific adjustment for persistent unmeasured differences such as
          layout, light, exposure, renovations, or floor.
        - A Student-t likelihood is used instead of a normal likelihood so unusual prices
          have less influence on the building trend.

        ### Evolution of the building factor

        The shared local factor follows a weekly Gaussian random walk:
        """
    )
    st.latex(r"B_0 = 0")
    st.latex(
        r"B_t = B_{t-1} + \epsilon_t, \qquad "
        r"\epsilon_t \sim \mathcal{N}(0,\sigma_B)"
    )
    st.latex(r"u_i \sim \mathcal{N}(0,\sigma_{\mathrm{unit}})")
    st.markdown("Physical floor 3 is anchored at zero in both buildings. Other levels accumulate shrunk adjacent-floor changes:")
    st.latex(
        r"A_{f_0}=0,\qquad A_{f_j}=A_{f_{j-1}}+\delta_j,\qquad "
        r"\delta_j\sim\mathcal{N}(0,\sigma_{\mathrm{floor}})"
    )
    st.markdown(
        "This allows adjacent weeks to be similar without forcing the trend to be linear. "
        "The displayed building index is anchored at 100 in the first period containing May 2019:"
    )
    st.latex(r"\mathrm{Index}_t = 100\,\exp(B_t)")
    st.markdown(
        """
        ### Uncertainty

        PyMC samples from the joint posterior distribution of all coefficients, weekly
        factors, unit effects, and variance parameters. The shaded band is the 2.5th–97.5th
        posterior percentile for each weekly index value. It reflects model and sampling
        uncertainty, but not every possible source of data error.

        ### Important limitations

        - Excluding all Blueground-associated units avoids their dynamic furnished pricing but
          also removes otherwise useful conventional-rental history from those apartments.
        - StreetEasy history is selected listing data and may omit off-platform rentals.
        - Repeated weekly observations from the same unit are correlated; the unit random
          effect handles persistent correlation, but not every time-varying unit difference.
        - The index is composition-adjusted by the listed controls, but it is not a formal
          market or signed-lease index.
        """
    )

weekly_dir = MODEL_DIR / "weekly"
required_model_files = [
    weekly_dir / "index.parquet",
    weekly_dir / "bedroom_prices.parquet",
    weekly_dir / "floor_effects.parquet",
    weekly_dir / "observation_diagnostics.parquet",
    weekly_dir / "metadata.json",
]
if not all(path.exists() for path in required_model_files):
    st.info("Run `uv run python models/rent_model.py --frequency weekly` to fit the model.")
else:
    weekly_mtime = max(path.stat().st_mtime_ns for path in required_model_files)
    (
        weekly_index,
        bedroom_prices,
        floor_effects,
        observation_diagnostics,
        weekly_metadata,
    ) = load_model_outputs(str(weekly_dir), weekly_mtime)

    building_names = weekly_metadata["buildings"]
    selected_building = st.selectbox(
        "Building for adjusted-price and diagnostic views",
        options=list(building_names),
        format_func=lambda slug: building_names[slug],
    )
    selected_building_name = building_names[selected_building]
    bedroom_prices = bedroom_prices[bedroom_prices["building_slug"] == selected_building]
    floor_effects = floor_effects[floor_effects["building_slug"] == selected_building]
    observation_diagnostics = observation_diagnostics[
        observation_diagnostics["building_slug"] == selected_building
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weekly_index["period"], y=weekly_index["index_upper"],
        mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=weekly_index["period"], y=weekly_index["index_lower"],
        mode="lines", line={"width": 0}, fill="tonexty",
        fillcolor="rgba(22,77,180,0.18)", name="95% credible interval",
    ))
    fig.add_trace(go.Scatter(
        x=weekly_index["period"], y=weekly_index["index_median"],
        mode="lines", line={"color": "#164db4", "width": 2}, name="Posterior median",
    ))
    fig.add_hline(y=100, line_dash="dot", line_color="gray")
    fig.update_layout(
        xaxis_title="Week", yaxis_title="Rent index (first post-cutoff week = 100)",
        height=560, hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Adjusted asking prices by bedroom count")
    price_fig = go.Figure()
    colors = {
        "Studio": ("#5f6368", "rgba(95,99,104,0.13)"),
        "1 BR": ("#164db4", "rgba(22,77,180,0.16)"),
        "2 BR": ("#b3261e", "rgba(179,38,30,0.14)"),
        "3 BR": ("#188038", "rgba(24,128,56,0.14)"),
    }
    bedroom_order = [
        group for group in ["Studio", "1 BR", "2 BR", "3 BR"]
        if group in set(bedroom_prices["bedroom_group"])
    ]
    for bedroom_group in bedroom_order:
        group = bedroom_prices[bedroom_prices["bedroom_group"] == bedroom_group]
        line_color, fill_color = colors[bedroom_group]
        price_fig.add_trace(go.Scatter(
            x=group["period"], y=group["price_upper"], mode="lines",
            line={"width": 0}, hoverinfo="skip", showlegend=False,
        ))
        price_fig.add_trace(go.Scatter(
            x=group["period"], y=group["price_lower"], mode="lines",
            line={"width": 0}, fill="tonexty", fillcolor=fill_color,
            hoverinfo="skip", showlegend=False,
        ))
        price_fig.add_trace(go.Scatter(
            x=group["period"], y=group["price_median"], mode="lines",
            line={"color": line_color, "width": 2}, name=bedroom_group,
        ))
    price_fig.update_layout(
        xaxis_title="Week", yaxis_title="Adjusted asking rent",
        yaxis_tickprefix="$", yaxis_tickformat=",", height=560, hovermode="x unified",
    )
    st.plotly_chart(price_fig, use_container_width=True)
    typical_sizes = bedroom_prices.groupby("bedroom_group")["typical_square_feet"].first().to_dict()
    reference_floor = int(bedroom_prices["reference_floor"].iloc[0])
    size_description = ", ".join(
        f"{group}: {typical_sizes[group]:.0f} ft²" for group in bedroom_order
    )
    st.caption(
        f"Posterior prices for typical non-Blueground {selected_building_name} units on floor "
        f"{reference_floor}, with average unit effect and neutral facing adjustment. Typical "
        f"sizes are {size_description}. Bands are 95% credible intervals."
    )

    st.subheader(f"Cumulative floor premium — {selected_building_name}")
    floor_fig = go.Figure(go.Scatter(
        x=floor_effects["physical_floor"],
        y=floor_effects["cumulative_median"],
        mode="lines+markers",
        line={"color": "#6f42c1", "width": 2},
        marker={"size": 8},
        error_y={
            "type": "data",
            "symmetric": False,
            "array": floor_effects["cumulative_upper"] - floor_effects["cumulative_median"],
            "arrayminus": floor_effects["cumulative_median"] - floor_effects["cumulative_lower"],
            "color": "rgba(111,66,193,0.55)",
        },
        customdata=floor_effects[["floor_label", "units", "increment_median"]],
        hovertemplate=(
            "Floor %{customdata[0]}<br>Cumulative premium: %{y:.1f}%"
            "<br>Units: %{customdata[1]}"
            "<br>Change from lower level: %{customdata[2]:+.1f}%<extra></extra>"
        ),
    ))
    floor_fig.add_hline(y=0, line_dash="dot", line_color="gray")
    floor_fig.update_layout(
        xaxis={
            "title": "Marketed floor",
            "tickmode": "array",
            "tickvals": floor_effects["physical_floor"].tolist(),
            "ticktext": floor_effects["floor_label"].tolist(),
            "range": [
                floor_effects["physical_floor"].min() - 0.4,
                floor_effects["physical_floor"].max() + 0.4,
            ],
        },
        yaxis_title="Premium relative to floor 3",
        yaxis_ticksuffix="%", height=480,
    )
    st.plotly_chart(floor_fig, use_container_width=True)
    floor_note = (
        " For Sierra, the axis retains marketed labels: floor 14 is physical floor 13 and PH "
        "is physical floor 14."
        if selected_building == "the-sierra-chelsea" else ""
    )
    st.caption(
        "Each point is the cumulative sum of posterior changes from lower physical floors. "
        "The shared floor-change scale shrinks neighboring levels toward similar rents."
        + floor_note + " Error bars are 95% credible intervals."
    )

    if selected_building == "the-sierra-chelsea":
        st.subheader("Garden and skyline exposure")
        facing = weekly_metadata["facing_effects_percent"]
        skyline = facing["skyline_vs_garden"]
        both_exposure = facing["both_vs_single_facing_midpoint"]
        facing_col1, facing_col2 = st.columns(2)
        facing_col1.metric("Skyline vs garden", f"{skyline['median']:+.1f}%")
        facing_col2.metric(
            "K both-facing vs single-facing midpoint", f"{both_exposure['median']:+.1f}%"
        )
        st.caption(
            f"95% intervals — skyline versus garden: {skyline['lower_95']:+.1f}% to "
            f"{skyline['upper_95']:+.1f}%; K both-facing deviation: "
            f"{both_exposure['lower_95']:+.1f}% to {both_exposure['upper_95']:+.1f}%. "
            "A–J are classified as garden, K as both, and L onward as street-facing "
            "(marketed as skyline)."
        )

    st.subheader("Observation fit and outlier diagnostics")
    outlier_count = int(observation_diagnostics["is_outlier_95"].sum())
    st.caption(
        f"{outlier_count:,} of {len(observation_diagnostics):,} unit-week observations have a "
        "two-sided posterior predictive tail probability below 5%. These are in-sample "
        "diagnostics, so they are useful for finding structure the model missed but are less "
        "stringent than leave-one-out residuals."
    )
    fit_tab, time_tab, outlier_tab = st.tabs(
        ["Observed vs fitted", "Residuals over time", "Largest outliers"]
    )
    with fit_tab:
        diagnostic_fig = go.Figure()
        residual_color_limit = max(
            10.0,
            float(observation_diagnostics["residual_percent"].abs().quantile(0.98)),
        )
        diagnostic_fig.add_trace(go.Scattergl(
            x=observation_diagnostics["fitted_rent"],
            y=observation_diagnostics["asking_rent"],
            mode="markers",
            marker={
                "size": 6,
                "opacity": 0.62,
                "color": observation_diagnostics["residual_percent"],
                "colorscale": "RdBu_r",
                "cmin": -residual_color_limit,
                "cmax": residual_color_limit,
                "colorbar": {"title": "Observed vs fitted (%)"},
            },
            customdata=observation_diagnostics[[
                "unit", "period", "bedroom_group", "marketed_floor",
                "residual_percent", "standardized_residual", "tail_probability",
            ]],
            hovertemplate=(
                "Unit %{customdata[0]} · %{customdata[1]|%Y-%m-%d}"
                "<br>%{customdata[2]} · floor %{customdata[3]}"
                "<br>Fitted: $%{x:,.0f}<br>Observed: $%{y:,.0f}"
                "<br>Residual: %{customdata[4]:+.1f}%"
                "<br>Standardized: %{customdata[5]:+.2f}"
                "<br>Tail probability: %{customdata[6]:.3f}<extra></extra>"
            ),
            name="Observations",
        ))
        axis_min = float(min(
            observation_diagnostics["fitted_rent"].min(),
            observation_diagnostics["asking_rent"].min(),
        ))
        axis_max = float(max(
            observation_diagnostics["fitted_rent"].max(),
            observation_diagnostics["asking_rent"].max(),
        ))
        diagnostic_fig.add_trace(go.Scatter(
            x=[axis_min, axis_max], y=[axis_min, axis_max], mode="lines",
            line={"color": "#555", "dash": "dash"}, name="Perfect fit",
            hoverinfo="skip",
        ))
        diagnostic_fig.update_layout(
            xaxis_title="Posterior median fitted rent",
            yaxis_title="Observed asking rent",
            xaxis_tickprefix="$", yaxis_tickprefix="$",
            xaxis_tickformat=",", yaxis_tickformat=",",
            height=620,
        )
        st.plotly_chart(diagnostic_fig, use_container_width=True)
    with time_tab:
        time_fig = go.Figure()
        bedroom_colors = {
            "Studio": "#5f6368", "1 BR": "#164db4",
            "2 BR": "#b3261e", "3 BR": "#188038",
        }
        for bedroom_group, color in bedroom_colors.items():
            group = observation_diagnostics[
                observation_diagnostics["bedroom_group"] == bedroom_group
            ]
            time_fig.add_trace(go.Scattergl(
                x=group["period"], y=group["residual_percent"], mode="markers",
                marker={"size": 6, "opacity": 0.55, "color": color},
                customdata=group[["unit", "asking_rent", "fitted_rent", "tail_probability"]],
                hovertemplate=(
                    "Unit %{customdata[0]} · %{x|%Y-%m-%d}"
                    "<br>Observed: $%{customdata[1]:,.0f}"
                    "<br>Fitted: $%{customdata[2]:,.0f}"
                    "<br>Residual: %{y:+.1f}%"
                    "<br>Tail probability: %{customdata[3]:.3f}<extra></extra>"
                ),
                name=bedroom_group,
            ))
        time_fig.add_hline(y=0, line_dash="dash", line_color="#555")
        time_fig.update_layout(
            xaxis_title="Week", yaxis_title="Observed minus fitted",
            yaxis_ticksuffix="%", height=560,
        )
        st.plotly_chart(time_fig, use_container_width=True)
    with outlier_tab:
        outlier_table = observation_diagnostics.sort_values(
            ["tail_probability", "period"]
        ).head(50).copy()
        outlier_table["period"] = outlier_table["period"].dt.date
        st.dataframe(
            outlier_table[[
                "unit", "period", "bedroom_group", "marketed_floor",
                "asking_rent", "fitted_rent", "residual_percent",
                "standardized_residual", "tail_probability",
            ]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "asking_rent": st.column_config.NumberColumn(format="$%d"),
                "fitted_rent": st.column_config.NumberColumn(format="$%.0f"),
                "residual_percent": st.column_config.NumberColumn(format="%.1f%%"),
                "standardized_residual": st.column_config.NumberColumn(format="%.2f"),
                "tail_probability": st.column_config.NumberColumn(format="%.4f"),
            },
        )

    bedrooms = weekly_metadata["bedroom_premiums_percent"]
    first = bedrooms["first_bedroom"]
    second = bedrooms["second_bedroom_increment"]
    third = bedrooms["third_bedroom_increment"]
    building_effects = weekly_metadata["building_effects_vs_sierra_percent"]
    stonehenge_effect = building_effects["stonehenge-gardens"]
    building_101_effect = building_effects["101w15-101-west-15th-street-new_york"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("First bedroom premium", f"{first['median']:+.1f}%")
    c2.metric("Second-bedroom increment", f"{second['median']:+.1f}%")
    c3.metric("Third-bedroom increment", f"{third['median']:+.1f}%")
    c4.metric("Stonehenge vs Sierra", f"{stonehenge_effect['median']:+.1f}%")
    c5.metric("101 W 15th vs Sierra", f"{building_101_effect['median']:+.1f}%")
    st.caption(
        f"95% intervals — first bedroom: {first['lower_95']:+.1f}% to {first['upper_95']:+.1f}%; "
        f"second increment: {second['lower_95']:+.1f}% to {second['upper_95']:+.1f}%; "
        f"third increment: {third['lower_95']:+.1f}% to {third['upper_95']:+.1f}%; "
        f"Stonehenge vs Sierra: {stonehenge_effect['lower_95']:+.1f}% to "
        f"{stonehenge_effect['upper_95']:+.1f}%; 101 W 15th vs Sierra: "
        f"{building_101_effect['lower_95']:+.1f}% to {building_101_effect['upper_95']:+.1f}%."
    )
    latest_adjusted = (
        bedroom_prices.sort_values("period").groupby("bedroom_group").tail(1)
        .set_index("bedroom_group")["price_median"]
    )
    if {"1 BR", "2 BR"}.issubset(latest_adjusted.index):
        typical_two_bed_gap = 100 * (
            latest_adjusted["2 BR"] / latest_adjusted["1 BR"] - 1
        )
        st.info(
            f"The {second['median']:+.1f}% second-bedroom coefficient holds square footage and floor "
            f"constant. It is not the price gap between typical apartments. At the modeled typical "
            f"sizes shown above, the latest adjusted 2 BR price is {typical_two_bed_gap:.1f}% above "
            "the adjusted 1 BR price."
        )
    else:
        st.info(
            "This building has no modeled 2 BR trajectory, so its adjusted studio/1 BR chart "
            "cannot illustrate the model-wide second-bedroom increment."
        )
    st.caption(
        f"PyMC Student-t model using {weekly_metadata['observations']:,} unit-week observations "
        f"from {weekly_metadata['units']} units since {weekly_metadata['cutoff']}."
    )
    st.warning(
        "All units with any confirmed Blueground furnished period are excluded entirely, "
        "including their earlier conventional-rental histories."
    )
    with st.expander("Model assumptions and diagnostics"):
        st.json(weekly_metadata)
