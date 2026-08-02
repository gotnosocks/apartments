import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DEFAULT_DB = Path("data/apartments.duckdb")
BUILDING_SLUG = "the-sierra-chelsea"
MODEL_DIR = Path("data/model")
KNOWN_INVALID_UNITS = {"7", "8"}

st.set_page_config(page_title="Sierra Chelsea rents", page_icon="🏢", layout="wide")
st.title("The Sierra Chelsea — rental price history")
st.caption("StreetEasy asking-rent and status history captured from individual unit pages.")


@st.cache_data(show_spinner=False)
def load_data(db_path: str, modified_ns: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    del modified_ns  # Included only to invalidate the cache when DuckDB changes.
    connection = duckdb.connect(db_path, read_only=True)
    listings = connection.execute(
        """SELECT source_listing_id, unit, floor, unit_letter, unit_suffix,
                  unit_format, unit_kind, unit_is_specific, is_furnished, bedrooms, bathrooms,
                  square_feet, canonical_address
           FROM listings
           WHERE source = 'streeteasy'
             AND source_listing_id LIKE ?""",
        [f"{BUILDING_SLUG}/%"],
    ).df()
    events = connection.execute(
        """SELECT e.source_listing_id, l.unit, l.floor, l.unit_format,
                  l.bedrooms, l.bathrooms, l.square_feet, l.is_furnished,
                  CAST(e.event_at AS DATE) AS event_date,
                  e.price AS asking_rent, e.event_type, e.raw_json
           FROM listing_events e
           JOIN listings l USING (source, source_listing_id)
           WHERE e.source = 'streeteasy'
             AND e.source_listing_id LIKE ?
             AND e.price IS NOT NULL
             AND e.event_at IS NOT NULL
           ORDER BY e.event_at, l.unit""",
        [f"{BUILDING_SLUG}/%"],
    ).df()
    connection.close()
    events["event_date"] = pd.to_datetime(events["event_date"])
    return listings, events


@st.cache_data(show_spinner=False)
def load_furnishing_periods(db_path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    connection = duckdb.connect(db_path, read_only=True)
    periods = connection.execute(
        """SELECT unit, starts_on, ends_on, furnishing_status, operator,
                  confidence, evidence
           FROM unit_furnishing_periods
           WHERE source='streeteasy' AND building_slug=?
           ORDER BY unit, starts_on""",
        [BUILDING_SLUG],
    ).df()
    connection.close()
    return periods


@st.cache_data(show_spinner=False)
def load_model_outputs(model_dir: str, modified_ns: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    del modified_ns
    path = Path(model_dir)
    index = pd.read_parquet(path / "index.parquet")
    index["period"] = pd.to_datetime(index["period"])
    bedroom_prices = pd.read_parquet(path / "bedroom_prices.parquet")
    bedroom_prices["period"] = pd.to_datetime(bedroom_prices["period"])
    metadata = json.loads((path / "metadata.json").read_text())
    return index, bedroom_prices, metadata


def bedroom_label(value) -> str:
    if pd.isna(value):
        return "Unknown"
    if float(value) == 0:
        return "Studio"
    number = int(value) if float(value).is_integer() else value
    return f"{number} BR"


db_input = st.sidebar.text_input("DuckDB path", str(DEFAULT_DB))
db_path = Path(db_input)
if not db_path.exists():
    st.error(f"Database not found: {db_path}")
    st.stop()

listings, events = load_data(str(db_path), db_path.stat().st_mtime_ns)
if events.empty:
    st.warning("No priced history events were found. Run `uv run apartments import-captures data`.")
    st.stop()

listings["bedroom_group"] = listings["bedrooms"].map(bedroom_label)
events["bedroom_group"] = events["bedrooms"].map(bedroom_label)

all_units = sorted(listings["unit"].dropna().astype(str).unique(), key=lambda value: (len(value), value))
default_invalid = sorted(KNOWN_INVALID_UNITS.intersection(all_units))
invalid_units = st.sidebar.multiselect(
    "Exclude invalid/non-unit identifiers",
    all_units,
    default=default_invalid,
    help="This app defaults to excluding units classified as non-specific or invalid.",
)

bedroom_options = sorted(events["bedroom_group"].unique())
selected_bedrooms = st.sidebar.multiselect("Bedrooms", bedroom_options, default=bedroom_options)
format_options = sorted(events["unit_format"].fillna("unknown").unique())
selected_formats = st.sidebar.multiselect("Unit format", format_options, default=format_options)
furnishing = st.sidebar.selectbox("Furnishing", ["All", "Furnished", "Unfurnished"])

minimum_date = events["event_date"].min().date()
maximum_date = events["event_date"].max().date()
date_range = st.sidebar.date_input(
    "Event date range",
    value=(minimum_date, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date,
)
selected_units = st.sidebar.multiselect("Show only selected units (optional)", all_units)

filtered = events[
    ~events["unit"].astype(str).isin(invalid_units)
    & events["bedroom_group"].isin(selected_bedrooms)
    & events["unit_format"].fillna("unknown").isin(selected_formats)
].copy()
if len(date_range) == 2:
    filtered = filtered[
        filtered["event_date"].dt.date.between(date_range[0], date_range[1])
    ]
if selected_units:
    filtered = filtered[filtered["unit"].astype(str).isin(selected_units)]
if furnishing == "Furnished":
    filtered = filtered[filtered["is_furnished"].fillna(False)]
elif furnishing == "Unfurnished":
    filtered = filtered[~filtered["is_furnished"].fillna(False)]

if filtered.empty:
    st.warning("No observations match these filters.")
    st.stop()

latest = (
    filtered.sort_values(["unit", "event_date"])
    .groupby("unit", as_index=False)
    .tail(1)
    .copy()
)
latest["rent_per_sqft"] = latest["asking_rent"] / latest["square_feet"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Units", filtered["unit"].nunique())
col2.metric("Price observations", f"{len(filtered):,}")
col3.metric("Earliest event", filtered["event_date"].min().date().isoformat())
col4.metric("Latest median asking rent", f"${latest['asking_rent'].median():,.0f}")

history_tab, trend_tab, model_tab, latest_tab, unit_tab, data_tab = st.tabs(
    ["All histories", "Observed trend", "Bayesian model", "Latest by unit", "Unit detail", "Data quality"]
)

with history_tab:
    st.subheader("Asking-rent observations by unit")
    fig = px.scatter(
        filtered.sort_values("event_date"),
        x="event_date",
        y="asking_rent",
        color="unit",
        hover_data=["bedroom_group", "floor", "square_feet", "is_furnished", "event_type"],
        labels={"event_date": "Date", "asking_rent": "Asking rent", "unit": "Unit"},
        render_mode="webgl",
    )
    fig.update_traces(mode="lines+markers", marker={"size": 5})
    fig.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",", legend_title="Unit", height=700)
    if filtered["unit"].nunique() > 30:
        fig.update_layout(showlegend=False)
        st.caption("The legend is hidden when more than 30 units are selected; hover to identify a unit.")
    st.plotly_chart(fig, use_container_width=True)

with trend_tab:
    st.subheader("Monthly median observed rent")
    st.caption(
        "Each unit contributes at most its last observed price in a month. This is a descriptive "
        "summary of StreetEasy history events, not a vacancy-weighted market index."
    )
    monthly_unit = filtered.assign(month=filtered["event_date"].dt.to_period("M").dt.to_timestamp())
    monthly_unit = (
        monthly_unit.sort_values("event_date")
        .groupby(["month", "unit", "bedroom_group"], as_index=False)
        .tail(1)
    )
    monthly = monthly_unit.groupby(["month", "bedroom_group"], as_index=False).agg(
        median_rent=("asking_rent", "median"),
        units=("unit", "nunique"),
    )
    fig = px.line(
        monthly,
        x="month",
        y="median_rent",
        color="bedroom_group",
        markers=True,
        hover_data=["units"],
        labels={"month": "Month", "median_rent": "Median asking rent", "bedroom_group": "Bedrooms"},
    )
    fig.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",", height=550)
    st.plotly_chart(fig, use_container_width=True)

    yearly = monthly_unit.assign(year=monthly_unit["month"].dt.year)
    yearly = yearly.groupby(["year", "bedroom_group"], as_index=False).agg(
        median_rent=("asking_rent", "median"), units=("unit", "nunique")
    )
    st.dataframe(yearly, use_container_width=True, hide_index=True)

with model_tab:
    st.subheader("Bayesian weekly building rent index")
    with st.expander("Model explainer and equations", expanded=False):
        st.markdown(
            """
            ### Goal

            The model estimates a shared weekly rent level for The Sierra Chelsea while adjusting
            for differences among the apartments observed in each week. It uses
            StreetEasy **asking rents**, not signed lease rents. Data before May 2019 is excluded.

            To stop frequently repriced furnished listings from dominating the fit, all events
            for the same unit and calendar week are reduced to one median asking rent.

            ### Observation model

            Let $y_{i,t}$ be the logarithm of the median asking rent for unit $i$ in week $t$.
            A simplified version of the fitted model is:
            """
        )
        st.latex(
            r"y_{i,t} \sim \operatorname{StudentT}(\nu=5,\, \mu_{i,t},\, \sigma)"
        )
        st.latex(
            r"\mu_{i,t} = \alpha + B_t + \beta_F F_{i,t}"
            r" + \gamma_1 I(\mathrm{BR}_i\ge1) + \gamma_2 I(\mathrm{BR}_i\ge2)"
            r" + \beta_S z(\log(\mathrm{sqft}_i)) + \beta_M M_i + u_i"
        )
        st.markdown(
            r"""
            Where:

            - $B_t$ is the building-wide rent factor for week $t$ in the primary model.
            - $F_{i,t}$ is 1 after that unit's first explicit `Listed by The Blueground`
              event and 0 during earlier conventionally managed listing periods. Uncertain transfer
              windows are omitted from model training.
            - $\gamma_1$ is the first-bedroom premium: one- and two-bedroom units both receive it.
            - $\gamma_2$ is the incremental second-bedroom premium: only two-bedroom units receive it.
              The total two-bedroom versus studio effect is $\gamma_1+\gamma_2$.
            - $z(\log(\mathrm{sqft}))$ is standardized log square footage.
            - $M_i$ indicates that square footage was missing and imputed from the bedroom group.
            - $u_i$ is a unit-specific adjustment for persistent unmeasured differences such as
              layout, light, exposure, renovations, or floor.
            - A Student-t likelihood is used instead of a normal likelihood so unusual prices
              have less influence on the building trend.

            ### Evolution of the building factor

            The building factor follows a weekly Gaussian random walk:
            """
        )
        st.latex(r"B_0 = 0")
        st.latex(
            r"B_t = B_{t-1} + \epsilon_t, \qquad "
            r"\epsilon_t \sim \mathcal{N}(0,\sigma_B)"
        )
        st.latex(r"u_i \sim \mathcal{N}(0,\sigma_{\mathrm{unit}})")
        st.markdown(
            "This allows adjacent weeks to be similar without forcing the trend to be linear. "
            "The displayed building index is anchored at 100 in the first period containing May 2019:"
        )
        st.latex(r"\mathrm{Index}_t = 100\,\exp(B_t)")
        st.markdown("The furnished coefficient is converted from log-rent units into a percentage:")
        st.latex(r"\mathrm{Furnished\ effect} = 100\,[\exp(\beta_F)-1]\%")
        st.markdown(
            """
            ### Uncertainty

            PyMC samples from the joint posterior distribution of all coefficients, weekly
            factors, unit effects, and variance parameters. The shaded band is the 2.5th–97.5th
            posterior percentile for each weekly index value. It reflects model and sampling
            uncertainty, but not every possible source of data error.

            ### Important limitations

            - A furnished era begins at the first explicit Blueground listing. This is strong
              marketing evidence, but it does not prove who held the underlying lease or identify
              the exact date furniture was installed.
            - StreetEasy history is selected listing data and may omit off-platform rentals.
            - Repeated weekly observations from the same unit are correlated; the unit random
              effect handles persistent correlation, but not every time-varying unit difference.
            - The index is composition-adjusted by the listed controls, but it is not a formal
              market or signed-lease index.
            """
        )

    weekly_dir = MODEL_DIR / "weekly"
    if not (weekly_dir / "index.parquet").exists():
        st.info("Run `uv run python models/rent_model.py --frequency weekly` to fit the model.")
    else:
        weekly_mtime = max(
            (weekly_dir / "index.parquet").stat().st_mtime_ns,
            (weekly_dir / "bedroom_prices.parquet").stat().st_mtime_ns,
            (weekly_dir / "metadata.json").stat().st_mtime_ns,
        )
        weekly_index, bedroom_prices, weekly_metadata = load_model_outputs(str(weekly_dir), weekly_mtime)

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

        st.subheader("Adjusted one- and two-bedroom asking prices")
        price_fig = go.Figure()
        colors = {
            "1 BR": ("#164db4", "rgba(22,77,180,0.16)"),
            "2 BR": ("#b3261e", "rgba(179,38,30,0.14)"),
        }
        for bedroom_group in ["1 BR", "2 BR"]:
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
        st.caption(
            "Posterior prices for typical unfurnished units with average unit effect and observed "
            f"square footage: approximately {typical_sizes['1 BR']:.0f} ft² for 1 BR and "
            f"{typical_sizes['2 BR']:.0f} ft² for 2 BR. Bands are 95% credible intervals."
        )

        furnished = weekly_metadata["furnished_premium_percent"]
        bedrooms = weekly_metadata["bedroom_premiums_percent"]
        first = bedrooms["first_bedroom"]
        second = bedrooms["second_bedroom_increment"]
        total = bedrooms["two_bedroom_vs_studio"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("First bedroom premium", f"{first['median']:+.1f}%")
        c2.metric("Second bedroom increment", f"{second['median']:+.1f}%")
        c3.metric("2 BR vs studio", f"{total['median']:+.1f}%")
        c4.metric("Furnished effect", f"{furnished['median']:+.1f}%")
        st.caption(
            f"95% intervals — first bedroom: {first['lower_95']:+.1f}% to {first['upper_95']:+.1f}%; "
            f"second increment: {second['lower_95']:+.1f}% to {second['upper_95']:+.1f}%; "
            f"2 BR vs studio: {total['lower_95']:+.1f}% to {total['upper_95']:+.1f}%; "
            f"furnished: {furnished['lower_95']:+.1f}% to {furnished['upper_95']:+.1f}%."
        )
        st.caption(
            f"PyMC Student-t model using {weekly_metadata['observations']:,} unit-week observations "
            f"from {weekly_metadata['units']} units since {weekly_metadata['cutoff']}."
        )
        st.warning(
            "Historical furnishing is inferred from the first explicit 'Listed by The Blueground' "
            "event. This supports a furnished-marketing interpretation but does not establish the "
            "underlying landlord/tenant relationship, so the coefficient is not necessarily causal."
        )
        with st.expander("Inferred historical furnishing periods"):
            furnishing_periods = load_furnishing_periods(str(db_path), db_path.stat().st_mtime_ns)
            st.dataframe(furnishing_periods, use_container_width=True, hide_index=True)
            st.caption(
                "Confirmed furnished periods start with an explicit Blueground listing. "
                "Unknown transition periods are excluded from model fitting."
            )
        with st.expander("Model assumptions and diagnostics"):
            st.json(weekly_metadata)

with latest_tab:
    st.subheader("Latest observed asking rent for each unit")
    fig = px.scatter(
        latest,
        x="floor",
        y="asking_rent",
        color="bedroom_group",
        hover_name="unit",
        hover_data=["event_date", "event_type", "square_feet", "rent_per_sqft", "is_furnished"],
        labels={"floor": "Inferred floor", "asking_rent": "Latest observed rent", "bedroom_group": "Bedrooms"},
    )
    fig.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",", height=550)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Penthouse units have no inferred numbered floor and therefore do not appear in the floor-axis plot.")

    sqft = latest.dropna(subset=["square_feet", "rent_per_sqft"])
    if not sqft.empty:
        fig = px.scatter(
            sqft,
            x="square_feet",
            y="asking_rent",
            color="bedroom_group",
            hover_name="unit",
            trendline=None,
            labels={"square_feet": "Square feet", "asking_rent": "Latest observed rent"},
        )
        fig.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",", height=500)
        st.plotly_chart(fig, use_container_width=True)

with unit_tab:
    unit_choice = st.selectbox("Unit", sorted(filtered["unit"].astype(str).unique()))
    unit_events = filtered[filtered["unit"].astype(str) == unit_choice].sort_values("event_date")
    fig = px.scatter(
        unit_events,
        x="event_date",
        y="asking_rent",
        hover_data=["event_type", "square_feet", "bedrooms", "bathrooms"],
        labels={"event_date": "Date", "asking_rent": "Asking rent"},
    )
    fig.update_traces(mode="lines+markers")
    fig.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",", height=450)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        unit_events[["event_date", "asking_rent", "event_type"]].sort_values("event_date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with data_tab:
    st.subheader("Coverage")
    coverage = listings.assign(has_sqft=listings["square_feet"].notna()).groupby(
        ["bedroom_group", "unit_format", "is_furnished"], dropna=False, as_index=False
    ).agg(units=("unit", "nunique"), units_with_sqft=("has_sqft", "sum"))
    st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.subheader("Event types")
    event_counts = filtered.groupby("event_type", dropna=False).size().reset_index(name="observations")
    st.dataframe(event_counts.sort_values("observations", ascending=False), use_container_width=True, hide_index=True)

    st.subheader("Filtered observations")
    st.dataframe(
        filtered[["unit", "floor", "bedroom_group", "is_furnished", "square_feet", "event_date", "asking_rent", "event_type"]]
        .sort_values("event_date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
