"""Step 5b: tally the blind reads of `lr5_draw.py` and copy them into the note's folder."""

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
S = Path("/data1/apartments/tmp/label-reuse")
R = pd.DataFrame(
    [
        json.loads(x)
        for k in (1, 2)
        for x in (S / f"read_labels_{k}.ndjson").open()
        if x.strip()
    ]
)
D = pd.read_parquet(S / "read_draw.parquet")
R = D[["read_id", "half", "building", "label", "lister", "text"]].merge(R, on="read_id")
R.to_csv(HERE / "reads.csv", index=False)
print("reads", len(R))
print(pd.crosstab(R.verdict, R.half, margins=True).to_string())
print(pd.crosstab(R.which_wrong, R.verdict).to_string())
print(R.names_unit.value_counts().to_dict())
print(R.a_count.value_counts().to_dict())
