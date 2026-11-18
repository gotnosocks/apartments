"""The readers' answers by set: the verdicts, the reason codes and the notes of chosen sets."""

import collections
import glob
import json
import sys

import pandas as pd

OUT = "/data1/apartments/tmp/rooms-up-read-2026-11-18/"
K = pd.read_csv(OUT + "key.csv", dtype={"listing_id": str}).set_index("listing_id")
rows = []
for f in sorted(glob.glob(OUT + "answers/g*.jsonl")):
    for line in open(f):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                print("bad line", f, line[:80])
A = pd.DataFrame(rows)
A["listing_id"] = A.listing_id.astype(str)
A = A[A.listing_id.isin(K.index)].drop_duplicates("listing_id")
A["set"] = A.listing_id.map(K.set)
A["cdf"] = A.listing_id.map(K.cdf)
A.to_json(OUT + "answers_joined.jsonl", orient="records", lines=True)
print(A.set.value_counts().to_dict(), "missing", len(K) - len(A))
for k in ("real_deal", "low_vs_history"):
    print(pd.crosstab(A[k], A.set).to_string())
codes = collections.Counter(c for r in A.reasons for c in r)
T = pd.DataFrame(
    {c: A.groupby("set").reasons.apply(lambda g: sum(c in r for r in g)) for c in codes}
).T
print(T.assign(n=pd.Series(codes)).sort_values("n", ascending=False).to_string())
for s in sys.argv[1:]:
    print("\n==", s)
    for _, r in A[A.set == s].sort_values("cdf").iterrows():
        print(f"{r.cdf:.3f} {r.real_deal:8s} {','.join(r.reasons):40s} {r.note[:230]}")
