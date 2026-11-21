import pandas as pd

M = pd.read_parquet(
    "/data1/apartments/tmp/commercial-sweep/marks.parquet",
    columns=["status", "m_ratio", "m_text", "half"],
)
t = M[(M.status == "train") & M.m_ratio]
print(pd.crosstab(t.m_text, t.half))
R = pd.read_parquet("/data1/apartments/tmp/commercial-sweep/reads.parquet")
r = R[R.m_ratio].copy()
r["bad"] = r.answer.isin(["commercial", "placeholder"])
for h in "AB":
    x = r[r.half == h]
    pools = t[t.half == h].groupby("m_text").size()
    g = x.groupby("m_text").bad.agg(["mean", "size"])
    print(
        h,
        g.to_dict(),
        "half-pool weighted",
        round(float((g["mean"] * pools).sum() / pools.sum()), 3),
    )
