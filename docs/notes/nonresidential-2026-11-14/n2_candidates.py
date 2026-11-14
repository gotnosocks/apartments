"""N2: candidate patterns for nonresidential ads, and the independent backing each row has.

I read the latest record of every listing in the sprint's copy of the feed records
(`recs.parquet`), whether or not the listing is one of L1's rows, since a row's backing can come
from another ad of its unit page. For each record I lowercase the description, fold its runs of
white space and its dashes as `cautions.plain` does, drop negated zoning ("not zoned for
commercial use") and the "live/work/play" slogan, and match the text patterns below. I also
keep the unit label (`display_unit`) the lister typed.

I narrowed the patterns once, after reading the text around a sample of each pattern's matches
with no price or gap in view: I dropped venting, net lease and per-square-foot asks with no
year, kept foot traffic and signage only in their commercial phrasings, and kept white box only
as a delivery condition.

The patterns, each a candidate signal:

- `label`: a unit label naming a commercial unit, such as `#STORE`, `RETAIL`, `COMMERCIAL`,
  `#OFFICE`, `#SALON` or `DENTAL-OFFICE`. This is a coded field, typed apart from the text.
- `zero_zero`: a row coded with 0 bedrooms, 0 full baths and 0 half baths.
- `sf_year`: an ask given per square foot per year, or net-lease terms (triple net, CAM
  charges, tax escalations).
- `zoned`: commercial or manufacturing zoning, or a zoning use group.
- `build_out`: build to suit, delivery in a white or vanilla box, key money, a grease trap, a
  liquor license, heavy foot traffic, signage rights or a stated frontage.
- `medical_prof`: a medical, dental or doctor's office, suite or practice, a professional office
  for rent, or professional use.
- `offer`: a retail, commercial, office, medical, showroom or restaurant space offered for rent
  or as available, a storefront for rent, or a space ideal for a business, a store or a clinic.
- `live_work`: live/work or work/live.
- `ground_retail`: ground-floor retail or commercial space, which S16's pattern left out.
- `words`: the remaining commercial words of S16's kind (a storefront, retail or commercial
  space, office space, a showroom), with none of the patterns above.

For each of L1's rows I then gather the backing that does not come from the row's own text:

- `bk_label`: the row's own label, or the label of another ad of its unit page, is commercial;
- `bk_other_ad`: another ad of the row's unit page (the ads file's `unit_id`) has a text
  matching one of the strong patterns (`sf_year` to `offer`), and its folded text differs from
  the row's own. An identical text is a copy of the row's ad, which I flag as `other_copy` and
  leave out of the backing;
- `bk_lot`: MapPLUTO gives the row's lot no apartments (`unitsres` of 0), through the registry
  L1 reads;
- `bk_zero_zero`: the row is coded with 0 bedrooms and 0 baths, a weak signal.

I count four kinds of signal: the row's own strong text (`k_text`), its own label (`k_label`),
another ad of its unit page with a strong text or a commercial label (`k_other`) and its lot
(`k_lot`). `rule_mark` marks a row with a signal of its own, text or label, and at least two
kinds in all. It is the draft of the rule, and the reads below test it.

A row's primary stratum is its first pattern in the order of `STRATA`, which runs from the
coded fields to the broadest words. I write `candidates.parquet` with the flags, the strata and
the backing of every candidate row, and `counts.json` with the counts. No price, gap or
residual enters this script.
"""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
DATASET = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/"
)
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
REGISTRY = (
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
)
PLUTO = "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"
S16 = "/data1/apartments/tmp/blind-spots-2026-11-14/"

# RE2 patterns, matched on the folded lowercase text.
TEXT = {
    "sf_year": (
        r"(?:per|/|a) ?(?:sq\.? ?ft\.?|sq\.? ?feet|square (?:foot|feet|ft)|sf|s\.f\.|rsf|psf)"
        r"\.? ?(?:per|/|a)? ?(?:yr|year|annum|annually)\b|\$ ?\d[\d,.]* ?psf\b"
        r"|\bnnn\b|\btriple[- ]net\b|\bcam charges?\b|\btax escalations?\b"
        r"|\breal estate tax(?:es)? (?:pass|escalation|over base)|\bmodified gross\b"
    ),
    "zoned": (
        r"\bzoned (?:for )?(?:commercial|retail|office|manufacturing|industrial|mixed[- ]use"
        r"|community facility|[cm]\d)|\buse groups?\b|\b(?:commercial|manufacturing) zoning\b"
        r"|\bzoning:? [cm]\d"
    ),
    "build_out": (
        r"\bbuild[- ]to[- ]suit\b|\b(?:white|vanilla)[- ]box (?:condition|delivery)\b"
        r"|\bdelivered (?:in )?(?:a )?(?:white|vanilla)[- ]box\b|\bkey money\b"
        r"|\bgrease trap\b|\bliquor licen[cs]e\b"
        r"|\b(?:heavy|high|great|excellent|strong|tremendous|constant|busy) (?:volume )?"
        r"foot traffic\b|\bsignage (?:opportunit|rights|available)"
        r"|\b\d+ ?(?:ft|feet|') (?:of )?frontage\b|\bfrontage of\b"
    ),
    "medical_prof": (
        r"\b(?:medical|dental|doctor'?s?|physician'?s?) (?:office|suite|practice)s?\b"
        r"|\bprofessional (?:office|suite)s? (?:space|for|available)|\bprofessional use\b"
        r"|\byour practice\b|\bmedical facility\b"
    ),
    "offer": (
        r"\b(?:retail|commercial|office|medical|showroom|restaurant|store ?front|warehouse"
        r"|industrial|community facility) (?:space|suite|unit|condo|loft)s? (?:is |now )?"
        r"(?:available|for (?:rent|lease)|for immediate)"
        r"|\bstore ?fronts? (?:is |now )?(?:available|for (?:rent|lease))"
        r"|\b(?:ideal|perfect|great|suitable|suited) for (?:a |an |your |any )?(?:retail"
        r"|medical|commercial|restaurant|showroom|doctor|dentist|salon|boutique|cafe"
        r"|bakery|store|shop|clinic|daycare)\b"
        r"|\b(?:ideal|perfect|great|suitable|suited) for (?:any|your|a|small) business\b"
        r"|\bbusiness use\b"
    ),
    "live_work": r"\blive ?(?:/|-|&|\+) ?work\b|\bwork ?(?:/|-|&|\+) ?live\b|\blivework\b",
    "ground_retail": (
        r"\bground[- ](?:floor|level) (?:retail|commercial|store|shop)s?\b"
    ),
    "words": (
        r"\bstore ?fronts?\b|\b(?:retail|commercial) (?:space|unit|use|tenant|property|condo"
        r"|store|lease)s?\b|\boffice space\b|\bshowroom\b|\bmedical office\b"
    ),
}
STRONG = ["sf_year", "zoned", "build_out", "medical_prof", "offer"]
STRATA = ["label", "zero_zero", *STRONG, "live_work", "ground_retail", "words"]
LABEL = (
    r"STORE|RETAIL|COMM|SALON|RESTAURANT|MEDICAL|DENTAL|PROFSPACE|PROFESSIONAL|^#PROF$"
    r"|SHOWROOM|WAREHOUSE|OFFICE"
)
NOT_LABEL = r"HOME ?OFFICE|W/OFFICE|WITH-\d*-?OFFICE|RESIDENTIAL|APARTMENT|COMMONS"


def fold(desc):
    low = pc.utf8_lower(pc.fill_null(desc, ""))
    low = pc.replace_substring_regex(low, "[‐-―−]", "-")
    low = pc.replace_substring_regex(low, r"\s+", " ")
    # Negated zoning and the "live/work/play" slogan say nothing about the unit.
    low = pc.replace_substring_regex(low, r"\bnot (?:be )?zoned [a-z -]{0,40}", " ")
    return pc.replace_substring_regex(
        low, r"\blive ?(?:/|-|,|&) ?work ?(?:/|-|,|&|and) ?(?:play|shop|dine)\b", " "
    )


f = pq.ParquetFile(RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g, columns=["listing_id", "last_collected_at", "display_unit", "description"]
    )
    low = fold(t["description"])
    cols = {
        "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
        "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
        "label": t["display_unit"].to_numpy(zero_copy_only=False),
        "desc_len": pc.utf8_length(low).to_numpy(zero_copy_only=False),
        "h": pd.util.hash_array(low.to_numpy(zero_copy_only=False).astype(object)),
    }
    for k, p in TEXT.items():
        cols["t_" + k] = pc.match_substring_regex(low, p).to_numpy(zero_copy_only=False)
    parts.append(pd.DataFrame(cols))
    del t, low
x = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
del parts
x["listing_id"] = x.listing_id.astype(str)
lab = x.label.fillna("").str.upper().str.strip()
x["label_comm"] = lab.str.contains(LABEL) & ~lab.str.contains(NOT_LABEL)
x["label_lw"] = lab.str.contains(r"LIVE.{0,3}WORK|WORK.{0,5}LIVE|LIVNWORK")
x["strong"] = x[["t_" + k for k in STRONG]].any(axis=1)
x["any_text"] = x[["t_" + k for k in TEXT]].any(axis=1)

# The ads file of L1's build gives every ad its unit page.
manifest = json.load(open(DATASET + "manifest.json"))
ads = pd.read_parquet(
    manifest["build"]["ads"]["path"], columns=["listing_id", "unit_id", "in_rows"]
)
ads["listing_id"] = ads.listing_id.astype(str)
x = x.merge(ads, on="listing_id", how="left")

d = pd.read_parquet(
    DATASET + "rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "bedrooms",
        "full_baths",
        "half_baths",
    ],
)
d["listing_id"] = d.listing_id.astype(str)
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"].astype(str)).all()
d["drawn16"] = d.listing_id.isin(
    set(pd.read_parquet(S16 + "draw.parquet").listing_id.astype(str))
)
d = d.rename(columns={"unit_id": "row_unit"}).merge(
    x.drop(columns=["t", "in_rows"]).rename(columns={"unit_id": "page"}),
    on="listing_id",
    how="left",
)
for c in [c for c in d.columns if c.startswith("t_")] + ["label_comm", "label_lw"]:
    d[c] = d[c].fillna(False).astype(bool)
d["strong"] = d[["t_" + k for k in STRONG]].any(axis=1)
d["desc_len"] = d.desc_len.fillna(0)
d["ukey"] = np.where(
    d.row_unit.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.row_unit.astype(str),
)

# Backing from other ads of the same unit page.
# Another ad with the same folded text as the row is a copy of it, so its text counts as backing
# only when it differs from the row's own.
pages = x[x.unit_id.notna()][["listing_id", "unit_id", "strong", "label_comm", "h"]]
pair = d[d.page.notna()][["listing_id", "page", "h"]].merge(
    pages.rename(columns={"listing_id": "other", "unit_id": "page", "h": "h_other"}),
    on="page",
)
pair = pair[pair.other != pair.listing_id]
pair["strong_new"] = pair.strong & (pair.h_other != pair.h)
by = pair.groupby("listing_id")
d["other_ads"] = d.listing_id.map(by.size()).fillna(0).astype(int)
d["bk_other_ad"] = d.listing_id.map(by.strong_new.any()).fillna(False).astype(bool)
d["other_copy"] = d.listing_id.map(by.strong.any()).fillna(False).astype(bool)
d["other_copy"] &= ~d.bk_other_ad
d["other_label"] = d.listing_id.map(by.label_comm.any()).fillna(False).astype(bool)
d["bk_label"] = d.label_comm | d.other_label

# Backing from the lot.
reg = pd.read_parquet(REGISTRY, columns=["building", "bbl"]).drop_duplicates("building")
pl = pd.read_parquet(
    PLUTO,
    columns=[
        "bbl",
        "unitsres",
        "unitstotal",
        "landuse",
        "bldgclass",
        "comarea",
        "retailarea",
    ],
)
reg["bbl"] = reg.bbl.astype(str)
pl["bbl"] = pl.bbl.astype("int64").astype(str)
lot = reg.merge(pl.drop_duplicates("bbl"), on="bbl", how="left").set_index("building")
for c in ["unitsres", "landuse", "bldgclass", "comarea", "retailarea"]:
    d["lot_" + c] = d.building.map(lot[c])
    if c != "bldgclass":
        d["lot_" + c] = pd.to_numeric(d["lot_" + c], errors="coerce")
d["bk_lot"] = d.lot_unitsres == 0
d["zero_zero"] = (d.bedrooms == 0) & (d.full_baths == 0) & (d.half_baths.fillna(0) == 0)
d["bk_zero_zero"] = d.zero_zero

flags = {
    "label": d.label_comm,
    "zero_zero": d.zero_zero,
    **{k: d["t_" + k] for k in TEXT},
}
flags["words"] = flags["words"] & ~d[["t_" + k for k in TEXT if k != "words"]].any(
    axis=1
)
cand = pd.concat(flags, axis=1).any(axis=1)
d["stratum"] = np.select([flags[k] for k in STRATA], STRATA, "")
# The kinds of signal: the row's own strong text, its own label, another ad of its unit page
# (its text or its label) and its lot. A row is marked when it has a signal of its own and at
# least two kinds in all.
d["k_text"] = d.strong
d["k_label"] = d.label_comm
d["k_other"] = d.bk_other_ad | d.other_label
d["k_lot"] = d.bk_lot
d["kinds"] = d[["k_text", "k_label", "k_other", "k_lot"]].astype(int).sum(axis=1)
d["own_signal"] = d.k_text | d.k_label
d["backing"] = d.kinds - d.own_signal.astype(int)
d["rule_mark"] = d.own_signal & (d.kinds >= 2)


def scope(m):
    m = m.fillna(False).astype(bool)
    return {
        "rows": int(m.sum()),
        "training": int((m & ~d.held).sum()),
        "heldout": int((m & d.held).sum()),
        "heldout_outside_s16": int((m & d.held & ~d.drawn16).sum()),
        "units": int(d.ukey[m].nunique()),
        "buildings": int(d.building[m].nunique()),
    }


res = {"patterns": {}, "strata": {}, "backing": {}}
for k, m in flags.items():
    res["patterns"][k] = scope(m)
for k in STRATA:
    m = d.stratum == k
    res["strata"][k] = scope(m) | {
        "with_text_over_80": int((m & (d.desc_len > 80)).sum()),
        "backed": int((m & (d.backing >= 1)).sum()),
        "bk_label": int((m & d.bk_label).sum()),
        "bk_other_ad": int((m & d.bk_other_ad).sum()),
        "other_copy": int((m & d.other_copy).sum()),
        "bk_lot": int((m & d.bk_lot).sum()),
        "bk_zero_zero": int((m & d.bk_zero_zero).sum()),
    }
res["candidates"] = scope(cand)
res["strong_text"] = scope(d.strong)
res["own_signal"] = scope(d.own_signal)
res["rule_mark"] = scope(d.rule_mark)
for k in ["bk_label", "bk_other_ad", "bk_lot", "bk_zero_zero"]:
    res["backing"][k] = scope(cand & d[k])
res["backing"]["any_strong_kind"] = scope(cand & (d.backing >= 1))
res["rule_mark_by_kind"] = {
    k: int((d.rule_mark & d[k]).sum())
    for k in ["k_text", "k_label", "k_other", "k_lot"]
}
res["labels_seen"] = x[x.label_comm].label.str.upper().value_counts().head(60).to_dict()
keep = [
    "listing_id",
    "building",
    "row_unit",
    "page",
    "ukey",
    "label",
    "bedrooms",
    "full_baths",
    "half_baths",
    "held",
    "drawn16",
    "desc_len",
    "stratum",
    *[c for c in d.columns if c.startswith(("t_", "bk_", "lot_", "k_"))],
    "label_comm",
    "label_lw",
    "other_label",
    "other_copy",
    "other_ads",
    "strong",
    "zero_zero",
    "kinds",
    "backing",
    "own_signal",
    "rule_mark",
]
d.loc[cand, keep].to_parquet(OUT + "candidates.parquet", index=False)
pair[pair.listing_id.isin(set(d.listing_id[cand]))].to_parquet(
    OUT + "candidate_pages.parquet", index=False
)
json.dump(res, open(OUT + "counts.json", "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "labels_seen"}, indent=1))
