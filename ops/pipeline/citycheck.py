"""Compare the lots, units and floors of a pipeline state with the city's records, and write a
JSON report and a short Markdown summary.

    pipeline/.venv/bin/python ops/pipeline/citycheck.py STATE --out DIR [--top N]
        [--memory SIZE] [--threads N]

The script attaches the DuckDB file STATE read-only under the name `pipeline`, since the build
qualifies its views with that catalog name. A copy of a state works under any file name. The
city views read Parquet files from the build's city cache by absolute path, so the cache has to
stay in place. The script writes DIR/citycheck.json and DIR/citycheck.md. DuckDB gets SIZE of
memory, 2GB unless given, and spills to a scratch folder under TMPDIR past it. Each section of
the JSON report carries the definitions of its measures, and each list of cases holds the top
N, 25 unless given.

1. Lots. The script counts buildings with ads, their ads and their fit-ready rows by the `link`
   of `buildings.lots`, which says whether the lot came from the address, the map point or
   both. As a second route apart from PAD address ranges and footprints, it looks up each
   building's street address among the lot addresses of the latest MapPLUTO release, and counts
   buildings and rows by the outcome: the build's lot, another lot or no lot. identity_check.py
   compares the same lots with the lot registry and scores them on the reviewed sample.
2. Units. For each lot, it counts distinct units with ads, over all time and over the 12 months
   up to the latest first day of a candidate ad. It compares the counts with the lot's
   `unitsres` in the MapPLUTO release of the lot's latest candidate ad, and with the apartments
   on the latest certificates of occupancy of the lot's BINs as of that ad's first day.
3. Floors. For each fit-ready row with a floor, it compares the floor with the lot's
   `numfloors` as of the row's date and with the building's StreetEasy floor count. The build
   refuses a label floor above StreetEasy's count, and the script compares those refused label
   floors with `numfloors` as well.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

# Margins above a city count, each a label and its largest margin. The last bin takes the rest.
UNIT_BINS = [("1", 1), ("2 to 5", 5), ("6 to 20", 20), ("more than 20", None)]
FLOOR_BINS = [
    ("1", 1),
    ("2", 2),
    ("3 to 5", 5),
    ("6 to 10", 10),
    ("more than 10", None),
]
UNIT_CLASSES = ["no_count", "zero_count", "within"] + [
    f"above by {b}" for b, _ in UNIT_BINS
]
FLOOR_CLASSES = ["no_lot"] + UNIT_CLASSES[:3] + [f"above by {b}" for b, _ in FLOOR_BINS]
LINKS = [
    "both",
    "address",
    "footprint",
    "tie",
    "address_only",
    "footprint_only",
    "none",
    "no_record",
]
ADDRESS_CLASSES = [
    "same",
    "among_several",
    "other",
    "only_mappluto",
    "no_match",
    "unparsed",
]

DEFINITIONS = {
    "lots": {
        "link": "The `link` of the building in buildings.lots: `both` when the PAD address "
        "range and the footprint under the map point give the same lot, `address` or "
        "`footprint` when they differ and that route's lot fits the building's record better, "
        "`tie` when they fit equally and the address's lot stands, `address_only` and "
        "`footprint_only` when one route finds nothing. `none` is a building with a record and "
        "no lot, `no_record` a building of an ad with no building record.",
        "buildings": "Buildings of at least one ad with a record, in ads.placed.",
        "ads": "Ads with a record naming the building.",
        "rows": "Fit-ready rows of analysis.rows in the building.",
        "mappluto_address": "The building's street address from its latest record, parsed as "
        "buildings.pad_link parses it, against the `address` of each lot in the latest "
        "MapPLUTO release, parsed the same way. Both sides give a borough, a street and a "
        "house number with its letter. A street name in the latest PAD street dictionary "
        "counts as its street code, so `6th Avenue` meets AVENUE OF THE AMERICAS. `same`: "
        "the address gives the build's lot alone. `among_several`: it gives several lots, the "
        "build's among them. `other`: it gives lots without the build's. `only_mappluto`: it "
        "gives a lot to a building without one. `no_match`: no lot has the address. "
        "`unparsed`: the address gives no house number or no borough. MapPLUTO lists one "
        "address for each lot, so a building on a corner or in a range of house numbers often "
        "finds no match, and `no_match` says nothing against the build's lot.",
    },
    "units": {
        "lot": "A lot of buildings.lots with at least one ad with a unit in its buildings.",
        "units_all": "Distinct units, the unit_id of ads.placed, with at least one ad in "
        "the lot's buildings. A unit is a unit page, so a unit under two pages counts twice "
        "unless a join of the unit ledger gives the pages one unit.",
        "units_12m": "Distinct units with an ad whose first day falls in the 12 months up to "
        "`as_of`, the latest first day of a candidate ad.",
        "unitsres": "The lot's `unitsres` in analysis.lot_facts for the lot's latest "
        "candidate ad, from the MapPLUTO release that ad reads. A lot without a candidate ad "
        "takes it from the latest release in buildings.lot_releases, and `unitsres_from` says "
        "which.",
        "co_units": "For each BIN of the lot's candidate ads, the apartments on the BIN's "
        "latest certificate of occupancy by the first day of the BIN's latest candidate ad, "
        "from analysis.building_certificates, summed over the BINs. A lot with a BIN "
        "lacking a count has no co_units.",
        "classes": "`no_count`: the city count is missing. `zero_count`: it is 0 and the lot "
        "has units with ads. `within`: the units with ads are at most the city count. "
        "`above by N`: they exceed it by N.",
        "top_above": "Lots with units_all above unitsres or co_units, the largest excess first. "
        "A unitsres of 0 counts as no excess here, and `top_zero_unitsres` lists those lots.",
    },
    "floors": {
        "floor": "The row's advertised floor, else its physical floor, else its label floor "
        "(`label_derived_floor`), as analysis.rows gives them. `source` says which. Rows "
        "whose `floor_status` refused or lacked a floor have none.",
        "numfloors": "The lot's `numfloors` in analysis.lot_facts for the row, from the "
        "latest MapPLUTO release published at least 7 days before the row's first day.",
        "streeteasy": "`building_floor_count` of the row: the building's floor count in its "
        "StreetEasy record, as buildings.details gives it. The build also matches lots partly "
        "by this count, so the two city comparisons are not independent.",
        "classes": "`no_lot`: the row's building has no lot. `no_count`: the count is "
        "missing. `zero_count`: it is 0. `within`: the floor is at most the count. "
        "`above by N`: the floor exceeds the count by N, rounded up.",
        "refused_labels": "Rows with `floor_status` above_captured_building_floor_count: the "
        "label floor of ads.reported is above the StreetEasy count, so the row has no floor. "
        "Their label floor against `numfloors`, in the same classes.",
        "top_above_numfloors": "Buildings with rows above `numfloors`, the most such rows "
        "first: their units, top floor, floor sources, and the lot's latest counts.",
    },
}


def classify(margin: str, count: str, bins) -> str:
    """SQL putting `margin`, a count above the city's `count`, in a class."""
    above = " ".join(
        f"WHEN {margin} <= {high} THEN 'above by {label}'" for label, high in bins[:-1]
    )
    return (
        f"CASE WHEN {count} IS NULL THEN 'no_count' WHEN {count} = 0 THEN 'zero_count' "
        f"WHEN {margin} <= 0 THEN 'within' {above} ELSE 'above by {bins[-1][0]}' END"
    )


SUFFIXES = [
    ("ST", "STREET"),
    ("STR", "STREET"),
    ("AVE", "AVENUE"),
    ("AV", "AVENUE"),
    ("PL", "PLACE"),
    ("BLVD", "BOULEVARD"),
    ("BL", "BOULEVARD"),
    ("RD", "ROAD"),
    ("LN", "LANE"),
    ("TER", "TERRACE"),
    ("TERR", "TERRACE"),
    ("PKWY", "PARKWAY"),
    ("CT", "COURT"),
    ("SQ", "SQUARE"),
    ("DR", "DRIVE"),
    ("HWY", "HIGHWAY"),
    ("PLZ", "PLAZA"),
    ("CIR", "CIRCLE"),
    ("EXPY", "EXPRESSWAY"),
    ("WY", "WAY"),
]
PATTERN = r"^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$"

# The parse of buildings.pad_link, over SOURCE, a query giving `id`, `boro` and `street`. It
# gives a row for each house number of each address, with the street as its PAD street code
# where the dictionary has the name.
ADDRESS_KEYS = r"""
WITH suffixes(abbr, word) AS (VALUES SUFFIXES),
cleaned AS (
    SELECT id, boro,
        trim(regexp_replace(regexp_replace(upper(street), '[.,'']', '', 'g'), '\s+', ' ', 'g'))
            AS street
    FROM (SOURCE)
), parts AS (
    SELECT id, boro, regexp_extract(street, 'PATTERN', ['n1', 'n2', 'letter', 'half', 'name'])
        AS p
    FROM cleaned
), named AS (
    SELECT id, boro, p.n1, p.n2, trim(p.letter) AS letter, p.half <> '' AS half,
        regexp_replace(p.name, '\b(\d+)(ST|ND|RD|TH)\b', '\1', 'g') AS name
    FROM parts
), spelled AS (
    SELECT n.id, n.boro, n.n1, n.n2, n.letter, n.half,
        concat_ws(' ',
            CASE regexp_extract(n.name, '^([EWNS]) ', 1)
                WHEN 'E' THEN 'EAST' WHEN 'W' THEN 'WEST' WHEN 'N' THEN 'NORTH'
                WHEN 'S' THEN 'SOUTH' END,
            CASE WHEN s.word IS NULL THEN regexp_replace(n.name, '^[EWNS] ', '')
                ELSE regexp_replace(regexp_replace(n.name, '^[EWNS] ', ''), ' \S+$', ' ' || s.word)
                END) AS name
    FROM named n
    LEFT JOIN suffixes s ON s.abbr = regexp_extract(n.name, ' (\S+)$', 1)
    WHERE n.n1 <> '' AND n.boro IS NOT NULL
), numbered AS (
    SELECT *, unnest(
        CASE WHEN boro = '4' AND n2 <> '' THEN [n1 || '-' || n2]
            WHEN n2 <> '' THEN [n1, n2]
            ELSE [n1] END
    ) AS number
    FROM spelled
)
SELECT n.id, n.boro, coalesce('code ' || d.code, n.name) AS street,
    n.number || n.letter || CASE WHEN n.half THEN ' 1/2' ELSE '' END AS house
FROM numbered n
LEFT JOIN street_codes d ON d.boro = n.boro AND d.name = n.name
""".replace("SUFFIXES", ", ".join(f"('{a}', '{w}')" for a, w in SUFFIXES)).replace(
    "PATTERN", PATTERN
)

BUILDING_ADDRESSES = """
SELECT building_id AS id, street,
    CASE WHEN left(community_district, 1) IN ('1', '2', '3', '4', '5')
            THEN left(community_district, 1)
        WHEN upper(city) IN ('NEW YORK', 'MANHATTAN') THEN '1'
        WHEN upper(city) = 'BRONX' THEN '2'
        WHEN upper(city) IN ('BROOKLYN', 'WILLIAMSBURG') THEN '3'
        WHEN upper(city) IN ('QUEENS', 'RIDGEWOOD', 'LONG ISLAND CITY', 'ASTORIA') THEN '4'
        WHEN upper(city) = 'STATEN ISLAND' THEN '5' END AS boro
FROM buildings.latest_record
WHERE building_id IN (SELECT building_id FROM building_links)
"""


def records(db, sql: str) -> list[dict]:
    cursor = db.execute(sql)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def tally(db, sql: str, order: list[str] | None = None) -> dict:
    """{class: count} from a query giving a class and a count. With `order`, the classes come
    in its order, with 0 for a class the query lacks, and any other class after them."""
    got = {str(k): int(n) for k, n in db.execute(sql).fetchall()}
    if order is None:
        return got
    return {k: got.get(k, 0) for k in [*order, *sorted(set(got) - set(order))]}


def prepare(db) -> str:
    """Make the temporary tables the sections share, and return the `as_of` day."""
    db.execute(
        """
        CREATE TEMP TABLE ad_units AS
        SELECT i.listing_id, i.building_id, i.unit_id, e.first_day
        FROM ads.placed i
        JOIN ads.exclusions e USING (listing_id)
        WHERE i.building_id IS NOT NULL
        """
    )
    db.execute(
        """
        CREATE TEMP TABLE fit_rows AS
        SELECT listing_id, unit_id, page, building_id,
            (price_at AT TIME ZONE 'UTC')::DATE AS first_day, advertised_floor, physical_floor,
            label_derived_floor, floor_status, building_floor_count
        FROM analysis.rows
        """
    )
    db.execute(
        """
        CREATE TEMP TABLE building_links AS
        WITH ads AS (
            SELECT building_id, count(*) AS ads FROM ad_units GROUP BY ALL
        ), fit AS (
            SELECT building_id, count(*) AS rows FROM fit_rows GROUP BY ALL
        )
        SELECT a.building_id, r.slug, r.street,
            CASE WHEN l.building_id IS NULL THEN 'no_record' ELSE coalesce(l.link, 'none') END
                AS link,
            l.bbl, a.ads, coalesce(f.rows, 0) AS rows
        FROM ads a
        LEFT JOIN fit f USING (building_id)
        LEFT JOIN buildings.lots l USING (building_id)
        LEFT JOIN buildings.latest_record r USING (building_id)
        """
    )
    db.execute(
        """
        CREATE TEMP TABLE pluto_latest AS
        SELECT try_cast(bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl, release,
            nullif(trim(address), '') AS address
        FROM city.pluto
        WHERE release = (SELECT any_value(pluto_release) FROM buildings.lots)
            AND try_cast(bbl AS DOUBLE) IS NOT NULL
        """
    )
    as_of = db.execute(
        "SELECT max(price_at AT TIME ZONE 'UTC')::DATE FROM analysis.candidates"
    ).fetchone()[0]
    return str(as_of)


def lots(db, top: int) -> dict:
    db.execute(
        """
        CREATE TEMP TABLE street_codes AS
        SELECT boro, trim(regexp_replace(name, '\\s+', ' ', 'g')) AS name, min(sc5) AS code
        FROM city.pad_streets, unnest([stname, full_stname]) t(name)
        WHERE release = (SELECT any_value(pad_release) FROM buildings.pad_link)
        GROUP BY ALL
        """
    )
    building_keys = ADDRESS_KEYS.replace("SOURCE", BUILDING_ADDRESSES)
    lot_keys = ADDRESS_KEYS.replace(
        "SOURCE",
        "SELECT bbl AS id, left(bbl, 1) AS boro, address AS street FROM pluto_latest "
        "WHERE address IS NOT NULL",
    )
    db.execute(f"CREATE TEMP TABLE building_keys AS {building_keys}")
    db.execute(f"CREATE TEMP TABLE lot_keys AS {lot_keys}")
    db.execute(
        """
        CREATE TEMP TABLE address_matches AS
        WITH found AS (
            SELECT b.id AS building_id,
                coalesce(list(DISTINCT p.id ORDER BY p.id) FILTER (WHERE p.id IS NOT NULL), [])
                    AS pluto_lots
            FROM building_keys b
            LEFT JOIN lot_keys p USING (boro, street, house)
            GROUP BY b.id
        )
        SELECT l.*, f.pluto_lots,
            CASE WHEN f.building_id IS NULL THEN 'unparsed'
                WHEN len(f.pluto_lots) = 0 THEN 'no_match'
                WHEN l.bbl IS NULL THEN 'only_mappluto'
                WHEN f.pluto_lots = [l.bbl] THEN 'same'
                WHEN list_contains(f.pluto_lots, l.bbl) THEN 'among_several'
                ELSE 'other' END AS mappluto_address
        FROM building_links l
        LEFT JOIN found f USING (building_id)
        """
    )
    by_link = records(
        db,
        """
        SELECT link, count(*) AS buildings, sum(ads)::BIGINT AS ads, sum(rows)::BIGINT AS rows
        FROM building_links GROUP BY link
        """,
    )
    by_link.sort(key=lambda r: LINKS.index(r["link"]))
    crossed = records(
        db,
        """
        SELECT link, mappluto_address, count(*) AS buildings, sum(rows)::BIGINT AS rows
        FROM address_matches GROUP BY ALL
        """,
    )
    address = {}
    for unit in ("buildings", "rows"):
        totals = {c: 0 for c in ADDRESS_CLASSES}
        links = {}
        for r in sorted(crossed, key=lambda r: LINKS.index(r["link"])):
            totals[r["mappluto_address"]] += r[unit]
            links.setdefault(r["link"], {c: 0 for c in ADDRESS_CLASSES})
            links[r["link"]][r["mappluto_address"]] += r[unit]
        address[unit] = {"all": totals, "by_link": links}
    cases = records(
        db,
        f"""
        WITH picked AS (
            SELECT * FROM address_matches
            WHERE mappluto_address IN ('other', 'only_mappluto')
            ORDER BY rows DESC, ads DESC, building_id
            LIMIT {top}
        ), pairs AS (
            SELECT building_id, unnest(pluto_lots) AS bbl FROM picked
        ), named AS (
            SELECT t.building_id, list(q.address ORDER BY q.bbl) AS pluto_addresses
            FROM pairs t
            JOIN pluto_latest q USING (bbl)
            GROUP BY t.building_id
        )
        SELECT m.slug, m.building_id, m.street, m.link, m.bbl, p.address AS lot_address,
            m.mappluto_address, m.pluto_lots, n.pluto_addresses, m.ads, m.rows
        FROM picked m
        LEFT JOIN named n USING (building_id)
        LEFT JOIN pluto_latest p ON p.bbl = m.bbl
        ORDER BY m.rows DESC, m.ads DESC, m.building_id
        """,
    )
    lotted = [r for r in by_link if r["link"] not in ("none", "no_record")]
    return {
        "definitions": DEFINITIONS["lots"],
        "buildings": sum(r["buildings"] for r in by_link),
        "buildings_with_lot": sum(r["buildings"] for r in lotted),
        "rows": sum(r["rows"] for r in by_link),
        "rows_with_lot": sum(r["rows"] for r in lotted),
        "by_link": by_link,
        "mappluto_address": address,
        "disagreements": cases,
    }


def units(db, as_of: str, top: int) -> dict:
    against = {
        "units_all vs unitsres": classify(
            "units_all - unitsres", "unitsres", UNIT_BINS
        ),
        "units_12m vs unitsres": classify(
            "units_12m - unitsres", "unitsres", UNIT_BINS
        ),
        "units_all vs co_units": classify(
            "units_all - co_units", "co_units", UNIT_BINS
        ),
        "units_12m vs co_units": classify(
            "units_12m - co_units", "co_units", UNIT_BINS
        ),
    }
    db.execute(
        f"""
        CREATE TEMP TABLE lot_units AS
        WITH ads AS (
            SELECT l.bbl, a.building_id, a.unit_id, a.first_day
            FROM ad_units a
            JOIN building_links l USING (building_id)
            WHERE l.bbl IS NOT NULL AND a.unit_id IS NOT NULL
        ), counted AS (
            SELECT bbl, count(DISTINCT unit_id) AS units_all,
                count(DISTINCT unit_id)
                    FILTER (WHERE first_day > DATE '{as_of}' - INTERVAL 12 MONTH) AS units_12m,
                list(DISTINCT building_id ORDER BY building_id) AS building_ids
            FROM ads GROUP BY bbl
        ), latest_ad AS (
            SELECT f.bbl, arg_max(f.unitsres, (c.price_at, f.listing_id)) AS unitsres,
                arg_max(f.pluto_release, (c.price_at, f.listing_id)) AS release
            FROM analysis.lot_facts f
            JOIN analysis.candidates c USING (listing_id)
            WHERE f.bbl IN (SELECT bbl FROM counted)
            GROUP BY f.bbl
        ), latest_release AS (
            SELECT bbl, arg_max(unitsres, published) AS unitsres, arg_max(release, published)
                AS release
            FROM buildings.lot_releases
            WHERE bbl IN (SELECT bbl FROM counted) AND bbl NOT IN (SELECT bbl FROM latest_ad)
            GROUP BY bbl
        ), bins AS (
            SELECT bin, arg_max(units, (first_day, listing_id)) AS units
            FROM analysis.building_certificates
            WHERE bin IS NOT NULL
            GROUP BY bin
        ), lot_bins AS (
            SELECT DISTINCT l.bbl, c.bin
            FROM analysis.building_certificates c
            JOIN building_links l USING (building_id)
            WHERE l.bbl IS NOT NULL AND c.bin IS NOT NULL
        ), certified AS (
            SELECT b.bbl, list(b.bin ORDER BY b.bin) AS bins,
                CASE WHEN count(*) = count(n.units) THEN sum(n.units)::BIGINT END AS co_units
            FROM lot_bins b
            LEFT JOIN bins n USING (bin)
            GROUP BY b.bbl
        ), streeteasy AS (
            SELECT l.bbl, max(r.residential_units) AS se_units
            FROM building_links l
            JOIN buildings.latest_record r USING (building_id)
            WHERE l.bbl IS NOT NULL
            GROUP BY l.bbl
        ), fit AS (
            SELECT bbl, sum(rows)::BIGINT AS rows, list(slug ORDER BY slug) AS slugs,
                list(DISTINCT link ORDER BY link) AS links
            FROM building_links WHERE bbl IS NOT NULL GROUP BY bbl
        )
        SELECT c.bbl, f.slugs, f.links, c.building_ids, c.units_all, c.units_12m,
            coalesce(a.unitsres, r.unitsres) AS unitsres,
            coalesce(a.release, r.release) AS unitsres_release,
            CASE WHEN a.bbl IS NOT NULL THEN 'latest_candidate_ad'
                WHEN r.bbl IS NOT NULL THEN 'latest_release' END AS unitsres_from,
            t.bins, t.co_units, s.se_units, f.rows
        FROM counted c
        LEFT JOIN latest_ad a USING (bbl)
        LEFT JOIN latest_release r USING (bbl)
        LEFT JOIN certified t USING (bbl)
        LEFT JOIN streeteasy s USING (bbl)
        LEFT JOIN fit f USING (bbl)
        """
    )
    measures = {}
    for name, case in against.items():
        measures[name] = tally(
            db, f"SELECT {case} AS c, count(*) FROM lot_units GROUP BY c", UNIT_CLASSES
        )
    excess = "greatest(units_all - coalesce(nullif(unitsres, 0), units_all), " + (
        "units_all - coalesce(co_units, units_all))"
    )
    cases = records(
        db,
        f"""
        SELECT u.slugs, u.bbl, p.address AS lot_address, u.links, u.units_all, u.units_12m,
            u.unitsres, u.unitsres_release, u.unitsres_from, u.bins, u.co_units, u.se_units,
            u.rows
        FROM lot_units u
        LEFT JOIN pluto_latest p USING (bbl)
        WHERE {excess} > 0
        ORDER BY {excess} DESC, u.units_all DESC, u.bbl
        LIMIT {top}
        """,
    )
    zero = records(
        db,
        f"""
        SELECT u.slugs, u.bbl, p.address AS lot_address, u.links, u.units_all, u.units_12m,
            u.unitsres_release, u.rows
        FROM lot_units u
        LEFT JOIN pluto_latest p USING (bbl)
        WHERE u.unitsres = 0
        ORDER BY u.units_all DESC, u.bbl
        LIMIT {top}
        """,
    )
    totals = db.execute(
        "SELECT count(*), sum(units_all), sum(units_12m) FROM lot_units"
    ).fetchone()
    return {
        "definitions": DEFINITIONS["units"],
        "as_of": as_of,
        "lots": int(totals[0]),
        "units_all": int(totals[1] or 0),
        "units_12m": int(totals[2] or 0),
        "lots_by_class": measures,
        "top_above": cases,
        "top_zero_unitsres": zero,
    }


def floors(db, top: int) -> dict:
    db.execute(
        f"""
        CREATE TEMP TABLE row_floors AS
        SELECT r.listing_id, r.unit_id, r.page, r.building_id, r.first_day, r.floor_status,
            coalesce(r.advertised_floor, r.physical_floor, r.label_derived_floor) AS floor,
            CASE WHEN r.advertised_floor IS NOT NULL THEN 'advertised'
                WHEN r.physical_floor IS NOT NULL THEN 'physical'
                WHEN r.label_derived_floor IS NOT NULL THEN 'label' END AS source,
            r.building_floor_count AS se_floors, f.bbl, f.link, f.pluto_release, f.numfloors,
            d.label_floor
        FROM fit_rows r
        LEFT JOIN analysis.lot_facts f USING (listing_id)
        LEFT JOIN ads.reported d USING (listing_id)
        """
    )
    lot_case = (
        "CASE WHEN bbl IS NULL THEN 'no_lot' ELSE "
        + classify("ceil(VALUE - numfloors)", "numfloors", FLOOR_BINS)
        + " END"
    )
    se_case = classify("ceil(floor - se_floors)", "se_floors", FLOOR_BINS)
    db.execute(
        f"""
        CREATE TEMP TABLE floor_classes AS
        SELECT *, {lot_case.replace("VALUE", "floor")} AS against_numfloors,
            {se_case} AS against_streeteasy
        FROM row_floors
        WHERE floor IS NOT NULL
        """
    )
    sources = {}
    for source in ("advertised", "physical", "label"):
        sources[source] = tally(
            db,
            f"""
            SELECT against_numfloors, count(*) FROM floor_classes
            WHERE source = '{source}' GROUP BY ALL
            """,
            FLOOR_CLASSES,
        )
    both = db.execute(
        """
        SELECT count(*) FROM floor_classes
        WHERE against_numfloors LIKE 'above%' AND against_streeteasy LIKE 'above%'
        """
    ).fetchone()[0]
    refused = tally(
        db,
        f"""
        SELECT {lot_case.replace("VALUE", "label_floor")} AS c, count(*) FROM row_floors
        WHERE floor_status = 'above_captured_building_floor_count' GROUP BY c
        """,
        FLOOR_CLASSES,
    )
    cases = records(
        db,
        f"""
        SELECT b.slug, f.bbl, p.address AS lot_address, f.link, count(*) AS rows,
            count(DISTINCT f.unit_id) AS units, max(f.floor) AS top_floor,
            arg_max(f.page, f.floor) AS top_page,
            list(DISTINCT f.source ORDER BY f.source) AS sources,
            arg_max(f.numfloors, f.first_day) AS numfloors,
            arg_max(f.pluto_release, f.first_day) AS pluto_release,
            arg_max(f.se_floors, f.first_day) AS se_floors, max(f.first_day) AS last_day
        FROM floor_classes f
        LEFT JOIN building_links b USING (building_id)
        LEFT JOIN pluto_latest p ON p.bbl = f.bbl
        WHERE f.against_numfloors LIKE 'above%'
        GROUP BY b.slug, f.bbl, p.address, f.link
        ORDER BY rows DESC, max(f.floor - f.numfloors) DESC, f.bbl
        LIMIT {top}
        """,
    )
    counts = db.execute("SELECT count(*), count(floor) FROM row_floors").fetchone()
    return {
        "definitions": DEFINITIONS["floors"],
        "rows": int(counts[0]),
        "rows_with_floor": int(counts[1]),
        "by_floor_status": tally(
            db,
            "SELECT floor_status, count(*) FROM row_floors GROUP BY ALL ORDER BY 2 DESC",
            [],
        ),
        "against_numfloors": tally(
            db,
            "SELECT against_numfloors, count(*) FROM floor_classes GROUP BY ALL",
            FLOOR_CLASSES,
        ),
        "against_numfloors_by_source": sources,
        "against_streeteasy": tally(
            db,
            "SELECT against_streeteasy, count(*) FROM floor_classes GROUP BY ALL",
            FLOOR_CLASSES,
        ),
        "above_both": int(both),
        "refused_labels_against_numfloors": refused,
        "top_above_numfloors": cases,
    }


def table(rows: list[dict], columns: list[str]) -> list[str]:
    def cell(value):
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return "" if value is None else str(value)

    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    lines += ["| " + " | ".join(cell(r[c]) for c in columns) + " |" for r in rows]
    return lines


def above(classes: dict) -> int:
    return sum(n for c, n in classes.items() if c.startswith("above"))


def summary(report: dict, shown: int = 10) -> str:
    lots, units_, floors_ = report["lots"], report["units"], report["floors"]
    lines = [
        "# City check",
        "",
        f"State {report['state']['path']}, modified {report['state']['modified']}. "
        f"Candidate ads run to {report['as_of']}. The check took {report['seconds']} s.",
        "",
        "## Lots",
        "",
        f"{lots['buildings_with_lot']:,} of {lots['buildings']:,} buildings with ads have a "
        f"lot, and {lots['rows_with_lot']:,} of {lots['rows']:,} fit-ready rows.",
        "",
        *table(lots["by_link"], ["link", "buildings", "ads", "rows"]),
        "",
        "The MapPLUTO address of each building, against the build's lot:",
        "",
        *table(
            [
                {"unit": u, **lots["mappluto_address"][u]["all"]}
                for u in ("buildings", "rows")
            ],
            ["unit", *ADDRESS_CLASSES],
        ),
        "",
        *table(
            lots["disagreements"][:shown],
            ["slug", "street", "link", "bbl", "pluto_lots", "rows"],
        ),
        "",
        "## Units",
        "",
        f"{units_['lots']:,} lots hold {units_['units_all']:,} units with ads, "
        f"{units_['units_12m']:,} of them with an ad in the 12 months to {units_['as_of']}.",
        "",
        *table(
            [{"measure": m, **c} for m, c in units_["lots_by_class"].items()],
            ["measure", *UNIT_CLASSES],
        ),
        "",
        *table(
            units_["top_above"][:shown],
            [
                "slugs",
                "bbl",
                "units_all",
                "units_12m",
                "unitsres",
                "co_units",
                "se_units",
            ],
        ),
        "",
        "## Floors",
        "",
        f"{floors_['rows_with_floor']:,} of {floors_['rows']:,} fit-ready rows have a floor. "
        f"{above(floors_['against_numfloors']):,} are above the lot's numfloors, "
        f"{above(floors_['against_streeteasy']):,} above StreetEasy's count and "
        f"{floors_['above_both']:,} above both. Of the label floors refused for exceeding "
        f"StreetEasy's count, {above(floors_['refused_labels_against_numfloors']):,} also "
        "exceed numfloors.",
        "",
        *table(
            [
                {"against": "numfloors", **floors_["against_numfloors"]},
                {"against": "streeteasy", **floors_["against_streeteasy"]},
                {
                    "against": "refused labels",
                    **floors_["refused_labels_against_numfloors"],
                },
            ],
            ["against", *FLOOR_CLASSES],
        ),
        "",
        *table(
            floors_["top_above_numfloors"][:shown],
            [
                "slug",
                "bbl",
                "rows",
                "units",
                "top_floor",
                "sources",
                "numfloors",
                "se_floors",
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("state", type=Path, help="the pipeline.duckdb file, or a copy")
    parser.add_argument("--out", type=Path, required=True, help="folder for the report")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--memory", default="2GB")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    state = args.state.resolve()
    if not state.is_file():
        sys.exit(f"no file {state}")
    args.out.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="citycheck-"))
    start = time.monotonic()
    seconds = {}
    try:
        db = duckdb.connect(
            config={
                "memory_limit": args.memory,
                "threads": args.threads,
                "temp_directory": str(scratch),
                "preserve_insertion_order": False,
                "TimeZone": "UTC",
            }
        )
        quoted = str(state).replace("'", "''")
        db.execute(f"ATTACH '{quoted}' AS pipeline (READ_ONLY)")
        db.execute("USE pipeline")
        sections = {}
        step = time.monotonic()
        as_of = prepare(db)
        seconds["prepare"] = round(time.monotonic() - step, 1)
        for name, run in (
            ("lots", lambda: lots(db, args.top)),
            ("units", lambda: units(db, as_of, args.top)),
            ("floors", lambda: floors(db, args.top)),
        ):
            step = time.monotonic()
            sections[name] = run()
            seconds[name] = round(time.monotonic() - step, 1)
            print(f"{name}: {seconds[name]} s", flush=True)
        db.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    stat = state.stat()
    report = {
        "state": {
            "path": str(state),
            "bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        },
        "as_of": as_of,
        "seconds": round(time.monotonic() - start, 1),
        "seconds_by_step": seconds,
        **sections,
    }
    (args.out / "citycheck.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n"
    )
    (args.out / "citycheck.md").write_text(summary(report))
    print(f"wrote {args.out / 'citycheck.json'} and {args.out / 'citycheck.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
