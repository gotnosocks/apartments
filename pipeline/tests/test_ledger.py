import importlib.util
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest
import sqlmesh.core.console
from sqlmesh.utils.errors import PlanError

PROJECT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
context, changed, latest_ask = helpers.context, helpers.changed, helpers.latest_ask
ledger = load("ledger_entries", PROJECT / "models" / "ledger" / "entries.py")

OTHER_AD = {
    "kind": "other_ad",
    "listing_id": "123",
    "detail": "the same unit, a year later",
}
QUOTE = {"kind": "ad_text", "quote": "spacious one bedroom"}
CITY = {"kind": "city_record", "detail": "MapPLUTO gives the lot 2 floors"}
LOT = "1000010001"


def line(**keys):
    return json.dumps({"decided": "2026-10-16", "evidence": [OTHER_AD], **keys})


def exclude(listing_id, when=None, **keys):
    return line(
        change="exclude",
        listing_id=listing_id,
        reason="nonresidential",
        when=when or {},
        **keys,
    )


def set_(listing_id, values, when, **keys):
    return line(change="set", listing_id=listing_id, set=values, when=when, **keys)


def drop_lot(listing_id, bbl=LOT, **keys):
    return json.dumps(
        {
            "change": "drop_lot",
            "listing_id": listing_id,
            "reason": "wrong_building",
            "when": {"bbl": bbl},
            "evidence": [CITY],
            "decided": "2026-10-17",
        }
        | keys
    )


def retract(text):
    return line(change="retract", entry=ledger.entry_id(text))


def write(folder, name, lines):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("".join(text + "\n" for text in lines))
    return folder / name


@pytest.mark.parametrize(
    "text, error",
    [
        ("[1]", "a line holds a JSON object"),
        (line(change="drop", listing_id="1"), "change is one of"),
        (
            exclude("1").replace('"reason": "nonresidential", ', ""),
            "an exclude needs reason",
        ),
        (exclude("1", rows=3), "an exclude takes no rows"),
        (
            line(change="exclude", listing_id="1", reason="x", evidence=[]),
            "evidence is a list",
        ),
        (exclude("1", evidence=[{"quote": "x"}]), "each item of evidence has a kind"),
        (
            exclude("1", evidence=[{"kind": "ad_text"}]),
            "ad_text evidence gives its quote",
        ),
        (exclude("1", evidence=[{"kind": "owner", "detail": " "}]), "gives its detail"),
        (exclude("1", evidence=[{"kind": "floor_plan"}]), "gives its plan or detail"),
        (
            exclude("1", evidence=[{"kind": "other_ad", "detail": "x"}]),
            "other_ad evidence gives its ads' IDs as listing_id or listings",
        ),
        (
            exclude("1", evidence=[{**OTHER_AD, "listings": ["2", "x"]}]),
            "other_ad evidence gives its ads' IDs",
        ),
        (
            exclude("1", evidence=[{"kind": "line_units", "detail": "x"}]),
            "line_units evidence gives its ads' IDs as listings",
        ),
        (
            exclude("123"),
            "other_ad evidence gives other ads than the entry's own",
        ),
        (exclude("1", decided="16 Oct"), "decided is a day"),
        (exclude("1", decided="20261016"), "decided is a day"),
        (exclude("1", when={"period": "2019-8"}), "when.period takes a month"),
        (exclude("1", when={"period": "2019-13"}), "when.period is no month"),
        (exclude("1", when={"bedrooms": float("inf")}), "Infinity is no number"),
        (
            exclude("1", when={"bedrooms": 5}).replace(": 5}", ": 1e400}"),
            "takes a finite number",
        ),
        (exclude("1", when={"rent": 3000}), "when maps some of"),
        (exclude("ad 1"), "listing_id is the ad's ID"),
        (exclude("\u00b2"), "listing_id is the ad's ID"),
        (
            set_("1", {"bedrooms": 2}, {"bedrooms": 1}, evidence=[QUOTE]),
            "a set needs evidence",
        ),
        (
            set_(
                "1",
                {"bedrooms": 2},
                {"bedrooms": 1},
                evidence=[QUOTE, {"kind": "read", "detail": "the reader agrees"}],
            ),
            "a set needs evidence",
        ),
        (
            set_("1", {"bedrooms": 2}, {"period": "2019-08"}),
            "the recorded bedrooms in when",
        ),
        (set_("1", {"full_baths": 2}, {"full_baths": 1}), "a set gives one of"),
        (
            set_("1", {"full_baths": 1.5, "half_baths": 0}, {}),
            "full_baths takes a whole",
        ),
        (
            set_("1", {"square_feet": 0}, {"square_feet": None}),
            "square_feet takes a value above 0",
        ),
        (
            set_("1", {"latest_ask": 0}, {"latest_ask": 31000}),
            "latest_ask takes a value above 0",
        ),
        (
            set_("1", {"latest_ask": 3100}, {"period": "2015-02"}),
            "the recorded latest_ask in when",
        ),
        (
            set_(
                "1",
                {"latest_ask": 3100},
                {"latest_ask": 31000},
                evidence=[
                    {"kind": "stated_size", "detail": "500 square feet"},
                    {"kind": "line_units", "listings": ["2"], "detail": "asks $3,000"},
                ],
            ),
            "a set needs evidence of a backing kind for latest_ask",
        ),
        (set_("1", {"square_feet": float("nan")}, {"square_feet": None}), "NaN is no"),
        (set_("1", {"bedrooms": 1.5}, {"bedrooms": 1}), "bedrooms takes a whole"),
        (set_("1", {"bedrooms": -1}, {"bedrooms": 1}), "at least 0"),
        (set_("1", [2], {"bedrooms": 1}), "a set gives one of"),
        (line(change="retract", entry="abc"), "entry is the 16 hex digits"),
        (
            line(change="retract", entry="0" * 16, when={"bedrooms": 1}),
            "a retract takes no when",
        ),
        (set_("1", {"bedrooms": 10**400}, {"bedrooms": 1}), "finite number"),
        (
            set_(
                "1",
                {"full_baths": 2**53, "half_baths": 0},
                {"full_baths": 1, "half_baths": 0},
            ),
            "takes a number below",
        ),
        (set_("1", {"bedrooms": 2.0**53}, {"bedrooms": 1}), "takes a number below"),
        (
            drop_lot("1", evidence=[OTHER_AD, QUOTE]),
            "a drop_lot needs evidence of a backing",
        ),
        (drop_lot("1", reason=""), "a drop_lot gives its reason"),
        (drop_lot("1", when={}), "a drop_lot gives the lot it takes away"),
        (
            json.dumps(
                {k: v for k, v in json.loads(drop_lot("1")).items() if k != "when"}
            ),
            "a drop_lot needs when",
        ),
        (
            drop_lot("1", when={"bbl": LOT, "period": "2019-08"}),
            "drop_lot's when maps some of bbl to values",
        ),
        (drop_lot("1", set={"bedrooms": 1}), "a drop_lot takes no set"),
        (drop_lot("1", "100001000"), "when.bbl takes a lot as 10 digits"),
        (drop_lot("1", int(LOT)), "when.bbl takes a lot as 10 digits"),
        (drop_lot("1", "6000010001"), "when.bbl takes a lot as 10 digits"),
        (exclude("1", {"bbl": LOT}), "exclude's when maps some of period"),
    ],
)
def test_parse_refuses(text, error):
    with pytest.raises(ledger.LedgerError, match=error):
        ledger.parse(text)


def test_parse_reads_a_drop_lot():
    row = ledger.parse(drop_lot("1", note="the ad's building is next door"))
    assert row["change"] == "drop_lot" and row["reason"] == "wrong_building"
    assert row["when_keys"] == ["bbl"] and row["when_bbl"] == LOT
    assert row["kinds"] == ["city_record"] and row["field"] is None


def test_parse_keeps_null_recorded_values():
    row = ledger.parse(set_("1", {"square_feet": 600}, {"square_feet": None}))
    assert row["when_keys"] == ["square_feet"] and row["when_square_feet"] is None
    assert row["field"] == "square_feet" and row["square_feet"] == 600.0


def test_parse_takes_whole_numbers_below_2_53():
    largest = 2**53 - 1
    row = ledger.parse(set_("1", {"bedrooms": largest}, {"bedrooms": 1}))
    assert row["bedrooms"] == largest
    values = {"full_baths": largest, "half_baths": 0}
    row = ledger.parse(set_("1", values, {"full_baths": 1, "half_baths": 0}))
    assert row["full_baths"] == largest


def test_read_refuses(tmp_path):
    first = exclude("1")
    cases = {
        "repeat": ([first, first], "b.ndjson:2: repeats b.ndjson:1"),
        "unknown": (
            [first, retract(exclude("2"))],
            "which is no earlier exclude, set or drop_lot",
        ),
        "twice": (
            [
                first,
                retract(first),
                line(change="retract", entry=ledger.entry_id(first), note="x"),
            ],
            "b.ndjson:3: .* is retracted at b.ndjson:2",
        ),
        "retracted retract": (
            [first, retract(first), retract(retract(first))],
            "no earlier",
        ),
        "bad line": ([first, "{"], "b.ndjson:2: not JSON"),
    }
    for name, (lines, error) in cases.items():
        path = write(tmp_path / name, "b.ndjson", lines)
        with pytest.raises(ledger.LedgerError, match=error):
            ledger.read([path])


def test_read_keeps_line_separators_in_strings(tmp_path):
    """JSON allows U+2028 inside a string, and the line stays whole."""
    text = json.dumps(json.loads(exclude("1", note="a\u2028b")), ensure_ascii=False)
    [row] = ledger.read([write(tmp_path, "a.ndjson", [text])])
    assert row["note"] == "a\u2028b" and row["entry"] == ledger.entry_id(text)


def test_read_orders_files_by_name(tmp_path):
    first = exclude("1")
    later = write(tmp_path, "2026-10-17.ndjson", [retract(first)])
    earlier = write(tmp_path, "2026-10-16.ndjson", ["", first])
    rows = ledger.read([later, earlier])
    assert [(r["file"], r["line"], r["seq"], r["change"]) for r in rows] == [
        ("2026-10-16.ndjson", 2, 1, "exclude"),
        ("2026-10-17.ndjson", 1, 2, "retract"),
    ]
    assert rows[1]["listing_id"] == "1"


def test_ledger_cases(tmp_path, monkeypatch):
    """The ledger excludes ads and sets values on the kept rows of the fixture:

    - a: an exclude with the row's month applies, and a second exclude of a, retracted later,
      changes nothing.
    - b: an exclude with another month goes stale.
    - c: two bedroom sets, and the later one applies.
    - d: a size set applies, and its retract undoes it.
    - e: a bath set gives the full and half bathrooms and leaves `bathrooms` as it was.
    - f: a bedroom set made on another bedroom count goes stale.
    - g: a size set on a row with no size applies, as its `when` gives null.
    - h: a size set on a row with a size applies.
    - i: an exclude with the row's latest ask applies.
    - j: an exclude with ten times the row's latest ask goes stale.
    - an exclude of an ad with no kept row stays absent.
    - k: a drop_lot with the lot of the row's building applies, and analysis.lot_facts gives
      the ad no lot, BIN or facts.
    - l: a drop_lot with another lot goes stale.
    - m: a drop_lot retracted later changes nothing.

    Only the two ledger models, analysis.ask_check, analysis.lot_facts, analysis.building_check
    and the views analysis.rows and analysis.ads build again, and analysis.latest_ask stays as it
    was."""
    folder = tmp_path / "ledger"
    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    ctx.plan(auto_apply=True, no_prompts=True)
    before = latest_ask(ctx)
    lots_before = ctx.fetchdf("SELECT * FROM analysis.lot_facts ORDER BY listing_id")
    kept = ctx.fetchdf(
        """SELECT *, strftime(period, '%Y-%m') AS month FROM analysis.kept
        WHERE half_baths IS NOT NULL ORDER BY listing_id LIMIT 6"""
    )
    a, b, c, d, e, f = (row for _, row in kept.iterrows())
    sqft = None if pd.isna(d.square_feet) else d.square_feet
    others = tuple(kept.listing_id)
    g, h = (
        ctx.fetchdf(
            f"""SELECT * FROM analysis.kept WHERE listing_id NOT IN {others}
            AND square_feet IS {sized} NULL ORDER BY listing_id LIMIT 1"""
        ).iloc[0]
        for sized in ("", "NOT")
    )
    others = (*others, g.listing_id, h.listing_id)
    i, j = (
        row
        for _, row in ctx.fetchdf(
            f"""SELECT k.listing_id, strftime(k.period, '%Y-%m') AS month, a.latest_ask
            FROM analysis.kept k JOIN analysis.latest_ask a USING (listing_id)
            WHERE listing_id NOT IN {others} ORDER BY listing_id LIMIT 2"""
        ).iterrows()
    )
    others = (*others, i.listing_id, j.listing_id)
    k, l, m = (
        row
        for _, row in ctx.fetchdf(
            f"""SELECT k.listing_id, l.bbl FROM analysis.kept k JOIN buildings.lots l
            USING (building_id)
            WHERE listing_id NOT IN {others} AND l.bbl IS NOT NULL ORDER BY listing_id LIMIT 3"""
        ).iterrows()
    )
    other_lot = str(int(l.bbl) + 1)
    entries = {
        "a": exclude(a.listing_id, {"period": a.month}),
        "a twice": exclude(a.listing_id, {"bedrooms": a.bedrooms}, note="twice"),
        "b": exclude(b.listing_id, {"period": "1999-01"}),
        "c": set_(c.listing_id, {"bedrooms": 7}, {"bedrooms": c.bedrooms}),
        "c later": set_(c.listing_id, {"bedrooms": 8}, {"bedrooms": c.bedrooms}),
        "d": set_(d.listing_id, {"square_feet": 999}, {"square_feet": sqft}),
        "e": set_(
            e.listing_id,
            {"full_baths": 5, "half_baths": 1},
            {"full_baths": int(e.full_baths), "half_baths": int(e.half_baths)},
        ),
        "f": set_(f.listing_id, {"bedrooms": 9}, {"bedrooms": f.bedrooms + 1}),
        "g": set_(g.listing_id, {"square_feet": 600}, {"square_feet": None}),
        "h": set_(h.listing_id, {"square_feet": 999}, {"square_feet": h.square_feet}),
        "i": exclude(i.listing_id, {"period": i.month, "latest_ask": i.latest_ask}),
        "j": exclude(j.listing_id, {"latest_ask": j.latest_ask * 10}),
        "absent": exclude("1", {"period": "2019-08"}),
        "k": drop_lot(k.listing_id, k.bbl),
        "l": drop_lot(l.listing_id, other_lot),
        "m": drop_lot(m.listing_id, m.bbl),
    }
    lines = list(entries.values())
    write(folder, "2026-10-16-cases.ndjson", lines)
    write(
        folder,
        "2026-10-17-retracts.ndjson",
        [retract(entries["a twice"]), retract(entries["d"]), retract(entries["m"])],
    )

    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "analysis.ads",
        "analysis.ask_check",
        "analysis.building_check",
        "analysis.lot_facts",
        "analysis.rows",
        "ledger.entries",
        "ledger.status",
    ]
    status = ctx.fetchdf("SELECT * FROM ledger.status ORDER BY file, line")
    ids = {name: ledger.entry_id(text) for name, text in entries.items()}
    assert dict(zip(status.entry, zip(status.status, status.differs))) == {
        ids["a"]: ("live", ""),
        ids["a twice"]: ("retracted", ""),
        ids["b"]: ("stale", "period"),
        ids["c"]: ("superseded", ""),
        ids["c later"]: ("live", ""),
        ids["d"]: ("retracted", ""),
        ids["e"]: ("live", ""),
        ids["f"]: ("stale", "bedrooms"),
        ids["g"]: ("live", ""),
        ids["h"]: ("live", ""),
        ids["i"]: ("live", ""),
        ids["j"]: ("stale", "latest_ask"),
        ids["absent"]: ("absent", ""),
        ids["k"]: ("live", ""),
        ids["l"]: ("stale", "bbl"),
        ids["m"]: ("retracted", ""),
        **{
            ledger.entry_id(retract(entries[name])): ("retract", "")
            for name in ("a twice", "d", "m")
        },
    }
    lots = ctx.fetchdf("SELECT * FROM analysis.lot_facts ORDER BY listing_id")
    dropped = lots.listing_id == k.listing_id
    assert lots[dropped].lot_entry.tolist() == [ids["k"]]
    facts = lots.columns.drop(["listing_id", "building_id", "lot_entry"])
    assert lots[dropped][facts].isna().all(axis=None)
    assert lots_before[lots_before.listing_id == k.listing_id].bbl.tolist() == [k.bbl]
    pd.testing.assert_frame_equal(
        lots[~dropped].drop(columns="lot_entry").reset_index(drop=True),
        lots_before[lots_before.listing_id != k.listing_id]
        .drop(columns="lot_entry")
        .reset_index(drop=True),
        check_dtype=False,
    )

    (count,) = ctx.engine_adapter.fetchone(
        "SELECT (SELECT count(*) FROM analysis.kept) - (SELECT count(*) FROM analysis.rows)"
    )
    assert count == 2
    (count,) = ctx.engine_adapter.fetchone(
        """SELECT count(*) FROM analysis.rows r JOIN analysis.latest_ask a USING (listing_id)
        WHERE r.latest_ask IS DISTINCT FROM a.latest_ask"""
    )
    assert count == 0
    differ = ctx.fetchdf(
        """SELECT listing_id, bedrooms, full_baths, half_baths, bathrooms, square_feet
        FROM (
            SELECT * EXCLUDE (latest_ask, relist_unit) FROM analysis.rows
            EXCEPT SELECT * FROM analysis.kept
        )
        ORDER BY listing_id"""
    )
    rows = {
        c.listing_id: [8, c.full_baths, c.half_baths, c.bathrooms, c.square_feet],
        e.listing_id: [e.bedrooms, 5, 1, e.bathrooms, e.square_feet],
        g.listing_id: [g.bedrooms, g.full_baths, g.half_baths, g.bathrooms, 600],
        h.listing_id: [h.bedrooms, h.full_baths, h.half_baths, h.bathrooms, 999],
    }
    expected = pd.DataFrame(
        [[key, *values] for key, values in sorted(rows.items())], columns=differ.columns
    )
    pd.testing.assert_frame_equal(differ, expected, check_dtype=False)
    pd.testing.assert_frame_equal(latest_ask(ctx), before)


def test_unbacked_set_stops_the_build(tmp_path, monkeypatch):
    """A set backed by the ad's words alone stops the plan at ledger.entries."""
    folder = tmp_path / "ledger"
    write(
        folder,
        "2026-10-16.ndjson",
        [set_("1", {"bedrooms": 2}, {"bedrooms": 1}, evidence=[QUOTE])],
    )
    console = helpers.Failures()
    monkeypatch.setattr(sqlmesh.core.console, "_CONSOLE", console)
    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    with pytest.raises(PlanError):
        ctx.plan(auto_apply=True, no_prompts=True)
    [error] = console.failed
    assert error.node.snapshot_name == '"pipeline"."ledger"."entries"'
    assert "2026-10-16.ndjson:1: a set needs evidence" in str(error.__cause__)


def git(*args):
    return subprocess.run(
        ["git", "-C", str(PROJECT), *args], capture_output=True, text=True, check=True
    ).stdout


def test_repo_ledger_reads():
    """The repo's corrections ledger and unit ledger follow the rules."""
    ledger.read(sorted((PROJECT / "ledger").glob("*.ndjson")))
    ledger.read_units(sorted((PROJECT / "ledger" / "units").glob("*.ndjson")))


def test_repo_unit_ledger_holds_entries():
    """The repo's unit ledger holds joins, splits and a move, each passing read_units."""
    rows = ledger.read_units(sorted((PROJECT / "ledger" / "units").glob("*.ndjson")))
    changes = {row["change"] for row in rows}
    assert {"join_units", "split_unit", "move_building"} <= changes


@pytest.mark.parametrize("folder", ["ledger", "ledger/units"])
def test_repo_ledger_only_grows(folder):
    """Each ledger file at the merge base with master stays as it was, and each new file sorts
    after master's files in its folder, including those merged since the branch left it. A line
    appended to an old file would sort before the entries of later files."""
    try:
        base = git("merge-base", "HEAD", "origin/master").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no merge base with origin/master")

    def files(commit):
        listed = git("ls-tree", "--name-only", commit, f"{folder}/").split()
        return [name for name in listed if name.endswith(".ndjson")]

    names = files(base)
    for name in names:
        old = git("show", f"{base}:pipeline/{name}")
        path = PROJECT / name
        assert path.exists(), f"{name} is gone"
        assert path.read_text() == old, f"{name} changed after its merge"
    # The ledger applies files in the order of their names.
    tip = files("origin/master")
    last = max((Path(name).name for name in names + tip), default="")
    for path in (PROJECT / folder).glob("*.ndjson"):
        if f"{folder}/{path.name}" not in names + tip:
            assert path.name > last, f"{path.name} sorts before {last}"


def importer():
    spec = importlib.util.spec_from_file_location(
        "ledger_import", PROJECT.parent / "ops" / "pipeline" / "ledger_import.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_drop_lot_import(tmp_path, monkeypatch, capsys):
    """The drop-lot importer turns a review line into a drop_lot entry, leaves out a line
    already in the ledger and refuses to write over a file. With every line in the ledger, it
    writes no file. It refuses a line the ledger's parser refuses, before writing anything."""
    spec = importlib.util.spec_from_file_location(
        "drop_lot_import", PROJECT.parent / "ops" / "pipeline" / "drop_lot_import.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / "pipeline" / "ledger"
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "LEDGER", folder)
    reviews = [
        {
            "listing_id": listing_id,
            "reason": "wrong_building",
            "bbl": LOT,
            "decided": "2026-10-17",
            "evidence": [
                {"kind": "lot_record", "detail": "zero_unit_lot: vacant lot"},
                {"kind": "ad_text", "detail": 'Ad text: "3rd floor walk-up"'},
                {"kind": "pad_lookup", "detail": "PAD gives another lot"},
            ],
            "note": "the ad is next door",
            "source": "labels.jsonl:4",
        }
        for listing_id in ("1", "2")
    ]
    path = tmp_path / "reviews.jsonl"
    path.write_text("".join(json.dumps(review) + "\n" for review in reviews))
    write(folder, "2026-10-16.ndjson", [drop_lot("1", source="reviews.jsonl:1")])

    assert module.main([str(path), "--name", "2026-10-17"]) == 0
    assert "1 entries, 1 already in the ledger" in capsys.readouterr().out
    [entry] = map(json.loads, (folder / "2026-10-17.ndjson").read_text().splitlines())
    assert entry == {
        "change": "drop_lot",
        "listing_id": "2",
        "reason": "wrong_building",
        "when": {"bbl": LOT},
        "evidence": [
            {"kind": "city_record", "detail": "zero_unit_lot: vacant lot"},
            {"kind": "ad_text", "quote": "3rd floor walk-up"},
            {"kind": "city_record", "detail": "PAD gives another lot"},
            {"kind": "read", "detail": "the ad is next door", "file": "labels.jsonl:4"},
        ],
        "decided": "2026-10-17",
        "source": "reviews.jsonl:2",
    }
    with pytest.raises(SystemExit, match="exists"):
        module.main([str(path), "--name", "2026-10-17"])
    capsys.readouterr()
    assert module.main([str(path), "--name", "2026-10-18"]) == 0
    assert "all 2 lines already in the ledger" in capsys.readouterr().out
    assert not (folder / "2026-10-18.ndjson").exists()
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(reviews[0] | {"bbl": "123"}) + "\n")
    with pytest.raises(SystemExit, match="bad.jsonl:1: "):
        module.main([str(bad), "--name", "2026-10-19"])
    assert not (folder / "2026-10-19.ndjson").exists()


@pytest.mark.parametrize(
    "stated, recorded, corrected, kind",
    [
        (800, 0, 1, "stated_size"),
        # Nearest a count past the corrected one.
        (1069, 0, 1, "stated_size"),
        (1400, 0, 2, "stated_size"),
        (1100, 3, 2, "stated_size"),
        # Nearer a count between the recorded and the corrected one, or the recorded one.
        (800, 0, 2, "read"),
        (500, 0, 1, "read"),
        # With no recorded count, the size has to lie nearest the corrected one.
        (800, None, 2, "read"),
        (1000, None, 2, "stated_size"),
        # No median for the corrected count, or for the recorded one.
        (2000, 0, 5, "read"),
        (1300, 4, 3, "read"),
    ],
)
def test_stated_size_rules_out_the_recorded_count(stated, recorded, corrected, kind):
    """The importer takes a stated size as backing when it lies nearer the corrected count's
    median than the medians of the recorded count and each count between them."""
    module = importer()
    medians = {0: 480, 1: 700, 2: 1000, 3: 1334}
    read = {
        "bedrooms": corrected,
        "second_signal": f"The unit's stated {stated:,} sq ft is in the ad.",
    }
    item = module.signal(read, medians, recorded)
    assert item["kind"] == kind
    # The item gives the medians the importer compared, and none of the reader's.
    assert item["square_feet"] == stated
    if kind == "stated_size":
        assert (
            f"median {corrected}-bedroom size ({medians[corrected]:,})"
            in item["detail"]
        )
    assert "is in the ad" not in item["detail"]


@pytest.mark.parametrize(
    "text, kind",
    [
        ("Stunning one bedroom with a windowed kitchen", "ad_text"),
        (
            "floor plan shows a studio with a divider wall (Ben, 2026-10-16)",
            "floor_plan",
        ),
        ("the video shows a second bedroom with a door (Ben, 2026-10-16)", "owner"),
        # A floor plan in the ad's own words stays the ad's words.
        ("Floor plan available on request, by Ben the agent", "ad_text"),
    ],
)
def test_rule_evidence(text, kind):
    """The importer takes a rule line's evidence as Ben's own reading when it gives his name and
    the day, and as the ad's words otherwise."""
    item = importer().rule_evidence(text)
    assert item["kind"] == kind
    assert item.get("quote", item.get("detail")) == text


def test_line_datasets_follow_the_base_rules(tmp_path, monkeypatch):
    """Each line of a correction file takes the dataset of the version adding it, and the
    lines a version repeats from its base rule take the base rule's datasets. A version adding
    all its lines ends the walk, as `bedrooms-ad-v4` to `v6` do, though they give a base."""
    module = importer()
    monkeypatch.setattr(module, "REPO", tmp_path)
    folder = tmp_path / "config" / "corrections"
    folder.mkdir(parents=True)

    def version(name, audits, given):
        text = "".join(json.dumps({"audit_id": audit}) + "\n" for audit in audits)
        (folder / f"{name}-20261016.jsonl").write_text(text)
        if given is not None:
            (folder / f"{name}-20261016.provenance.json").write_text(json.dumps(given))
        return f"config/corrections/{name}-20261016.jsonl"

    version(
        "rule-v1", ["a", "b"], {"dataset": "/d/one", "rows": 2, "base_rule": "rule-v0"}
    )
    version(
        "rule-v2",
        ["a", "b", "c"],
        {"dataset": "/d/two", "rows": 1, "base_rule": "rule-v1"},
    )
    v3 = version(
        "rule-v3",
        ["a", "b", "c", "d"],
        {"dataset": "/d/three", "rows": 1, "base_rule": "rule-v2"},
    )
    assert module.line_datasets(v3) == {
        1: "/d/one",
        2: "/d/one",
        3: "/d/two",
        4: "/d/three",
    }

    other = version(
        "rule-v4",
        ["a", "x", "e"],
        {"dataset": "/d/four", "rows": 1, "base_rule": "rule-v1"},
    )
    with pytest.raises(SystemExit, match="doesn't start with the lines"):
        module.line_datasets(other)
    bare = version("rule-v5", ["a"], None)
    with pytest.raises(SystemExit, match="no provenance file"):
        module.line_datasets(bare)
    short = version("rule-v6", ["a"], {"dataset": "/d/six", "rows": 2})
    with pytest.raises(SystemExit, match="fewer lines"):
        module.line_datasets(short)
    baseless = version("rule-v7", ["a", "b"], {"dataset": "/d/seven", "rows": 1})
    with pytest.raises(SystemExit, match="no base"):
        module.line_datasets(baseless)
    orphan = version(
        "rule-v8", ["a", "b"], {"dataset": "/d/eight", "rows": 1, "base_rule": "x"}
    )
    with pytest.raises(SystemExit, match="0 files for its base"):
        module.line_datasets(orphan)


@pytest.mark.parametrize(
    "period, month",
    [("2016-12", "2016-12"), ("2016-12-01", "2016-12"), ("2016-12-15", None)],
)
def test_quarantine_month(period, month):
    """A quarantine line gives its month as YYYY-MM or as the month's first day."""
    module = importer()
    if month is None:
        with pytest.raises(SystemExit):
            module.month(period)
    else:
        assert module.month(period) == month


@pytest.mark.parametrize(
    "note, source, first",
    [
        (
            'Ad text: "corner space huge windows. vented former restaurant".',
            "ask-check reads (pipeline #937 flags)",
            {
                "kind": "ad_text",
                "quote": "corner space huge windows. vented former restaurant",
            },
        ),
        (
            'Ad text: "two levels ... food is welcome."',
            "ask-check reads (pipeline #937 flags)",
            {"kind": "ad_text", "quote": "two levels ... food is welcome."},
        ),
        (
            "Ask 33,333 for a 2BR is repeated digits; same unit asked $2,556 (2017)",
            "ask-check reads (pipeline #937 flags)",
            {
                "kind": "read",
                "detail": "Ask 33,333 for a 2BR is repeated digits; same unit asked $2,556 (2017)",
            },
        ),
        (
            "this is a 2 month sublet",
            "regex second pass over the API keep reads",
            {"kind": "ad_text", "quote": "this is a 2 month sublet"},
        ),
        (
            "short-term rental starts may 1, 2019 for 6 months only",
            None,
            {
                "kind": "ad_text",
                "quote": "short-term rental starts may 1, 2019 for 6 months only",
            },
        ),
    ],
)
def test_quarantine_evidence(note, source, first):
    """The importer files a quarantine note as a read when a reading pass wrote it without the
    `Ad text:` prefix, and as the ad's words otherwise, and puts the line's reason after it."""
    line = {"reason": "a reason", "evidence": note}
    if source:
        line["source"] = source
    assert importer().quarantine_evidence(line) == [
        first,
        {"kind": "read", "detail": "a reason"},
    ]
    assert importer().quarantine_evidence({"reason": "a reason"}) == [
        {"kind": "read", "detail": "a reason"}
    ]
