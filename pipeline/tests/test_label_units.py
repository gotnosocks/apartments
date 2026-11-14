import functools
import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from apartments.unit_spelling_aliases import normalize_label

MODELS = Path(__file__).parent.parent / "models"
PORT_DIFF = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "port_diff.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


labels = load("label_units", MODELS / "analysis" / "label_units.py")

# The rows in the order of their ads: page unit, building, label and bedrooms, then the unit a
# split of the unit ledger gives the row, if any. The comments give the layer expected to join
# each case.
ROWS = [
    # labels: one label written three ways, and a split of the first unit by the unit ledger.
    ("u:01", "b1", "4-b", 2),
    ("u:01", "b1", "4-b", 2, "u:01~review-7"),
    ("u:02", "b1", "4b", 2),
    ("u:03", "b1", "apt-4b", 2),
    # aliases: a group with u:12, a unit with no rows, which a history pair confirms. The
    # second group has no pair, so it stays apart.
    ("u:10", "b1", "ph04", 3),
    ("u:11", "b1", "ph4", 3),
    ("u:13", "b1", "r01", 1),
    ("u:14", "b1", "r1", 1),
    # words: "four" and "third-fl" join; "five" has other bedrooms than "5".
    ("u:20", "b1", "four", 1),
    ("u:21", "b1", "4", 1),
    ("u:22", "b1", "five", 1),
    ("u:23", "b1", "5", 2),
    ("u:24", "b1", "third-fl", 1),
    ("u:25", "b1", "3fl", 1),
    # history: one pair joins; the others have other bedrooms or another building.
    ("u:30", "b1", "12c", 2),
    ("u:31", "b1", "12d", 2),
    ("u:32", "b1", "14c", 2),
    ("u:33", "b1", "14d", 3),
    ("u:34", "b2", "14c", 2),
    # swapped.
    ("u:40", "b2", "C7", 1),
    ("u:41", "b2", "7C", 1),
    # word_letters.
    ("u:50", "b2", "fiveb", 2),
    ("u:51", "b2", "5B", 2),
    # spelled: "GARDEN" and "G" stay apart, as the median of G's rows is 2.5.
    ("u:60", "b2", "3RDFL", 0),
    ("u:61", "b2", "3", 0),
    ("u:62", "b2", "PENTHOUSEA", 3),
    ("u:63", "b2", "PHA", 3),
    ("u:64", "b2", "GARDEN", 2),
    ("u:65", "b2", "G", 2),
    ("u:65", "b2", "G", 3),
    # A split with an ad of u:71's page and an ad of u:70's page, as the unit ledger's `into`
    # gives. Each ad counts for its page, so u:70 and u:72 join and u:71 stays apart.
    ("u:70", "b3", "2", 1),
    ("u:70", "b3", "2", 1, "u:71~review-9"),
    ("u:71", "b3", "3", 1, "u:71~review-9"),
    ("u:71", "b3", "3", 1),
    ("u:72", "b3", "02", 1),
]
PAIRS = [("u:30", "u:31"), ("u:32", "u:33"), ("u:32", "u:34"), ("u:11", "u:12")]
EXPECTED = {
    "u:01": ("u:01", 3, "labels"),
    "u:02": ("u:01", 3, "labels"),
    "u:03": ("u:01", 3, "labels"),
    "u:10": ("u:10", 2, "aliases"),
    "u:11": ("u:10", 2, "aliases"),
    "u:20": ("u:20", 2, "words"),
    "u:21": ("u:20", 2, "words"),
    "u:24": ("u:24", 2, "words"),
    "u:25": ("u:24", 2, "words"),
    "u:30": ("u:30", 2, "history"),
    "u:31": ("u:30", 2, "history"),
    "u:40": ("u:40", 2, "swapped"),
    "u:41": ("u:40", 2, "swapped"),
    "u:50": ("u:50", 2, "word_letters"),
    "u:51": ("u:50", 2, "word_letters"),
    "u:60": ("u:60", 2, "spelled"),
    "u:61": ("u:60", 2, "spelled"),
    "u:62": ("u:62", 2, "spelled"),
    "u:63": ("u:62", 2, "spelled"),
    "u:70": ("u:70", 2, "labels"),
    "u:72": ("u:70", 2, "labels"),
}


def page(building, label):
    return f"https://streeteasy.com/building/{building}/{label}"


def frame() -> pd.DataFrame:
    """The rows of ROWS with their page unit as `unit_id`, as the layers read them, and the unit
    the unit ledger gives them as `ledger_unit`."""
    rows = pd.DataFrame(
        [row[:4] for row in ROWS], columns=["unit_id", "building", "label", "bedrooms"]
    )
    rows["bedrooms"] = rows.bedrooms.astype(float)
    rows["ledger_unit"] = [row[4] if len(row) > 4 else row[0] for row in ROWS]
    return rows


def pages() -> list:
    """Each page unit's page in ads.placed."""
    found = {row[0]: page(row[1], row[2]) for row in ROWS}
    found["u:12"] = page("b1", "PH004")
    return sorted(found.items())


def page_frame() -> pd.DataFrame:
    """The pages of `pages` with their building and label, as the model reads them."""
    found = pd.DataFrame(pages(), columns=["unit_id", "page"])
    found[["building", "label"]] = found.page.str.extract(labels.PAGE)
    return found


class Fetcher:
    """Stands in for a SQLMesh context: it runs a Python model's queries on `db`, with each
    model's table under its own name, and gives the variables of `variables`."""

    def __init__(self, db, variables=None):
        self.db = db
        self.variables = variables or {}

    def resolve_table(self, name):
        return name

    def fetchdf(self, query):
        return self.db.sql(query).df()

    def var(self, name, default=None):
        return self.variables.get(name, default)


def test_alias_key_is_v2():
    words = [
        "PH04", "ph-004", "Apt 3B", "apartment12", "2nd-floor", "fl2", "Floor 3", "third",
        "THIRD-FL", "tenthfloor", "suite-5", "r01", "0", "00", "residence4c", "unit-ph", "-",
        "4-FLR", "unit 7", "11th", "1st-flr", "aptb", "ph-2-a", "garden",
    ]  # fmt: skip
    assert [labels.alias_key(w) for w in words] == [
        normalize_label(w, "unit-spelling-alias-v2") for w in words
    ]


def test_alias_groups():
    """The ph04 group holds u:12, a unit with no rows, and a pair confirms it. No pair joins
    the r01 group's units."""
    assert labels.alias_groups(page_frame(), PAIRS) == [("u:10", "u:11", "u:12")]


def test_layers_match_the_chain(tmp_path):
    """Each layer gives every row the unit the chain's step of `unit-labels-v17` gives it, run
    on the same rows with the same pairs and alias groups."""
    data = load("port_diff", PORT_DIFF).frontier()
    pairs_file, aliases_file = tmp_path / "pairs.jsonl", tmp_path / "aliases.jsonl"
    pairs_file.write_text(
        "".join(json.dumps({"unit_id": a, "other_unit_id": b}) + "\n" for a, b in PAIRS)
    )
    groups = labels.alias_groups(page_frame(), PAIRS)
    aliases_file.write_text(
        "".join(
            json.dumps({"alias_group_id": i, "unit_id": u, "history_confirmed": True})
            + "\n"
            for i, group in enumerate(groups)
            for u in group
        )
    )
    history = functools.partial(
        data.merge_history_pairs, pairs=pairs_file, aliases=aliases_file
    )
    swapped = functools.partial(data.merge_swapped_labels, base=history)
    letters = functools.partial(data.merge_word_letter_labels, base=swapped)
    steps = [
        data.merge_unit_labels,
        functools.partial(data.merge_unit_aliases, aliases=aliases_file),
        functools.partial(data.merge_word_labels, aliases=aliases_file),
        history,
        swapped,
        letters,
        functools.partial(data.merge_spelled_labels, base=letters),
    ]
    rows = frame().drop(columns="ledger_unit")
    chain = rows.assign(
        canonical_unit_url=[page(b, x) for b, x in zip(rows.building, rows.label)]
    )
    ours = labels.layers(rows, PAIRS, groups)
    for name, step, units in zip(labels.LAYERS, steps, ours):
        assert list(units) == list(step(chain).unit_id), name


def run_model(variables=None) -> pd.DataFrame:
    """The model's table, run on the rows of ROWS and the pairs of PAIRS with `variables`."""
    db = duckdb.connect()
    db.execute("CREATE SCHEMA analysis; CREATE SCHEMA ads")
    rows = frame()
    rows["listing_id"] = [str(1000 + i) for i in range(len(rows))]
    rows["page"] = [page(b, x) for b, x in zip(rows.building, rows.label)]
    db.register("frame", rows)
    db.execute(
        "CREATE TABLE analysis.ledger_rows AS "
        "SELECT listing_id, ledger_unit AS unit_id, building, page, bedrooms FROM frame"
    )
    db.execute(
        "CREATE TABLE analysis.history_pairs (unit_id VARCHAR, other_unit_id VARCHAR)"
    )
    db.executemany("INSERT INTO analysis.history_pairs VALUES (?, ?)", PAIRS)
    # The ads of the rows, and an ad of u:12, a unit with no rows.
    db.execute(
        "CREATE TABLE ads.placed AS "
        "SELECT listing_id, ledger_unit AS unit_id, page, unit_id AS page_unit FROM frame"
    )
    db.execute(
        "INSERT INTO ads.placed VALUES ('1', 'u:12', ?, 'u:12')", [page("b1", "PH004")]
    )
    (table,) = labels.execute.__wrapped__(Fetcher(db, variables), None, None, None)
    assert list(table.columns) == list(labels.COLUMNS)
    return table


def test_label_units_model():
    """The model joins page units. The rows of the unit ledger's splits keep their split's
    unit, which the table leaves out, so u:71's split, with an ad of u:70's page, joins neither
    u:70 nor u:71."""
    table = run_model()
    found = {r.unit_id: (r.label_unit, r.units, r.layer) for r in table.itertuples()}
    assert found == EXPECTED


def test_label_units_model_v18():
    """Under `unit-labels-v18`, the history pair of "12c" and "12d" stays apart, and every
    other unit joins as under v17."""
    table = run_model({"label_rule": "unit-labels-v18"})
    found = {r.unit_id: (r.label_unit, r.units, r.layer) for r in table.itertuples()}
    assert found == {u: v for u, v in EXPECTED.items() if u not in ("u:30", "u:31")}


def test_unknown_label_rule():
    with pytest.raises(ValueError, match="no label rule"):
        run_model({"label_rule": "unit-labels-v99"})


# Labels with the key `spelling_key` gives them.
SPELLINGS = {
    # Case, spaces, punctuation, leading zeros and lead words.
    "4b": ["4B", "4-b", "4 b", "4_B", "#04B", "Apt 4B", "APT-4B", "Unit 4b", "no4b"],
    # A floor and a letter, either way round.
    "9h": ["9H", "H9", "h-9", "H-09"],
    # Penthouses.
    "ph": ["PH", "Penthouse", "penthouse"],
    "pha": ["PH-A", "PENTHOUSE A", "PenthouseA"],
    "2ph": ["PH2", "ph-02", "Penthouse 2", "2PH"],
    # Floors, ordinals and number words.
    "3": ["3", "03", "3rd", "3rd-floor", "THIRD-FL", "fl3", "3fl", "third", "Floor 3"],
    "1": ["1", "1st", "first-floor"],
    # A lone zero ahead of letters.
    "b": ["B", "0B", "00b"],
    "me": ["me", "0ME", "m-e"],
    # Numbers stay apart.
    "1-2": ["1-2", "1 2"],
    "12": ["12", "012"],
    "0": ["0", "00"],
    # Labels of lead words alone.
    "": ["unit", "Apt", "#", "-"],
}


@pytest.mark.parametrize("key", list(SPELLINGS))
def test_spelling_key(key):
    assert [labels.spelling_key(w) for w in SPELLINGS[key]] == [key] * len(
        SPELLINGS[key]
    )


def test_spelling_keys():
    """Each unit gets the keys of its labels, with empty keys and missing labels left out."""
    pages = pd.DataFrame(
        {
            "unit_id": ["v:1", "v:1", "v:2", "v:3", "v:4"],
            "label": ["4-B", "04b", "B4", None, "unit"],
        }
    )
    assert labels.spelling_keys(pages) == {"v:1": {"4b"}, "v:2": {"4b"}}


def test_history_layer_v18():
    """Given spellings, the history layer joins the units of a pair only when their labels
    agree up to spelling. "5a" and "3a" stay apart, as do "1" and a page with no label."""
    rows = pd.DataFrame(
        [
            ("v:1", "b9", "4d", 2.0),
            ("v:2", "b9", "d-4", 2.0),
            ("v:3", "b9", "5a", 1.0),
            ("v:4", "b9", "3a", 1.0),
            ("v:5", "b9", "1", 1.0),
            ("v:6", "b9", None, 1.0),
        ],
        columns=["unit_id", "building", "label", "bedrooms"],
    )
    pairs = [("v:1", "v:2"), ("v:3", "v:4"), ("v:5", "v:6")]
    history = labels.LAYERS.index("history")
    v17 = labels.layers(rows, pairs, [])
    v18 = labels.layers(rows, pairs, [], labels.spelling_keys(rows))
    assert list(v17[history]) == ["v:1", "v:1", "v:3", "v:3", "v:5", "v:5"]
    assert list(v18[history]) == ["v:1", "v:1", "v:3", "v:4", "v:5", "v:6"]
