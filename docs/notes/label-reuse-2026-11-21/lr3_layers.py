"""Step 3b: the label_units layer behind each cross-page pair of `lr2_fit_units.py`.

I run the seven layers of `pipeline/models/analysis/label_units.py` under v17 and v18 on the
inputs of `lr3_inputs.py`, as `label-join-2026-11-13/count.py` did, and check that v17 gives
the rows file's `label_unit`. For each pair (a 0-bed training row and a row coded 2 or more of
its label unit on another page) I take the first layer after which the two page units share a
code under v17, and whether v18 still joins them. Only units, labels and counts are read.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parents[3]
S = Path("/data1/apartments/tmp/label-reuse")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lu = load("label_units", WT / "pipeline/models/analysis/label_units.py")
ledger = pd.read_parquet(S / "ledger.parquet")
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
        S / "pairs.parquet", columns=["unit_id", "other_unit_id"]
    ).itertuples(index=False, name=None)
)
pages = pd.read_parquet(S / "pages.parquet")
groups = lu.alias_groups(pages[["unit_id", "building", "label"]], pairs)
every = pages[["unit_id", "pages"]].explode("pages")
every["label"] = every.pages.str.extract(lu.PAGE)[1]
keys = lu.spelling_keys(every[["unit_id", "label"]])
del every
P = pd.read_parquet(S / "label_unit_pairs.parquet")
P["z_pu"] = P.z_unit.str.replace(r"~review-.*$", "", regex=True)
P["o_pu"] = P.o_unit.str.replace(r"~review-.*$", "", regex=True)
print("pairs", len(P), "rows", P.z_id.nunique(), "label units", P.label_unit.nunique())

for rule, k in (("v17", None), ("v18", keys)):
    ids, unit, steps = lu.coded_layers(rows, pairs, groups, k)
    index = pd.Index(ids)
    first = pd.DataFrame({"u": unit, "i": np.arange(len(unit))}).drop_duplicates("u")
    at = np.full(len(ids), -1)
    at[first.u.to_numpy()] = first.i.to_numpy()
    zc, oc = index.get_indexer(P.z_pu), index.get_indexer(P.o_pu)
    ok = (
        (zc >= 0)
        & (oc >= 0)
        & (at[np.maximum(zc, 0)] >= 0)
        & (at[np.maximum(oc, 0)] >= 0)
    )
    layer = np.full(len(P), "none", dtype=object)
    for i in reversed(range(len(steps))):
        same = np.zeros(len(P), bool)
        same[ok] = steps[i][at[zc[ok]]] == steps[i][at[oc[ok]]]
        layer[same] = lu.LAYERS[i]
    P[f"layer_{rule}"] = layer
    if rule == "v17":
        final = pd.Series(ids[steps[-1]], index=ledger.index)
        kept = ~ledger.dropped & ~ledger.unit_id.str.contains("~review-", na=False)
        print(
            "v17 gives label_unit on kept rows without review splits:",
            round(float((final[kept] == ledger.label_unit[kept]).mean()), 6),
            int((final[kept] != ledger.label_unit[kept]).sum()),
        )
    del ids, unit, steps

print("\npairs by v17 layer and v18 kept:")
print(pd.crosstab(P.layer_v17, P.layer_v18 != "none", margins=True).to_string())
r = P.groupby("z_id").agg(
    layer=("layer_v17", lambda s: ",".join(sorted(set(s)))),
    v18_joins_any=("layer_v18", lambda s: bool((s != "none").any())),
)
print("\nrows by v17 layers of their pairs:")
print(r.layer.value_counts().to_string())
print("rows with a cross-page 2+ row that v18 still joins:", int(r.v18_joins_any.sum()))
lab = P.drop_duplicates("label_unit").groupby("layer_v17").size()
print("\nlabel units by layer of their first pair:", lab.to_dict())
P.to_parquet(S / "label_unit_pairs_layers.parquet")
print(
    P.assign(
        zl=P.z_page.str.extract(r"/([^/]+)$")[0],
        ol=P.o_page.str.extract(r"/([^/]+)$")[0],
    )[["layer_v17", "layer_v18", "zl", "ol", "o_bed"]]
    .sample(25, random_state=1)
    .to_string()
)
