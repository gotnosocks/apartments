"""Tables for docs/notes/building-level-read-2026-11-20.md, from the working files of the read.

Reads /data1/apartments/tmp/po-bldmodes (levels_*.parquet, union_rows.parquet, packet.parquet,
union.csv from s1 to s8) and the published deals.json. Writes the csv files beside this script.
Run with the bridge-frontier python; pandas and scipy only.
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

SRC = Path("/data1/apartments/tmp/po-bldmodes")
OUT = Path(__file__).parent

# Class of each of the 96 buildings, as read (note section "Cause by building").
CLASSES = {
    "commercial": """43-west-46 138-7-avenue 147-11-street 19-howard 113-university-place 269-norman
        513-west-26 553-west-25 367-7-avenue 221-west-41 102-east-35 15-east-13 remy-101-west-28
        794-union 52-walker 1980-3-avenue 1318-fulton 65-spring 2726-broadway 1067-pacific
        83-debevoise 514-union 70-hester 1015-madison 45-west-28 55-west-28 161-madison 32-west-39
        70-hudson 347-west-broadway 180-butler 231-flatbush 140-metropolitan 32-richardson
        204-east-35 524-3-street""",
    "placeholder": """10-marconi 1042-herkimer 911-dekalb 22-revere 246-vernon 114-patchen 718-chauncey
        1209-union 350-knickerbocker 16-goodwin 384-st-johns 198-west-9 161-covert 662-nostrand
        985-jefferson 922-lincoln 993-lafayette 123-henry 1330-prospect-place""",
    "wrong_ask_or_beds": """208-east-117 390-new-york-avenue 1841-prospect-place 334-east-69 317-linden
        86-cornelia 353-5-street 98-ellery""",
    "real_difference": """21-clark aka-times-square henry-villard-houses 121-decatur 115-willow
        235-east-72 mandarin-oriental-residences 86-bedford""",
    "two_buildings_one_id": """70-henry 22-east-18 381-bleecker 101-mac-dougal 29-leonard 226-west-11
        322-east-57 the-dorilton 22-old-fulton""",
    "model_shape": """113-west-69 142-duane 406-east-50 75-grand the-majestic 3-riverview-terrace
        181-east-64 124-dekalb 665-bushwick the-branson-at-fifth 360-south-1-street""",
    "unclear": "142-east-65 428-columbus 123-east-86 321-troutman 43-west-11",
}


def klass(name: str) -> str:
    hits = []
    for cls, members in CLASSES.items():
        for m in members.split():
            if name.startswith(m + "-") or name == m:
                hits.append((len(m), cls))
    return max(hits)[1] if hits else "NONE"


u = pd.read_csv(SRC / "union.csv")
u["class"] = u.b.map(klass)
assert (u["class"] != "NONE").all(), u[u["class"] == "NONE"].b.tolist()
u.round(3).to_csv(OUT / "classes.csv", index=False)
print(u["class"].value_counts().to_string())

L = pd.read_parquet(SRC / "levels_live.parquet").set_index("building")
P = pd.read_parquet(SRC / "union_rows.parquet")
P["lid"] = P.listing_id.astype(int)

# Rows of the ten worst, without ad text beyond a short start.
top = u.sort_values("mx", ascending=False).b.head(10).tolist()
t = P[P.building.isin(top)].drop_duplicates("lid").copy()
t["text_start"] = t.desc.fillna("").map(
    lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", s)).strip()[:40]
)
t = t.sort_values(["building", "latest_day"])
t["day"] = t.latest_day.astype(str).str[:10]
t[
    [
        "building",
        "lid",
        "day",
        "bedrooms",
        "latest_ask",
        "ratio",
        "in_live",
        "in_back",
        "text_start",
    ]
].round(2).to_csv(OUT / "ten_worst_rows.csv", index=False)

# High side: Deals ads in buildings with a level over 0.5, and thin buildings over 0.3.
D = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
D["rank"] = np.arange(1, len(D) + 1)
unc = D[D.cautions.map(len) == 0].copy()
unc["urank"] = np.arange(1, len(unc) + 1)
D = D.merge(unc[["listing_id", "urank"]], how="left", on="listing_id")
D["level"] = D.building.map(L.level)
D["n_train"] = D.building.map(L.n_train)
D["rhat"] = D.building.map(L.rhat)
s = (np.log(D.model_hi80) - np.log(D.model_lo80)) / 2 / 1.2816
D["z"] = (np.log(D.ask) - np.log(D.model_median)) / s
D["below_share_no_level"] = norm.cdf(D.z + D.level / s)
D["rank_no_level"] = [
    int(np.searchsorted(D.below_share.values, v)) + 1 for v in D.below_share_no_level
]
D["cautions"] = D.cautions.map(",".join)
cols = [
    "listing_id",
    "building",
    "unit",
    "bedrooms",
    "ask",
    "model_median",
    "below_share",
    "rank",
    "urank",
    "rank_no_level",
    "level",
    "n_train",
    "rhat",
    "cautions",
]
D[D.level > 0.5][cols].round(3).to_csv(OUT / "high_level_deals_ads.csv", index=False)
D[(D.level > 0.3) & (D.n_train <= 8)][cols].round(3).to_csv(
    OUT / "thin_high_level_deals_ads.csv", index=False
)
print("deals", len(D), "uncautioned", len(unc))
print(
    "level>0.5 ads",
    (D.level > 0.5).sum(),
    "buildings",
    D[D.level > 0.5].building.nunique(),
    "max rhat",
    D[D.level > 0.5].rhat.max().round(3),
)
print(
    "first 300: level>0.3",
    ((D["rank"] <= 300) & (D.level > 0.3)).sum(),
    "level>0.2",
    ((D["rank"] <= 300) & (D.level > 0.2)).sum(),
)
thin5 = D[(D.level > 0.3) & (D.n_train <= 5)]
print("thin<=5:", len(thin5), "in first 300", (thin5["rank"] <= 300).sum())
thin8 = D[(D.level > 0.3) & (D.n_train <= 8)]
print(
    "thin<=8:",
    len(thin8),
    "in first 300",
    (thin8["rank"] <= 300).sum(),
    "ranks",
    sorted(thin8["rank"].tolist())[:6],
)
