"""Question 4: the ads that meet both marks, the scope a pipeline rule would have had.

The first draft's rule, chosen on half A of buildings by the reads and checked on half B: an
ad coded 0 bed whose text states 2 or more bedrooms for the unit itself (`T`) and whose unit
has another typed ad coded 2 or more (`U_any`) takes the text's count. Ledger-named ads are
left out. The review round replaced the rule with ledger sets (`z8_full_draw.py`,
`z9_candidates.py`); this count shows that a rule would cover only one ad beyond the training
rows.
"""

from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/zero-bed")

if __name__ == "__main__":
    Z = pd.read_parquet(OUT / "zeros.parquet")
    r = Z["T"] & Z.U_any & ~Z.in_ledger
    print(
        "ads changed",
        int(r.sum()),
        "training rows",
        int((r & Z.train).sum()),
        "open Deals ads",
        int((r & Z.live_open.fillna(False).astype(bool)).sum()),
    )
    m = pd.read_parquet(OUT / "marked.parquet")
    g = m[m["T"] & m.U_any]
    print(
        "units",
        g.unit_id.nunique(),
        "buildings",
        g.building.nunique(),
        "listers",
        g.lister.nunique(),
        "halves",
        g.half.value_counts().to_dict(),
    )
    print(
        "count set (bed_text)",
        g.bed_text.value_counts().sort_index().to_dict(),
        "equal to the unit's lowest count of 2 or more",
        int((g.bed_text == g.u2_min).sum()),
    )
    w = m["T"] & ~m.U_any
    print("text only, left by the rule", int(w.sum()))
