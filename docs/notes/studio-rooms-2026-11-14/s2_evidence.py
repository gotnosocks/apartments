"""S17, part 2: a dossier of evidence for each of the 30 drawn rows, frozen before any read.

For each row of `sample.parquet` I gather what the correction rules accept as backing, from
the ads file and records of the build behind L1's dataset and from the listing codes:

1. the row's own coded fields: bedrooms, full baths, room count, stated size, unit label,
   date, lister and floor plan count;
2. the unit's other ads (the same `unit_id`, which here is one-to-one with the StreetEasy unit
   page), each with its date, coded bedrooms, baths, rooms and size, whether L1's rows keep it
   and why not, and the texts of up to 5 of them nearest in time;
3. units of the same line in the building: I parse the label into a floor and a line ("5C"
   is floor 5 of line C, "1205" floor 12 of line 05, a bare "3" a floor-through), and list
   the building's ads on other floors of that line, by label;
4. the building's ads with the same coded room count, as a count by coded bedrooms, for
   context only;
5. floor plan images already on disk, matched by listing id or image key. The coordinator
   barred plan fetches for this screen, so I fetch nothing.

Dollar figures in every text become `[amount]`, and no ask or L1 prediction goes into a
dossier, since price alone backs nothing. I write `dossiers/row_NN.md`, the frozen tables
`row_ads.parquet`, `unit_ads.parquet` and `line_ads.parquet`, the matched plans under
`plans/`, and `evidence.json` with SHA-256s of all of them."""

import glob
import hashlib
import json
import os
import re
import shutil

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/studio-rooms-2026-11-14/"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
PLAN_DIRS = [
    "/data1/apartments/archive/floor-plans/",
    "/data1/apartments/tmp/suspect/floorplans/",
    "/data1/apartments/tmp/outlier-sprint/",
]
MAXLEN, OTHER_LEN, N_TEXTS = 3500, 1200, 5
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?|\bUSD\s?\d[\d,]*"
    r"|\b\d{1,2},?\d{3}(?:\.\d{2})?(?=\s*(?:/|per|a)\s*(?:mo\b|month))",
)

s = pd.read_parquet(OUT + "sample.parquet")
ads = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "unit_id",
        "building",
        "page",
        "on_day",
        "bedrooms",
        "full_baths",
        "half_baths",
        "square_feet",
        "floor_plans",
        "exclusion_reasons",
        "in_rows",
    ],
)
ads["label"] = ads.page.str.rsplit("/", n=1).str[-1].str.lower()
row = ads[ads.listing_id.isin(s.listing_id)]
units = set(row.unit_id.dropna())
blds = set(row.building)
bld_ads = ads[ads.building.isin(blds)].copy()
del ads


def line_of(label):
    """The floor and line of a unit label, or (None, None) when I can't parse it."""
    if not isinstance(label, str):
        return None, None
    lab = re.sub(r"^(?:apt|unit|#)[-_ ]*", "", label)
    if m := re.fullmatch(r"(?:ph)?(\d{1,3})-?([a-z]{1,2})", lab):
        return m[1], "letter:" + m[2]
    if m := re.fullmatch(r"(\d{1,2})(\d{2})", lab):
        return m[1], "number:" + m[2]
    if m := re.fullmatch(r"(\d{1,2})(?:fl|floor)?", lab):
        return m[1], "floor-through"
    if m := re.fullmatch(r"([a-z])-?(\d{1,2})", lab):
        return m[2], "letter:" + m[1]
    return None, None


fl = bld_ads.label.map(line_of)
bld_ads["floor"], bld_ads["line"] = fl.str[0], fl.str[1]

# Coded rooms, raw sizes, listers and texts for every ad of these buildings.
ids = set(bld_ads.listing_id)
codes = pd.read_parquet(CODES, columns=["listing_id", "rooms", "floorplans"])
codes = codes[codes.listing_id.isin(ids)]
f = pq.ParquetFile(RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g,
        columns=[
            "listing_id",
            "last_collected_at",
            "lister",
            "room_count",
            "living_area",
            "n_plans",
            "description",
        ],
    )
    t = t.filter(pc.is_in(t["listing_id"], value_set=pc.cast(list(ids), "string")))
    parts.append(t.to_pandas())
recs = (
    pd.concat(parts)
    .sort_values("last_collected_at")
    .drop_duplicates("listing_id", keep="last")
    .drop(columns="last_collected_at")
)
bld_ads = bld_ads.merge(codes, on="listing_id", how="left").merge(
    recs, on="listing_id", how="left"
)
bld_ads["size"] = bld_ads.square_feet.fillna(bld_ads.living_area)
bld_ads["desc"] = (
    bld_ads.description.fillna("").map(lambda x: MONEY.sub("[amount]", x)).str.strip()
)

# Floor plans already on disk, by listing id directory or by image key.
stored = [
    p
    for d in PLAN_DIRS
    for p in glob.glob(d + "**/*", recursive=True)
    if p.endswith((".webp", ".png", ".jpg")) and "/photos/" not in p
]


def plans_on_disk(lid, keys):
    keys = [k for k in (keys if keys is not None else []) if k]
    hits = []
    for p in stored:
        name = os.path.basename(p)
        stem = name.split("-p_e")[0].split(".")[0]
        if f"/{lid}/" in p or name.endswith(f"-{lid}.webp"):
            hits.append(p)
        elif len(stem) >= 6 and any(k.startswith(stem) for k in keys):
            hits.append(p)
    return sorted(set(hits))


def num(v, fmt="{:g}"):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "" if v is None else str(v)
    return "" if np.isnan(v) else fmt.format(v)


def reasons(v):
    return ", ".join(v) if v is not None and len(v) else ""


os.makedirs(OUT + "dossiers", exist_ok=True)
os.makedirs(OUT + "plans", exist_ok=True)
unit_rows, line_rows, row_rows = [], [], []
for _, r in s.iterrows():
    me = bld_ads[bld_ads.listing_id == r.listing_id].iloc[0]
    plans = plans_on_disk(me.listing_id, me.floor_plans)
    L = [
        f"# Row {r.row_id:02d}",
        "",
        "## The row's own ad",
        "",
        f"- Listing {me.listing_id}, building `{me.building}`, unit label `{me.label}`"
        f" (parsed floor {me.floor}, line {me.line})",
        f"- Opened {me.on_day}; lister {me.lister}",
        f"- Coded: bedrooms {num(me.bedrooms)}, full baths {num(me.full_baths)}, half baths"
        f" {num(me.half_baths)}, rooms {num(me.rooms)} (record room count"
        f" {num(me.room_count)}), stated size {num(me['size'])} sq ft",
        f"- Floor plans attached to the ad: {num(me.floorplans) or 0}; stored on disk:"
        f" {len(plans)}",
        "",
        "### Its description",
        "",
        me.desc[:MAXLEN] or "(none)",
        "",
    ]
    row_rows.append(me.drop(labels=["description"]))
    u = bld_ads[(bld_ads.unit_id == me.unit_id) & (bld_ads.listing_id != me.listing_id)]
    u = u.sort_values("on_day")
    L += [
        f"## The unit's other ads ({len(u)})",
        "",
        "| listing | opened | beds | full baths | rooms | size | lister | in L1's rows |"
        " plans attached |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, o in u.iterrows():
        kept = "yes" if o.in_rows else f"no ({reasons(o.exclusion_reasons)})"
        L.append(
            f"| {o.listing_id} | {o.on_day} | {num(o.bedrooms)} | {num(o.full_baths)} |"
            f" {num(o.rooms)} | {num(o['size'])} | {o.lister} | {kept} |"
            f" {num(o.floorplans) or 0} |"
        )
        plans += plans_on_disk(o.listing_id, o.floor_plans)
        unit_rows.append(
            pd.concat([o.drop(labels=["description"]), pd.Series({"row_id": r.row_id})])
        )
    L.append("")
    if len(u):
        near = u.assign(
            dd=(pd.to_datetime(u.on_day) - pd.to_datetime(me.on_day)).abs()
        ).sort_values("dd")
        for _, o in near.head(N_TEXTS).iterrows():
            L += [
                f"### Text of {o.listing_id} ({o.on_day}, coded {num(o.bedrooms)} beds,"
                f" {num(o.rooms)} rooms)",
                "",
                o.desc[:OTHER_LEN] or "(none)",
                "",
            ]
    if me.line is not None:
        ln = bld_ads[
            (bld_ads.building == me.building)
            & (bld_ads.line == me.line)
            & (bld_ads.label != me.label)
            & (bld_ads.unit_id != me.unit_id)
        ]
    else:
        ln = bld_ads.iloc[:0]
    L += [
        f"## Units of the same line ({me.line}) in the building: {ln.label.nunique()} units,"
        f" {len(ln)} ads",
        "",
    ]
    if len(ln):
        L += [
            "| unit | floor | ads | coded beds | full baths | rooms | sizes | years |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for lab, g in ln.groupby("label"):

            def vals(c, g=g):
                v = sorted({num(x) for x in g[c] if num(x)})
                return ", ".join(v) if len(v) <= 6 else ", ".join(v[:6]) + ", ..."

            L.append(
                f"| {lab} | {g.floor.iloc[0]} | {len(g)} | {vals('bedrooms')} |"
                f" {vals('full_baths')} | {vals('rooms')} | {vals('size')} |"
                f" {str(g.on_day.min())[:4]} to {str(g.on_day.max())[:4]} |"
            )
            line_rows.append(g.drop(columns=["description"]).assign(row_id=r.row_id))
        L.append("")
    b = bld_ads[bld_ads.building == me.building]
    same = b[(b.rooms == me.rooms) & (b.unit_id != me.unit_id)]
    by = same.bedrooms.value_counts().sort_index()
    L += [
        f"## The building's other ads with {num(me.rooms)} coded rooms, for context: "
        + (
            ", ".join(f"{num(k)} beds on {v}" for k, v in by.items())
            if len(by)
            else "none"
        )
        + f" (the building has {b.unit_id.nunique()} unit pages and {len(b)} ads)",
        "",
    ]
    plans = sorted(set(plans))
    L += ["## Floor plans stored on disk", ""]
    if plans:
        for p in plans:
            dst = OUT + f"plans/row_{r.row_id:02d}_{os.path.basename(p)}"
            shutil.copy(p, dst)
            L.append(f"- {dst}")
    else:
        L.append("- none")
    open(OUT + f"dossiers/row_{r.row_id:02d}.md", "w").write("\n".join(L) + "\n")
    print(r.row_id, me.label, me.line, len(u), ln.label.nunique(), len(plans))

for name, rows in [
    ("row_ads", row_rows),
    ("unit_ads", unit_rows),
    ("line_ads", line_rows),
]:
    t = pd.DataFrame(rows) if name != "line_ads" else pd.concat(rows)
    for c in ["floor_plans", "exclusion_reasons"]:
        t[c] = t[c].map(lambda v: list(v) if v is not None else [])
    t.drop(columns=[c for c in ["desc"] if c in t], errors="ignore").to_parquet(
        OUT + f"{name}.parquet"
    )


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


files = sorted(
    glob.glob(OUT + "dossiers/*.md")
    + glob.glob(OUT + "plans/*")
    + [OUT + f"{n}.parquet" for n in ["row_ads", "unit_ads", "line_ads"]]
)
json.dump(
    {os.path.relpath(p, OUT): sha(p) for p in files},
    open(OUT + "evidence.json", "w"),
    indent=1,
)
