"""Run label_units' layers under v17 and v18 on L1's build inputs, cut the label units into
pieces as analysis.history_splits does, and write each row's units under both rules."""

import importlib.util
import sys
import time

import numpy as np
import pandas as pd

WT = sys.argv[1]
S = "/data1/apartments/tmp/sprint-20261113/label-join"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lu = load("label_units", f"{WT}/pipeline/models/analysis/label_units.py")
hs = load("history_splits", f"{WT}/pipeline/models/analysis/history_splits.py")
t = time.time()
ledger = pd.read_parquet(f"{S}/ledger.parquet")
ledger["label"] = ledger.page.str.extract(r"/([^/]+)$")[0]
ledger.loc[ledger.label == "", "label"] = None
rows = pd.DataFrame(
    {
        "unit_id": ledger.page_unit,
        "building": ledger.building,
        "label": ledger.label,
        "bedrooms": ledger.bedrooms,
    }
)
pairs = list(
    pd.read_parquet(
        f"{S}/pairs.parquet", columns=["unit_id", "other_unit_id"]
    ).itertuples(index=False, name=None)
)
pages = pd.read_parquet(f"{S}/pages.parquet")
groups = lu.alias_groups(pages[["unit_id", "building", "label"]], pairs)
every = pages[["unit_id", "pages"]].explode("pages")
every["label"] = every.pages.str.extract(lu.PAGE)[1]
keys = lu.spelling_keys(every[["unit_id", "label"]])
print("loaded", time.time() - t, len(rows), len(pairs), len(groups), len(keys))
out = {}
for rule, k in (("v17", None), ("v18", keys)):
    ids, unit, steps = lu.coded_layers(rows, pairs, groups, k)
    table = lu.label_units(ids, unit, steps)
    table.to_parquet(f"{S}/label_units_{rule}.parquet")
    # Each page unit with rows, with its unit after layers 3 and 4 and after the last layer.
    first = pd.DataFrame({"unit": unit, "i": np.arange(len(unit))}).drop_duplicates(
        "unit"
    )
    pd.DataFrame(
        {
            "page_unit": ids[first.unit.to_numpy()],
            "after3": ids[steps[2][first.i.to_numpy()]],
            "after4": ids[steps[3][first.i.to_numpy()]],
            "final": ids[steps[-1][first.i.to_numpy()]],
        }
    ).to_parquet(f"{S}/page_units_{rule}.parquet")
    print(rule, table.layer.value_counts().to_dict())
    found = dict(zip(table.unit_id, table.label_unit))
    out[rule] = ledger.unit_id.map(found).fillna(ledger.unit_id)
    out[rule + "_layer"] = ledger.unit_id.map(dict(zip(table.unit_id, table.layer)))
    print(rule, "seconds", time.time() - t)
del rows, pages, every, keys, ids, unit, steps, table, first
ledger["label17"] = out["v17"]
ledger["label18"] = out["v18"]
ledger["layer17"] = out["v17_layer"]
kept = ~ledger.dropped
same = (ledger.label17[kept] == ledger.label_unit[kept]).mean()
print(
    "v17 reproduces label_unit on kept rows:",
    same,
    (ledger.label17[kept] != ledger.label_unit[kept]).sum(),
)


def split(label, mask):
    r = ledger[mask].assign(unit=label[mask])
    multi = r.groupby("unit").bedrooms.transform("nunique") > 1
    r = r[multi].sort_values(["unit", "price_at", "listing_id"])
    r["piece"] = hs.pieces(
        r[["unit", "listing_id", "bedrooms", "square_feet"]].reset_index(drop=True)
    )
    cut = r[r.piece > 0]
    found = pd.Series(label[mask].to_numpy(), index=ledger.index[mask])
    found.loc[cut.index] = cut.unit + "~" + cut.piece.astype(str)
    return found


rf = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet",
    columns=["listing_id", "square_feet", "bathrooms"],
)
ledger = ledger.merge(rf, on="listing_id", how="left")
s17 = split(ledger.label17, kept)
print(
    "v17 split reproduces split_unit:",
    (s17 == ledger.split_unit[kept]).mean(),
    (s17 != ledger.split_unit[kept]).sum(),
)
s18 = split(ledger.label18, kept)
ledger["split17"] = s17
ledger["split18"] = s18
ledger[
    [
        "listing_id",
        "dropped",
        "page_unit",
        "unit_id",
        "building",
        "label",
        "bedrooms",
        "price_at",
        "period",
        "label_unit",
        "split_unit",
        "label17",
        "label18",
        "layer17",
        "split17",
        "split18",
    ]
].to_parquet(f"{S}/units.parquet")
print("done", time.time() - t)
