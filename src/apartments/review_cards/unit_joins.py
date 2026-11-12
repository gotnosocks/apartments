"""The `unit-joins` queue: chains of ads the repost screen links across several unit labels.

The outlier sprint links ads it takes for one apartment taken down and posted again
(`<sprint>/C/links-final.parquet`, one row per link with its `chain_id`). Landlords reuse photos
and text across a line of apartments, so a link only nominates a join. Ben set the standard on
2026-11-12: a join needs a label that fails a test of being a real unit, by missing from the
city's records of an adequately recorded lot or by sitting outside the building's own grid of
floors and lines.

The producer reads the chains whose ads carry two or more labels of one building and skips the
ones the unit ledger already joins. For each building it gathers:

- every label ever advertised there, by floor, for the card's grid;
- the city's apartment numbers for the building's lot, from the sprint's pulls of HPD
  complaints and violations (`<sprint>/G/city/by-comp*.jsonl`, `by-viol.jsonl` and the per-lot
  `comp-<bbl>.json`), marshals' evictions (`evictions.json`) and the condo roll's unit lots
  (`condo/units.json` through `condo/pluto_condono.json`);
- PLUTO's residential units and floors, and HPD's legal class A count, for judging whether
  the records cover the building.

The producer drops the ads whose page the unit ledger already joins to another, since a page
takes part in one join at most, and skips a chain left with fewer than two labels. It also skips
a chain when two or more of its labels are in the city's records, as two recorded apartments
are two apartments. Photos, text and timing only nominate, so a card proposes a join only when
a label fails one of these tests:

- the label is missing from the city's records of a lot they cover well, meaning the records
  name at least 80% of the units PLUTO or HPD's legal class A count gives, or the lot has a
  condo unit roll (a `city_record` item);
- the label's floor lies above the lot's floors in PLUTO and HPD (a `city_record` item);
- no other label in the building or in the city's records uses the label's line, the letters
  after the floor number (a `line_units` item, with the ads of the label's floor).

A card with none of these asks the question alone, with no proposal, and its claim says which
test came up short. The proposal joins the chain's labels into the label with the most ads
among those the city records hold, or among all of them when the records hold none.

The sprint's own label test (`<sprint>/G/code/std.py`) is still running, so the queue covers
only the chains in the five buildings of the worked examples (`EXAMPLES`). Passing `examples=None`
to `build` takes every linked building.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import duckdb

from . import common as c
from .studio_beds import line_of

QUEUE = "unit-joins"
EXAMPLES = (
    "16-monitor-street-brooklyn",
    "1084-bedford-avenue-brooklyn",
    "226-east-59-street-new_york",
    "309-west-84-street-new_york",
    "1510-lex-carnegie-hill-place",
)
ANSWERS = [
    {"code": "yes", "label": "One apartment", "key": "y", "applies": True},
    {"code": "no", "label": "Different apartments", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
]
BOROUGHS = {"1": "MN", "2": "BX", "3": "BK", "4": "QN", "5": "SI"}
# The share of a lot's units the city's records must name for a missing label to count.
COVERED = 0.8
# Apartment numbers in city records that name no apartment.
JUNK = re.compile(
    r"^(BLDG|BUILDING|BASEMENT|BASEM|BASEME|BASE|BSMT|CELLAR|ROOF|HALL|LOBBY|STORE|PUBLIC|NA|"
    r"NONE|ALL|YARD|\d*(ST|ND|RD|TH)?FL(R|OOR|O|OO)?\d*|.*(FLOOR|FLOO|BATH|KIT|HALL|STAIR).*)$"
)


def norm(label: str | None) -> str:
    """A unit label as the city's records and StreetEasy's pages can both be matched on."""
    text = re.sub(r"[^A-Z0-9]", "", (label or "").upper())
    text = re.sub(r"^(APT|UNIT|APARTMENT|NO)(?=\w)", "", text)
    return text.lstrip("0")


def floor_of(ad: dict) -> str:
    if ad.get("label_floor") is not None:
        return str(c.whole(ad["label_floor"]))
    m = re.match(r"\D*(\d+)", c.label(ad["page"]) or "")
    return str(int(m.group(1))) if m else "?"


def chains(con, links: Path, examples) -> dict[str, list[str]]:
    """Each chain's listing IDs, for the chains in the wanted buildings."""
    where = ""
    if examples is not None:
        names = ", ".join(f"'{b}'" for b in examples)
        where = f"WHERE a.building IN ({names})"
    rows = con.execute(
        f"""
        WITH l AS (
            SELECT chain_id, earlier::VARCHAR AS lid FROM read_parquet('{links}')
            UNION SELECT chain_id, later::VARCHAR FROM read_parquet('{links}'))
        SELECT l.chain_id::VARCHAR, list(DISTINCT l.lid ORDER BY l.lid)
        FROM l JOIN ads a ON a.listing_id = l.lid {where}
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    return dict(rows)


def lots(sources: c.Sources, buildings: set[str], con) -> dict[str, str]:
    """The tax lot of each building slug, from the pipeline's building lots."""
    ids = dict(
        con.execute(
            "SELECT DISTINCT building, building_id::VARCHAR FROM ads WHERE building IN "
            "(SELECT unnest(?))",
            [sorted(buildings)],
        ).fetchall()
    )
    with duckdb.connect(str(sources.state), read_only=True) as state:
        found = dict(
            state.execute(
                "SELECT building_id::VARCHAR, bbl FROM buildings.lots "
                "WHERE building_id::VARCHAR IN (SELECT unnest(?))",
                [sorted(ids.values())],
            ).fetchall()
        )
    return {b: found[i] for b, i in ids.items() if found.get(i)}


def city_labels(
    sources: c.Sources, bbls: set[str], con
) -> dict[str, dict[str, set[str]]]:
    """The apartment numbers each source of city records holds for each lot, normalized."""
    city = sources.sprint / "G" / "city"
    out: dict[str, dict[str, set[str]]] = {b: {} for b in bbls}

    def add(bbl, source, label):
        n = norm(label)
        if bbl in out and n and not JUNK.match(n):
            out[bbl].setdefault(source, set()).add(n)

    wanted = sorted(bbls)
    for name in (
        "by-comp.jsonl",
        "by-comp-b.jsonl",
        "by-comp-c.jsonl",
        "by-viol.jsonl",
    ):
        path = city / name
        if path.exists():
            source = "HPD violations" if "viol" in name else "HPD complaints"
            for bbl, apt in con.execute(
                f"SELECT bbl::VARCHAR, apartment::VARCHAR FROM read_json_auto('{path}', "
                "format='newline_delimited') WHERE bbl::VARCHAR IN (SELECT unnest(?))",
                [wanted],
            ).fetchall():
                add(bbl, source, apt)
    for bbl in wanted:
        path = city / f"comp-{bbl}.json"
        if path.exists():
            for r in json.loads(path.read_text()):
                add(bbl, "HPD complaints", r.get("apartment"))
    if (city / "evictions.json").exists():
        for r in json.loads((city / "evictions.json").read_text()):
            add(
                (r.get("bbl") or "")[:10],
                "marshals' evictions",
                r.get("eviction_apt_num"),
            )
    condo = city / "condo"
    if (condo / "units.json").exists():
        bill = {
            (r["borocode"], int(r["condono"])): r["bbl"][:10]
            for r in json.loads((condo / "pluto_condono.json").read_text())
        }
        for r in json.loads((condo / "units.json").read_text()):
            bbl = bill.get((r["boro"], int(r["condo_number"]) % 100000))
            add(bbl, "condo unit lots", r.get("aptno"))
    return out


def lot_counts(sources: c.Sources, bbls: set[str]) -> dict[str, dict]:
    """PLUTO's residential units and floors and HPD's legal class A apartments, by lot."""
    out: dict[str, dict] = {b: {} for b in bbls}
    with duckdb.connect(str(sources.state), read_only=True) as state:
        for bbl, units, floors in state.execute(
            """
            SELECT left(bbl, 10), arg_max(unitsres, release), arg_max(numfloors, release)
            FROM city.pluto WHERE left(bbl, 10) IN (SELECT unnest(?)) GROUP BY 1
            """,
            [sorted(bbls)],
        ).fetchall():
            out[bbl]["pluto_units"] = c.whole(float(units)) if units else None
            out[bbl]["pluto_floors"] = c.whole(float(floors)) if floors else None
    city = sources.sprint / "G" / "city"
    for bbl in bbls:
        path = city / f"bldg-{bbl}.json"
        if path.exists():
            rows = json.loads(path.read_text())
            out[bbl]["legal_a"] = sum(int(r.get("legalclassa") or 0) for r in rows)
            out[bbl]["stories"] = max(
                (int(r.get("legalstories") or 0) for r in rows), default=0
            )
    return out


def years(ads: list[dict]) -> str:
    first = min(c.day(x["on_day"])[:4] for x in ads)
    last = max(c.day(x["on_day"])[:4] for x in ads)
    return first if first == last else f"{first}-{last}"


def grid(building_ads: list[dict], chain_labels: set[str], known: set[str]) -> dict:
    by_label: dict[str, list[dict]] = {}
    for x in building_ads:
        if c.label(x["page"]):
            by_label.setdefault(c.label(x["page"]), []).append(x)
    floors: dict[str, list[dict]] = {}
    for lab, xs in by_label.items():
        mark = (
            "candidate"
            if lab in chain_labels
            else "city"
            if norm(lab) in known
            else "oneoff"
            if len(xs) == 1
            else ""
        )
        cell = {"label": lab, "ads": len(xs), "years": years(xs)}
        if mark:
            cell["mark"] = mark
        floors.setdefault(floor_of(xs[0]), []).append(cell)

    def order(f):
        return (0, int(f)) if f.isdigit() else (1, f)

    return {
        "type": "grid",
        "title": "Labels ever advertised in the building",
        "floors": [
            {"floor": f, "cells": sorted(floors[f], key=lambda x: x["label"])}
            for f in sorted(floors, key=order)
        ],
    }


def spans(labels: set[str]) -> str:
    return ", ".join(sorted(labels, key=lambda x: (len(x), x))) if labels else "none"


def build(sources: c.Sources, examples=EXAMPLES) -> tuple[dict, list[dict]]:
    con = c.connect(sources)
    joined = c.live_unit_pages(sources.ledger / "units")
    found = chains(con, sources.sprint / "C" / "links-final.parquet", examples)
    ads = c.ads_by_ids(con, {lid for ids in found.values() for lid in ids})
    groups = []
    for chain_id, ids in found.items():
        xs = sorted(
            (ads[i] for i in ids if i in ads),
            key=lambda x: (x["on_day"], x["listing_id"]),
        )
        if len({x["building"] for x in xs}) != 1:
            continue
        building = xs[0]["building"]
        xs = [x for x in xs if x["page"] and f"{building}/{slug(x)}" not in joined]
        if len({slug(x) for x in xs}) < 2:
            continue
        groups.append((chain_id, building, xs))

    buildings = {b for _, b, _ in groups}
    mates: dict[str, list[dict]] = {}
    for x in c.ads_in_buildings(con, buildings):
        mates.setdefault(x["building"], []).append(x)
    lot = lots(sources, buildings, con)
    records = city_labels(sources, set(lot.values()), con)
    counts = lot_counts(sources, set(lot.values()))
    raw = c.raw_records(con, {x["listing_id"] for _, _, xs in groups for x in xs})

    cards = []
    skipped = 0
    for chain_id, building, xs in groups:
        bbl = lot.get(building)
        made = card(chain_id, building, xs, mates[building], bbl, records, counts, raw)
        if made is None:
            skipped += 1
        else:
            cards.append(made)
    ordered = sorted(cards, key=lambda x: ("proposal" not in x, x["id"]))
    return (
        c.meta(
            QUEUE,
            "unit_joins",
            title="One apartment under several labels?",
            summary=(
                f"{len(ordered)} chains of ads the repost screen links across unit labels, with "
                "the building's labels and city records."
            ),
            question="Are these labels one apartment?",
            help=(
                "Join only when a label fails a test of being a real unit: not in city records, "
                "or off the building's grid. Shared photos and text only nominate."
            ),
            answers=ANSWERS,
            dropped={"two or more labels in city records": skipped},
            scope="the five worked examples"
            if examples is not None
            else "every linked building",
        ),
        ordered,
    )


def slug(ad: dict) -> str:
    return ad["page"].rstrip("/").rsplit("/", 1)[-1]


def off_grid(
    labels: set[str], building_ads: list[dict], known: set[str], floors: int | None
) -> dict[str, str]:
    """The labels outside the building's grid, each with the reason."""
    out = {}
    lines = {
        line[1]
        for lab in {c.label(x["page"]) for x in building_ads} - labels
        if (line := line_of(lab))
    } | {line[1] for lab in known if (line := line_of(lab))}
    for lab in sorted(labels):
        line = line_of(lab)
        if line is None:
            continue
        if floors and line[0] > floors:
            out[lab] = f"floor {line[0]} lies above the lot's {floors} floors"
        elif line[1] not in lines:
            out[lab] = (
                f"no other label in the building or the city's records uses line "
                f"{line[1].upper()}"
            )
    return out


def card(
    chain_id, building, xs, building_ads, bbl, records, counts, raw
) -> dict | None:
    by_label = Counter(c.label(x["page"]) for x in xs)
    labels = set(by_label)
    held = records.get(bbl, {}) if bbl else {}
    known = set().union(*held.values()) if held else set()
    in_city = {lab for lab in labels if norm(lab) in known}
    if len(in_city) >= 2:
        return None
    missing = labels - in_city
    pool = in_city or labels
    ever = Counter(c.label(x["page"]) for x in building_ads)
    target = max(pool, key=lambda lab: (ever[lab], -len(lab), lab))
    rest = sorted(labels - {target})

    lot = counts.get(bbl, {})
    facts = [{"label": "Tax lot", "value": bbl or "not found"}]
    if lot.get("pluto_units") is not None:
        facts.append(
            {"label": "PLUTO residential units", "value": str(lot["pluto_units"])}
        )
    if lot.get("pluto_floors"):
        facts.append({"label": "PLUTO floors", "value": str(lot["pluto_floors"])})
    if lot.get("legal_a") is not None:
        facts.append(
            {
                "label": "HPD legal class A apartments",
                "value": f"{lot['legal_a']} on {lot['stories']} stories",
            }
        )
    for source in (
        "condo unit lots",
        "HPD complaints",
        "HPD violations",
        "marshals' evictions",
    ):
        if source in held:
            facts.append(
                {
                    "label": f"Apartments in {source}",
                    "value": f"{len(held[source])}: {cut(spans(held[source]))}",
                }
            )
    facts.append(
        {
            "label": "The chain's labels in city records",
            "value": spans(in_city),
            "mark": "good" if in_city else None,
        }
    )
    facts.append(
        {
            "label": "The chain's labels missing from them",
            "value": spans(missing),
            "mark": "bad" if missing and known else None,
        }
    )
    facts = [{k: v for k, v in f.items() if v is not None} for f in facts]

    units = max(lot.get("pluto_units") or 0, lot.get("legal_a") or 0)
    covered = "condo unit lots" in held or bool(units and len(known) >= COVERED * units)
    floors = max(lot.get("pluto_floors") or 0, lot.get("stories") or 0) or None
    outside = off_grid(labels, building_ads, known, floors)
    evidence = []
    if missing and covered:
        sources = ", ".join(sorted(held))
        evidence.append(
            {
                "kind": "city_record",
                "detail": (
                    f"The city's records of lot {bbl} ({sources}) name {len(known)} apartments "
                    f"of the lot's {units}, {spans(in_city)} among them, and none for "
                    f"{spans(missing)}."
                ),
            }
        )
    for lab, why in outside.items():
        if why.startswith("floor"):
            evidence.append(
                {"kind": "city_record", "detail": f"{lab}: {why} (PLUTO, HPD)."}
            )
            continue
        floor = line_of(lab)[0]
        mates = [
            x
            for x in building_ads
            if (line := line_of(c.label(x["page"])))
            and line[0] == floor
            and c.label(x["page"]) not in labels
        ][-10:]
        if mates:
            evidence.append(
                {
                    "kind": "line_units",
                    "listings": [x["listing_id"] for x in mates],
                    "detail": (
                        f"{lab}: {why}. Floor {floor}'s other labels are "
                        f"{spans({c.label(x['page']) for x in mates})}."
                    ),
                }
            )
    if evidence:
        why = ""
    elif not missing:
        why = " The city's records hold none of the chain's labels apart from one, and every label fits the building's grid, so nothing besides the ads backs a join."
    else:
        why = (
            f" The city's records name {len(known)} apartments of the lot's "
            f"{units or 'unknown number of'} units, too few to treat a missing label as "
            "no unit, and every label fits the building's grid, so nothing besides the ads "
            "backs a join."
        )
    ads_block = {
        "type": "ads",
        "title": "The chain",
        "nominating": True,
        "ads": [
            c.card_ad(
                x,
                raw.get(x["listing_id"]),
                photos=6,
                mark="candidate" if c.label(x["page"]) in missing else None,
            )
            for x in xs
        ],
    }
    made = {
        "id": f"{building}:{'+'.join(sorted(lab.lower() for lab in labels))}"[:180]
        + f"~{chain_id}",
        "chain": chain_id,
        "title": f"{c.address(building)}: {', '.join(sorted(labels))}",
        "subtitle": " · ".join(
            x
            for x in (
                c.beds_text(xs[-1]["bedrooms"]),
                c.money(xs[-1]["latest_ask"]),
                f"{c.day(xs[0]['on_day'])} to {c.day(xs[-1]['on_day'])}",
            )
            if x
        ),
        "claim": (
            f"The repost screen links {len(xs)} ads under {len(labels)} labels as one apartment "
            f"taken down and posted again.{why}"
        ),
        "proposal": {
            "ledger": "units",
            "line": {
                "change": "join_units",
                "building": building,
                "units": [target.lower(), *(lab.lower() for lab in rest)],
            },
            "evidence": evidence,
            "summary": f"Join {', '.join(rest)} into {target}.",
        },
        "options": [],
        "blocks": [
            grid(building_ads, labels, known),
            {"type": "facts", "title": "City records", "rows": facts},
            ads_block,
        ],
    }
    if not evidence:
        del made["proposal"]
    return made


def cut(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[: text.rfind(",", 0, limit)] + ", ..."


def main(out: Path, sources: c.Sources) -> Path:
    meta, cards = build(sources)
    return c.write_queue(out, meta, cards)
