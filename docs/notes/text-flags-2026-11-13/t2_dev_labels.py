"""Text flags, step 2b: the development readers' labels by flag and part of the draw.

I join each reader's labels to the dev key and count the labels in each part. With
`--quotes FLAG` I also print the evidence quote of each ad of that flag, by part and label,
for writing the new patterns.
"""

import sys

import pandas as pd
from common import read_labels

lab = read_labels("dev")
missing = lab.label.isna().sum()
print(f"dev ads {len(lab)}, without a label {missing}")
table = lab.groupby(["flag", "stratum"]).label.value_counts().unstack(fill_value=0)
with pd.option_context("display.width", 200):
    print(table)
if len(sys.argv) > 2 and sys.argv[1] == "--quotes":
    part = lab[lab.flag == sys.argv[2]].sort_values(["stratum", "label"])
    for r in part.itertuples():
        print(f"{r.stratum} | {r.label} | {r.id} | {r.evidence}")
