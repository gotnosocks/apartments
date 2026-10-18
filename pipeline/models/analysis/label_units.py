"""analysis.label_units: the units the chain's label rule, `unit-labels-v17`, joins.

StreetEasy sometimes files one apartment under several unit pages of a building, with its label
spelled differently on each: "4-B" and "4B", "ph04" and "ph4", "four" and "4", "C7" and "7C",
"3rd-floor" and "3". The model joins such pages into one unit in seven layers, in the order
v17 takes them. Each layer starts from the units the layer before gave:

1. `labels`: it gives the unit pages of a building whose labels are one label written another
   way ("APT-4B", "4-B", "04B") the least unit ID among them.
2. `aliases`: it joins the units of an alias group. The model groups each building's unit pages
   in ads.placed by their label with case, punctuation and the leading zeros of every number
   dropped, a bare floor ("2nd-floor", "fl-2") read as its number, and a leading apt, unit,
   suite or residence word dropped, as `unit-spelling-alias-v2` does. It keeps a group of two
   or more pages when a pair of analysis.history_pairs joins two of them.
3. `words`: it joins a unit labelled with a number word ("four", "third-fl") to the unit of the
   building labelled with that number.
4. `history`: it joins the two units of each pair of analysis.history_pairs in one building.
5. `swapped`: it joins a unit labelled letter first ("C7") to the building's unit labelled digit
   first ("7C").
6. `word_letters`: it joins a unit labelled with a number word and a letter ("fourb", "five-a")
   to the unit labelled with that number and letter.
7. `spelled`: it joins units whose labels are one label spelled out and short ("3RDFL" and
   "3", "PENTHOUSEA" and "PHA", "GARDEN" and "G", "4REAR" and "4R").

Layers 3 to 7 join two units only where the median bedroom counts of their rows agree, taken
over the units of the layer before. A joined unit takes the least unit ID among its members.
The chain's v17 reads its history pairs and alias groups from files built from crawled unit
pages, in the neighbourhoods of the served dataset. The model builds both from the API records
for every building, so it also joins units in the other neighbourhoods.

The model reads the rows of analysis.ledger_rows, so it joins units after the unit-month check,
as the fit does. It takes each row's `page_unit` from ads.placed, the unit of its ad after the
unit ledger's joins and before its splits, and runs the layers on those units, as the fit runs
v17 before the unit reviews split units. The unit ledger holds the joins of `unit-reviews-v5`
as well, so the layers run after them, while the fit applies them after v17. The rows of a split
count toward the bedrooms of their page's unit there. A split's ID carries a `~review-` suffix and matches no page unit, so
analysis.rows finds no label unit for its rows and leaves them in the split. The model lists
each page unit of the rows joined with another unit or given another unit's ID, with its label
unit, the count of page units with rows in that label unit and the layer that first joined it.
analysis.rows gives each row the label unit of its unit, or the unit itself, as `label_unit`,
and analysis.history_splits then cuts label units as `unit-splits-v4` does.
"""

import re
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlglot import exp
from sqlmesh import ExecutionContext, model

COLUMNS = {
    "unit_id": "VARCHAR",
    "label_unit": "VARCHAR",
    "units": "BIGINT",
    "layer": "VARCHAR",
}
LAYERS = ("labels", "aliases", "words", "history", "swapped", "word_letters", "spelled")

# The patterns stay strings, as SQLMesh stores a Python model's globals and cannot store a
# compiled pattern. `re` compiles each once and keeps it.
# Unit labels written as words ("four", "third-fl") and the number they stand for.
LABEL_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "first": "1",
    "second": "2", "third": "3", "fourth": "4", "fifth": "5",
}  # fmt: skip
WORD_LABEL = r"^(" + "|".join(LABEL_WORDS) + r")(?=$|[-_ ]?(?:fl|floor)$)"
LETTER_FIRST = r"^([A-Z]{1,2})(\d{1,2})$"
# Number words with a letter after them ("fourb", "five-a"), longest first so "fourth" is not
# read as "four" and "th".
WORD_LETTER_WORDS = {
    **LABEL_WORDS,
    "eleven": "11", "twelve": "12", "sixth": "6", "seventh": "7",
    "eighth": "8", "ninth": "9", "tenth": "10",
}  # fmt: skip
WORD_LETTER = (
    r"^(" + "|".join(sorted(WORD_LETTER_WORDS, key=len, reverse=True)) + r")"
    r"[-_ ]?([a-z]{0,2})$"
)
# Labels spelled out, each rewritten to its short spelling, in order: "THIRD", "THREEFL" -> "3"
# by SPELLED_WORD; then "3RDFL", "3FL", "3RD" -> "3"; "2WFL" -> "2W"; "3FRONT" -> "3F", "3REAR",
# "3BACK" -> "3R"; "PENTHOUSEA" -> "PHA"; "GARDEN", "GDN", "GROUND", "GARDENFL" -> "G";
# "PARLOUR", "PARLORFL" -> "PARLOR".
SPELLED_WORDS = {k.upper(): v for k, v in WORD_LETTER_WORDS.items()}
SPELLED_WORD = (
    r"^(" + "|".join(sorted(SPELLED_WORDS, key=len, reverse=True)) + r")(?=(?:FL)?$)"
)
SPELLED_LABELS = [
    (r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?$", r"\1"),
    (r"^(\d+[A-Z])FL$", r"\1"),
    (r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?FRONT$", r"\1F"),
    (r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?(?:REAR|BACK)$", r"\1R"),
    (r"^PENTHOUSE", "PH"),
    (r"^(?:GARDEN|GDN|GROUND)(?:FL)?$", "G"),
    (r"^PARLOU?R(?:FL)?$", "PARLOR"),
]  # fmt: skip
ORDINALS = {
    word: str(n)
    for n, word in enumerate(
        "first second third fourth fifth sixth seventh eighth ninth tenth".split(), 1
    )
}
FLOOR = "(?:fl|flr|floor)"
# A unit page's URL, with the building and label of its path, for DuckDB's regexp_extract.
PAGE = r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?(?://[^/?#]*)?/building/([^/?#]+)/([^/?#]+)(?:[?#].*)?$"


def label_key(label: str) -> str:
    """A unit label written one way: "APT-4B", "UNIT4B", "4-B", "04B" -> "4B"; "7TH-FLOOR",
    "7THFL" -> "7THFL"."""
    label = re.sub(r"^(?:APT|UNIT)\.?-?|^NO\.?-?(?=\d)", "", label.upper())
    label = re.sub(r"[-_#. ]", "", label)
    label = re.sub(r"(?:FLOOR|FLR)$", "FL", label)
    return re.sub(r"^0+(?=\d)", "", label)


def spelled_key(label: str) -> str:
    """A unit label's short spelling, by SPELLED_WORD and SPELLED_LABELS."""
    key = re.sub(SPELLED_WORD, lambda m: SPELLED_WORDS[m[1]], label_key(label))
    for pattern, short in SPELLED_LABELS:
        key = re.sub(pattern, short, key)
    return key


def alias_key(label: str) -> str:
    """A unit label as `unit-spelling-alias-v2` writes it: lowercased, without punctuation or
    the leading zeros of its numbers, a floor alone as its number, and without a leading apt,
    unit, suite or residence word."""
    text = re.sub(r"[^a-z0-9]+", "", label.lower())
    text = re.sub(r"\d+", lambda m: m.group().lstrip("0") or "0", text)
    text = re.sub(r"^(?:apt|apartment|unit|suite|residence)(?=\d)", "", text)
    if m := re.fullmatch(rf"(\d+)(?:st|nd|rd|th)?{FLOOR}?", text):
        return m[1]
    if m := re.fullmatch(rf"{FLOOR}(\d+)", text):
        return m[1]
    if m := re.fullmatch(rf"({'|'.join(ORDINALS)}){FLOOR}?", text):
        return ORDINALS[m[1]]
    return text


def alias_groups(pages: pd.DataFrame, pairs) -> list:
    """The alias groups of `pages`, which gives each unit's `unit_id` and the `building` and
    `label` of its page: the units of a building whose labels share an `alias_key`, where a pair
    of `pairs` joins two of them."""
    pages = pages.dropna(subset=["building", "label"])
    members = defaultdict(set)
    keys = map_distinct(pages.label, alias_key)
    for unit, building, key in zip(pages.unit_id, pages.building, keys):
        if key:
            members[building, key].add(unit)
    group = {u: key for key, units in members.items() if len(units) > 1 for u in units}
    confirmed = {group[a] for a, b in pairs if a in group and group[a] == group.get(b)}
    return [tuple(sorted(members[key])) for key in sorted(confirmed)]


class Units:
    """Joins of unit codes, each set under its least code."""

    def __init__(self):
        self.parent = {}

    def find(self, unit):
        parent = self.parent
        parent.setdefault(unit, unit)
        while parent[unit] != unit:
            parent[unit] = parent[parent[unit]]
            unit = parent[unit]
        return unit

    def join(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def roots(self, n: int) -> np.ndarray:
        """The least code joined to each code below `n`."""
        found = np.arange(n)
        for unit in list(self.parent):
            found[unit] = self.find(unit)
        return found


# SQLMesh offers a Python model's functions to its audits as macros, so a function named after
# a macro, such as `each`, hides that macro.
def map_distinct(values: pd.Series, f) -> pd.Series:
    """`values` mapped by `f`, calling it once for each distinct value."""
    distinct = values.dropna().unique()
    return values.map(dict(zip(distinct, map(f, distinct))))


def medians(beds: np.ndarray, units: np.ndarray, n: int) -> np.ndarray:
    """The median bedroom count of the rows of each unit code below `n`, NaN for a code with
    no rows."""
    found = np.full(n, np.nan)
    median = pd.Series(beds).groupby(units).median()
    found[median.index.to_numpy()] = median.to_numpy()
    return found


def coded_layers(rows: pd.DataFrame, pairs, groups) -> tuple:
    """The sorted unit IDs of `rows` and `groups`, and the code of each row's unit after each
    of the seven layers, as a list of arrays. A unit's code is its place among the sorted IDs,
    so the least code of a set of units is the code of its least ID.

    `rows` gives `unit_id`, `building`, `label` (the last part of the unit page's URL) and
    `bedrooms`, in the order of the rows' ads. `pairs` gives (unit_id, unit_id) tuples and
    `groups` tuples of unit IDs, from `alias_groups`. Layer 3 follows v17 in taking the rows'
    word labels in order, so the order of `rows` matters there."""
    ids = np.array(sorted(set(rows.unit_id).union(*groups)), dtype=object)
    n = len(ids)
    index = pd.Index(ids)
    unit = index.get_indexer(rows.unit_id)
    building = pd.factorize(rows.building)[0].astype(np.int64)
    label, distinct = pd.factorize(rows.label)
    beds = rows.bedrooms.to_numpy(dtype=float)
    has = label >= 0
    lower = [text.lower() for text in distinct]

    # Each distinct label's key, as a code among the distinct keys, and each row's key code.
    key_of, keys = pd.factorize(
        pd.Series([label_key(x) for x in distinct], dtype=object)
    )
    key_code = {k: i for i, k in enumerate(keys)}
    key = np.full(len(rows), -1)
    key[has] = key_of[label[has]]

    def cell(b, k):
        """A code for the key `k` in the building `b`."""
        return b * (len(keys) + 1) + k

    def last_unit(units):
        """The unit of the last row with each key of a building, by its `cell` code."""
        found = pd.DataFrame(
            {"cell": cell(building[has], key[has]), "unit": units[has]}
        )
        found = found.drop_duplicates("cell", keep="last")
        return dict(zip(found.cell, found.unit))

    out = []

    # 1. labels.
    least = pd.Series(unit[has]).groupby(cell(building[has], key[has])).transform("min")
    first = unit.copy()
    first[has] = least.to_numpy()
    out.append(first)

    # 2. aliases.
    joins = Units()
    for a, b in set(zip(unit[unit != first], first[unit != first])):
        joins.join(a, b)
    codes = iter(index.get_indexer([u for group in groups for u in group]))
    for group in groups:
        head = next(codes)
        for _ in group[1:]:
            joins.join(head, next(codes))
    out.append(joins.roots(n)[unit])

    # 3. words. Each distinct label read as a number word gives the code of its number's key,
    # where a row has that key.
    before = out[-1]
    word = np.full(len(distinct), -1)
    for i, text in enumerate(lower):
        if m := re.match(WORD_LABEL, text):
            number = LABEL_WORDS[m[1]] + re.sub(WORD_LABEL, "", text)
            word[i] = key_code.get(label_key(number), -1)
    median = medians(beds, before, n)
    found = pd.DataFrame({"cell": cell(building[has], key[has]), "unit": before[has]})
    found = found.drop_duplicates("cell", keep="first")
    twins = dict(zip(found.cell, found.unit))
    joined = {}
    for i in np.flatnonzero(has):
        if word[label[i]] < 0:
            continue
        a = before[i]
        target = twins.get(cell(building[i], word[label[i]]))
        if target is not None and median[target] == median[a]:
            joined[a] = joined[target] = min(target, a)
    step = np.arange(n)
    step[list(joined)] = list(joined.values())
    out.append(step[before])

    # 4. history.
    before = out[-1]
    median = medians(beds, before, n)
    found = pd.DataFrame({"unit": unit, "to": before}).drop_duplicates(
        "unit", keep="last"
    )
    to = np.full(n, -1)
    to[found.unit.to_numpy()] = found.to.to_numpy()
    found = pd.DataFrame({"to": before, "building": building})
    found = found.drop_duplicates("to", keep="last")
    home = np.full(n, -1)
    home[found.to.to_numpy()] = found.building.to_numpy()
    joins = Units()
    x = index.get_indexer([p[0] for p in pairs])
    y = index.get_indexer([p[1] for p in pairs])
    for a, b in zip(np.where(x >= 0, to[x], -1), np.where(y >= 0, to[y], -1)):
        if a < 0 or b < 0 or a == b or home[a] != home[b]:
            continue
        if median[a] == median[b]:
            joins.join(a, b)
    out.append(joins.roots(n)[before])

    # 5. swapped.
    before = out[-1]
    median = medians(beds, before, n)
    swap = np.full(len(keys), -1)
    for i, k in enumerate(keys):
        if m := re.match(LETTER_FIRST, k):
            swap[i] = key_code.get(m[2] + m[1], -1)
    unit_of = last_unit(before)
    joins = Units()
    size = len(keys) + 1
    for place, a in unit_of.items():
        if swap[place % size] < 0:
            continue
        other = unit_of.get(cell(place // size, swap[place % size]))
        if other is not None and other != a and median[a] == median[other]:
            joins.join(a, other)
    out.append(joins.roots(n)[before])

    # 6. word_letters.
    before = out[-1]
    median = medians(beds, before, n)
    letters = np.full(len(distinct), -1)
    for i, text in enumerate(lower):
        if m := re.match(WORD_LETTER, text):
            letters[i] = key_code.get(label_key(WORD_LETTER_WORDS[m[1]] + m[2]), -1)
    unit_of = last_unit(before)
    joins = Units()
    for i in np.flatnonzero(has):
        if letters[label[i]] < 0:
            continue
        a = before[i]
        other = unit_of.get(cell(building[i], letters[label[i]]))
        if other is not None and other != a and median[a] == median[other]:
            joins.join(a, other)
    out.append(joins.roots(n)[before])

    # 7. spelled. Units of one building and spelled key with one median join, as all pairs
    # among them do in v17.
    before = out[-1]
    median = medians(beds, before, n)
    spelled = pd.factorize(pd.Series([spelled_key(x) for x in distinct], dtype=object))[
        0
    ]
    found = pd.DataFrame(
        {"building": building[has], "spelled": spelled[label[has]], "unit": before[has]}
    ).drop_duplicates()
    found["median"] = median[found.unit.to_numpy()]
    found = found.dropna(subset=["median"])
    found["least"] = found.groupby(["building", "spelled", "median"]).unit.transform(
        "min"
    )
    joins = Units()
    for a, b in zip(
        found.unit[found.unit != found.least], found.least[found.unit != found.least]
    ):
        joins.join(a, b)
    out.append(joins.roots(n)[before])
    return ids, unit, out


def layers(rows: pd.DataFrame, pairs, groups) -> list:
    """The unit of each row of `rows` after each of the seven layers, as a list of Series, from
    `coded_layers`."""
    ids, _, steps = coded_layers(rows, pairs, groups)
    return [pd.Series(ids[step], index=rows.index) for step in steps]


def label_units(ids: np.ndarray, unit: np.ndarray, steps: list) -> pd.DataFrame:
    """The table of the model from the codes `coded_layers` gives: each unit of the rows in a
    label unit with another unit of them, or under another unit's ID, with its label unit, the
    count of the rows' units in it and the first layer to join it."""
    n = len(ids)
    layer = np.full(n, len(LAYERS))
    for i, step in enumerate(steps):
        # The distinct (unit, label unit) pairs, so a label unit's count of pairs is its count
        # of units.
        pair = pd.unique(unit.astype(np.int64) * n + step)
        units, label = pair // n, pair % n
        count = np.bincount(label, minlength=n)
        moved = units[(count[label] > 1) | (label != units)]
        layer[moved] = np.minimum(layer[moved], i)
    units, label = np.divmod(np.sort(pair), n)
    keep = layer[units] < len(LAYERS)
    return pd.DataFrame(
        {
            "unit_id": ids[units[keep]],
            "label_unit": ids[label[keep]],
            "units": count[label[keep]],
            "layer": np.array(LAYERS, dtype=object)[layer[units[keep]]],
        }
    )


@model(
    "analysis.label_units",
    kind="FULL",
    columns=COLUMNS,
    grain="unit_id",
    audits=[
        ("unique_values", {"columns": [exp.column("unit_id")]}),
        (
            "not_null",
            {"columns": [exp.column(name) for name in COLUMNS]},
        ),
    ],
    description="Each page unit of analysis.ledger_rows the label rule joins with another unit, with its label unit, the count of page units in that label unit and the layer that first joined it.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    rows_table = context.resolve_table("analysis.ledger_rows")
    pairs_table = context.resolve_table("analysis.history_pairs")
    placed = context.resolve_table("ads.placed")
    rows = context.fetchdf(
        f"""SELECT p.page_unit AS unit_id, r.building,
            nullif(regexp_extract(r.page, '/([^/]+)$', 1), '') AS label, r.bedrooms
        FROM {rows_table} r JOIN {placed} p USING (listing_id) ORDER BY listing_id"""
    )
    if rows.empty:
        return
    pairs = list(
        context.fetchdf(f"SELECT unit_id, other_unit_id FROM {pairs_table}").itertuples(
            index=False, name=None
        )
    )
    pages = context.fetchdf(
        f"""SELECT unit_id, nullif(regexp_extract(page, '{PAGE}', 1), '') AS building,
            nullif(regexp_extract(page, '{PAGE}', 2), '') AS label
        FROM (
            SELECT page_unit AS unit_id, min(page) AS page FROM {placed}
            WHERE page_unit IS NOT NULL GROUP BY page_unit
        )"""
    )
    ids, unit, steps = coded_layers(rows, pairs, alias_groups(pages, pairs))
    found = label_units(ids, unit, steps)
    if not found.empty:
        yield found
