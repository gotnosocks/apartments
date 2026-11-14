"""Text flags, step 2: the development sample, read before any new pattern was written.

For each flag I split the listings of L1's dataset with a known description by which of a
few patterns mark them, and draw a fixed number from each part:

- `income_restricted`: the old flag and `b0income.INCOME` both, the old flag alone, INCOME
  alone, the Deals caution's income pattern alone (`cautions.TEXT["income"]`), and the
  candidates none of the three marks, half of them with "affordab" as their only candidate
  word;
- `shared_space`: the old flag's hits through "roommate", through a shared bath or kitchen
  and through "sro", and unmarked candidates through co-living, share wording ("apartment
  share", "room for rent", "room in a"), sharing a bath or kitchen, a misspelled roommate or
  a housemate, and the rest of the candidates;
- `rent_stabilized`: the old flag's hits, unmarked candidates with a misspelled or bare
  "stabilized", and unmarked candidates through rent regulation, rent control or "RS".

The readers get each flag's rubric from `common.RUBRICS`. The draw, the counts of each part
and the batches go to `OUT/reads/dev-*`. The matches of every pattern go to
`OUT/t2_matches.parquet` for `t3_eval.py`.
"""

import json
import re

import numpy as np
import pandas as pd
from common import (
    B0INCOME,
    CANDIDATES,
    OUT,
    cautions,
    match_all,
    texts_for,
    write_batches,
)

SEED = 20261113
PATTERNS = {
    "b0income": B0INCOME,
    "caution": re.compile(cautions.TEXT["income"]),
    **{f"cand_{f}": rx for f, rx in CANDIDATES.items()},
    # The income candidates without "affordab".
    "cand_noaff": re.compile(
        CANDIDATES["income_restricted"].pattern.replace("|affordab", "")
    ),
    "roommate": re.compile(r"roommate"),
    "shared_bk": re.compile(r"shared (?:bath|kitchen)"),
    "sro": re.compile(r"\bsro\b"),
    "coliving": re.compile(r"co-?living"),
    "share_words": re.compile(
        r"\b(?:apartment|apt|house|room) share\b|\bin a share\b"
        r"|\bshared (?:apartment|house|unit)|\brooms? (?:for rent|available)"
        r"|private (?:bed)?room in|\broom in (?:a|an|my|our)\b"
    ),
    "sharing_bk": re.compile(r"shar(?:e|ed|ing) (?:a |the |an )?(?:bath|kitchen)"),
    "mates": re.compile(r"roomate|housemate|flatmate"),
    "stab_word": re.compile(r"stabili[sz]|stabl[ie]?[sz]|stabal|stabe?li"),
}

MATCHES = OUT / "t2_matches.parquet"
# Matching every description takes about 13 minutes, so a rerun reuses the saved matches.
if not MATCHES.exists():
    match_all(PATTERNS).to_parquet(MATCHES, index=False)
m = pd.read_parquet(MATCHES)
k = m[m.known]
old = {
    f: k[f].to_numpy(bool)
    for f in ("income_restricted", "shared_space", "rent_stabilized")
}
inc, sh, st = old["income_restricted"], old["shared_space"], old["rent_stabilized"]
b0, cau = k.b0income.to_numpy(bool), k.caution.to_numpy(bool)
ci, cs, cr = (
    k[f"cand_{f}"].to_numpy(bool)
    for f in ("income_restricted", "shared_space", "rent_stabilized")
)
inc_rest = ci & ~inc & ~b0 & ~cau
noaff = k.cand_noaff.to_numpy(bool)
strata = {
    ("income_restricted", "old+b0income"): inc & b0,
    ("income_restricted", "old only"): inc & ~b0,
    ("income_restricted", "b0income only"): ~inc & b0,
    ("income_restricted", "caution only"): ~inc & ~b0 & cau,
    ("income_restricted", "candidate, affordab only"): inc_rest & ~noaff,
    ("income_restricted", "candidate, other words"): inc_rest & noaff,
    ("shared_space", "old roommate"): sh & k.roommate.to_numpy(bool),
    ("shared_space", "old shared bath or kitchen"): sh & k.shared_bk.to_numpy(bool),
    ("shared_space", "old sro"): sh & k.sro.to_numpy(bool),
    ("shared_space", "cand co-living"): ~sh & k.coliving.to_numpy(bool),
    ("shared_space", "cand share words"): ~sh & k.share_words.to_numpy(bool),
    ("shared_space", "cand sharing bath or kitchen"): ~sh & k.sharing_bk.to_numpy(bool),
    ("shared_space", "cand mates"): ~sh & k.mates.to_numpy(bool),
    ("shared_space", "cand other"): ~sh
    & cs
    & ~k[["coliving", "share_words", "sharing_bk", "mates"]].any(axis=1).to_numpy(),
    ("rent_stabilized", "old"): st,
    ("rent_stabilized", "cand stabilized word"): ~st & k.stab_word.to_numpy(bool),
    ("rent_stabilized", "cand regulated or control"): ~st
    & cr
    & ~k.stab_word.to_numpy(bool),
}
size = {
    ("income_restricted", "old+b0income"): 25,
    ("income_restricted", "old only"): 20,
    ("income_restricted", "b0income only"): 25,
    ("income_restricted", "caution only"): 25,
    ("income_restricted", "candidate, affordab only"): 20,
    ("income_restricted", "candidate, other words"): 20,
    ("shared_space", "old roommate"): 20,
    ("shared_space", "old shared bath or kitchen"): 20,
    ("shared_space", "old sro"): 10,
    ("shared_space", "cand co-living"): 15,
    ("shared_space", "cand share words"): 25,
    ("shared_space", "cand sharing bath or kitchen"): 15,
    ("shared_space", "cand mates"): 10,
    ("shared_space", "cand other"): 15,
    ("rent_stabilized", "old"): 30,
    ("rent_stabilized", "cand stabilized word"): 30,
    ("rent_stabilized", "cand regulated or control"): 10,
}
rng = np.random.default_rng(SEED)
ids = k.listing_id.to_numpy()
counts, draws = {}, []
for (flag, name), mask in strata.items():
    pool = ids[mask]
    counts[f"{flag}: {name}"] = int(len(pool))
    take = rng.choice(pool, size=min(size[(flag, name)], len(pool)), replace=False)
    draws.append(pd.DataFrame({"listing_id": take, "flag": flag, "stratum": name}))
sample = pd.concat(draws, ignore_index=True)
# A listing drawn for two parts of one flag is read once, in its first part.
sample = sample.drop_duplicates(["listing_id", "flag"])
texts = texts_for(sample.listing_id)
sample["text"] = sample.listing_id.map(texts)
batches = write_batches(sample, "dev", 30)
summary = {
    "known": int(len(k)),
    "old_flags": {f: int(v.sum()) for f, v in old.items()},
    "b0income": int(b0.sum()),
    "caution": int(cau.sum()),
    "candidates": {f: int(k[f"cand_{f}"].sum()) for f in CANDIDATES},
    "strata": counts,
    "drawn": {
        f"{f}: {s}": int(n)
        for (f, s), n in sample.groupby(["flag", "stratum"]).size().items()
    },
    "batches": batches,
}
(OUT / "reads" / "dev-summary.json").write_text(
    json.dumps(summary, indent=2, default=str)
)
print(
    json.dumps(
        {k_: v for k_, v in summary.items() if k_ != "batches"}, indent=2, default=str
    )
)
