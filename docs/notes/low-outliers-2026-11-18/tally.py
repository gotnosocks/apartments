import json, glob, collections, pandas as pd

K = pd.read_csv("key.csv", dtype={"listing_id": str}).set_index("listing_id")
rows = []
for f in sorted(glob.glob("answers/g*.jsonl")):
    for line in open(f):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception as e:
            print("bad line", f, line[:80])
            continue
        rows.append(r)
A = pd.DataFrame(rows)
A["listing_id"] = A.listing_id.astype(str)
A = A[A.listing_id.isin(K.index)].drop_duplicates("listing_id")
A["set"] = A.listing_id.map(K.set)
A["cdf"] = A.listing_id.map(K.cdf)
A.to_json("answers_joined.jsonl", orient="records", lines=True)
n = A.set.value_counts()
print(n.to_dict(), "missing", len(K) - len(A))
codes = collections.Counter(c for r in A.reasons for c in r)
T = pd.DataFrame(
    {
        c: A.groupby("set").apply(lambda g: sum(c in r for r in g.reasons) / len(g))
        for c in codes
    }
).T
T["n_all"] = pd.Series(codes)
print(
    (T.sort_values("below", ascending=False) * [100, 100, 100, 100, 1])
    .round(0)
    .astype(int)
    .to_string()
)
for k in ["low_vs_history", "real_deal"]:
    print(
        (pd.crosstab(A[k], A.set, normalize="columns") * 100)
        .round(0)
        .astype(int)
        .to_string()
    )
print(
    "no reason:",
    A.groupby("set")
    .apply(lambda g: sum(len(r) == 0 for r in g.reasons) / len(g))
    .round(2)
    .to_dict(),
)
