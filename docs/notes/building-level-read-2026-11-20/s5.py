import pandas as pd, numpy as np

pd.set_option(
    "display.width", 300, "display.max_rows", 2000, "display.max_colwidth", 60
)
p = pd.read_parquet("packet.parquet")
L = pd.concat([pd.read_parquet(f"levels_{t}.parquet") for t in ("live", "back")])
mx = L.groupby("building").rhat.max()
r = p[p.grp == "rhat"].copy()
r["mx"] = r.building.map(mx)
r["dl"] = r.desc.fillna("").str.len()
r["hasrec"] = r.desc.notna()
r = r.sort_values(["mx", "building", "latest_day"], ascending=[False, True, True])
big = r.building.map(r.groupby("building").size()) > 45
r = r[~big]
print(len(r), r.hasrec.mean(), (r.dl > 5).mean())
for b, g in r.groupby("building", sort=False):
    print(f"\n## {b} rhat {g.mx.iloc[0]:.2f} {g.neighbourhood.iloc[0]}")
    print(
        g[
            [
                "listing_id",
                "latest_day",
                "bedrooms",
                "full_baths",
                "latest_ask",
                "ratio",
                "nb_p99",
                "unit",
                "square_feet",
                "heldout",
                "run",
                "src",
                "dl",
                "shared_space",
                "furn_rent",
            ]
        ]
        .round(2)
        .to_string(index=False, header=False)
    )
