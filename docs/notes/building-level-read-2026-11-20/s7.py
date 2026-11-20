import pandas as pd, numpy as np

p = pd.read_parquet("union_rows.parquet")
L = pd.concat([pd.read_parquet(f"levels_{t}.parquet") for t in ("live", "back")])
mx = L.groupby("building").rhat.max()
p["mx"] = p.building.map(mx)
p = p.sort_values(["mx", "building", "latest_day"], ascending=[False, True, True])
out = []
tot = 0
for b, g in p.groupby("building", sort=False):
    if len(g) > 30:
        g = g.drop_duplicates("desc").head(4)
    out.append(f"\n## {b} ({g.neighbourhood.iloc[0]})")
    seen = {}
    for r in g.itertuples():
        d = (
            (r.desc if isinstance(r.desc, str) else "[NO RECORD]")
            .strip()
            .replace("\n", " ")
        )
        h = f"- {r.listing_id} {str(r.latest_day)[:10]} {r.bedrooms:.0f}bd/{r.full_baths:.0f}ba ${r.latest_ask:,.0f} x{r.ratio:.1f} unit={r.unit} sf={r.square_feet} live={int(r.in_live)}"
        if d in seen and len(d) > 40:
            out.append(h + f" [same text as {seen[d]}]")
            continue
        seen[d] = r.listing_id
        tot += len(d)
        out.append(h + f"\n  TEXT: {d}")
open("texts.txt", "w").write("\n".join(out))
print(tot)
