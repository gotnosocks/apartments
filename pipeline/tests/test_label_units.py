import functools
import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd

from apartments.unit_spelling_aliases import normalize_label

MODELS = Path(__file__).parent.parent / "models"
PORT_DIFF = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "port_diff.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


labels = load("label_units", MODELS / "analysis" / "label_units.py")

# The rows in the order of their ads: unit, building, label and bedrooms. The comments give
# the layer expected to join each case.
ROWS = [
    # labels: one label written three ways, and a split of the first unit by the unit ledger.
    ("u:01", "b1", "4-b", 2),
    ("u:01~review-7", "b1", "4-b", 2),
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
]
PAIRS = [("u:30", "u:31"), ("u:32", "u:33"), ("u:32", "u:34"), ("u:11", "u:12")]
EXPECTED = {
    "u:01": ("u:01", 4, "labels"),
    "u:01~review-7": ("u:01", 4, "labels"),
    "u:02": ("u:01", 4, "labels"),
    "u:03": ("u:01", 4, "labels"),
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
}


def page(building, label):
    return f"https://streeteasy.com/building/{building}/{label}"


def frame() -> pd.DataFrame:
    rows = pd.DataFrame(ROWS, columns=["unit_id", "building", "label", "bedrooms"])
    rows["bedrooms"] = rows.bedrooms.astype(float)
    return rows


def pages() -> list:
    """Each unit's page in ads.placed. A split of the unit ledger has no page of its own."""
    found = {u: page(b, label) for u, b, label, _ in ROWS if "~" not in u}
    found["u:12"] = page("b1", "PH004")
    return sorted(found.items())


def page_frame() -> pd.DataFrame:
    """The pages of `pages` with their building and label, as the model reads them."""
    found = pd.DataFrame(pages(), columns=["unit_id", "page"])
    found[["building", "label"]] = found.page.str.extract(labels.PAGE)
    return found


class Fetcher:
    """Stands in for a SQLMesh context: it runs a Python model's queries on `db`, with each
    model's table under its own name."""

    def __init__(self, db):
        self.db = db

    def resolve_table(self, name):
        return name

    def fetchdf(self, query):
        return self.db.sql(query).df()


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
    rows = frame()
    chain = rows.assign(
        canonical_unit_url=[page(b, x) for b, x in zip(rows.building, rows.label)]
    )
    ours = labels.layers(rows, PAIRS, groups)
    for name, step, units in zip(labels.LAYERS, steps, ours):
        assert list(units) == list(step(chain).unit_id), name


def test_label_units_model():
    db = duckdb.connect()
    db.execute("CREATE SCHEMA analysis; CREATE SCHEMA ads")
    rows = frame()
    rows["listing_id"] = [str(1000 + i) for i in range(len(rows))]
    rows["page"] = [page(b, x) for b, x in zip(rows.building, rows.label)]
    db.register("frame", rows)
    db.execute(
        "CREATE TABLE analysis.ledger_rows AS "
        "SELECT listing_id, unit_id, building, page, bedrooms FROM frame"
    )
    db.execute(
        "CREATE TABLE analysis.history_pairs (unit_id VARCHAR, other_unit_id VARCHAR)"
    )
    db.executemany("INSERT INTO analysis.history_pairs VALUES (?, ?)", PAIRS)
    db.execute(
        "CREATE TABLE ads.placed (listing_id VARCHAR, unit_id VARCHAR, page VARCHAR)"
    )
    db.executemany(
        "INSERT INTO ads.placed VALUES (?, ?, ?)",
        [(str(i), u, p) for i, (u, p) in enumerate(pages())],
    )
    (table,) = labels.execute.__wrapped__(Fetcher(db), None, None, None)
    assert list(table.columns) == list(labels.COLUMNS)
    found = {r.unit_id: (r.label_unit, r.units, r.layer) for r in table.itertuples()}
    assert found == EXPECTED
