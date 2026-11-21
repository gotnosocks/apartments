"""Step 4: kinds of the pages behind the unit mark, from fields only.

Every pair of the mark lies on one page (`lr1_pairs.py`), so no label_units layer and no
label rule is involved. For each 0-bed training row of `U_any` I read, from the live build's
ads file and records:

- the page's label and its form (a floor number alone, a floor and letter, letters alone,
  other);
- for a label of a floor number alone ("2"), whether another page of the building carries that
  floor with a letter ("2A", "2R", "F2"), so the bare label names a floor of several apartments;
- the page's typed ads (bedrooms not set by an active ledger entry) in order of first day, and
  how often the count changes between under 2 and 2 or more;
- whether the 0-bed ad and an ad coded 2 or more on the page were on the market together for
  14 days or more (from `on_day` or `first_day` to `off_day`, open ads to the build's last day);
- the lister (`legacy.sourceGroupLabel` of the latest record) of the 0-bed ad and of the page's
  ads coded 2 or more;
- the stated size and full baths of the 0-bed ad and of the page's ads coded 2 or more: both
  sizes stated and within 10% of each other, both stated and apart by 25% or more, or not
  both stated;
- the size the 0-bed ad's own text states (`bed_text` of `rentfrontier.b0bedtext`).

No ask enters any column or selection.
"""

import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "zero-bed-apartments-2026-11-21"))
from z3_size import records  # noqa: E402

ZB = Path("/data1/apartments/tmp/zero-bed")
S = Path("/data1/apartments/tmp/label-reuse")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
OVERLAP = 14

P = pd.read_parquet(S / "mark_pairs.parquet")
units = sorted(P.unit_id.unique())
z = (
    P.drop_duplicates("z_id")[["z_id", "unit_id", "U_strict", "z_label", "building"]]
    .rename(columns={"z_id": "listing_id", "z_label": "label"})
    .reset_index(drop=True)
)
M = pd.read_parquet(ZB / "marked.parquet", columns=["listing_id", "bed_text", "lister"])
z = z.merge(M, on="listing_id", how="left")

c = duckdb.connect()
c.execute("set memory_limit='2GB'; set threads=2")
c.register("units", pd.DataFrame({"unit_id": units}))
A = c.execute(f"""select listing_id, unit_id, bedrooms, first_day,
    coalesce(on_day, first_day) on_d, off_day, square_feet, full_baths
  from '{ADS}' where unit_id in (select unit_id from units)""").df()
L = c.execute(f"""select distinct building, regexp_extract(page, '[^/]+$') AS "label"
  from '{ADS}' where building in (select distinct building from '{ADS}'
    where unit_id in (select unit_id from units))""").df()
last = A.off_day.max()
A["off_d"] = A.off_day.fillna(last)
o_ids = set(P.o_id)
A["is_o"] = A.listing_id.isin(o_ids)
# The page's typed ads: the 2+ ads of the pairs (bedset already applied in lr1) and every
# typed ad under 2, as z2 counts u1 and u0 (z2 drops bedset ads on both sides; ads under 2
# set by the ledger are few and only move the switch count).
typed = A[A.bedrooms.notna() & ((A.bedrooms < 2) | A.is_o)].sort_values(
    ["unit_id", "first_day", "listing_id"]
)
hi = (typed.bedrooms >= 2).astype(int)
typed["switch"] = (hi != hi.groupby(typed.unit_id).shift()) & typed.unit_id.duplicated()
page = typed.groupby("unit_id").agg(
    typed_ads=("listing_id", "size"),
    switches=("switch", "sum"),
    counts=("bedrooms", "nunique"),
)

Ai = A.set_index("listing_id")
zo = P[["z_id", "o_id", "unit_id"]].copy()
zo["z_on"] = Ai.on_d.reindex(zo.z_id).to_numpy()
zo["z_off"] = Ai.off_d.reindex(zo.z_id).to_numpy()
zo["o_on"] = Ai.on_d.reindex(zo.o_id).to_numpy()
zo["o_off"] = Ai.off_d.reindex(zo.o_id).to_numpy()
ov = (
    pd.to_datetime(np.minimum(zo.z_off, zo.o_off))
    - pd.to_datetime(np.maximum(zo.z_on, zo.o_on))
).dt.days
zo["overlap"] = ov
zo["gap"] = (
    (pd.to_datetime(Ai.first_day.reindex(zo.o_id).to_numpy()))
    - pd.to_datetime(Ai.first_day.reindex(zo.z_id).to_numpy())
).days

cache = S / "o_listers.parquet"
if not cache.exists():
    records({str(i) for i in o_ids})[["listing_id", "lister"]].to_parquet(cache)
R = pd.read_parquet(cache)
zo = zo.merge(
    R.rename(columns={"listing_id": "o_id", "lister": "o_lister"}),
    on="o_id",
    how="left",
)
zo = zo.merge(
    z[["listing_id", "lister"]].rename(columns={"listing_id": "z_id"}), on="z_id"
)
zo["same_lister"] = (zo.lister == zo.o_lister) & zo.lister.notna()
for side, ids in (("z", zo.z_id), ("o", zo.o_id)):
    zo[f"{side}_sf"] = Ai.square_feet.reindex(ids).to_numpy()
    zo[f"{side}_baths"] = Ai.full_baths.reindex(ids).to_numpy()
ratio = zo.o_sf / zo.z_sf
zo["size"] = np.select(
    [ratio.between(1 / 1.1, 1.1), (ratio >= 1.25) | (ratio <= 1 / 1.25)],
    ["same size", "sizes apart"],
    "not both stated",
)
zo["more_baths"] = zo.o_baths > zo.z_baths
per = zo.groupby("z_id").agg(
    max_overlap=("overlap", "max"),
    any_same_lister=("same_lister", "any"),
    min_gap=("gap", lambda s: s.abs().min()),
    any_same_size=("size", lambda s: (s == "same size").any()),
    any_apart=("size", lambda s: (s == "sizes apart").any()),
    any_more_baths=("more_baths", "any"),
)
z = z.merge(per, left_on="listing_id", right_index=True).merge(
    page, left_on="unit_id", right_index=True
)


def form(label: str) -> str:
    s = re.sub(r"[^a-z0-9]", "", (label or "").lower())
    s = re.sub(r"^(apt|unit)", "", s)
    if re.fullmatch(r"0*\d{1,2}(st|nd|rd|th)?(fl|flr|floor)?", s):
        return "floor number alone"
    if re.fullmatch(r"0*\d{1,2}[a-z]{1,2}|[a-z]{1,2}0*\d{1,2}", s):
        return "floor and letter"
    if re.fullmatch(r"\d{3,5}[a-z]?", s):
        return "three or more digits"
    if re.fullmatch(r"[a-z]+", s):
        return "letters alone"
    return "other"


def norm(label: str) -> str:
    s = re.sub(r"[^a-z0-9]", "", (label or "").lower())
    return re.sub(r"(st|nd|rd|th)?(fl|flr|floor)$", "", re.sub(r"^(apt|unit)", "", s))


z["form"] = z.label.map(form)
L["n"] = L.label.map(norm)
lettered = set()
for b, n in zip(L.building, L.n):
    if m := re.fullmatch(r"0*(\d{1,2})[a-z]{1,2}|[a-z]{1,2}0*(\d{1,2})", n):
        lettered.add((b, m[1] or m[2]))
z["floor_label_shared"] = [
    f == "floor number alone" and (b, norm(x).lstrip("0") or "0") in lettered
    for f, b, x in zip(z.form, z.building, z.label)
]
z["size"] = np.select(
    [z.any_same_size, z.any_apart], ["same size", "sizes apart"], "not both stated"
)
z["text"] = np.select(
    [z.bed_text.isna(), z.bed_text == 0, z.bed_text == 1],
    ["states none", "studio", "1 bed"],
    "2 or more",
)


def kind(r) -> str:
    if r.max_overlap >= OVERLAP:
        return "on the market together"
    if r.floor_label_shared:
        return "floor label, several per floor"
    if r.switches <= 1:
        return "one change of layout"
    return "layout changes back and forth"


z["kind"] = z.apply(kind, axis=1)
z.to_parquet(S / "kinds.parquet")
zo.to_parquet(S / "pair_times.parquet")


def show(g: pd.DataFrame, name: str) -> None:
    print(f"\n== {name}: rows {len(g)}, units {g.unit_id.nunique()}")
    u = g.drop_duplicates("unit_id")
    for col in ("kind", "form", "text", "size"):
        t = pd.DataFrame(
            {"rows": g[col].value_counts(), "units": g.groupby(col).unit_id.nunique()}
        )
        print(t.to_string())
    print("same lister on a 2+ ad:", g.any_same_lister.value_counts().to_dict())
    print(pd.crosstab(g.kind, g.any_same_lister, margins=True).to_string())
    print(pd.crosstab(g.kind, g.text, margins=True).to_string())
    print(pd.crosstab(g.kind, g["size"], margins=True).to_string())
    print("a 2+ ad states more full baths:", int(g.any_more_baths.sum()))
    print(
        "floor number alone and several units per floor:",
        int(g.floor_label_shared.sum()),
    )
    print(
        "switches per unit:",
        u.switches.clip(upper=4).value_counts().sort_index().to_dict(),
    )
    print(
        "typed ads per unit:",
        u.typed_ads.clip(upper=10).value_counts().sort_index().to_dict(),
    )
    print(
        "nearest 2+ ad, days:",
        g.min_gap.describe(percentiles=[0.25, 0.5, 0.75]).round(0).to_dict(),
    )
    print("overlap >= 1 day:", int((g.max_overlap >= 1).sum()))
    print("top listers:", g.lister.value_counts().head(8).to_dict())
    print(
        "top buildings by units:",
        g.groupby("building").unit_id.nunique().nlargest(8).to_dict(),
    )


show(z, "U_any")
show(z[z.U_strict], "U_strict")
