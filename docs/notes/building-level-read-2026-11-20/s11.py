import pandas as pd, re

pd.set_option("display.width", 250)
U = pd.read_parquet("union_rows.parquet")
print(U.columns.tolist(), len(U))
u = pd.read_csv("union.csv")
top = u.b.head(10).tolist()
P = pd.read_parquet("packet.parquet")
print(P.columns.tolist())
out = []
for b in top:
    r = u[u.b == b].iloc[0]
    out.append(
        f"\n### {b}\nR-hat live {r.rl:.2f}, backtest {r.rb:.2f}; level live {r.ll:.2f}, backtest {r.lb:.2f}\n\n| listing | day | beds | ask | x nb median | in live / back | text (start) |\n|---|---|---|---|---|---|---|"
    )
    g = (
        P[P.building == b].sort_values("latest_day").drop_duplicates("listing_id")
        if "building" in P
        else None
    )
    for x in g.itertuples():
        d = re.sub(r"[\s|]+", " ", str(getattr(x, "desc", "") or ""))[:90]
        runs = (
            ",".join(sorted(set(P[P.listing_id == x.listing_id].run)))
            if "run" in P
            else ""
        )
        out.append(
            f"| {x.listing_id} | {str(x.latest_day)[:10]} | {x.bedrooms:.0f} | ${x.latest_ask:,.0f} | {x.ratio:.1f} | {runs} | {d} |"
        )
open("ten.md", "w").write("\n".join(out))
print("\n".join(out)[:6000])
print(
    U[U.building == "1330-prospect-place-brooklyn"].to_string()
    if "building" in U
    else ""
)
