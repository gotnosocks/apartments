"""Outdoor size, step 1: the extractor against the reads I developed it on.

S7's Sonnet readers gave the private outdoor area of 400 ads in square feet, summing several
private spaces and leaving shared ones out (`causal-screens-2026-11-13/s7_text.py`, the
labels in `s7_labels.parquet`). S16's readers judged 30 ads with an S7 area of 300 sq ft or
more and 30 with a private outdoor word on an uncoded listing (`blind-spots-2026-11-14`). I
run `b0outdoorsize.outdoor_area` on each of these texts and print where it disagrees with the
reader. These 460 ads are my development set, and the precision draw of step 4 leaves them
out.

    python o1_dev.py [-v]
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier.b0outdoorsize import areas, outdoor_area, plain  # noqa: E402

S7 = Path("/data1/apartments/tmp/sprint-20261113/")
S16 = Path("/data1/apartments/tmp/blind-spots-2026-11-14/prec/")
OUT = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/")
verbose = "-v" in sys.argv

x = pd.read_parquet(S7 / "s7_picks.parquet").merge(
    pd.read_parquet(S7 / "s7_labels.parquet"), on="read_id"
)
got = [outdoor_area(t) for t in x.description]
x["mine"], x["src"] = [g[0] for g in got], [g[1] for g in got]
x["reader"] = x.outdoor_sqft
both = x.mine.notna() & x.reader.notna()
agree = both & ((x.mine - x.reader).abs() <= 0.05 * x.reader)
s7_agree = (
    x.out_sqft.notna()
    & x.reader.notna()
    & ((x.out_sqft - x.reader).abs() <= 0.05 * x.reader)
)
res = {
    "s7_reads": len(x),
    "reader_area": int(x.reader.notna().sum()),
    "mine_area": int(x.mine.notna().sum()),
    "s7_area": int(x.out_sqft.notna().sum()),
    "both": int(both.sum()),
    "agree_5pct": int(agree.sum()),
    "mine_only": int((x.mine.notna() & x.reader.isna()).sum()),
    "reader_only": int((x.mine.isna() & x.reader.notna()).sum()),
    "s7_agree_5pct": int(s7_agree.sum()),
    "s7_only": int((x.out_sqft.notna() & x.reader.isna()).sum()),
}
for _, r in x[(x.mine.notna() | x.reader.notna()) & ~agree].iterrows():
    print(f"--- S7 read {r.read_id}: mine {r.mine} ({r.src}), reader {r.reader}")
    if verbose:
        low = plain(r.description)
        print(json.dumps(areas(low)))
        print(low[:3000])

for name in ("outdoor_large", "outdoor_uncoded"):
    b = pd.read_json(S16 / f"{name}.jsonl", lines=True)
    b = b.merge(pd.read_json(S16 / f"answers_{name}.jsonl", lines=True), on="read_id")
    b["mine"] = [outdoor_area(t)[0] for t in b.description]
    tab = pd.crosstab(b.answer, b.mine.notna())
    res[name] = {f"{k}/{v}": int(tab.loc[k, v]) for k in tab.index for v in tab.columns}
    for _, r in b[(b.answer != "yes") & b.mine.notna()].iterrows():
        print(f"--- S16 {name} {r.read_id}: mine {r.mine}, reader {r.answer}")
        print("    ", r.evidence)
print(json.dumps(res, indent=1))
(OUT / "o1_dev.json").write_text(json.dumps(res, indent=1))
