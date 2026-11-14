"""S16, part 7: score the precision reads of part 5.

For each pattern I count the reader's yes, no and unclear answers on its 30 matches and give
the precision two ways, each with a 95% Wilson interval: yes over all 30, counting an unclear
answer as a miss, and yes over the answers that settle it."""

import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/prec/"
PATTERNS = (
    "studio_rooms",
    "studio_text_beds",
    "nonresidential",
    "outdoor_uncoded",
    "outdoor_large",
)


def wilson(k, n, z=1.96):
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(mid - half, 3), round(mid + half, 3)


res = {}
for p in PATTERNS:
    b = pd.read_json(OUT + p + ".jsonl", lines=True)
    a = pd.read_json(OUT + "answers_" + p + ".jsonl", lines=True)
    assert len(a) == len(b) == 30 and (a.read_id == b.read_id).all()
    c = a.answer.value_counts()
    yes, no, unclear = (int(c.get(k, 0)) for k in ("yes", "no", "unclear"))
    res[p] = {
        "yes": yes,
        "no": no,
        "unclear": unclear,
        "precision_all": round(yes / 30, 3),
        "precision_all_ci": wilson(yes, 30),
        "precision_settled": round(yes / (yes + no), 3),
        "precision_settled_ci": wilson(yes, yes + no),
    }
    print(p, json.dumps(res[p]))
json.dump(res, open(OUT + "precision.json", "w"), indent=1)
