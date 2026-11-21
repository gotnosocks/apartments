"""Write blind reader batches for every unread ratio-mark training row (2026-11-21 hand read).

The rows are the ratio mark's training rows of the live run (status `train` in
`sw3_counts.py`, so none carries an active ledger exclude), less the 70 already read in
`reads.csv`. Each read block is built as in `sw4_draw.py`: coded fields, label, date and whole
text with dollar figures masked, and up to four other ads of the same unit. A row that also
carries the short mark gets three ads of other units of the building nearest in time, as the
short strata did. No ask is shown. Blocks are cached by listing id so the second reads reuse
them with new read ids (`ratio_r2_second.py`).
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sw4_draw import MONEY, fields, texts_for  # noqa: E402

SWEEP = Path("/data1/apartments/tmp/commercial-sweep")
OUT = Path("/data1/apartments/tmp/ratio-read")
SEED = 20261121
N_BATCH = 31

if __name__ == "__main__":
    M = pd.read_parquet(SWEEP / "marks.parquet")
    M["listing_id"] = M.listing_id.astype(str)
    done = set(pd.read_csv(HERE / "reads.csv", dtype=str).listing_id)
    D = M[(M.status == "train") & M.m_ratio & ~M.listing_id.isin(done)].copy()
    print(
        "rows",
        len(D),
        "with a text word",
        int(D.m_text.sum()),
        "without",
        int((~D.m_text).sum()),
        "halves",
        D.half.value_counts().to_dict(),
        "short",
        int(D.m_short.sum()),
    )
    rng = np.random.default_rng(SEED)
    D = D.iloc[rng.permutation(len(D))].reset_index(drop=True)
    D["read_id"] = [f"R{i + 1:03d}" for i in range(len(D))]
    ctx = {}
    for r in D.itertuples():
        u = M[(M.unit_id == r.unit_id) & (M.listing_id != r.listing_id)].copy()
        u["dt"] = (pd.to_datetime(u.first_day) - pd.Timestamp(r.first_day)).abs()
        ids = list(u.sort_values("dt").listing_id.head(4))
        if r.m_short:
            b = M[(M.building == r.building) & (M.unit_id != r.unit_id)].copy()
            b["dt"] = (pd.to_datetime(b.first_day) - pd.Timestamp(r.first_day)).abs()
            ids += list(b.sort_values("dt").listing_id.head(3))
        ctx[r.listing_id] = ids
    need = set(D.listing_id.astype(int)) | {int(i) for v in ctx.values() for i in v}
    X = texts_for(need).set_index("listing_id").desc
    Mi = M.set_index("listing_id")
    body = {}
    for r in D.itertuples():
        lines = [
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
        body[r.listing_id] = "\n".join(lines)
    (OUT / "blocks.json").write_text(json.dumps(body))
    for k, part in enumerate(np.array_split(np.arange(len(D)), N_BATCH)):
        rows = D.iloc[part]
        p = OUT / f"batch_r1_{k + 1:02d}.md"
        p.write_text(
            "\n\n".join(
                f"### {r.read_id}\n{body[r.listing_id]}" for r in rows.itertuples()
            )
            + "\n"
        )
        print(p.name, len(rows), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    keep = [
        "read_id",
        "listing_id",
        "unit_id",
        "building",
        "half",
        "bed",
        "bedrooms",
        "first_day",
        "ratio",
        "label",
        "m_text",
        "m_short",
        "l2bt_held",
    ]
    D[keep].to_parquet(OUT / "draw_r1.parquet")
