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
        (set_("1", {"square_feet": 0}, {"square_feet": None}), "a size above 0"),
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
    ],
)
def test_parse_refuses(text, error):
    with pytest.raises(ledger.LedgerError, match=error):
        ledger.parse(text)


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
            "which is no earlier exclude or set",
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
    - an exclude of an ad with no kept row stays absent.

    Only the two ledger models and the views analysis.rows and analysis.ads build again, and
    analysis.latest_ask stays as it was."""
    folder = tmp_path / "ledger"
    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    ctx.plan(auto_apply=True, no_prompts=True)
    before = latest_ask(ctx)
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
        "absent": exclude("1", {"period": "2019-08"}),
    }
    lines = list(entries.values())
    write(folder, "2026-10-16-cases.ndjson", lines)
    write(
        folder,
        "2026-10-17-retracts.ndjson",
        [retract(entries["a twice"]), retract(entries["d"])],
    )

    ctx = context(monkeypatch, tmp_path / "state", ledger=folder)
    plan = ctx.plan(auto_apply=True, no_prompts=True)
    assert changed(plan) == [
        "analysis.ads",
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
        ids["absent"]: ("absent", ""),
        ledger.entry_id(retract(entries["a twice"])): ("retract", ""),
        ledger.entry_id(retract(entries["d"])): ("retract", ""),
    }

    (count,) = ctx.engine_adapter.fetchone(
        "SELECT (SELECT count(*) FROM analysis.kept) - (SELECT count(*) FROM analysis.rows)"
    )
    assert count == 1
    differ = ctx.fetchdf(
        """SELECT listing_id, bedrooms, full_baths, half_baths, bathrooms, square_feet
        FROM (SELECT * FROM analysis.rows EXCEPT SELECT * FROM analysis.kept)
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
    """The repo's ledger follows the rules."""
    ledger.read(sorted((PROJECT / "ledger").glob("*.ndjson")))


def test_repo_ledger_only_grows():
    """Each ledger file at the merge base with master stays as it was, and each new file sorts
    after master's files, including those merged since the branch left it. A line appended to
    an old file would sort before the entries of later files."""
    try:
        base = git("merge-base", "HEAD", "origin/master").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no merge base with origin/master")
    names = git("ls-tree", "--name-only", base, "ledger/").split()
    for name in names:
        old = git("show", f"{base}:pipeline/{name}")
        path = PROJECT / name
        assert path.exists(), f"{name} is gone"
        assert path.read_text() == old, f"{name} changed after its merge"
    # The ledger applies files in the order of their names.
    tip = git("ls-tree", "--name-only", "origin/master", "ledger/").split()
    last = max((Path(name).name for name in names + tip), default="")
    for path in (PROJECT / "ledger").glob("*.ndjson"):
        if f"ledger/{path.name}" not in names + tip:
            assert path.name > last, f"{path.name} sorts before {last}"


def importer():
    spec = importlib.util.spec_from_file_location(
        "ledger_import", PROJECT.parent / "ops" / "pipeline" / "ledger_import.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
