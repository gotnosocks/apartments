import importlib.util
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

MODELS = Path(__file__).parent.parent / "models"
PORT_DIFF = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "port_diff.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


splits = load("history_splits", MODELS / "analysis" / "history_splits.py")

NAN = float("nan")
# Unit, listing ID, first day, bedrooms and square feet of each ad, with the piece v4 gives it.
ADS = [
    # A change of 2 or more splits, and a change back rejoins the first piece.
    ("u:1", "101", "2020-01-01", 1, NAN, 0),
    ("u:1", "102", "2021-01-01", 4, NAN, 1),
    ("u:1", "103", "2022-01-01", 1, NAN, 0),
    # A change of one splits. An ad with no bedroom count stays in the piece before it.
    ("u:2", "201", "2020-01-01", 2, 900, 0),
    ("u:2", "202", "2020-06-01", 3, 900, 1),
    ("u:2", "203", "2021-01-01", NAN, NAN, 1),
    ("u:2", "204", "2022-01-01", 2, 900, 0),
    ("u:2", "205", "2023-01-01", 0, 900, 2),
    # A change of one holds when the last counted ad gave no size and this one gives one, but a
    # change of two splits with or without a size.
    ("u:3", "301", "2020-01-01", 0, NAN, 0),
    ("u:3", "302", "2021-01-01", 1, 1500, 0),
    ("u:3", "303", "2022-01-01", 3, NAN, 1),
    ("u:3", "304", "2023-01-01", 5, 1500, 2),
    # Ads of one day go by listing ID as a string, so "1000" comes before "999".
    ("u:4", "999", "2020-01-01", 2, NAN, 1),
    ("u:4", "1000", "2020-01-01", 1, NAN, 0),
    # One bedroom count: the unit keeps a single piece.
    ("u:5", "501", "2020-01-01", 1, NAN, 0),
    ("u:5", "502", "2021-01-01", 1, 700, 0),
]


def frame() -> pd.DataFrame:
    rows = pd.DataFrame(
        [ad[:5] for ad in ADS],
        columns=["unit_id", "listing_id", "day", "bedrooms", "square_feet"],
    )
    rows["price_at"] = pd.to_datetime(rows.day, utc=True)
    return rows


def test_pieces_match_the_chain():
    """`pieces` gives each ad the piece v4 gives it, and the chain's own v4 agrees."""
    rows = frame()
    rows["unit"] = rows.unit_id
    order = rows.sort_values(["unit", "price_at", "listing_id"]).index
    found = pd.Series(splits.pieces(rows.loc[order]), index=order).sort_index()
    assert found.tolist() == [ad[5] for ad in ADS]
    data = load("port_diff", PORT_DIFF).frontier()
    chain = data.DATA_RULES["unit-splits-v4"](
        rows.assign(source_listing_id=rows.listing_id)
    )
    ours = np.where(found > 0, rows.unit + "~" + found.astype(str), rows.unit)
    assert ours.tolist() == chain.unit_id.tolist()


class Fetcher:
    """Stands in for a SQLMesh context: it runs a Python model's queries on `db`, with each
    model's table under its own name."""

    def __init__(self, db):
        self.db = db

    def resolve_table(self, name):
        return name

    def fetchdf(self, query):
        return self.db.sql(query).df()


def test_history_splits_model():
    """The model walks label units: u:6's page unit joins u:1's label unit, so its two-bedroom ad
    of 2023 counts as a change from u:1's one-bedroom ad of 2022. It lists only the ads moved out
    of the first piece."""
    db = duckdb.connect()
    db.execute("CREATE SCHEMA analysis")
    rows = frame()
    rows.loc[len(rows)] = [
        "u:6",
        "601",
        "2023-01-01",
        2,
        NAN,
        pd.Timestamp("2023-01-01", tz="UTC"),
    ]
    db.register("frame", rows)
    db.execute(
        "CREATE TABLE analysis.ledger_rows AS "
        "SELECT listing_id, unit_id, price_at, bedrooms::DOUBLE AS bedrooms, "
        "square_feet::DOUBLE AS square_feet FROM frame"
    )
    db.execute(
        "CREATE TABLE analysis.label_units AS SELECT 'u:6' AS unit_id, 'u:1' AS label_unit"
    )
    (table,) = splits.execute.__wrapped__(Fetcher(db), None, None, None)
    assert list(table.columns) == list(splits.COLUMNS)
    found = sorted(table.itertuples(index=False, name=None))
    assert found == [
        ("102", "u:1", "u:1~1"),
        ("202", "u:2", "u:2~1"),
        ("203", "u:2", "u:2~1"),
        ("205", "u:2", "u:2~2"),
        ("303", "u:3", "u:3~1"),
        ("304", "u:3", "u:3~2"),
        ("601", "u:1", "u:1~2"),
        ("999", "u:4", "u:4~1"),
    ]
