"""The `penthouse` column of D1's dataset against S14's text penthouse marks.

`rentfrontier.b0penthouse` wrote S14's text pattern into a copy of the duplex dataset as the
column `penthouse`. The script counts the rows it marks, overall and among L1's held-out ads
of the latest split, and how many of them `duplex` marks too. It then compares the column
with S14's `pen_text` (`docs/notes/unusual-units-2026-11-13/u1_text.py`), listing by listing.

The two can differ in their choice of description. S14 read the description of each listing's
last record in the S2 records file, ordered by `last_collected_at` alone and with no floor on
its length. The column reads the description of the latest record in the records file of the
dataset's own pipeline build, by the later of `collected_at` and `last_collected_at`, and
needs over 20 characters (`b0data.MIN_DESCRIPTION`). For each listing where the two disagree,
the script reads both descriptions again and sorts the disagreement into

1. a description of 20 characters or fewer in S14's record, which the column's floor drops;
2. a different description in the two records;
3. the same description, which only a difference in the patterns could explain.

The script runs on thelio in about 3 GB."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier/src"))
from rentfrontier.b0data import MIN_DESCRIPTION  # noqa: E402

D = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse"
)
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
S14 = "/data1/apartments/tmp/sprint-20261113/unusual-units/u1_text.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"


def build_texts(path, ids):
    """The description of each listing's latest record in the build's records file, by the
    later of its two times, as `b0penthouse` picks it."""
    f = pq.ParquetFile(path)
    seen = {}
    for g in range(f.num_row_groups):
        t = f.read_row_group(
            g, columns=["listing_id", "collected_at", "last_collected_at"]
        )
        lid = [str(x) for x in t["listing_id"].to_pylist()]
        at = [
            max((x for x in pair if x is not None), default=None)
            for pair in zip(
                t["collected_at"].to_pylist(), t["last_collected_at"].to_pylist()
            )
        ]
        keep = [
            i in ids and a is not None and (i not in seen or seen[i][0] < a)
            for i, a in zip(lid, at)
        ]
        if not any(keep):
            continue
        raws = f.read_row_group(g, columns=["raw_listing_json"]).filter(pa.array(keep))
        rows = [(i, a) for i, a, k in zip(lid, at, keep) if k]
        for (i, a), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
            if i not in seen or seen[i][0] < a:
                text = str((json.loads(raw) if raw else {}).get("description") or "")
                seen[i] = (a, text)
    return {i: text for i, (_, text) in seen.items()}


def s14_texts(ids):
    """The description of each listing's last record in S14's records file, by
    `last_collected_at` alone."""
    f = pq.ParquetFile(RECS)
    seen = {}
    for g in range(f.num_row_groups):
        t = f.read_row_group(
            g, columns=["listing_id", "last_collected_at", "description"]
        )
        mask = pc.is_in(pc.cast(t["listing_id"], pa.string()), pa.array(sorted(ids)))
        t = t.filter(mask).to_pandas()
        for r in t.itertuples():
            k = str(r.listing_id)
            if k not in seen or seen[k][0] < r.last_collected_at:
                seen[k] = (r.last_collected_at, r.description or "")
    return {i: text for i, (_, text) in seen.items()}


rows = pd.read_parquet(
    D + "/rows.parquet", columns=["listing_id", "duplex", "penthouse"]
)
rows["listing_id"] = rows.listing_id.astype(str)
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
held = a["heldout"]
assert len(held) == len(rows)
assert (rows.listing_id.to_numpy()[held] == a["listing"].astype(str)).all()
s14 = pd.read_parquet(S14, columns=["listing_id", "desc_len", "pen_text"])
s14["listing_id"] = s14.listing_id.astype(str)
rows["s14"] = rows.listing_id.map(s14.set_index("listing_id").pen_text).eq(True)
rows["held"] = held

out = {"rows": len(rows), "held": int(held.sum())}
for name, part in (("all", rows), ("held", rows[rows.held])):
    out[name] = {
        "penthouse": int(part.penthouse.sum()),
        "duplex": int(part.duplex.sum()),
        "both": int((part.penthouse & part.duplex).sum()),
        "either": int((part.penthouse | part.duplex).sum()),
        "s14_text": int(part.s14.sum()),
        "agree_marked": int((part.penthouse & part.s14).sum()),
        "column_only": int((part.penthouse & ~part.s14).sum()),
        "s14_only": int((~part.penthouse & part.s14).sum()),
    }

# Every disagreement over all rows, sorted by its cause.
diff = rows[rows.penthouse != rows.s14].drop_duplicates("listing_id")
ids = set(diff.listing_id)
mine = build_texts(
    json.loads(Path(D, "manifest.json").read_text())["build"]["records"]["path"], ids
)
theirs = s14_texts(ids)
cause = {}
for r in diff.itertuples():
    m, t = mine.get(r.listing_id, ""), theirs.get(r.listing_id, "")
    if r.s14 and len(t) <= MIN_DESCRIPTION:
        c = "s14_short"
    elif m != t:
        c = "different_text"
    else:
        c = "same_text"
    cause[r.listing_id] = c
rows["cause"] = rows.listing_id.map(cause)
for name, part in (("all", rows), ("held", rows[rows.held])):
    d = part[part.penthouse != part.s14]
    out[name]["disagreements"] = {
        side: d[d.penthouse == (side == "column_only")].cause.value_counts().to_dict()
        for side in ("column_only", "s14_only")
    }

# L1's 80% coverage and the median of its absolute error on the held-out ads of each mark,
# for D1's revised predictions.
h = rows[rows.held].reset_index(drop=True)
qs = list(a["quantiles"])
inside = (a["y"] >= a["q"][:, qs.index(0.1)]) & (a["y"] <= a["q"][:, qs.index(0.9)])
err = np.abs(a["y"] - a["pred"])
dup, pen = h.duplex.to_numpy(), h.penthouse.to_numpy()
out["l1_heldout"] = {
    name: {
        "ads": int(m.sum()),
        "cover80": round(float(inside[m].mean()), 4),
        "median_abs_error": round(float(np.median(err[m])), 5),
    }
    for name, m in (
        ("all", np.ones(len(h), bool)),
        ("marked", dup | pen),
        ("duplex", dup),
        ("penthouse_without_duplex", pen & ~dup),
        ("other", ~(dup | pen)),
    )
}
print(json.dumps(out, indent=1))
