"""S14, part 1: match each listing's last description and unit label for a penthouse, a garden
apartment and a floor of a townhouse, and draw the ads for the readers.

The script reads the description of each listing's last record, as `s7_text.py` does for
duplexes. The records carry no title, so the description is the only text. The unit label is
the end of the ad's URL in L1's pipeline rows, read with `unit_features.unit_label`, as L1's
`unit:penthouse` column reads it.

For each kind the script counts the mentions a positive pattern finds and the mentions an
exclusion pattern finds among them, and marks the listing when the positives outnumber the
exclusions. An ad with a "penthouse lounge" and a "penthouse apartment" still counts. pyarrow's
RE2 has no lookahead, so the exclusions run as a second count.

1. Penthouse: the word penthouse, less the mentions that are amenities ("penthouse lounge",
   "penthouse-level amenities", "penthouse roof deck", "located at the penthouse level"), plurals and marketing ("penthouses",
   "penthouse residences", "penthouse-style"). Or a label starting PH or containing PENT.
2. Garden apartment: "garden level", "garden floor", "garden apartment", "garden duplex" and
   the like, or a private garden, backyard or rear yard, less complexes ("garden apartment
   complex"), places ("Carroll Garden apartment") and gardens shared with residents. Or a
   label with GARDEN, GDN or GRDN.
3. Townhouse floor: "parlor floor", "floor-through", "in a ... brownstone", "floor of a
   townhouse", "brownstone apartment" and the like, less a block or neighbourhood
   ("brownstone-lined", "brownstone Brooklyn", "the charm of a brownstone"). Or a label with
   PARLOR.

The readers get 100 matched ads of each kind, 50 unmatched ads of each kind with weaker words
and 50 ads with none of the three marks and none of the weaker words, all drawn at random from
listings of L1's dataset with a description over 80 characters. The readers see the
description and the unit label, never the sample or the marks."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402
from rentfrontier.unit_features import unit_label  # noqa: E402

OUT = c.OUT + "unusual-units/"
os.makedirs(OUT, exist_ok=True)

PEN = r"(?i)\bpenthouse"
PEN_EXCL = (
    r"(?i)\bpenthouses\b"
    r"|\b(?:at|located on) the penthouse[- ]level"
    r"|\bpenthouse[- ](?:level[- ]|floor[- ]|rooftop[- ]|roof[- ]?top[- ]|sky[- ]|amenity[- ])?"
    r"(?:lounge|fitness|gym|health|club|amenit|viewing|sun ?deck|roof|pool|spa|lobby|party"
    r"|game|media|screening|co-?work|work ?space|library|bar\b|garden|social|entertain"
    r"|common|shared|resident|laundry|storage|style|like|quality|feel|views?\b|calib"
    r"|finish|apartments\b|residences\b|homes\b|units\b|collection|suites\b|suite of)"
)
PEN_LABEL = r"^PH|PENT"
PEN_WEAK = r"(?i:\btop[- ]floor\b|\btop[- ]most\b)|\bPH\b"

GAR = (
    r"(?i)\bgarden[- ](?:level|floor|apartment|apt|unit|duplex|triplex|studio|suite"
    r"|residence|home|flat|rental)\b"
    r"|\b(?:private|own|exclusive) (?:(?:landscaped|planted|lush|outdoor|rear|back|sunny"
    r"|large|huge|big|beautiful|lovely|charming|spacious|shaded|enclosed|fenced|walled"
    r"|tranquil|serene|secluded|oversized|generous|gorgeous|stunning) )?(?:garden|back ?yard"
    r"|rear yard)\b"
)
GAR_EXCL = (
    r"(?i)\bgarden[- ](?:apartment|unit)s? (?:complex|community|development|building|style)"
    r"|\b(?:carroll|kew|sunnyside|botanic|botanical|square|lefferts|hilary|windsor|city)"
    r" garden[- ](?:level|floor|apartment|unit)"
    r"|\b(?:garden|back ?yard|rear yard),? (?:shared|for|available to|open to|accessible to)"
    r" (?:by |with )?(?:all |the |our |other )?(?:residents|tenants|building|everyone"
    r"|neighbors)"
)
GAR_LABEL = r"GARDEN|GARDN|GDN|GRDN|^GRD"
GAR_WEAK = r"(?i)\bback ?yard|\brear yard|\bground[- ](?:floor|level)\b|\blower[- ]level\b|\bgarden\b"

TH = r"(?:town ?house|brownstone|brown stone|row ?house)"
TOWN = (
    r"(?i)\bparlou?r[- ](?:floor|level)\b|\bfloor[- ]?(?:through|thru)\b"
    r"|\b(?:in|of|within|inside) (?:a|an|this|the|our|one) (?:[\w'-]+ ){0,4}?"
    + TH
    + r"\b"
    r"|\b"
    + TH
    + r"[- ](?:apartment|apt|unit|floor|duplex|triplex|studio|flat|rental)\b"
)
TOWN_EXCL = (
    r"(?i)\b(?:in|of|within|inside) (?:a|an|this|the|our|one) (?:[\w'-]+ ){0,4}?"
    + TH
    + r"[- ](?:lined|block|street|neighbou?rhood|district|area|style|like|brooklyn|community"
    r"|enclave|charm|feel|vibe|rows?\b|belt|facade|exterior)"
    r"|\b(?:charm|feel|style|look|elegance) of (?:a|an|the) (?:[\w'-]+ ){0,4}?"
    + TH
    + r"\b"
)
TOWN_LABEL = r"PARLOU?R"
TOWN_WEAK = r"(?i)\bbrownstone|\btown ?house|\brow ?house|\bwalk[- ]?up\b"

READER_PROMPT = """You are labelling NYC rental ads for a research check. Read the file BATCH
(JSON lines, each with `read_id`, `unit_label` and `description`). `unit_label` is the
unit's name in the ad's address (e.g. 4B, PHA, GARDEN, PARLOR), upper-cased with punctuation
removed, or empty. For every line, decide three things from the label and the text alone, then
write one JSON line per ad to OUT with keys `read_id`, `penthouse`, `garden_apartment`,
`townhouse_floor`, `evidence`.

1. `penthouse` (true or false): the advertised apartment is itself a penthouse, i.e. the ad or
   the building calls this unit a penthouse (the word penthouse for this apartment, or a unit
   label starting PH or reading PENTHOUSE), unless the text contradicts it. False when
   "penthouse" names a building, a building's amenity floor or lounge ("penthouse-level
   amenities", "penthouse fitness center"), a roof deck shared by all residents, other units
   the building offers, or a style ("penthouse-like finishes"). A top-floor apartment that
   nobody calls a penthouse is false.
2. `garden_apartment` (true or false): the advertised apartment is on the ground, garden or
   lower level and has its own private garden, backyard or yard, or the ad or label calls it
   a garden apartment, garden level, garden floor or garden unit. False when the garden or
   yard is shared by the building's residents or is a roof garden, when the apartment is on an
   upper floor, when "garden" names a place (Carroll Gardens, Madison Square Garden, Botanic
   Garden), and for a unit in a "garden apartment complex" or "garden-style" development
   unless the unit itself is on the ground floor with its own garden.
3. `townhouse_floor` (true or false): the advertised apartment is a floor, part of a floor or
   a few floors of a townhouse, brownstone or row house (e.g. the parlor floor, a
   floor-through, the top floor of a brownstone, an apartment in a townhouse), not the whole
   house. A floor-through or parlor-floor apartment in a small walk-up of two to five floors
   counts as true. False for a whole house for rent, for a "townhouse" unit of a new
   development or condo complex that is a separate house, for an apartment in an elevator,
   loft or large apartment building, and when "brownstone" or "townhouse" describes only the
   block or neighbourhood ("brownstone-lined street").

If the text lists several units, judge the one being advertised (the first one if unclear).
The three are independent: an apartment can be a garden apartment and a townhouse floor at
once, or none of them.

`evidence`: the few words of the ad or label behind any true answer, at most 20 words, or ""
when all three are false.

Use the Read tool on BATCH, and write OUT with the Write tool as plain JSON lines, exactly one
per input line, in input order, with JSON booleans. Then reply only with the count of lines
written and the count of true values for each key. Do not reply with the labels themselves.
"""

KINDS = {
    "pen": (PEN, PEN_EXCL, PEN_LABEL, PEN_WEAK),
    "gar": (GAR, GAR_EXCL, GAR_LABEL, GAR_WEAK),
    "town": (TOWN, TOWN_EXCL, TOWN_LABEL, TOWN_WEAK),
}

f = pq.ParquetFile(c.RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "last_collected_at", "description"])
    desc = pc.fill_null(t["description"], "")
    cols = {
        "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
        "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
        "desc_len": pc.utf8_length(desc).to_numpy(zero_copy_only=False),
    }
    for k, (pos, excl, _, weak) in KINDS.items():
        cols[k + "_n"] = pc.count_substring_regex(desc, pos).to_numpy(
            zero_copy_only=False
        )
        cols[k + "_x"] = pc.count_substring_regex(desc, excl).to_numpy(
            zero_copy_only=False
        )
        cols[k + "_weak"] = pc.match_substring_regex(desc, weak).to_numpy(
            zero_copy_only=False
        )
    parts.append(pd.DataFrame(cols))
x = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
x["listing_id"] = x.listing_id.astype(str)
pipe = pd.read_parquet(c.PIPE, columns=["listing_id", "page"]).drop_duplicates(
    "listing_id"
)
pipe["listing_id"] = pipe.listing_id.astype(str)
pipe["label"] = unit_label(pipe.page)
x = x.merge(pipe[["listing_id", "label"]], on="listing_id", how="left")
x["label"] = x.label.fillna("")
for k, (_, _, lab, _) in KINDS.items():
    x[k + "_text"] = x[k + "_n"] > x[k + "_x"]
    x[k + "_label"] = x.label.str.contains(lab, regex=True)
    x[k] = x[k + "_text"] | x[k + "_label"]
# Ads with only excluded penthouse mentions join the weaker words for recall.
x["pen_weak"] = x.pen_weak | (x.pen_n > 0)
x.drop(columns="t").to_parquet(OUT + "u1_text.parquet")

ids = set(pd.read_parquet(c.DATA, columns=["listing_id"]).listing_id.astype(str))
x = x[x.listing_id.isin(ids) & (x.desc_len > 80)].reset_index(drop=True)
summary = {"listings": len(x)}
for k in KINDS:
    summary[k] = {
        "text": float(x[k + "_text"].mean()),
        "label": float(x[k + "_label"].mean()),
        "either": float(x[k].mean()),
        "weak_unmatched": float((x[k + "_weak"] & ~x[k]).mean()),
    }
print(json.dumps(summary, indent=1), flush=True)

rng = np.random.default_rng(20261114)


def draw(m, n, label):
    s = x[m]
    s = s.iloc[rng.choice(len(s), min(n, len(s)), replace=False)]
    return pd.DataFrame({"listing_id": s.listing_id, "sample": label})


none = ~x.pen & ~x.gar & ~x.town
noweak = ~x.pen_weak & ~x.gar_weak & ~x.town_weak
picks = pd.concat(
    [draw(x[k], 100, k + "_matched") for k in KINDS]
    + [draw(~x[k] & x[k + "_weak"], 50, k + "_weak") for k in KINDS]
    + [draw(none & noweak, 50, "unmatched_random")]
)
# an ad drawn for two samples is read once and counts in both
picks = picks.groupby("listing_id", as_index=False, sort=False)["sample"].agg("|".join)
want = set(picks.listing_id)
text = {}
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g, columns=["listing_id", "last_collected_at", "description"]
    ).to_pandas()
    t = t[t.listing_id.astype(str).isin(want)]
    for r in t.itertuples():
        k = str(r.listing_id)
        if k not in text or text[k][0] < r.last_collected_at:
            text[k] = (r.last_collected_at, r.description)
picks["description"] = picks.listing_id.map(
    lambda k: (text.get(k) or (0, ""))[1][:3000]
)
picks = picks.merge(x[["listing_id", "label"]], on="listing_id", how="left")
picks = picks.sample(frac=1, random_state=1).reset_index(drop=True)
picks["read_id"] = np.arange(len(picks))
picks.to_parquet(OUT + "u1_picks.parquet")
# the readers see neither the sample label nor the marks
rd = OUT + "read/"
os.makedirs(rd, exist_ok=True)
nb = int(np.ceil(len(picks) / 25))
for i in range(nb):
    part = picks.iloc[i::nb]
    with open(rd + f"batch{i:02d}.jsonl", "w") as fh:
        for r in part.itertuples():
            fh.write(
                json.dumps(
                    {
                        "read_id": int(r.read_id),
                        "unit_label": r.label,
                        "description": r.description,
                    }
                )
                + "\n"
            )
with open(OUT + "reader_prompt.md", "w") as fh:
    fh.write(READER_PROMPT)
print(nb, "batches", picks["sample"].value_counts().to_dict(), flush=True)
