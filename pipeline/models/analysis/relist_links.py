"""analysis.relist_links: the pairs of analysis.relist_pairs, each with the outcome of joining
their unit pages.

A relist unit is a set of unit pages of a lot, all for the same apartment. The model starts with
each unit page as its own relist unit and takes the pairs from the closest in time outward:
ordered by the absolute gap, then by the unit pages' and ads' IDs, so the outcome is the same in
every build. For each pair it finds the relist unit of each page:

- `same`: an earlier pair already put both pages in one relist unit.
- `layout`: a page of either relist unit holds a kept ad with a bedroom count other than the
  pair's. Such a page already mixes apartments, often under a broker who moves one ad from label
  to label along a floor, and joining it would chain those apartments together.
- `clash`: two pages of the two relist units had ads on the market together for more than 7
  days. An apartment can't be on the market twice at once, so the model leaves them apart.
- `joined`: otherwise it joins the two relist units, under the lesser unit page ID.

To find a clash, the model gives each unit page the spans of its kept ads, from the day each
came on the market to the day it went off, or to the build's as-of day for an ad still on.
Overlaps of up to 7 days allow for a broker who posts the new ad before taking the old one down.
`relist_unit` and `next_relist_unit` give the relist units of the two pages after every pair,
and analysis.relist_units lists them.
"""

from collections import defaultdict

import pandas as pd
from sqlglot import exp
from sqlmesh import ExecutionContext, model

COLUMNS = {
    "bbl": "VARCHAR",
    "listing_id": "VARCHAR",
    "next_listing_id": "VARCHAR",
    "unit_id": "VARCHAR",
    "next_unit_id": "VARCHAR",
    "gap": "INTEGER",
    "photos": "BIGINT",
    "outcome": "VARCHAR",
    "relist_unit": "VARCHAR",
    "next_relist_unit": "VARCHAR",
}
# Days two ads of one apartment may share on the market.
OVERLAP = 7


def link(pairs, spans, bedrooms):
    """The outcome of each pair of `pairs`, in its order, and the relist unit of each unit page.
    `pairs` gives (unit_id, next_unit_id) tuples, `spans` maps a unit page to the (first, last)
    days of its ads, as day numbers, and `bedrooms` maps a unit page to the set of its ads'
    bedroom counts."""
    parent, members = {}, {}

    def find(unit):
        while parent.get(unit, unit) != unit:
            unit = parent[unit]
        return unit

    def layouts(unit):
        return set().union(*(bedrooms.get(u, set()) for u in members.get(unit, [unit])))

    def clash(a, b):
        return any(
            min(end, other_end) - max(start, other_start) > OVERLAP
            for u in members.get(a, [a])
            for v in members.get(b, [b])
            for start, end in spans.get(u, [])
            for other_start, other_end in spans.get(v, [])
        )

    outcomes = []
    for unit, next_unit in pairs:
        a, b = find(unit), find(next_unit)
        if a == b:
            outcomes.append("same")
        elif len(layouts(a) | layouts(b)) > 1:
            outcomes.append("layout")
        elif clash(a, b):
            outcomes.append("clash")
        else:
            outcomes.append("joined")
            low, high = min(a, b), max(a, b)
            parent[high] = low
            members[low] = members.get(low, [low]) + members.pop(high, [high])
    return outcomes, find


@model(
    "analysis.relist_links",
    kind="FULL",
    columns=COLUMNS,
    grain=["listing_id", "next_listing_id"],
    audits=[
        (
            "unique_combination_of_columns",
            {"columns": [exp.column("listing_id"), exp.column("next_listing_id")]},
        ),
        (
            "not_null",
            {
                "columns": [
                    exp.column(name)
                    for name in (
                        "listing_id",
                        "next_listing_id",
                        "outcome",
                        "relist_unit",
                    )
                ]
            },
        ),
    ],
    description="The pairs of analysis.relist_pairs, each with the outcome of joining their unit pages and the relist units they end in.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    pairs = context.resolve_table("analysis.relist_pairs")
    kept = context.resolve_table("analysis.kept")
    market = context.resolve_table("ads.market")
    links = context.fetchdf(
        f"""SELECT bbl, listing_id, next_listing_id, unit_id, next_unit_id, gap, photos
        FROM {pairs}
        ORDER BY abs(gap), unit_id, next_unit_id, listing_id, next_listing_id"""
    )
    if links.empty:
        return
    spans, bedrooms = defaultdict(list), defaultdict(set)
    for unit, beds, first, last in context.fetchdf(
        f"""WITH units AS (
            SELECT unit_id FROM {pairs} UNION SELECT next_unit_id FROM {pairs}
        )
        SELECT k.unit_id, k.bedrooms, m.on_day - DATE '1970-01-01' AS first,
            coalesce(m.off_day, m.as_of) - DATE '1970-01-01' AS last
        FROM {kept} k
        LEFT JOIN {market} m USING (listing_id)
        SEMI JOIN units USING (unit_id)"""
    ).itertuples(index=False):
        bedrooms[unit].add(float(beds))
        if not pd.isna(first):
            spans[unit].append((int(first), int(last)))
    outcomes, find = link(zip(links.unit_id, links.next_unit_id), spans, bedrooms)
    links["outcome"] = outcomes
    links["relist_unit"] = links.unit_id.map(find)
    links["next_relist_unit"] = links.next_unit_id.map(find)
    yield pd.DataFrame(links, columns=list(COLUMNS))
