import duckdb
import pandas as pd

# Listing ID, unit, label unit, first day, bedrooms and bathrooms of each row, with the fate
# analysis.label_months gives it, or None for a row it keeps.
ROWS = [
    # Two pages of one label unit in January: the later ad stays. February keeps its own row.
    ("11", "u:1", "u:1", "2024-01-05", 1, 1, "superseded_in_label_month"),
    ("21", "u:2", "u:1", "2024-01-20", 1, 1, None),
    ("12", "u:1", "u:1", "2024-02-03", 1, 1, None),
    # A ledger split keeps its own ID, which no label unit joins.
    ("13", "u:1~review-13", "u:1~review-13", "2024-01-25", 1, 1, None),
    # Two bedroom counts, or two bathroom counts, in a label-month drop every row of it.
    ("31", "u:3", "u:3", "2024-03-01", 2, 1, "conflicting_layout_same_label_month"),
    ("41", "u:4", "u:3", "2024-03-10", 3, 1, "conflicting_layout_same_label_month"),
    ("51", "u:5", "u:5", "2024-03-01", 1, 1, "conflicting_layout_same_label_month"),
    ("61", "u:6", "u:5", "2024-03-02", 1, 2, "conflicting_layout_same_label_month"),
    # A missing count conflicts with no other count. analysis.ledger_rows holds no such row
    # at present, since ads.exclusions drops an ad without both counts, so this case only
    # guards the check against one.
    ("52", "u:5", "u:5", "2024-04-01", 1, 1, "superseded_in_label_month"),
    ("62", "u:6", "u:5", "2024-04-02", None, 1, None),
    # On one day, the greater ad ID as text stays: "999" over "1000".
    ("999", "u:7", "u:7", "2024-05-01", 0, 1, None),
    ("1000", "u:8", "u:7", "2024-05-01", 0, 1, "superseded_in_label_month"),
]


def test_label_months_cases(render_context, tmp_path):
    """The model drops the rows of a label-month after the chain's two steps, on label units:
    every row of a month with two layouts, and the earlier rows of any other month."""
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    db.execute("CREATE SCHEMA analysis")
    rows = pd.DataFrame(
        [row[:6] for row in ROWS],
        columns=["listing_id", "unit_id", "label_unit", "day", "bedrooms", "bathrooms"],
    )
    rows["price_at"] = pd.to_datetime(rows.day, utc=True)
    rows["period"] = rows.price_at.dt.tz_convert(None).dt.to_period("M").dt.start_time
    db.register("frame", rows)
    db.execute(
        "CREATE TABLE analysis.ledger_rows AS SELECT listing_id, unit_id, price_at, "
        "period::DATE AS period, bedrooms::DOUBLE AS bedrooms, bathrooms::DOUBLE AS bathrooms "
        "FROM frame"
    )
    db.execute(
        "CREATE TABLE analysis.label_units AS SELECT DISTINCT unit_id, label_unit FROM frame "
        "WHERE unit_id <> label_unit"
    )
    query = render_context.render("analysis.label_months").sql(dialect="duckdb")
    found = {
        listing: (unit, fate)
        for listing, unit, fate in db.sql(
            f"SELECT listing_id, label_unit, fate FROM ({query})"
        ).fetchall()
    }
    assert found == {row[0]: (row[2], row[6]) for row in ROWS if row[6]}
