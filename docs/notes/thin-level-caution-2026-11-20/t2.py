"""Sizing of placeholder-text and commercial ads among training rows of the Deals datasets, and the
held-out gap (l2bt) of ads in buildings that hold one."""

import re, numpy as np, pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 120)
T = pd.read_parquet("texts_flags.parquet")
T["listing_id"] = T.listing_id.astype(str)
BITS = [
    "bed",
    "apt",
    "kitchen",
    "living",
    "bath",
    "closet",
    "studio",
    "home",
    "laundry",
    "live",
]
for k, b in enumerate(BITS):
    T["r_" + b] = (T.bits.to_numpy() >> k) & 1
low = T.text.fillna("").str.lower()
PLACE = re.compile(
    r"^(draft|tbd|tba|desc(ription)?|test|n/?a|none|coming soon|more (info|details) (coming|to come)( soon)?|details (coming|to come)( soon)?|description coming soon|\W*)$"
)
T["empty_"] = T.n == 0
T["nodesc"] = T.n < 0
T["short"] = (T.n > 0) & (T.n < 10)
T["placeword"] = (
    (T.n > 0) & (T.n < 40) & low.map(lambda s: bool(PLACE.match(s.strip(" .!"))))
)
T["placeholder"] = T.empty_ | T.short | T.placeword
COM = re.compile(
    r"office space|retail|store ?front|commercial (space|unit|lease|use|property|building|tenant)|medical (office|space|use)|doctor'?s? office|dental office|professional (office|space|use)|restaurant (space|available|for)|warehouse|gallery space|art gallery|triple net|\bnnn\b|per (sf|sq\.? ?ft\.?|square foot)|/ ?r?sf\b|rentable square|build to suit|signage|foot traffic|white ?box|community facility|(store|shop|space|office|offices) for (rent|lease)|land lease|any use|all uses"
)
T["com"] = low.map(lambda s: bool(COM.search(s)))
T["res"] = (
    T.r_bed | T.r_apt | T.r_living | T.r_closet | T.r_laundry | T.r_live | T.r_home
).astype(bool)
T["commercial"] = T.com & ~T.res & (T.n >= 10)
print(
    "listings",
    len(T),
    "nodesc",
    T.nodesc.sum(),
    "empty",
    T.empty_.sum(),
    "short",
    T.short.sum(),
    "placeword",
    T.placeword.sum(),
    "com",
    T.com.sum(),
    "commercial",
    T.commercial.sum(),
)
print(
    T[T.short | T.placeword]
    .text.str.strip()
    .str.lower()
    .value_counts()
    .head(40)
    .to_string()
)
T.to_parquet("texts_ruled.parquet")
K = [
    "listing_id",
    "n",
    "nodesc",
    "empty_",
    "short",
    "placeword",
    "placeholder",
    "commercial",
    "com",
    "res",
    "text",
    "record",
]
import pyarrow.parquet as pq


def ds(path, heldout):
    f = pd.read_parquet(
        path,
        columns=[
            "listing_id",
            "building",
            "neighbourhood",
            "bedrooms",
            "latest_ask",
            "latest_day",
            "description_known",
        ],
    )
    f["listing_id"] = f.listing_id.astype(str)
    f["held"] = heldout
    f["year"] = pd.to_datetime(f.latest_day).dt.year
    med = (
        f[~f.held]
        .groupby(["neighbourhood", "year", "bedrooms"])
        .latest_ask.median()
        .rename("med")
        .reset_index()
    )
    f = f.merge(med, how="left", on=["neighbourhood", "year", "bedrooms"])
    f["ratio"] = f.latest_ask / f.med
    return f.merge(T[K], how="left", on="listing_id")


from pathlib import Path

RUNS = Path("/data1/apartments/frontier/runs")
SETS = {
    "live": (
        "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3",
        "/data1/apartments/frontier/datasets/b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet",
    ),
    "back": (
        "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j",
        "/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext/rows.parquet",
    ),
}
for tag, (run, path) in SETS.items():
    held = np.load(RUNS / run / "posterior.npz")["heldout"]
    f = ds(path, held)
    tr = f[~f.held]
    print(
        f"\n==== {tag}: training rows {len(tr)}, text matched {tr.n.notna().sum()}, description_known false {(~tr.description_known.fillna(False).astype(bool)).sum()}"
    )
    tr = tr.rename(columns={"empty_": "empty"})
    for c in ("nodesc", "empty", "short", "placeword", "placeholder", "commercial"):
        tr[c] = tr[c].fillna(False).astype(bool)
    tr["hi15"] = tr.ratio > 1.5
    tr["hi2"] = tr.ratio > 2
    tr["ph_hi15"] = tr.placeholder & tr.hi15
    tr["ph_bed01"] = tr.placeholder & (tr.bedrooms <= 1)
    tr["ph_bed01_hi15"] = tr.ph_bed01 & tr.hi15
    tr["com_hi2"] = tr.commercial & tr.hi2
    y = tr.groupby("year").agg(
        rows=("held", "size"),
        nodesc=("nodesc", "sum"),
        empty=("empty", "sum"),
        short=("short", "sum"),
        placeword=("placeword", "sum"),
        placeholder=("placeholder", "sum"),
        ph_over1_5x=("ph_hi15", "sum"),
        ph_bed01_over1_5x=("ph_bed01_hi15", "sum"),
        commercial=("commercial", "sum"),
        com_over2x=("com_hi2", "sum"),
    )
    y.loc["all"] = y.sum()
    print(y.to_string())
    for c in ("empty", "short", "placeword", "commercial"):
        x = tr[tr[c]]
        print(
            c,
            "rows",
            len(x),
            "buildings",
            x.building.nunique(),
            "median ratio to nb-year-bed median",
            round(x.ratio.median(), 2),
            "share >1.5x",
            round((x.ratio > 1.5).mean(), 3),
            "share >2x",
            round((x.ratio > 2).mean(), 3),
            "share <0.67x",
            round((x.ratio < 0.67).mean(), 3),
            "| all rows >1.5x",
            round((tr.ratio > 1.5).mean(), 3),
        )
    print(
        "empty by bedrooms:",
        tr[tr["empty"] | tr.short | tr.placeword]
        .groupby("bedrooms")
        .ratio.agg(["size", "median"])
        .round(2)
        .to_dict("index"),
    )
    if tag == "live":
        tr[tr.commercial][
            [
                "listing_id",
                "building",
                "year",
                "bedrooms",
                "latest_ask",
                "ratio",
                "text",
            ]
        ].to_parquet("commercial_live.parquet")
        tr[tr.com & ~tr.commercial][
            [
                "listing_id",
                "building",
                "year",
                "bedrooms",
                "latest_ask",
                "ratio",
                "text",
            ]
        ].to_parquet("com_res_live.parquet")
        tr[tr.placeholder][
            [
                "listing_id",
                "building",
                "year",
                "bedrooms",
                "latest_ask",
                "ratio",
                "text",
                "n",
            ]
        ].to_parquet("placeholder_live.parquet")
# l2bt: gap of held-out ads in buildings holding a flagged training ad
o = pd.read_parquet("l2_ads.parquet")
S = pd.read_parquet("l2_rows_slim.parquet")
S["listing_id"] = S.listing_id.astype(str)
S = S.merge(
    T[["listing_id", "placeholder", "empty_", "short", "placeword", "commercial"]],
    how="left",
    on="listing_id",
).fillna(
    {
        "placeholder": False,
        "commercial": False,
        "empty_": False,
        "short": False,
        "placeword": False,
    }
)
f2 = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet",
    columns=["neighbourhood", "bedrooms", "latest_ask", "latest_day"],
)
S["year"] = pd.to_datetime(f2.latest_day).dt.year.to_numpy()
S["nb"] = f2.neighbourhood.to_numpy()
S["bed"] = f2.bedrooms.to_numpy()
S["ask"] = f2.latest_ask.to_numpy()
tr = S[~S.heldout]
med = tr.groupby(["nb", "year", "bed"]).ask.median().rename("med").reset_index()
tr = tr.merge(med, how="left", on=["nb", "year", "bed"])
tr["ratio"] = tr.ask / tr.med
tr["short_any"] = tr.short.astype(bool) | tr.placeword.astype(bool)
tr["ph15"] = tr.placeholder.astype(bool) & (tr.ratio > 1.5)
tr["sh15"] = tr.short_any & (tr.ratio > 1.5)
tr["com2"] = tr.commercial.astype(bool) & (tr.ratio > 2)
g = tr.groupby("building").agg(
    n=("ask", "size"),
    ph=("placeholder", "sum"),
    sh=("short_any", "sum"),
    ph15=("ph15", "sum"),
    sh15=("sh15", "sum"),
    com=("commercial", "sum"),
    com2=("com2", "sum"),
)
o = o.merge(g, how="left", left_on="building", right_index=True)
own = S[S.heldout].set_index("listing_id")
o["own_ph"] = o.listing_id.map(own.placeholder).astype(bool)
o["own_com"] = o.listing_id.map(own.commercial).astype(bool)


def line(k, m):
    for hf in (0, 1, 2):
        x = o[m & ((o.half == hf) | (hf == 2)) & ~o.own_ph & ~o.own_com]
        print(
            f"{k:34s} half {'AB*'[hf]} ads {len(x):6d} bld {x.building.nunique():5d} gap {x.gap.mean():+.4f} med {x.gap.median():+.4f} below5 {(x.cdf < 0.05).mean():.3f} above95 {(x.cdf > 0.95).mean():.3f}"
        )


print(
    "\n==== l2bt held-out ads (own ad not placeholder/commercial), by what the building's training ads hold"
)
line("all", o.n > -1)
line("building holds commercial", o.com > 0)
line("  commercial, building n<=5", (o.com > 0) & (o.n <= 5))
line("  commercial, n<=20", (o.com > 0) & (o.n <= 20))
line("  commercial share>=20%", (o.com / o.n >= 0.2))
line("  commercial at >2x median", o.com2 > 0)
line("  commercial >2x, n<=20", (o.com2 > 0) & (o.n <= 20))
line("building holds placeholder", o.ph > 0)
line("  short/word placeholder", o.sh > 0)
line("  placeholder at >1.5x", o.ph15 > 0)
line("  short placeholder at >1.5x", o.sh15 > 0)
line("  placeholder >1.5x, n<=20", (o.ph15 > 0) & (o.n <= 20))
line("  placeholder share>=20%", (o.ph / o.n >= 0.2))
line("  placeholder share>=20%, >1.5x", (o.ph15 / o.n >= 0.2))
hi = (o.level > 0.3) & (o.n_bld <= 5)
print(
    "hi3_thin5 ads",
    hi.sum(),
    "with commercial in bld",
    (hi & (o.com > 0)).sum(),
    "placeholder",
    (hi & (o.ph > 0)).sum(),
    "either",
    (hi & ((o.com > 0) | (o.ph > 0))).sum(),
)
hi = (o.level > 0.4) & (o.n_bld <= 20)
print(
    "hi4_le20 ads",
    hi.sum(),
    "with commercial in bld",
    (hi & (o.com > 0)).sum(),
    "placeholder",
    (hi & (o.ph > 0)).sum(),
    "placeholder>1.5x",
    (hi & (o.ph15 > 0)).sum(),
    "either",
    (hi & ((o.com > 0) | (o.ph > 0))).sum(),
)
x = o[(o.level > 0.3) & (o.n_bld <= 5)]
print(
    "hi3_thin5 gap with flagged bld",
    x[(x.com > 0) | (x.ph15 > 0)].gap.mean(),
    len(x[(x.com > 0) | (x.ph15 > 0)]),
    "without",
    x[~((x.com > 0) | (x.ph15 > 0))].gap.mean(),
)
o.to_parquet("l2_ads_flags.parquet")
