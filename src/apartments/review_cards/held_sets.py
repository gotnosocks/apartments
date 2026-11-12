"""The `held-sets` queue: the corrections held back for want of backing.

`config/reviews/ledger-held-*.jsonl` holds sets that a rule proposed from the ad's text alone
and the ledger move of 2026-10-16 kept out of the ledger, since a quote from the ad does not
back a set on its own (Ben, 2026-10-15). The producer reads each held line and drops it when:

- the corrections ledger in this checkout already has an entry in force for the listing;
- the build no longer keeps the ad's row;
- the row's recorded values no longer match the line's `when`, so the set would not apply.

For each remaining line the producer looks for the backing the line lacks, with the checks of
the `studio-beds` queue for a bedroom count and with the unit's other ads within 24 months for
baths. The card shows the held quote, the backing found and the unit's other ads. The proposal
is the held line itself with the backing found added to its evidence. Its `when` comes from the
row's record, for the period and every field the line sets. A bedroom card also offers the
other counts from studio to 4 bedrooms, and 5 when the quote names 5, without the quote in
their evidence. When two held lines set the same field of one ad, the card goes to the first in
the queue's order and the rest count as repeated.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common as c
from . import studio_beds as sb

QUEUE = "held-sets"
EXTRA = (
    "agree",
    "disagree",
    "audit_id",
    "rule",
    "unit_id",
    "evidence",
    "decided",
    "source",
)
ANSWERS = [
    {"code": "yes", "label": "Yes, set it", "key": "y", "applies": True},
    {"code": "no", "label": "The record is right", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
]
FIELDS = ("bedrooms", "full_baths", "half_baths")


def held_lines(reviews: Path) -> list[dict]:
    out = []
    for path in sorted(reviews.glob("ledger-held-*.jsonl")):
        for n, text in enumerate(path.read_text().splitlines(), 1):
            if text.strip():
                line = json.loads(text)
                line["_held"] = f"{path.name}:{n}"
                out.append(line)
    return out


def matches(line: dict, record: dict | None) -> bool:
    """True when the row still holds the values the line's `when` gives."""
    if record is None:
        return False
    return all(
        key == "period"
        and record["period"] == value
        or key != "period"
        and record.get(key) == c.whole(value)
        for key, value in line.get("when", {}).items()
    )


def baths_backing(ad: dict, line: dict, mates: list[dict]) -> list[dict]:
    """The unit's other ads within 24 months coding the baths the line sets."""
    want = {k: c.whole(v) for k, v in line["set"].items()}
    hits = [
        x
        for x in mates
        if x["unit_id"] == ad["unit_id"]
        and x["listing_id"] != ad["listing_id"]
        and abs(x["on_day"] - ad["on_day"]) <= sb.WINDOW
        and all(c.whole(x[k]) == v for k, v in want.items())
    ]
    if not hits:
        return []
    return [
        {
            "kind": "other_ad",
            "listings": [x["listing_id"] for x in hits],
            "detail": (
                f"The unit's ads {', '.join(x['listing_id'] for x in hits)} code "
                f"{baths_text(want)}."
            ),
        }
    ]


def baths_text(values: dict) -> str:
    full = values.get("full_baths")
    half = values.get("half_baths")
    parts = [f"{full} full bath{'s' if full != 1 else ''}"] if full is not None else []
    if half is not None:
        parts.append(f"{half} half bath{'s' if half != 1 else ''}")
    return " and ".join(parts)


def recorded_when(changes: dict, record: dict) -> dict:
    """The `when` of a set: the record's period and its value of each field the set sets."""
    when = {k: None if record.get(k) is None else float(record[k]) for k in changes}
    return {**when, "period": record["period"]}


def change_text(changes: dict, record: dict) -> str:
    if "bedrooms" in changes:
        return (
            f"bedrooms from {c.beds_text(record.get('bedrooms'))} to "
            f"{c.beds_text(changes['bedrooms'])}"
        )
    before = {k: c.whole(record.get(k)) for k in changes}
    after = {k: c.whole(v) for k, v in changes.items()}
    return f"baths from {baths_text(before)} to {baths_text(after)}"


def proposal(
    line: dict, record: dict, items: list[dict], change: dict | None = None
) -> dict:
    out = {k: v for k, v in line.items() if k not in EXTRA and not k.startswith("_")}
    if change is not None:
        out["set"] = change
    out["when"] = recorded_when(out["set"], record)
    quotes = [e for e in line.get("evidence", []) if e["kind"] in ("ad_text", "read")]
    return {
        "ledger": "corrections",
        "line": out,
        "evidence": (quotes if change is None else []) + items,
        "summary": f"Set the ad's {change_text(out['set'], record)}.",
    }


def build(sources: c.Sources) -> tuple[dict, list[dict], dict]:
    con = c.connect(sources)
    live = c.live_entries(sources.ledger)
    lines = held_lines(sources.reviews)
    ads = c.ads_by_ids(con, [line["listing_id"] for line in lines])
    dropped = {"in force": 0, "not kept": 0, "changed since": 0, "repeated": 0}
    kept = []
    for line in lines:
        ad = ads.get(str(line["listing_id"]))
        if str(line["listing_id"]) in live:
            dropped["in force"] += 1
        elif ad is None or ad["fate"] != "kept" or ad.get("row_period") is None:
            dropped["not kept"] += 1
        elif not matches(line, c.record_of(ad)):
            dropped["changed since"] += 1
        else:
            kept.append((line, ad))

    mates: dict[str, list[dict]] = {}
    for x in c.ads_in_buildings(con, {ad["building"] for _, ad in kept}):
        mates.setdefault(x["building"], []).append(x)
    nb_sizes = sb.size_medians(con, {ad["neighbourhood"] for _, ad in kept} - {None})
    drafts = []
    for line, ad in kept:
        group = mates.get(ad["building"], [])
        if "bedrooms" in line["set"]:
            found = sb.backing(ad, group, nb_sizes)
            items = found.get(c.whole(line["set"]["bedrooms"]), [])
        else:
            found, items = None, baths_backing(ad, line, group)
        drafts.append((line, ad, found, items))
    drafts.sort(
        key=lambda d: (
            -len({i["kind"] for i in d[3]}),
            str(d[0]["listing_id"]),
            d[0]["_held"],
        )
    )
    raw = c.raw_records(
        con,
        {
            x["listing_id"]
            for _, ad, *_ in drafts
            for x in mates.get(ad["building"], [])
            if x["unit_id"] == ad["unit_id"]
        },
    )
    cards = []
    ids = set()
    for d in drafts:
        made = card(*d, mates, raw)
        if made["id"] in ids:
            dropped["repeated"] += 1
        else:
            ids.add(made["id"])
            cards.append(made)
    meta = c.meta(
        QUEUE,
        "held_sets",
        title="Corrections waiting for backing",
        summary=(
            f"{len(cards)} sets a rule proposed from the ad's text, held out of the ledger until "
            "something besides the text backs them."
        ),
        question="Is the proposed value right?",
        help=(
            "The quote only nominates. Look at the floor plan, the photos and the unit's other "
            "ads. For bedrooms, pick another count below if the apartment has a different number."
        ),
        answers=ANSWERS,
        dropped=dropped,
    )
    return meta, cards, dropped


def card(line, ad, found, items, mates, raw) -> dict:
    lid = ad["listing_id"]
    record = c.record_of(ad)
    field = "bedrooms" if "bedrooms" in line["set"] else "baths"
    rows = [
        {"label": i["kind"].replace("_", " "), "value": i["detail"], "mark": "good"}
        for i in items
    ]
    if found:
        target = c.whole(line["set"]["bedrooms"])
        for k in sorted(set(found) - {target}):
            rows += [
                {
                    "label": f"{i['kind'].replace('_', ' ')} ({c.beds_text(k)})",
                    "value": i["detail"],
                }
                for i in found[k]
            ]
    if not rows:
        rows = [{"label": "Backing", "value": "none found", "mark": "bad"}]
    rows.append({"label": "Held by", "value": f"{line.get('rule')} ({line['_held']})"})
    others = [
        x
        for x in mates.get(ad["building"], [])
        if x["unit_id"] == ad["unit_id"] and x["listing_id"] != lid
    ]
    quotes = [e.get("quote") or e.get("detail") for e in line.get("evidence", [])]
    blocks = [
        {"type": "facts", "title": "Backing for the change", "rows": rows},
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
        {
            "type": "text",
            "title": "The words the rule read",
            "body": " / ".join(q for q in quotes if q),
            "nominating": True,
        }
    )
    options = []
    if found is not None:
        target = c.whole(line["set"]["bedrooms"])
        current = (
            c.whole(record["bedrooms"]) if record.get("bedrooms") is not None else None
        )
        names = set().union(*(sb.counts_named(q) for q in quotes if q))
        options = [
            {
                "code": f"beds-{k}",
                "label": "studio" if k == 0 else f"{k} bedroom{'s' if k > 1 else ''}",
                "proposal": proposal(
                    line, record, found.get(k, []), {"bedrooms": float(k)}
                ),
            }
            for k in sorted(set(range(5)) | ({5} & names))
            if k not in (target, current)
        ]
    prop = proposal(line, record, items)
    return {
        "id": f"listing:{lid}:{field}",
        "title": f"{c.address(ad['building'])}: {c.label(ad['page']) or '?'}",
        "subtitle": " · ".join(
            x
            for x in (
                ad.get("neighbourhood"),
                c.beds_text(ad["bedrooms"]),
                c.money(ad["latest_ask"]),
                c.day(ad["on_day"]),
            )
            if x
        ),
        "claim": (
            f"A rule read the ad's text as saying the "
            f"{change_text(prop['line']['set'], record)}."
        ),
        "proposal": prop,
        "options": options,
        "blocks": blocks,
    }


def main(out: Path, sources: c.Sources) -> Path:
    meta, cards, _ = build(sources)
    return c.write_queue(out, meta, cards)
