"""Text flags, step 3: the fresh sample, drawn after the new patterns were frozen.

I match `b0textflags.INCOME_V2` and `b0textflags.SHARED_V2` on every known description, as the
module does, and save the old and new flags of every listing to `OUT/t3_flags.parquet` for the
scoring and the gaps. Then I split each flag's listings into parts by the old flag, the new
flag and the candidate words of `t2_dev.py`, and draw from each part. I leave out every
listing the development readers saw, so the scores describe the other listings:

- `income_restricted` and `shared_space`: both flags, the old flag only, the new flag only,
  unmarked candidates in two or three groups, and a few listings with no candidate word as a
  check;
- `rent_stabilized`, which keeps its old pattern: the old flag, unmarked listings with a word
  starting "stab" in a stabilized sense ("stabilized lease", "rent stablized"), unmarked
  listings with rent regulation, rent control or "RS", and a few with none of these.

The development sample's "stabilized" candidates were mostly "established", so the
candidate here starts at a word boundary. The counts of each part go to
`OUT/reads/eval-summary.json`, and the batches and prompts to `OUT/reads/eval-*`.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from common import OUT, READS, match_all, texts_for, write_batches

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier.b0textflags import INCOME_V2, SHARED_V2  # noqa: E402

SEED = 20261114
FLAGS = OUT / "t3_flags.parquet"
STAB_WORD = re.compile(r"\bstab(?:ili[sz]|l[ie]?[sz]|al|e?li)|rentstab")
# Matching every description takes about 10 minutes, so a rerun reuses the saved flags.
if not FLAGS.exists():
    new = match_all(
        {"income_v2": INCOME_V2, "shared_v2": SHARED_V2, "stab_word2": STAB_WORD}
    )
    t2 = pd.read_parquet(OUT / "t2_matches.parquet").drop(
        columns=["building", "held", "description_known", "known"]
    )
    t2 = t2.drop(columns=["income_restricted", "shared_space", "rent_stabilized"])
    new.merge(t2, on="listing_id", how="left", validate="one_to_one").to_parquet(
        FLAGS, index=False
    )
m = pd.read_parquet(FLAGS)
dev = set(pd.read_csv(READS / "dev-key.csv", dtype={"listing_id": str}).listing_id)
k = m[m.known & ~m.listing_id.isin(dev)]


def col(name):
    return k[name].to_numpy(bool)


inc, inc2, sh, sh2, st = (
    col(c)
    for c in (
        "income_restricted",
        "income_v2",
        "shared_space",
        "shared_v2",
        "rent_stabilized",
    )
)
cau, ci, noaff = col("caution"), col("cand_income_restricted"), col("cand_noaff")
inc_none = ~inc & ~inc2
cs, sw, sbk = col("cand_shared_space"), col("share_words"), col("sharing_bk")
sh_none = ~sh & ~sh2
cr, sw2 = col("cand_rent_stabilized"), col("stab_word2")
strata = {
    ("income_restricted", "both"): (inc & inc2, 40),
    ("income_restricted", "old only"): (inc & ~inc2, 30),
    ("income_restricted", "new only"): (~inc & inc2, 60),
    ("income_restricted", "neither, caution"): (inc_none & cau, 40),
    ("income_restricted", "neither, candidate without affordab"): (
        inc_none & ~cau & noaff,
        40,
    ),
    ("income_restricted", "neither, affordab only"): (
        inc_none & ~cau & ci & ~noaff,
        40,
    ),
    ("income_restricted", "neither, no candidate"): (inc_none & ~cau & ~ci, 20),
    ("shared_space", "both"): (sh & sh2, 50),
    ("shared_space", "old only"): (sh & ~sh2, 100),
    ("shared_space", "new only"): (~sh & sh2, 50),
    ("shared_space", "neither, share words or sharing a bath or kitchen"): (
        sh_none & (sw | sbk),
        40,
    ),
    ("shared_space", "neither, other candidate"): (sh_none & cs & ~sw & ~sbk, 40),
    ("shared_space", "neither, no candidate"): (sh_none & ~cs, 20),
    ("rent_stabilized", "old"): (st, 50),
    ("rent_stabilized", "unmarked, stabilized word"): (~st & sw2, 50),
    ("rent_stabilized", "unmarked, regulated, control or RS"): (
        ~st & ~sw2 & cr & ~col("stab_word"),
        20,
    ),
    ("rent_stabilized", "unmarked, no candidate"): (~st & ~sw2 & ~cr, 10),
}
rng = np.random.default_rng(SEED)
ids = k.listing_id.to_numpy()
counts, draws = {}, []
for (flag, name), (mask, size) in strata.items():
    pool = ids[mask]
    counts[f"{flag}: {name}"] = int(len(pool))
    take = rng.choice(pool, size=min(size, len(pool)), replace=False)
    draws.append(pd.DataFrame({"listing_id": take, "flag": flag, "stratum": name}))
sample = pd.concat(draws, ignore_index=True)
texts = texts_for(sample.listing_id)
sample["text"] = sample.listing_id.map(texts)
batches = write_batches(sample, "eval", 30)
summary = {
    "known": int(m.known.sum()),
    "dev_left_out": int(m.known.sum() - len(k)),
    "strata_without_dev": counts,
    "drawn": {
        f"{f}: {s}": int(n)
        for (f, s), n in sample.groupby(["flag", "stratum"], sort=False).size().items()
    },
    "batches": batches,
}
(READS / "eval-summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({k_: v for k_, v in summary.items() if k_ != "batches"}, indent=2))
