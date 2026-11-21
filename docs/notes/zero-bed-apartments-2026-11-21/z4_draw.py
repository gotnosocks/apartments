"""Question 2: a stratified draw of 40 marked rows for blind reads, and the reader batches.

Strata (`z3_size.py`): text and unit, text only, unit with every other typed ad at 2 or more,
unit with mixed counts. Ten rows each, five from each half of buildings, drawn with a seed.
Each block shows the ad's coded fields (label, bedrooms, baths, size, room count), its day
and whole text, and the coded fields and text start of up to five other ads of the same unit:
the three nearest in time, and the nearest ad coded 2 or more and the nearest coded under 2
when those three hold none. Dollar figures are masked as [amount] and no ask is shown. The blocks give
no stratum, and the 40 are shuffled into four batches.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "commercial-sweep-2026-11-20"))
from sw4_draw import MONEY, texts_for  # noqa: E402

OUT = Path("/data1/apartments/tmp/zero-bed")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
SEED = 20261121
PER = 5
STRATA = ["text and unit", "text only", "unit, all 2+", "unit, mixed"]


def clean(d: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", d or "")).strip()


def fields(r) -> str:
    sq = "" if pd.isna(r.square_feet) else f", {int(r.square_feet)} sq ft"
    bed = "no count" if pd.isna(r.bedrooms) else f"{r.bedrooms:g} bed"
    return f"label {r.label!r}, {bed}, {r.full_baths} full and {r.half_baths} half baths{sq}"


if __name__ == "__main__":
    m = pd.read_parquet(OUT / "marked.parquet")
    rng = np.random.default_rng(SEED)
    picks = []
    for s in STRATA:
        for h in "AB":
            g = m[(m.stratum == s) & (m.half == h)]
            picks.append(g.iloc[rng.choice(len(g), PER, replace=False)])
    D = pd.concat(picks)
    D = D.iloc[rng.permutation(len(D))].reset_index(drop=True)
    D["read_id"] = [f"Z{i + 1:02d}" for i in range(len(D))]
    c = duckdb.connect()
    c.execute("set memory_limit='2GB'")
    A = c.execute(
        f"""select listing_id, unit_id, first_day, bedrooms, full_baths,
      half_baths, square_feet, regexp_extract(page, '[^/]+$') as "label" from '{ADS}'
      where unit_id in (select unnest(?))""",
        [list(D.unit_id)],
    ).df()
    ctx = {}
    for r in D.itertuples():
        u = A[(A.unit_id == r.unit_id) & (A.listing_id != r.listing_id)].copy()
        u["dt"] = (pd.to_datetime(u.first_day) - pd.Timestamp(r.first_day)).abs()
        u = u.sort_values("dt")
        ids = list(u.listing_id.head(3))
        for part in (u[u.bedrooms >= 2], u[u.bedrooms < 2]):
            if len(part) and not set(part.listing_id) & set(ids):
                ids.append(part.listing_id.iloc[0])
        ctx[r.listing_id] = sorted(ids, key=lambda i: u.set_index("listing_id").dt[i])
    need = {int(i) for i in D.listing_id} | {int(i) for v in ctx.values() for i in v}
    X = texts_for(need).set_index("listing_id").desc.map(clean)
    Ai = A.set_index("listing_id")
    blocks = []
    for r in D.itertuples():
        me = Ai.loc[r.listing_id]
        rooms = "no room count" if pd.isna(r.rooms) else f"{r.rooms:g} rooms"
        lines = [
            f"### {r.read_id}",
            f"Building: {r.building}. Ad posted {str(r.first_day)[:10]}. Coded: {fields(me)}, {rooms}.",
            "Text: " + (MONEY.sub("[amount]", X.get(r.listing_id, "")) or "(empty)"),
        ]
        for i in ctx[r.listing_id]:
            o = Ai.loc[i]
            txt = MONEY.sub("[amount]", X.get(i, ""))[:400]
            lines.append(
                f"- Other ad of the same unit, posted {str(o.first_day)[:10]}: {fields(o)}. "
                f"Text start: {txt or '(empty)'}"
            )
        blocks.append("\n".join(lines))
    for k, part in enumerate(np.array_split(np.arange(len(D)), 4)):
        p = OUT / f"batch_{k + 1}.md"
        p.write_text("\n\n".join(blocks[i] for i in part) + "\n")
        print(p.name, len(part), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    keep = [
        "read_id",
        "listing_id",
        "unit_id",
        "building",
        "half",
        "stratum",
        "bed_text",
        "u2",
        "u1",
        "u0",
        "u2_min",
        "lister",
        "first_day",
    ]
    D[keep].to_parquet(OUT / "draw.parquet")
    print(D.groupby(["stratum", "half"]).size().to_string())
    print(json.dumps({"rows": len(D), "seed": SEED}))
