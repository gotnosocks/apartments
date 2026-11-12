"""The review queue producers, run on a small synthetic build of one building."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from apartments.review_cards import common as c
from apartments.review_cards import held_sets, outliers, studio_beds, unit_joins

BUILDING = "1-test-street-new_york"
BBL = "1000010001"
PAGE = f"https://streeteasy.com/building/{BUILDING}/"

# listing ID, unit slug, unit ID, first day, bedrooms, square feet, text
ADS = [
    (100, "3a", "u3a", "2022-01-10", 2.0, 900.0, "Sunny two bedroom."),
    (
        101,
        "3a",
        "u3a",
        "2023-02-01",
        0.0,
        880.0,
        "Lovely 2 bedroom with a view of the park.",
    ),
    (102, "4a", "u4a", "2022-03-01", 2.0, 910.0, "A 2 bed on the fourth floor."),
    (103, "5a", "u5a", "2022-04-01", 2.0, 905.0, "A 2 bed on the fifth floor."),
    (104, "3b", "u3b", "2021-05-01", 0.0, 450.0, "Compact studio."),
    (105, "3bb", "u3bb", "2021-06-15", 0.0, 450.0, "Compact studio."),
    (106, "6b", "u6b", "2021-07-01", 0.0, 440.0, "Studio, sixth floor."),
    (107, "7b", "u7b", "2021-08-01", 0.0, 460.0, "Studio, seventh floor."),
    (108, "8b", "u8b", "2021-09-01", 0.0, 455.0, "Studio, eighth floor."),
]


def write_parquet(con, name: str, sql: str, folder: Path) -> str:
    path = folder / f"{name}.parquet"
    con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet)")
    return path.name


@pytest.fixture
def sources(tmp_path: Path) -> c.Sources:
    data = tmp_path / "datasets"
    data.mkdir()
    con = duckdb.connect()
    values = ", ".join(
        f"({lid}, '{unit}', '{uid}', DATE '{day}', {beds}, {size}, '{text}')"
        for lid, unit, uid, day, beds, size, text in ADS
    )
    con.execute(
        f"CREATE TABLE src (lid BIGINT, unit VARCHAR, uid VARCHAR, d DATE, beds DOUBLE, "
        f"size DOUBLE, txt VARCHAR); INSERT INTO src VALUES {values}"
    )
    ads = write_parquet(
        con,
        "ads",
        f"""
        SELECT lid::VARCHAR AS listing_id, uid AS unit_id, '1' AS building_id,
               '{BUILDING}' AS building, '{PAGE}' || unit AS page, 'Testville' AS neighbourhood,
               'RENTED' AS status, d AS on_day, d + 20 AS off_day, 3000.0::DOUBLE AS first_ask,
               3000.0::DOUBLE AS latest_ask, beds AS bedrooms, 1.0::DOUBLE AS full_baths, 0.0::DOUBLE AS half_baths,
               size AS square_feet, NULL::DOUBLE AS advertised_floor,
               regexp_extract(unit, '^(\\d+)')::DOUBLE AS label_floor,
               []::VARCHAR[] AS floor_plans, []::VARCHAR[] AS exclusion_reasons,
               []::VARCHAR[] AS ledger_entries, 'kept' AS fate, true AS in_rows
        FROM src
        """,
        data,
    )
    rows = write_parquet(
        con,
        "rows",
        "SELECT lid::VARCHAR AS listing_id, d AS period, beds AS bedrooms, 1.0::DOUBLE AS full_baths, "
        "0.0::DOUBLE AS half_baths, size AS square_feet, 3000.0::DOUBLE AS latest_ask FROM src",
        data,
    )
    records = write_parquet(
        con,
        "records",
        """
        SELECT lid AS listing_id, d::TIMESTAMP AS collected_at, d::TIMESTAMP AS last_collected_at,
               json_object('description', txt,
                           'media', json_object('photos', [json_object('key', 'k' || lid)]),
                           'legacy', json_object('sourceGroupLabel', 'Agency'))::VARCHAR
                   AS raw_listing_json
        FROM src ORDER BY lid
        """,
        data,
    )
    entry = {
        "built": "2026-11-10T00:00:00Z",
        "code": {"clean": True, "commit": "abc1234"},
        "records": {"path": records},
        "ads_file": {"path": ads},
        "rows": {"path": rows},
    }
    (data / "catalog.ndjson").write_text(json.dumps(entry) + "\n")

    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    con.execute(
        f"""
        COPY (SELECT lid::VARCHAR AS listing_id, 'latest' AS source, '1 Test St' AS address,
                     upper(unit) AS unit, 'Testville' AS neighbourhood, d AS day, 3000.0::DOUBLE AS ask,
                     2000.0::DOUBLE AS model_median, 1800.0::DOUBLE AS model_lo80,
                     2300.0::DOUBLE AS model_hi80,
                     (lid - 100)::DOUBLE AS miss, 'unit' AS basis, NULL::DOUBLE AS prev_ask,
                     NULL::DATE AS prev_day, NULL::DOUBLE AS prev_bedrooms
              FROM src) TO '{diagnostics / "ads.parquet"}' (FORMAT parquet)
        """
    )

    ledger = tmp_path / "ledger"
    (ledger / "units").mkdir(parents=True)
    held = {
        "change": "set",
        "listing_id": "108",
        "set": {"bedrooms": 0.0},
        "when": {"bedrooms": 0.0},
        "evidence": [{"kind": "ad_text", "quote": "Studio"}],
        "decided": "2026-10-08",
        "source": "x",
    }
    (ledger / "2026-10-08.ndjson").write_text(json.dumps(held) + "\n")
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    line = {
        "change": "set",
        "listing_id": "104",
        "set": {"bedrooms": 1.0},
        "when": {"bedrooms": 0.0},
        "evidence": [{"kind": "ad_text", "quote": "one bedroom"}],
        "rule": "bedrooms-ad-v3",
        "audit_id": "a",
        "agree": 0,
        "disagree": 0,
        "unit_id": "u3b",
        "decided": "2026-10-08",
        "source": "x",
    }
    (reviews / "ledger-held-2026-10-16-chain.jsonl").write_text(json.dumps(line) + "\n")

    state = tmp_path / "state.duckdb"
    with duckdb.connect(str(state)) as db:
        db.execute(
            "CREATE SCHEMA buildings; CREATE SCHEMA city; "
            f"CREATE TABLE buildings.lots AS SELECT 1 AS building_id, '{BBL}' AS bbl; "
            f"CREATE TABLE city.pluto AS SELECT '{BBL}' AS bbl, '12' AS unitsres, "
            "'8' AS numfloors, '26v2' AS release"
        )

    sprint = tmp_path / "sprint"
    (sprint / "C").mkdir(parents=True)
    (sprint / "G" / "city").mkdir(parents=True)
    con.execute(
        f"COPY (SELECT 104::BIGINT AS earlier, 105::BIGINT AS later, 'S1' AS cell, "
        f"7 AS chain_id) TO '{sprint / 'C' / 'links-final.parquet'}' (FORMAT parquet)"
    )
    comps = [{"apartment": a} for a in ("3A", "3B", "4A", "5A", "6B", "7B", "8B")]
    (sprint / "G" / "city" / f"comp-{BBL}.json").write_text(json.dumps(comps))
    return c.Sources(
        datasets=data,
        diagnostics=diagnostics,
        ledger=ledger,
        reviews=reviews,
        state=state,
        sprint=sprint,
        memory="500MB",
    )


def read_queue(folder: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((folder / "meta.json").read_text())
    cards = [json.loads(x) for x in (folder / "cards.jsonl").read_text().splitlines()]
    assert meta["count"] == len(cards)
    assert len({x["id"] for x in cards}) == len(cards)
    assert not list(folder.glob(".*"))
    return meta, cards


def test_outliers_skips_settled_ads_and_orders_by_miss(sources, tmp_path):
    meta, cards = read_queue(outliers.main(tmp_path / "q", sources, size=3))
    assert meta["queue"] == "outliers"
    assert [a["code"] for a in meta["answers"]] == ["right", "unsure"]
    # 108 has the largest miss but a ledger entry in force.
    assert [x["id"] for x in cards] == ["listing:107", "listing:106", "listing:105"]
    ad = cards[0]["blocks"][1]["ads"][0]
    assert ad["record"]["period"] == "2021-08"
    assert ad["photos"] == [c.media_url("k107", c.PHOTO_SIZE)]
    assert "proposal" not in cards[0]


def test_studio_beds_finds_the_named_count_with_backing(sources, tmp_path):
    _, cards = read_queue(studio_beds.main(tmp_path / "q", sources))
    assert [x["id"] for x in cards] == ["listing:101:bedrooms"]
    card = cards[0]
    line = card["proposal"]["line"]
    assert line["set"] == {"bedrooms": 2.0}
    assert line["when"] == {"bedrooms": 0.0, "period": "2023-02"}
    kinds = [e["kind"] for e in card["proposal"]["evidence"]]
    assert kinds[0] == "ad_text"
    assert {"other_ad", "line_units"} <= set(kinds)
    assert [o["code"] for o in card["options"]] == ["beds-1", "beds-3", "beds-4"]
    for option in card["options"]:
        assert "ad_text" not in [e["kind"] for e in option["proposal"]["evidence"]]
    ad = card["blocks"][1]["ads"][0]
    assert ad["photos"] == [c.media_url("k101", c.PHOTO_SIZE)]


def test_stated_size_beats_every_count_between():
    ad = {
        "listing_id": "1",
        "unit_id": "u",
        "page": PAGE + "9z",
        "bedrooms": 0.0,
        "square_feet": 700.0,
        "fate": "kept",
        "neighbourhood": "N",
        "on_day": None,
    }
    sizes = {
        ("N", 0): sorted([400.0] * 5 + [700.0]),
        ("N", 1): [650.0] * 5,
        ("N", 2): [720.0] * 5,
    }
    found = studio_beds.backing(ad, [], sizes)
    # 700 lies nearer the 1-bedroom median than the studio median, and nearer the 2-bedroom
    # median than both, so both counts are backed.
    assert sorted(found) == [1, 2]
    # Once the 1-bedroom median moves to 690, the 2-bedroom one at 720 no longer beats it.
    sizes[("N", 1)] = [690.0] * 5
    assert sorted(studio_beds.backing(ad, [], sizes)) == [1]
    # Without the ad's own size the studio median stays at 400.
    assert "400" in studio_beds.backing(ad, [], sizes)[1][0]["detail"]


def test_median_without_leaves_out_one_copy():
    assert studio_beds.median_without([1.0, 2.0, 9.0], 9.0) == (1.5, 2)
    assert studio_beds.median_without([1.0, 2.0, 9.0], 5.0) == (2.0, 3)
    assert studio_beds.median_without([3.0], 3.0) is None


def test_named_takes_the_most_mentioned_count():
    count, quote = studio_beds.named("A three bedroom, or 2BR, with three-bed views")
    assert count == 3
    assert "three bedroom" in quote
    assert studio_beds.named("A sunny corner apartment") is None


def test_held_sets_strips_rule_fields_and_adds_the_period(sources, tmp_path):
    path = sources.reviews / "ledger-held-2026-10-16-chain.jsonl"
    first = json.loads(path.read_text())
    # A second held line for the same ad and field, and one with no `when` for a field it sets.
    path.write_text(
        path.read_text()
        + json.dumps({**first, "set": {"bedrooms": 2.0}})
        + "\n"
        + json.dumps(
            {**first, "listing_id": "103", "set": {"full_baths": 2.0}, "when": {}}
        )
        + "\n"
    )
    meta, cards = read_queue(held_sets.main(tmp_path / "q", sources))
    assert meta["dropped"] == {
        "in force": 0,
        "not kept": 0,
        "changed since": 0,
        "repeated": 1,
    }
    baths = next(x for x in cards if x["id"] == "listing:103:baths")
    assert baths["proposal"]["line"]["when"] == {"full_baths": 1.0, "period": "2022-04"}
    cards = [x for x in cards if x["id"] == "listing:104:bedrooms"]
    (card,) = cards
    line = card["proposal"]["line"]
    assert line == {
        "change": "set",
        "listing_id": "104",
        "set": {"bedrooms": 1.0},
        "when": {"bedrooms": 0.0, "period": "2021-05"},
    }
    assert card["proposal"]["evidence"][0] == {
        "kind": "ad_text",
        "quote": "one bedroom",
    }
    assert "beds-0" not in [o["code"] for o in card["options"]]
    for option in card["options"]:
        assert "ad_text" not in [e["kind"] for e in option["proposal"]["evidence"]]


def test_unit_joins_proposes_the_label_in_city_records(sources, tmp_path):
    meta, cards = unit_joins.build(sources, examples=None)
    assert meta["scope"] == "every linked building"
    _, cards = read_queue(c.write_queue(tmp_path / "q", meta, cards))
    (card,) = cards
    assert card["id"] == f"{BUILDING}:3b+3bb~7"
    assert card["proposal"]["line"] == {
        "change": "join_units",
        "building": BUILDING,
        "units": ["3b", "3bb"],
    }
    # The records name 7 of PLUTO's 12 units, too few for the missing 3BB to count, but no
    # other label uses line BB.
    (item,) = card["proposal"]["evidence"]
    assert item["kind"] == "line_units"
    assert sorted(item["listings"]) == ["100", "101"]
    assert "line BB" in item["detail"]
    grid, facts, chain = card["blocks"]
    assert grid["type"] == "grid"
    cells = {x["label"]: x.get("mark") for f in grid["floors"] for x in f["cells"]}
    assert cells["3B"] == "candidate"
    assert cells["4A"] == "city"
    assert {"label": "PLUTO residential units", "value": "12"} in facts["rows"]
    assert chain["nominating"] is True
    assert [a.get("mark") for a in chain["ads"]] == [None, "candidate"]


def test_norm_matches_city_and_page_labels():
    assert unit_joins.norm("Apt 03-B") == "3B"
    assert unit_joins.norm("3b") == "3B"


def links(sources, rows):
    con = duckdb.connect()
    values = ", ".join(f"({a}, {b}, 'S1', {chain})" for a, b, chain in rows)
    con.execute(
        f"COPY (SELECT col0::BIGINT AS earlier, col1::BIGINT AS later, col2 AS cell, "
        f"col3 AS chain_id FROM (VALUES {values})) "
        f"TO '{sources.sprint / 'C' / 'links-final.parquet'}' (FORMAT parquet)"
    )


def test_unit_joins_skips_two_recorded_labels(sources):
    links(sources, [(106, 107, 8)])
    meta, cards = unit_joins.build(sources, examples=None)
    assert cards == []
    assert meta["dropped"] == {"two or more labels in city records": 1}


def test_unit_joins_asks_without_a_proposal_when_nothing_backs_it(sources):
    # 3C is missing from the thin records, but line C and floor 3 fit the grid of 4C.
    comps = [{"apartment": a} for a in ("3B", "4C")]
    (sources.sprint / "G" / "city" / f"comp-{BBL}.json").write_text(json.dumps(comps))
    con = duckdb.connect()
    data = sources.datasets
    entry = json.loads((data / "catalog.ndjson").read_text())
    ads = data / entry["ads_file"]["path"]
    con.execute(
        f"COPY (SELECT * REPLACE (CASE listing_id WHEN '105' THEN '{PAGE}3c' "
        f"WHEN '106' THEN '{PAGE}4c' ELSE page END AS page) FROM '{ads}') "
        f"TO '{data / 'ads2.parquet'}' (FORMAT parquet)"
    )
    entry["ads_file"]["path"] = "ads2.parquet"
    (data / "catalog.ndjson").write_text(json.dumps(entry) + "\n")
    _, cards = unit_joins.build(sources, examples=None)
    (card,) = cards
    assert "proposal" not in card
    assert "too few" in card["claim"]


def test_unit_joins_leaves_out_pages_already_joined(sources):
    join = {
        "change": "join_units",
        "building": BUILDING,
        "units": ["3bb", "8b"],
        "evidence": [{"kind": "owner", "detail": "x"}],
        "decided": "2026-11-01",
    }
    (sources.ledger / "units" / "2026-11-01.ndjson").write_text(json.dumps(join) + "\n")
    _, cards = unit_joins.build(sources, examples=None)
    assert cards == []
