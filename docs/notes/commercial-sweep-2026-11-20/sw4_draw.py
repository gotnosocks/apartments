"""Draw about 150 marked training rows for blind reads, and write the reader batches.

The draw takes training rows of the live run (status `train` in `sw3_counts.py`) in strata:
the ratio mark with a text word, the ratio mark alone, each narrowed text word alone, and
short texts alone split by coded 0 bed or more. Each read shows the ad's coded fields, label,
date and whole text, and the coded fields and text start of up to four other ads of the same
unit; a short-text read also shows up to three ads of other units of the building nearest in
time. No ask is shown and dollar figures in texts are masked, so the readers never see where
the ask sits against the area or the model. Batches mix the strata in a seeded order.
"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path("/data1/apartments/tmp/commercial-sweep")
REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
SEED = 20261120
STRATA = [
    ("ratio_text", 30),
    ("ratio_only", 40),
    ("per_sf", 8),
    ("warehouse", 8),
    ("storefront", 8),
    ("retail", 8),
    ("office", 8),
    ("short_0bed", 20),
    ("short_beds", 20),
]
MONEY = re.compile(
    r"\$\s?[\d,.]+\s?(?:k|m)?\b|\b\d[\d,.]*\s?(?:dollars|usd)\b|"
    r"\b\d[\d,.]*\s*(?:/\s*mo(?:nth)?|per\s+month|a\s+month|monthly)\b",
    re.I,
)


def stratum(r) -> str | None:
    if r.m_ratio:
        return "ratio_text" if r.m_text else "ratio_only"
    if r.m_text:
        for c, s in (
            ("t_per_sf", "per_sf"),
            ("t_warehouse", "warehouse"),
            ("t_storefront", "storefront"),
            ("n_retail", "retail"),
            ("n_office", "office"),
        ):
            if r[c]:
                return s
    if r.m_short:
        return "short_0bed" if r.bed == 0 else "short_beds"
    return None


def texts_for(ids: set[int]) -> pd.DataFrame:
    f = pq.ParquetFile(REC)
    parts = []
    for g in range(f.metadata.num_row_groups):
        got = f.read_row_group(g, columns=["listing_id"]).column(0).to_numpy()
        if not ids.intersection(got.tolist()):
            continue
        p = f.read_row_group(
            g, columns=["listing_id", "collected_at", "raw_listing_json"]
        ).to_pandas()
        parts.append(p[p.listing_id.isin(ids)])
    R = pd.concat(parts).sort_values("collected_at").groupby("listing_id").tail(1)
    js = R.raw_listing_json.map(json.loads)
    return pd.DataFrame(
        {
            "listing_id": R.listing_id.astype(str).values,
            "desc": js.map(lambda j: j.get("description") or "").values,
        }
    )


def fields(r) -> str:
    sq = "" if pd.isna(r.square_feet) else f", {int(r.square_feet)} sq ft"
    return f"label {r.label!r}, {r.bed:g} bed, {r.full_baths} full and {r.half_baths} half baths{sq}"


if __name__ == "__main__":
    M = pd.read_parquet(OUT / "marks.parquet")
    t = M[M.status == "train"].copy()
    t["stratum"] = t.apply(stratum, axis=1)
    pool = t.stratum.value_counts()
    rng = np.random.default_rng(SEED)
    draw = []
    for s, n in STRATA:
        x = t[t.stratum == s]
        draw.append(x.iloc[rng.choice(len(x), size=min(n, len(x)), replace=False)])
    D = pd.concat(draw)
    D = D.iloc[rng.permutation(len(D))].reset_index(drop=True)
    D["read_id"] = [f"C{i + 1:03d}" for i in range(len(D))]
    D["pool"] = D.stratum.map(pool)
    print("pool", pool.to_dict())
    print(
        "drawn",
        D.stratum.value_counts().to_dict(),
        "halves",
        D.half.value_counts().to_dict(),
    )
    ctx = {}
    for r in D.itertuples():
        u = M[(M.unit_id == r.unit_id) & (M.listing_id != r.listing_id)].copy()
        u["dt"] = (pd.to_datetime(u.first_day) - pd.Timestamp(r.first_day)).abs()
        ids = list(u.sort_values("dt").listing_id.head(4))
        if r.stratum.startswith("short"):
            b = M[(M.building == r.building) & (M.unit_id != r.unit_id)].copy()
            b["dt"] = (pd.to_datetime(b.first_day) - pd.Timestamp(r.first_day)).abs()
            ids += list(b.sort_values("dt").listing_id.head(3))
        ctx[r.listing_id] = ids
    need = set(D.listing_id.astype(int)) | {int(i) for v in ctx.values() for i in v}
    X = texts_for(need).set_index("listing_id").desc
    Mi = M.set_index("listing_id")
    blocks = []
    for r in D.itertuples():
        lines = [
            f"### {r.read_id}",
            f"Building: {r.building}. Ad posted {r.first_day}. Coded: {fields(r)}.",
            "Text: " + (MONEY.sub("[amount]", X.get(r.listing_id, "")) or "(empty)"),
        ]
        for i in ctx[r.listing_id]:
            o = Mi.loc[i]
            same = (
                "same unit" if o.unit_id == r.unit_id else "other unit of the building"
            )
            txt = MONEY.sub("[amount]", X.get(i, ""))[:300].replace("\n", " ")
            lines.append(
                f"- Other ad ({same}), posted {o.first_day}: {fields(o)}. "
                f"Text start: {txt or '(empty)'}"
            )
        blocks.append("\n".join(lines))
    for k in range(0, len(blocks), 25):
        p = OUT / f"batch_{k // 25 + 1}.md"
        p.write_text("\n\n".join(blocks[k : k + 25]) + "\n")
        print(p.name, hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    keep = [
        "read_id",
        "listing_id",
        "unit_id",
        "building",
        "half",
        "stratum",
        "pool",
        "bed",
        "ratio",
        "label",
        "m_ratio",
        "m_text",
        "m_short",
        "l2bt_held",
    ]
    D[keep].to_parquet(OUT / "draw.parquet")
