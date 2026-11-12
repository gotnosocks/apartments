"""The `outliers` queue: the held-out ads the served model misses most.

The site's diagnostics (`<site>/diagnostics/ads.parquet`) give each held-out ad the model's
predictive median, its 80% range and the miss in predictive standard deviations. The producer
takes the ads with the largest absolute miss, skipping each ad the build already leaves out or
the ledger in this checkout already sets or excludes, since a reading of those is done. Each
card shows the ad next to the model's numbers, the unit's other ads and up to eight ads of the
building with the same bedroom count from the two years before it, so Ben can say whether the
record looks right. A wrong record goes through the site's "Something else is wrong" answer,
with a typed fix, so this queue proposes nothing itself.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from . import common as c

QUEUE = "outliers"
SIZE = 300
COMPARABLES = 8
ANSWERS = [
    {"code": "right", "label": "Data looks right", "key": "r"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
]


def candidates(sources: c.Sources, con, size: int) -> list[dict]:
    """The held-out ads with the largest absolute miss, one row per ad, before the skips. An ad
    in both the latest split and the market keeps its larger miss."""
    path = sources.diagnostics / "ads.parquet"
    rows = con.execute(
        f"""
        SELECT * FROM read_parquet('{path}')
        WHERE miss IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY listing_id ORDER BY abs(miss) DESC) = 1
        ORDER BY abs(miss) DESC, listing_id
        LIMIT {int(size)}
        """
    )
    names = [d[0] for d in rows.description]
    return [dict(zip(names, r, strict=True)) for r in rows.fetchall()]


def settled(ad: dict | None, live: dict) -> bool:
    """True for an ad a reading has already settled: out of the build's rows, or set or
    excluded by an entry in force."""
    if ad is None:
        return True
    return (
        ad["fate"] != "kept"
        or bool(ad["exclusion_reasons"])
        or bool(ad["ledger_entries"])
        or str(ad["listing_id"]) in live
    )


def build(sources: c.Sources, size: int = SIZE) -> tuple[dict, list[dict]]:
    con = c.connect(sources)
    live = c.live_entries(sources.ledger)
    pool = candidates(sources, con, size * 3)
    ads = c.ads_by_ids(con, [r["listing_id"] for r in pool])
    chosen = [r for r in pool if not settled(ads.get(str(r["listing_id"])), live)][
        :size
    ]

    # The unit's other ads, and the building's ads with the same bedroom count from the two
    # years before the ad.
    by_building: dict[str, list[dict]] = {}
    for x in c.ads_in_buildings(
        con, {ads[str(r["listing_id"])]["building"] for r in chosen}
    ):
        by_building.setdefault(x["building"], []).append(x)
    others: dict[str, list[dict]] = {}
    peers: dict[str, list[dict]] = {}
    for row in chosen:
        lid = str(row["listing_id"])
        ad = ads[lid]
        mates = by_building.get(ad["building"], [])
        others[lid] = [
            x for x in mates if x["unit_id"] == ad["unit_id"] and x["listing_id"] != lid
        ]
        start = ad["on_day"] - timedelta(days=730)
        near = [
            x
            for x in mates
            if x["unit_id"] != ad["unit_id"]
            and x["bedrooms"] == ad["bedrooms"]
            and x["fate"] == "kept"
            and start <= x["on_day"] <= ad["on_day"]
        ]
        peers[lid] = near[-COMPARABLES:]
    wanted = set(ads) | {
        x["listing_id"]
        for group in (others, peers)
        for xs in group.values()
        for x in xs
    }
    raw = c.raw_records(con, wanted)

    cards = [
        card(row, ads[str(row["listing_id"])], others, peers, raw) for row in chosen
    ]
    return (
        c.meta(
            QUEUE,
            "outliers",
            title="Ads the model misses most",
            summary=(
                f"The {len(cards)} held-out ads farthest from the served model's prediction, "
                "with the unit's other ads and the building's ads of the same size."
            ),
            question="Does this ad's record look right?",
            help=(
                "Look at the bedrooms, baths, size and price against the photos, the floor plan "
                "and the unit's other ads. If something in the record is wrong, use Something "
                "else is wrong and type the fix."
            ),
            answers=ANSWERS,
        ),
        cards,
    )


def card(row: dict, ad: dict, others: dict, peers: dict, raw: dict) -> dict:
    lid = str(row["listing_id"])
    over = row["miss"] > 0
    facts = [
        {"label": "Ask", "value": c.money(row["ask"])},
        {"label": "Model median", "value": c.money(row["model_median"])},
        {
            "label": "Model 80% range",
            "value": f"{c.money(row['model_lo80'])} to {c.money(row['model_hi80'])}",
            "mark": "bad",
        },
        {
            "label": "Miss",
            "value": f"{row['miss']:+.1f} sd ({'over' if over else 'under'} the model)",
        },
        {
            "label": "Model's basis",
            "value": f"{row['basis']}, from {row['source']} fit",
        },
    ]
    if row.get("prev_ask") is not None and row["prev_ask"] == row["prev_ask"]:
        facts.append(
            {
                "label": "Unit's previous ad",
                "value": (
                    f"{c.money(row['prev_ask'])} on {c.day(row['prev_day'])}, "
                    f"{c.beds_text(row['prev_bedrooms'])}"
                ),
            }
        )
    blocks = [
        {"type": "facts", "title": "Ask against the model", "rows": facts},
        {
            "type": "ads",
            "title": "The ad",
            "ads": [c.card_ad(ad, raw.get(lid), photos=12, mark="candidate")],
        },
    ]
    if others[lid]:
        blocks.append(
            {
                "type": "ads",
                "title": "The unit's other ads",
                "ads": [
                    c.card_ad(x, raw.get(x["listing_id"]), photos=4)
                    for x in others[lid]
                ],
            }
        )
    if peers[lid]:
        blocks.append(
            {
                "type": "ads",
                "title": f"Other {c.beds_text(ad['bedrooms'])} ads in the building, two years before",
                "ads": [
                    c.card_ad(
                        x, raw.get(x["listing_id"]), photos=1, plans=1, text=False
                    )
                    for x in peers[lid]
                ],
            }
        )
    unit = c.label(ad["page"]) or "?"
    return {
        "id": f"listing:{lid}",
        "title": f"{row.get('address') or c.address(ad['building'])}: {unit}",
        "subtitle": " · ".join(
            x
            for x in (
                row.get("neighbourhood"),
                c.beds_text(ad["bedrooms"]),
                c.money(row["ask"]),
                c.day(row["day"]),
            )
            if x
        ),
        "claim": (
            f"The ask of {c.money(row['ask'])} is {abs(row['miss']):.1f} predictive sd "
            f"{'above' if over else 'below'} the model's median of {c.money(row['model_median'])}."
        ),
        "blocks": blocks,
    }


def main(out: Path, sources: c.Sources, size: int = SIZE) -> Path:
    meta, cards = build(sources, size)
    return c.write_queue(out, meta, cards)
