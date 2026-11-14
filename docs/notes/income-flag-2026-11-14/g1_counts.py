"""S15b, step 1: the rows the negation guard changes and the tiers the rebuild reads.

I ran this once with the rebuilt copy at `NEW` and the copy it replaces still at `OLD`,
before I moved the new copy into place. The script:

1. checks that every column of the old copy is unchanged in the new one except
   `income_restricted_v2`, and counts the rows, listings, training rows and held-out ads
   whose flag the guard turns off or on;
2. counts, among the rows the guarded flag marks, those with an `ami_pct_text`, with at
   least one stated percentage, with several and with an income band, for training rows and
   held-out ads, and the tiers in S15b's bins;
3. writes two samples for the Sonnet readers, from the descriptions `g0_texts.py` copied:
   the listings the guard unmarks (all of them, up to 40), and 50 listings with a tier plus
   every listing with several tiers, with the values the rebuild read.

Results go to `OUT/g1_counts.json`, the samples to `OUT/unmarked_sample.txt` and
`OUT/tier_sample.txt`.

    systemd-run --user --scope -q -p MemoryMax=3G python g1_counts.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import b0textflags

BASE = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
OLD, NEW = Path(BASE), Path(BASE + ".new")
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
BINS = ["50 or less", "51 to 80", "81 to 100", "101 to 130", "above 130"]


def tier_bin(pct, tiers):
    """S15b's bin for an ad with tier `pct` (NaN if none is tied) stating `tiers` tiers."""
    if tiers == 0:
        return "none stated"
    if pct != pct:
        return "several, none tied"
    return BINS[int(np.searchsorted([50, 80, 100, 130], pct, side="left"))]


old = pd.read_parquet(OLD / "rows.parquet")
new = pd.read_parquet(NEW / "rows.parquet")
assert len(old) == len(new)
assert (old.listing_id.to_numpy() == new.listing_id.to_numpy()).all()
same = [c for c in old.columns if c != "income_restricted_v2"]
pd.testing.assert_frame_equal(old[same], new[same])
held = np.load(RUN + "pred_scores.npz", allow_pickle=True)["heldout"]
was, now = (
    old.income_restricted_v2.to_numpy(bool),
    new.income_restricted_v2.to_numpy(bool),
)
res = {"rows": len(new), "heldout": int(held.sum())}
res["guard"] = {
    f"{name} {part}": {
        "rows": int((on & rows).sum()),
        "listings": int(new.listing_id[on & rows].nunique()),
    }
    for name, on in (("unmarked", was & ~now), ("marked", ~was & now))
    for part, rows in (
        ("all", np.ones(len(new), bool)),
        ("training", ~held),
        ("heldout", held),
    )
}
res["guard"]["marked before"] = {
    "training": int((was & ~held).sum()),
    "heldout": int((was & held).sum()),
}
res["guard"]["marked after"] = {
    "training": int((now & ~held).sum()),
    "heldout": int((now & held).sum()),
}

new["bin"] = [tier_bin(p, t) for p, t in zip(new.ami_pct_text, new.ami_tiers_text)]
terms = {}
for part, rows in (("training", ~held), ("heldout", held)):
    x = new[now & rows]
    band = x.income_min_text.notna() | x.income_max_text.notna()
    terms[part] = {
        "ads": len(x),
        "ami_pct": int(x.ami_pct_text.notna().sum()),
        "share_ami_pct": float(x.ami_pct_text.notna().mean()),
        "any_stated": int((x.ami_tiers_text >= 1).sum()),
        "share_any_stated": float((x.ami_tiers_text >= 1).mean()),
        "several": int((x.ami_tiers_text > 1).sum()),
        "band": int(band.sum()),
        "share_band": float(band.mean()),
        "income_min": int(x.income_min_text.notna().sum()),
        "income_max": int(x.income_max_text.notna().sum()),
        "bins": x.bin.value_counts().to_dict(),
        "tiers": x.ami_pct_text.value_counts().sort_index().to_dict(),
        "listings_with_pct": int(x.listing_id[x.ami_pct_text.notna()].nunique()),
    }
res["terms"] = terms
print(json.dumps(res, indent=1, default=str))
json.dump(res, open(OUT / "g1_counts.json", "w"), indent=1, default=str)

# Samples for the readers.
texts = pd.read_parquet(OUT / "v2_texts.parquet")
texts["listing_id"] = texts.listing_id.astype(str)
texts = texts.drop_duplicates("listing_id").set_index("listing_id").text
new["listing_id"] = new.listing_id.astype(str)
rng = np.random.default_rng(20261114)
gone = np.array(sorted(set(new.listing_id[was & ~now])))
gone = rng.permutation(gone)[:40]
with open(OUT / "unmarked_sample.txt", "w") as f:
    for i, lid in enumerate(gone, 1):
        f.write(f"=== Ad U{i} (listing {lid})\n{texts.get(lid, '')}\n\n")
per = new[now].drop_duplicates("listing_id").set_index("listing_id")
one = per.index[per.ami_pct_text.notna()].to_numpy()
several = per.index[per.ami_tiers_text > 1].to_numpy()
pick = list(rng.permutation(one)[:50]) + list(several)
with open(OUT / "tier_sample.txt", "w") as f:
    for i, lid in enumerate(pick, 1):
        r = per.loc[lid]
        f.write(
            f"=== Ad T{i} (listing {lid})\n"
            f"Extracted: ami_pct_text={r.ami_pct_text}, ami_tiers_text={r.ami_tiers_text}, "
            f"income_min_text={r.income_min_text}, income_max_text={r.income_max_text}\n"
            f"{texts.get(lid, '')}\n\n"
        )
print(len(gone), "unmarked listings and", len(pick), "tier listings written")
