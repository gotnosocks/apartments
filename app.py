from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DEFAULT_DB = Path("data/apartments.duckdb")
BUILDINGS = {
    "the-sierra-chelsea": "The Sierra Chelsea",
    "stonehenge-gardens": "Stonehenge Gardens",
    "101w15-101-west-15th-street-new_york": "101 W 15th",
}
KNOWN_INVALID_UNITS = {"the-sierra-chelsea": {"7", "8"}}

st.set_page_config(page_title="West 15th Street rents", page_icon="🏢", layout="wide")
st.title("West 15th Street — rental price history")
st.caption("StreetEasy asking-rent and status history captured from individual unit pages.")


@st.cache_data(show_spinner=False)
def load_data(
    db_path: str, building_slug: str, modified_ns: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del modified_ns  # Included only to invalidate the cache when DuckDB changes.
    connection = duckdb.connect(db_path, read_only=True)
    listings = connection.execute(
        """SELECT source_listing_id, unit, floor, unit_letter, unit_suffix,
                  unit_format, unit_kind, unit_is_specific, is_furnished, bedrooms, bathrooms,
                  square_feet, canonical_address
           FROM listings
           WHERE source = 'streeteasy'
             AND building_slug = ?""",
        [building_slug],
    ).df()
    events = connection.execute(
        """SELECT e.source_listing_id, l.unit, l.floor, l.unit_format,
                  l.bedrooms, l.bathrooms, l.square_feet, l.is_furnished,
                  CAST(e.event_at AS DATE) AS event_date,
                  e.price AS asking_rent, e.event_type, e.raw_json
           FROM listing_events e
           JOIN listings l USING (source, source_listing_id)
           WHERE e.source = 'streeteasy'
             AND l.building_slug = ?
             AND e.price IS NOT NULL
             AND e.event_at IS NOT NULL
           ORDER BY e.event_at, l.unit""",
        [building_slug],
    ).df()
    connection.close()
    events["event_date"] = pd.to_datetime(events["event_date"])
    return listings, events


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

building_slug = st.sidebar.selectbox(
    "Building", options=list(BUILDINGS), format_func=lambda slug: BUILDINGS[slug]
)
st.header(BUILDINGS[building_slug])
listings, events = load_data(str(db_path), building_slug, db_path.stat().st_mtime_ns)
if events.empty:
    st.warning("No priced history events were found. Run `uv run apartments import-captures data`.")
    st.stop()

listings["bedroom_group"] = listings["bedrooms"].map(bedroom_label)
events["bedroom_group"] = events["bedrooms"].map(bedroom_label)

all_units = sorted(listings["unit"].dropna().astype(str).unique(), key=lambda value: (len(value), value))
default_invalid = sorted(KNOWN_INVALID_UNITS.get(building_slug, set()).intersection(all_units))
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

history_tab, trend_tab, latest_tab, unit_tab, data_tab = st.tabs(
    ["All histories", "Observed trend", "Latest by unit", "Unit detail", "Data quality"]
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
