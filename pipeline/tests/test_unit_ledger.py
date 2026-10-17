import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
context, changed = helpers.context, helpers.changed
ledger = load("ledger_entries", PROJECT / "models" / "ledger" / "entries.py")

OTHER_AD = {"kind": "other_ad", "listing_id": "123", "detail": "the same unit"}
CITY = {"kind": "city_record", "detail": "the lot's buildings in PLUTO"}
QUOTE = {"kind": "ad_text", "quote": "two units combined"}


def unit_line(change, **keys):
    return json.dumps(
        {"change": change, "decided": "2026-10-17", "evidence": [OTHER_AD], **keys}
    )


def join(building, units, **keys):
    return unit_line("join_units", building=building, units=units, **keys)


def split(building, unit, listings, **keys):
    return unit_line(
        "split_unit", building=building, unit=unit, listings=listings, **keys
    )


def move(building, to, **keys):
    return unit_line("move_building", building=building, to=to, evidence=[CITY], **keys)


def retract(text):
    return unit_line("retract", entry=ledger.entry_id(text))


def write(folder, name, lines):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("".join(text + "\n" for text in lines))
    return folder / name


@pytest.mark.parametrize(
    "text, error",
    [
        (join("b", ["1"]), "a join_units gives at least two units"),
        (join("b", "1"), "a join_units gives at least two units"),
        (join("b", ["1", "1"]), "a join_units gives each unit once"),
        (join("b", ["1", "2/3"]), "each unit is a slug"),
        (join("B", ["1", "2"]), "building is a slug"),
        (join("b", ["1", 2]), "each unit is a slug"),
        (split("b", "1", []), "a split_unit gives its ads' IDs as listings"),
        (split("b", "1", [1]), "a split_unit gives its ads' IDs as listings"),
        (split("b", "1", ["5", "5"]), "a split_unit gives each ad once"),
        (
            split("b", "1", ["5"], into="5"),
            "a split_unit's into gives an ad of another",
        ),
        (split("b", "1", ["5"], into=6), "a split_unit's into gives an ad of another"),
        (join("b", ["1", "2"], into="5"), "a join_units takes no into"),
        (
            split("b", "1", ["123"]),
            "other_ad evidence gives other ads than the entry's own",
        ),
        (move("b", "b"), "a move_building moves a building to another"),
        (move("b", "c?"), "to is a slug"),
        (
            join("b", ["1", "2"], evidence=[QUOTE]),
            "a join_units needs evidence of a backing",
        ),
        (unit_line("join_units", building="b"), "a join_units needs units"),
        (join("b", ["1", "2"], listing_id="5"), "a join_units takes no listing_id"),
        (unit_line("exclude", listing_id="5"), "change is one of join_units"),
        (unit_line("retract", entry="abc"), "entry is the 16 hex digits"),
    ],
)
def test_parse_unit_refuses(text, error):
    with pytest.raises(ledger.LedgerError, match=error):
        ledger.parse_unit(text)


def test_read_units_refuses(tmp_path):
    """Each case is a file of its own, read alone. The message gives the file and line."""
    a = join("b", ["1", "2"])
    s = split("b", "1", ["5", "6"])
    m = move("b", "c")
    cases = {
        "repeat": ([a, a], "x.ndjson:2: repeats x.ndjson:1"),
        "page twice": (
            [a, join("b", ["2", "3"])],
            "x.ndjson:2: the page https://streeteasy.com/building/b/2 is in the join at x.ndjson:1",
        ),
        "ad twice": (
            [s, split("b", "2", ["6"])],
            "x.ndjson:2: ad 6 is in the split at x.ndjson:1",
        ),
        "moves twice": ([m, move("b", "d")], "x.ndjson:2: b moves at x.ndjson:1"),
        "moves to a moved building": (
            [m, move("a", "b")],
            "x.ndjson:2: b moves at x.ndjson:1, so nothing moves to it",
        ),
        "moves a target": (
            [m, move("c", "d")],
            "x.ndjson:2: c takes the move at x.ndjson:1, so it stays where it is",
        ),
        "retract later": (
            [retract(a), a],
            "x.ndjson:1: retracts .*, which is no earlier unit entry",
        ),
        "retract twice": (
            [a, retract(a), retract(a) + " "],
            "x.ndjson:3: .* is retracted at x.ndjson:2",
        ),
        "unbacked": (
            [split("b", "1", ["5"], evidence=[QUOTE])],
            "x.ndjson:1: a split_unit needs",
        ),
        "into no split": (
            [split("b", "2", ["7"], into="9")],
            "x.ndjson:1: ad 9 is in no earlier split of b in force without an into",
        ),
        "into a later split": (
            [split("b", "2", ["7"], into="6"), s],
            "x.ndjson:1: ad 6 is in no earlier split of b",
        ),
        "into another building": (
            [s, split("c", "2", ["7"], into="6")],
            "x.ndjson:2: ad 6 is in no earlier split of c",
        ),
        "into a pointing split": (
            [s, split("b", "2", ["7"], into="6"), split("b", "3", ["8"], into="7")],
            "x.ndjson:3: ad 7 is in no earlier split of b",
        ),
        "into a retracted split": (
            [s, retract(s), split("b", "2", ["7"], into="6")],
            "x.ndjson:3: ad 6 is in no earlier split of b",
        ),
        "retract a split pointed into": (
            [s, split("b", "2", ["7"], into="6"), retract(s)],
            "x.ndjson:3: the split at x.ndjson:2 points into x.ndjson:1, so it stays",
        ),
    }
    for name, (lines, error) in cases.items():
        folder = tmp_path / name.replace(" ", "-")
        with pytest.raises(ledger.LedgerError, match=error):
            ledger.read_units([write(folder, "x.ndjson", lines)])


def test_read_units_frees_a_retracted_entrys_claims(tmp_path):
    """After a retract, another entry may take the retracted entry's pages, ads and moves."""
    a, s, m = join("b", ["1", "2"]), split("b", "1", ["5"]), move("b", "c")
    first = write(tmp_path, "1.ndjson", [a, s, m, retract(a), retract(s), retract(m)])
    second = write(
        tmp_path,
        "2.ndjson",
        [join("b", ["2", "3"]), split("b", "2", ["5"]), move("c", "b")],
    )
    rows = ledger.read_units([second, first])
    assert [(row["file"], row["line"], row["seq"]) for row in rows] == [
        *(("1.ndjson", n, n) for n in range(1, 7)),
        *(("2.ndjson", n, n + 6) for n in range(1, 4)),
    ]
    assert [row["building"] for row in rows[3:6]] == ["b", "b", "b"]
    assert rows[0]["pages"] == [
        "https://streeteasy.com/building/b/1",
        "https://streeteasy.com/building/b/2",
    ]


def test_read_units_points_into_a_split(tmp_path):
    """A split with an `into` gives the entry of the split it points into. Once it is retracted,
    the split it pointed into can be retracted too."""
    s = split("b", "1", ["5", "6"])
    pointing = split("b", "2", ["7"], into="6")
    rows = ledger.read_units(
        [write(tmp_path, "x.ndjson", [s, pointing, retract(pointing), retract(s)])]
    )
    assert [(row["into_ad"], row["into_entry"]) for row in rows[:2]] == [
        (None, None),
        ("6", ledger.entry_id(s)),
    ]


def test_unit_ledger_cases(tmp_path, monkeypatch):
    """The fixture holds five buildings. The unit ledger's entries:
    - join: the two units of 89 Adelphi Street.
    - join absent: a unit of 260 West 91st Street and a unit with no ads.
    - join retracted: units 14 and 16 of 270 15th Street, retracted later. Unit 14 then joins
      unit 6 in a later file.
    - split: two ads of unit 14, the greater listed first, so the new unit ends with the first
      listed ad rather than the lesser one, then an ad with no record. Unit 14 joins unit 6 in
      the later file, so the split ads start from the joined unit's ID.
    - split stale: an ad of unit 16 listed under unit 12, and an ad with no record.
    - split absent: an ad with no record alone.
    - split into: an ad of another unit of 270 15th Street, into the split's ad with no record,
      so its unit comes from the split's other ads.
    - split into stale: an ad of 129 West 89th Street, into the absent split's ad.
    - move: 1115 Union Street to 260 West 91st Street, a building with a record.
    - move stale: to a slug of no building.
    - move absent: a building with no ads.
    """
    folder = tmp_path / "ledger"
    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    ctx.plan(auto_apply=True, no_prompts=True)
    # Without a unit ledger, ads.placed repeats ads.identity.
    (differ,) = ctx.engine_adapter.fetchone(
        """SELECT count(*) FROM (
            (SELECT * EXCLUDE (placements) FROM ads.placed
                EXCEPT ALL SELECT * FROM ads.identity)
            UNION ALL
            (SELECT * FROM ads.identity
                EXCEPT ALL SELECT * EXCLUDE (placements) FROM ads.placed)
        )"""
    )
    (placed,) = ctx.engine_adapter.fetchone(
        "SELECT count(*) FROM ads.placed WHERE placements <> []"
    )
    assert (differ, placed) == (0, 0)
    identity = ctx.fetchdf("SELECT * FROM ads.identity")

    def units(building):
        return sorted(
            identity[identity.building == building]
            .page.str.rsplit("/", n=1)
            .str[1]
            .unique()
        )

    def ads(building, unit):
        on_page = identity.building.eq(building) & identity.page.str.endswith(
            "/" + unit
        )
        return sorted(identity.listing_id[on_page & identity.unit_id.notna()])

    adelphi = "89-adelphi-street-brooklyn"
    west_91 = "260-west-91-street-new_york"
    union = "1115-union-street-brooklyn"
    west_89 = "129-west-89-street-new_york"
    fifteenth = "270-15-street-brooklyn"
    split_ads = ads(fifteenth, "14")[::-1][:2]
    assert len(split_ads) == 2
    into_unit, into_ad = next(
        (unit, ad)
        for unit in units(fifteenth)
        if unit not in ("14", "6")
        for ad in ads(fifteenth, unit)
        if ad != "1342669"
    )
    stale_unit = units(west_89)[0]
    (stale_ad, *_) = ads(west_89, stale_unit)
    entries = {
        "join": join(adelphi, units(adelphi)),
        "join absent": join(west_91, [units(west_91)[0], "no-such-unit"]),
        "join retracted": join(fifteenth, ["14", "16"]),
        "split": split(fifteenth, "14", [*split_ads, "3"]),
        "split stale": split(fifteenth, "12", ["1", "1342669"]),
        "split absent": split(west_89, "1a", ["2"]),
        "split into": split(fifteenth, into_unit, [into_ad], into="3"),
        "split into stale": split(west_89, stale_unit, [stale_ad], into="2"),
        "move": move(union, west_91),
        "move stale": move(west_89, "no-such-building"),
        "move absent": move("no-such-building-either", fifteenth),
    }
    later = {
        "retract": retract(entries["join retracted"]),
        "join later": join(fifteenth, ["14", "6"]),
    }
    write(folder / "units", "2026-10-17-cases.ndjson", entries.values())
    write(folder / "units", "2026-10-18-later.ndjson", later.values())

    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    # A unit entry changes the units and buildings of ads, so every step after ads.identity
    # that reads them builds again.
    assert changed(plan) == [
        "ads.placed",
        "analysis.ads",
        "analysis.ask_check",
        "analysis.building_certificates",
        "analysis.building_check",
        "analysis.candidates",
        "analysis.kept",
        "analysis.latest_ask",
        "analysis.latest_change",
        "analysis.lot_facts",
        "analysis.lot_landmarks",
        "analysis.rows",
        "ledger.status",
        "ledger.unit_entries",
        "ledger.unit_status",
    ]
    status = ctx.fetchdf("SELECT * FROM ledger.unit_status")
    ids = {name: ledger.entry_id(text) for name, text in {**entries, **later}.items()}
    assert dict(zip(status.entry, zip(status.status, status.differs))) == {
        ids["join"]: ("live", ""),
        ids["join absent"]: ("absent", ""),
        ids["join retracted"]: ("retracted", ""),
        ids["split"]: ("live", ""),
        ids["split stale"]: ("stale", "1342669"),
        ids["split absent"]: ("absent", ""),
        ids["split into"]: ("live", ""),
        ids["split into stale"]: ("stale", "into"),
        ids["move"]: ("live", ""),
        ids["move stale"]: ("stale", "to"),
        ids["move absent"]: ("absent", ""),
        ids["retract"]: ("retract", ""),
        ids["join later"]: ("live", ""),
    }

    placed = ctx.fetchdf("SELECT * FROM ads.placed").set_index("listing_id")
    before = identity.set_index("listing_id")
    page = before.page.str.rsplit("/", n=1).str[1]
    expected = before.copy()
    placements = {ad: [] for ad in before.index}
    for entry, joined in (
        ("join", before.building.eq(adelphi)),
        ("join later", before.building.eq(fifteenth) & page.isin(["14", "6"])),
    ):
        expected.loc[joined, "unit_id"] = before.unit_id[joined].min()
        for ad in before.index[joined]:
            placements[ad].append(ids[entry])
    # The joins come first, so the split ads start from unit 6's ID, the lesser of the join.
    assert (expected.unit_id[split_ads] != before.unit_id[split_ads]).all()
    for ad in split_ads:
        expected.loc[ad, "unit_id"] += "~review-" + split_ads[0]
        placements[ad].append(ids["split"])
    # The pointing split's ad takes the split's unit, whatever its own page.
    expected.loc[into_ad, "unit_id"] = expected.unit_id[split_ads[0]]
    placements[into_ad].append(ids["split into"])
    moved = before.building.eq(union)
    (west_91_id,) = before.building_id[before.building.eq(west_91)].unique()
    expected.loc[moved, ["building", "building_id"]] = [west_91, west_91_id]
    for ad in before.index[moved]:
        placements[ad].append(ids["move"])
    expected["placements"] = [sorted(placements[ad]) for ad in expected.index]
    placed["placements"] = placed.placements.map(list)
    placed["reasons"] = placed.reasons.map(list)
    expected["reasons"] = expected.reasons.map(list)
    got = placed.sort_index().to_dict("index")
    want = expected.sort_index()[placed.columns].to_dict("index")
    assert [
        (ad, column, got[ad][column], want[ad][column])
        for ad in want
        for column in placed.columns
        if got[ad][column] != want[ad][column]
    ] == []

    # The unit-month check and the ads file take the units and buildings of ads.placed.
    (differ,) = ctx.engine_adapter.fetchone(
        """SELECT count(*) FROM analysis.candidates c JOIN ads.placed p USING (listing_id)
        WHERE (c.unit_id, c.building, c.building_id) IS DISTINCT FROM
            (p.unit_id, p.building, p.building_id)"""
    )
    (unplaced,) = ctx.engine_adapter.fetchone(
        """SELECT count(*) FROM analysis.ads a JOIN ads.placed p USING (listing_id)
        WHERE (a.unit_id, a.building, a.placements) IS DISTINCT FROM
            (p.unit_id, p.building, p.placements)"""
    )
    assert (differ, unplaced) == (0, 0)
