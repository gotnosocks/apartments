"""Step 5: a blind read of 16 pages of the largest kind, for what the fields cannot tell.

Pool: `U_strict` rows of the kind "one change of layout" (`lr4_kinds.py`): every other typed
ad of the page codes 2 or more, the ads were never on the market together for 14 days, the
count changes once between under 2 and 2 or more, and the label is no bare floor number shared
with lettered apartments. Eight rows are drawn from each half of buildings with a seed. Each
block gives the 0-bed ad and up to three ads of the page coded 2 or more (the nearest in time),
each with its coded fields, lister, day and whole text. Dollar figures are masked as [amount]
and no ask is shown. The blocks give no kind or stratum.
"""

import hashlib
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "commercial-sweep-2026-11-20"))
from sw4_draw import MONEY, texts_for  # noqa: E402

S = Path("/data1/apartments/tmp/label-reuse")
ZB = Path("/data1/apartments/tmp/zero-bed")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
SEED = 20261121
PER = 8

z = pd.read_parquet(S / "kinds.parquet")
z = z.merge(
    pd.read_parquet(ZB / "zeros.parquet", columns=["listing_id", "half"]),
    on="listing_id",
)
pool = z[z.U_strict & (z.kind == "one change of layout")]
print("pool", len(pool), pool.half.value_counts().to_dict())
rng = np.random.default_rng(SEED)
D = pd.concat(
    [g.iloc[rng.choice(len(g), PER, replace=False)] for _, g in pool.groupby("half")]
)
D = D.iloc[rng.permutation(len(D))].reset_index(drop=True)
D["read_id"] = [f"L{i + 1:02d}" for i in range(len(D))]

T = pd.read_parquet(S / "pair_times.parquet")
T = T[T.z_id.isin(D.listing_id)].sort_values("gap", key=abs)
others = T.groupby("z_id").head(3)
c = duckdb.connect()
ids = sorted(set(D.listing_id) | set(others.o_id))
A = (
    c.execute(
        f"""select listing_id, first_day, bedrooms, full_baths, half_baths, square_feet,
      regexp_extract(page, '[^/]+$') AS "label" from '{ADS}' where listing_id in (select unnest(?))""",
        [ids],
    )
    .df()
    .set_index("listing_id")
)
lister = dict(zip(T.z_id, T.lister)) | dict(zip(T.o_id, T.o_lister))
X = texts_for({int(i) for i in ids}).set_index("listing_id").desc


def clean(d: str) -> str:
    import re

    d = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", d or "")).strip()
    return MONEY.sub("[amount]", d) or "(empty)"


def fields(i: str) -> str:
    r = A.loc[i]
    sq = "" if pd.isna(r.square_feet) else f", {int(r.square_feet)} sq ft"
    return (
        f"posted {str(r.first_day)[:10]} by {lister.get(i) or 'an unnamed lister'}; "
        f"label {r.label!r}, {r.bedrooms:g} bed, {r.full_baths} full and {r.half_baths} half "
        f"baths{sq}"
    )


blocks = []
for r in D.itertuples():
    lines = [
        f"### {r.read_id}",
        f"Building: {r.building}.",
        f"Ad A: {fields(r.listing_id)}.",
    ]
    lines.append("Ad A text: " + clean(X.get(r.listing_id, "")))
    for k, o in enumerate(others[others.z_id == r.listing_id].o_id, 1):
        lines.append(f"Ad B{k}: {fields(o)}.")
        lines.append(f"Ad B{k} text: " + clean(X.get(o, "")))
    blocks.append("\n".join(lines))
for k, part in enumerate(np.array_split(np.arange(len(D)), 2)):
    p = S / f"read_batch_{k + 1}.md"
    p.write_text("\n\n".join(blocks[i] for i in part) + "\n")
    print(p.name, len(part), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
D[
    [
        "read_id",
        "listing_id",
        "unit_id",
        "building",
        "half",
        "label",
        "form",
        "lister",
        "text",
    ]
].to_parquet(S / "read_draw.parquet")
print(D[["read_id", "half", "building", "label", "lister", "text"]].to_string())
