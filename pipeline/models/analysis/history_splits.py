"""analysis.history_splits: the pieces the chain's history rule, `unit-splits-v4`, cuts units into.

A unit page sometimes collects the ads of apartments of different sizes, after a combination, a
rebuild or a miscoded ad: a one-bedroom at $3,395 and a four-bedroom at $14,999 under one page.
The model walks each label unit's rows by their price date, then by listing ID as a string, as v4
does, and starts a new piece at an ad whose bedroom count differs from the last ad with a count.

1. An ad with no bedroom count stays in the piece of the ad before it.
2. An ad with a bedroom count the unit has had before goes back to that count's latest piece, so
   a convertible apartment coded 1, 2, 1 keeps its one-bedroom ads together.
3. A change of one bedroom keeps the piece when the last ad with a count gave no size and this ad
   gives one. At 110 West 26th Street, lofts of 1,400 to 1,650 sq ft go out as anything from a
   studio to a three-bedroom, and size-less one-bedroom ads would otherwise split away from the
   lofts' full listings.

Each step looks only at earlier ads, so a row's piece depends on its own ad and the ads before
it. The first piece keeps the unit's ID, and later pieces take the ID with "~1", "~2" and so on.

The fit runs v4 after every other rule, so the model reads each row's label unit from
analysis.label_units, or its unit from analysis.ledger_rows, after the unit ledger's splits. It
walks only the units holding two or more bedroom counts, as a unit with one count keeps a single
piece. It lists the rows of the later pieces, each with its label unit and its piece.
analysis.rows gives each row its piece, or its label unit, as `split_unit`, and the observations
take that as `unit_id`.
"""

import math

import pandas as pd
from sqlglot import exp
from sqlmesh import ExecutionContext, model

COLUMNS = {"listing_id": "VARCHAR", "unit_id": "VARCHAR", "split_unit": "VARCHAR"}
# v4 splits at a change of one bedroom or more.
BEDROOMS = 1


def pieces(rows: pd.DataFrame) -> list:
    """Each row's piece of its unit, 0 for the first, for rows with `unit`, `listing_id`,
    `bedrooms` and `square_feet`, sorted by unit, price date and listing ID."""
    found = []
    last_unit = None
    for unit, listing, beds, size in zip(
        rows.unit.tolist(),
        rows.listing_id.tolist(),
        rows.bedrooms.to_numpy(dtype=float).tolist(),
        rows.square_feet.to_numpy(dtype=float).tolist(),
    ):
        if unit != last_unit:
            last_unit = unit
            piece_of, piece, count, last_beds, last_size, seen = (
                {},
                0,
                1,
                math.nan,
                math.nan,
                {},
            )
        if listing not in piece_of:
            change = abs(beds - last_beds)
            held = change < 2 and math.isnan(last_size) and not math.isnan(size)
            if change >= BEDROOMS and not held:
                if beds in seen:
                    piece = seen[beds]
                else:
                    piece, count = count, count + 1
            piece_of[listing] = piece
            if not math.isnan(beds):
                seen[beds] = piece
                last_beds, last_size = beds, size
        found.append(piece_of[listing])
    return found


@model(
    "analysis.history_splits",
    kind="FULL",
    columns=COLUMNS,
    grain="listing_id",
    audits=[
        ("unique_values", {"columns": [exp.column("listing_id")]}),
        ("not_null", {"columns": [exp.column(name) for name in COLUMNS]}),
    ],
    description="Each row of analysis.ledger_rows the history rule moves out of the first piece of its label unit, with its label unit and its piece.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    rows_table = context.resolve_table("analysis.ledger_rows")
    labels_table = context.resolve_table("analysis.label_units")
    rows = context.fetchdf(
        f"""WITH r AS (
            SELECT r.listing_id, coalesce(l.label_unit, r.unit_id) AS unit, r.price_at,
                r.bedrooms, r.square_feet
            FROM {rows_table} r LEFT JOIN {labels_table} l USING (unit_id)
        )
        SELECT unit, listing_id, bedrooms, square_feet FROM r
        WHERE unit IN (SELECT unit FROM r GROUP BY unit HAVING count(DISTINCT bedrooms) > 1)
        ORDER BY unit, price_at, listing_id"""
    )
    if rows.empty:
        return
    rows["piece"] = pieces(rows)
    found = rows[rows.piece > 0]
    if found.empty:
        return
    yield pd.DataFrame(
        {
            "listing_id": found.listing_id.to_numpy(),
            "unit_id": found.unit.to_numpy(),
            "split_unit": found.unit + "~" + found.piece.astype(str),
        }
    )
