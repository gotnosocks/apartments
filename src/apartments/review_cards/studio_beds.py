"""The `studio-beds` queue: studio-coded rows whose text names two or more bedrooms.

The rows file codes about 334,000 kept rows as studios. For each one the producer reads the
description of the ad's latest record and keeps the ads whose text names two to five bedrooms
("2 bedroom", "three-bed", "3BR") and never says "studio". Of a sample of 40 such ads read for
the building model, 25 were whole apartments and 11 studios (`docs/TODO.md`), so the text only
nominates. A bedroom count changes only with independent backing (Ben, 2026-10-15), and the
producer looks for three kinds of it. Each check can back any count, a studio included, and the
card lists what turns up for the other counts too, since the unit's studio-coded ads count
against the text:

- `other_ad`: another ad of the same unit within 24 months coding that count;
- `stated_size`: the ad's coded size lies closer to the median size of that count than of any
  other count, among the building's sized ads (three or more of the count) or else the
  neighbourhood's;
- `line_units`: two or more ads of the building's other units in the same line (the same
  letters after the floor number), at least two thirds of them coding that count.

Cards with the most kinds of backing for the named count come first. The proposal sets the
named count; the options set 1 to 4 bedrooms, each with the backing found for its count.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from statistics import median

from . import common as c

QUEUE = "studio-beds"
WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}
# DuckDB's RE2 screen, and the same pattern for Python to pull the counts out.
PATTERN = (
    r"\b(two|three|four|five|2|3|4|5)[\s-]*"
    r"(bed|beds|bedroom|bedrooms|br|bd|bdrm|bdrms)\b"
)
NAMED = re.compile(PATTERN, re.IGNORECASE)
COUNTS = (1, 2, 3, 4)
WINDOW = timedelta(days=730)
LINE = re.compile(r"(\d+)([a-z]+)")
ANSWERS = [
    {"code": "yes", "label": "Yes, set it", "key": "y", "applies": True},
    {"code": "no", "label": "It's a studio", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
]


def screen(con) -> list[tuple[str, str]]:
    """The studio-coded kept rows whose latest record's text names two to five bedrooms and
    never says studio, as (listing ID, description)."""
    return con.execute(
        f"""
        WITH studio AS (SELECT listing_id::BIGINT AS lid FROM rows WHERE bedrooms = 0),
        txt AS (
            SELECT r.listing_id AS lid,
                   arg_max(json_extract_string(r.raw_listing_json, '$.description'),
                           r.last_collected_at) AS d
            FROM records r SEMI JOIN studio s ON r.listing_id = s.lid
            GROUP BY 1)
        SELECT lid::VARCHAR, d FROM txt
        WHERE regexp_matches(lower(d), '{PATTERN}') AND NOT contains(lower(d), 'studio')
        ORDER BY lid
        """
    ).fetchall()


def named(text: str) -> tuple[int, str]:
    """The bedroom count the text names most often (the smaller on a tie), with the words
    around its first mention."""
    text = c.plain(text)
    found = [
        (WORDS.get(m.group(1).lower()) or int(m.group(1)), m)
        for m in NAMED.finditer(text)
    ]
    tally = Counter(n for n, _ in found)
    count = min(tally, key=lambda n: (-tally[n], n))
    first = next(m for n, m in found if n == count)
    start = max(0, text.rfind(" ", 0, max(0, first.start() - 60)) + 1)
    end = text.find(" ", first.end() + 60)
    quote = text[start : end if end > 0 else len(text)].strip()
    return count, quote


def line_of(unit: str | None) -> tuple[int, str] | None:
    m = LINE.fullmatch((unit or "").lower())
    return (int(m.group(1)), m.group(2)) if m else None


def size_medians(con, neighbourhoods) -> dict:
    """Median coded size by neighbourhood and bedroom count, over kept ads."""
    con.execute("CREATE OR REPLACE TEMP TABLE wanted_nb (n VARCHAR)")
    con.executemany("INSERT INTO wanted_nb VALUES (?)", [[n] for n in neighbourhoods])
    rows = con.execute(
        """
        SELECT neighbourhood, bedrooms, median(square_feet), count(*)
        FROM ads
        WHERE fate = 'kept' AND square_feet > 100 AND bedrooms BETWEEN 0 AND 5
          AND neighbourhood IN (SELECT n FROM wanted_nb)
        GROUP BY 1, 2
        """
    ).fetchall()
    return {(n, c.whole(b)): (m, k) for n, b, m, k in rows if k >= 5}


def backing(ad: dict, mates: list[dict], nb_sizes: dict) -> dict[int, list[dict]]:
    """The backing found for each count, by count."""
    out: dict[int, list[dict]] = {}
    lid = ad["listing_id"]
    unit = c.label(ad["page"])

    own = [
        x
        for x in mates
        if x["unit_id"] == ad["unit_id"]
        and x["listing_id"] != lid
        and x["bedrooms"] is not None
        and abs(x["on_day"] - ad["on_day"]) <= WINDOW
    ]
    for k in sorted({c.whole(x["bedrooms"]) for x in own}):
        hits = [x for x in own if c.whole(x["bedrooms"]) == k]
        out.setdefault(k, []).append(
            {
                "kind": "other_ad",
                "listings": [x["listing_id"] for x in hits],
                "detail": (
                    f"The unit's ads {', '.join(x['listing_id'] for x in hits)} "
                    f"({', '.join(c.day(x['on_day'])[:7] for x in hits)}) code "
                    f"{c.beds_text(k)}."
                ),
            }
        )

    size = ad.get("square_feet")
    if size and size > 100:
        sized = [
            x for x in mates if x["fate"] == "kept" and (x["square_feet"] or 0) > 100
        ]
        by_count: dict[int, list[float]] = {}
        for x in sized:
            if x["bedrooms"] is not None and x["listing_id"] != lid:
                by_count.setdefault(c.whole(x["bedrooms"]), []).append(x["square_feet"])
        building = {k: median(v) for k, v in by_count.items() if len(v) >= 3}
        place, medians = "the building", building
        if 0 not in building or len(building) < 2:
            place = ad.get("neighbourhood") or "the neighbourhood"
            medians = {
                k: m
                for (n, k), (m, _) in nb_sizes.items()
                if n == ad.get("neighbourhood")
            }
        if 0 in medians and len(medians) >= 2:
            nearest = min(medians, key=lambda k: (abs(size - medians[k]), k))
            rest = ", ".join(
                f"{c.beds_text(k)} {m:,.0f}"
                for k, m in sorted(medians.items())
                if k != nearest
            )
            out.setdefault(nearest, []).append(
                {
                    "kind": "stated_size",
                    "detail": (
                        f"The ad gives {size:,.0f} sq ft, nearest the median "
                        f"{c.beds_text(nearest)} in {place} at {medians[nearest]:,.0f} "
                        f"(the other medians: {rest})."
                    ),
                }
            )

    line = line_of(unit)
    if line:
        floor, letters = line
        peers = [
            x
            for x in mates
            if x["fate"] == "kept"
            and x["bedrooms"] is not None
            and (other := line_of(c.label(x["page"])))
            and other[1] == letters
            and other[0] != floor
        ]
        tally = Counter(c.whole(x["bedrooms"]) for x in peers)
        for k, n in tally.items():
            if n >= 2 and n >= len(peers) * 2 / 3:
                hits = [x for x in peers if c.whole(x["bedrooms"]) == k][-10:]
                labels = sorted({c.label(x["page"]) for x in hits})
                out.setdefault(k, []).append(
                    {
                        "kind": "line_units",
                        "listings": [x["listing_id"] for x in hits],
                        "detail": (
                            f"{n} of the {len(peers)} kept ads of line {letters.upper()} on "
                            f"other floors ({', '.join(labels)}) code {c.beds_text(k)}."
                        ),
                    }
                )
    return out


def proposal(ad: dict, count: int, items: list[dict], quote: str) -> dict:
    record = c.record_of(ad)
    return {
        "ledger": "corrections",
        "line": {
            "change": "set",
            "listing_id": ad["listing_id"],
            "set": {"bedrooms": float(count)},
            "when": {"bedrooms": float(record["bedrooms"]), "period": record["period"]},
        },
        "evidence": [{"kind": "ad_text", "quote": quote}, *items],
        "summary": f"Set the ad's bedrooms from 0 to {count}.",
    }


def build(sources: c.Sources) -> tuple[dict, list[dict]]:
    con = c.connect(sources)
    live = c.live_entries(sources.ledger)
    found = [(lid, text) for lid, text in screen(con) if lid not in live]
    ads = c.ads_by_ids(con, [lid for lid, _ in found])
    found = [(lid, text) for lid, text in found if ads.get(lid, {}).get("row_period")]
    mates: dict[str, list[dict]] = {}
    for x in c.ads_in_buildings(con, {ads[lid]["building"] for lid, _ in found}):
        mates.setdefault(x["building"], []).append(x)
    nb_sizes = size_medians(
        con, {ads[lid]["neighbourhood"] for lid, _ in found} - {None}
    )

    drafts = []
    for lid, text in found:
        ad = ads[lid]
        count, quote = named(text)
        items = backing(ad, mates.get(ad["building"], []), nb_sizes)
        drafts.append((ad, count, quote, items))
    drafts.sort(
        key=lambda d: (
            -len({i["kind"] for i in d[3].get(d[1], [])}),
            -sum(len(i.get("listings", [])) for i in d[3].get(d[1], [])),
            d[0]["listing_id"],
        )
    )
    raw = c.raw_records(
        con,
        {
            x["listing_id"]
            for ad, *_ in drafts
            for x in mates.get(ad["building"], [])
            if x["unit_id"] == ad["unit_id"]
        },
    )
    cards = [
        card(ad, count, quote, items, mates, raw) for ad, count, quote, items in drafts
    ]
    return (
        c.meta(
            QUEUE,
            "studio_beds",
            title="Studios that may not be studios",
            summary=(
                f"{len(cards)} kept ads coded as studios whose text names two or more bedrooms "
                "and never says studio, with the backing found for each count."
            ),
            question="Does this apartment have the bedrooms its text names?",
            help=(
                "The text only nominates. Look at the floor plan, the size and the unit's other "
                "ads. Pick another count below if the apartment has a different number."
            ),
            answers=ANSWERS,
        ),
        cards,
    )


def card(ad, count, quote, items, mates, raw) -> dict:
    lid = ad["listing_id"]
    unit = c.label(ad["page"]) or "?"
    mine = items.get(count, [])
    rows = [
        {"label": i["kind"].replace("_", " "), "value": i["detail"], "mark": "good"}
        for i in mine
    ]
    for k in sorted(set(items) - {count}):
        rows += [
            {
                "label": f"{i['kind'].replace('_', ' ')} ({c.beds_text(k)})",
                "value": i["detail"],
            }
            for i in items[k]
        ]
    if not rows:
        rows = [{"label": "Backing", "value": "none found", "mark": "bad"}]
    building = mates.get(ad["building"], [])
    others = [
        x for x in building if x["unit_id"] == ad["unit_id"] and x["listing_id"] != lid
    ]
    blocks = [
        {
            "type": "facts",
            "title": f"Independent backing for {count} bedrooms",
            "rows": rows,
        },
        {
            "type": "ads",
            "title": "The ad",
            "ads": [c.card_ad(ad, raw.get(lid), photos=12, mark="candidate")],
        },
    ]
    if others:
        blocks.append(
            {
                "type": "ads",
                "title": "The unit's other ads",
                "ads": [
                    c.card_ad(x, raw.get(x["listing_id"]), photos=3) for x in others
                ],
            }
        )
    blocks.append(
        {"type": "text", "title": "The words", "body": quote, "nominating": True}
    )
    options = [
        {
            "code": f"beds-{k}",
            "label": f"{k} bedroom{'s' if k > 1 else ''}",
            "proposal": proposal(ad, k, items.get(k, []), quote),
        }
        for k in COUNTS
        if k != count
    ]
    return {
        "id": f"listing:{lid}:bedrooms",
        "title": f"{c.address(ad['building'])}: {unit}",
        "subtitle": " · ".join(
            x
            for x in (
                ad.get("neighbourhood"),
                "coded studio",
                c.money(ad["latest_ask"]),
                c.day(ad["on_day"]),
            )
            if x
        ),
        "claim": f"The ad is coded as a studio, and its text names {count} bedrooms.",
        "question": f"Is this a {count} bedroom apartment?",
        "proposal": proposal(ad, count, mine, quote),
        "options": options,
        "blocks": blocks,
    }


def main(out: Path, sources: c.Sources) -> Path:
    meta, cards = build(sources)
    return c.write_queue(out, meta, cards)
