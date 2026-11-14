"""Shared pieces of the text-flag screen: paths, the old patterns and their candidates, the
readers' rubrics, and a pass that matches patterns over every listing's description.

`t1_texts.py` writes the descriptions. Each pattern runs on the text as `cautions.plain` leaves
it (lowercase, single spaces, plain hyphens), and only where the description is known, as
`b0data` sets its flags. The old patterns run on that text too: `plain` only folds white
space and dashes, so they mark the same listings as on `b0data`'s lowercased text, and
`t2_dev.py` counts any listing where they do not.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import cautions  # noqa: E402
from rentfrontier.b0data import MIN_DESCRIPTION, TEXT_FLAGS  # noqa: E402
from rentfrontier.b0income import INCOME as B0INCOME  # noqa: E402

OUT = Path("/data1/apartments/tmp/text-flags-2026-11-13")
TEXTS = OUT / "texts.parquet"
ROWS = OUT / "rows.parquet"
READS = OUT / "reads"
FLAGS = ("income_restricted", "shared_space", "rent_stabilized")
OLD = {f: re.compile(TEXT_FLAGS[f]) for f in FLAGS}
# Looser words for each flag. An unmarked ad with one of them is a candidate for a miss.
CANDIDATES = {
    "income_restricted": re.compile(
        r"\bhpd\b|\bhdc\b|lotter|housing connect|affordab|restricted|\bami\b"
        r"|income[- ]?(?:limit|eligib|guideline|band|bracket|cap|range|level|restrict)"
        r"|max(?:imum)?\.? (?:\w+ )?income|(?:low|moderate|middle)[- ]income|median income"
        r"|mitchell[- ]?lama|inclusionary|regulatory agreement|section ?8"
    ),
    "shared_space": re.compile(
        r"shar(?:e|ed|ing) (?:a |the |an )?(?:bath|kitchen|common|living)|\bsro\b"
        r"|single room|co-?living|room(?:mate|ate)|housemate|flatmate"
        r"|\b(?:apartment|apt|house|room) share\b|\bin a share\b|\bshared (?:apartment|house|unit)"
        r"|\brooms? (?:for rent|available)|private (?:bed)?room in|\broom in (?:a|an|my|our)\b"
        r"|furnished room|rent(?:ing)? (?:a|one|the|my) room"
    ),
    "rent_stabilized": re.compile(
        r"stabili[sz]|stabl[ie]?[sz]|stabal|stabe?li|rent[- ]?regulat|rent[- ]?control"
        r"|\br\.?s\.? (?:unit|apartment|apt|lease)"
    ),
}
# The rubric each reader gets for its flag.
RUBRICS = {
    "income_restricted": """\
Question: is THIS apartment offered under an income-restricted affordable-housing program?

Answer "yes" when the text says the apartment itself is income-restricted or affordable
under a program with income limits: a housing lottery (NYC Housing Connect, an HPD or HDC
lottery), an AMI band ("80% AMI", "130% AMI unit"), maximum or minimum household incomes set
by a program, an HPD or HDC regulated affordable unit, Mitchell-Lama, a 421-a or inclusionary
affordable unit, a re-rental of a lottery unit.

Answer "no" when:
- it is an ordinary market-rate ad, even if it asks for income of 40 times the rent, a
  minimum income, a credit score or guarantors;
- the building has affordable or income-restricted units but the text says or implies this
  apartment is not one of them, or it only quotes a fee schedule mentioning
  income-restricted units ("application fee $20, optional for income restricted units");
- "affordable" is sales talk ("affordable luxury", "an affordable two bedroom"), or the
  text says there are no income restrictions;
- it only says Section 8 or vouchers are welcome, or that the unit is rent-stabilized.

Answer "unclear" only when the text is too short or garbled to decide.""",
    "shared_space": """\
Question: does the ad offer a room or bed in a shared apartment or house, an SRO room, or a
unit whose bathroom or kitchen is shared with OTHER tenants (people outside the renter's
own household)?

Answer "yes" for: a room for rent in a shared apartment, a room in a co-living suite, an
SRO or single-room-occupancy room, a studio or room with a bathroom or kitchen in the hall
or shared with other units or tenants, an ad looking for a roommate to share the
advertiser's apartment.

Answer "no" for:
- a whole apartment, even if pitched as "great for roommates", "roommate friendly",
  "flex", or with a note about roommate change fees or a broker helping find roommates;
- an apartment whose own bedrooms share one of its bathrooms ("the other two bedrooms
  share a bath");
- shared building amenities (a shared roof deck, a shared laundry, a co-working lounge);
- a former SRO building converted to ordinary apartments.

Answer "unclear" only when the text is too short or garbled to decide.""",
    "rent_stabilized": """\
Question: does the text say that THIS apartment is rent-stabilized (rent-regulated under
New York's rent stabilization law, including a stabilized lease in a 421-a building)?

Answer "yes" when the text says the apartment, or the building's apartments without
exception, are rent-stabilized, including misspellings ("rent stablized") and "stabilized
lease".

Answer "no" when:
- the text says the apartment is not stabilized, free-market or deregulated;
- it says only that other apartments of the building are stabilized;
- "stabilized" means something else, or rent stabilization is only mentioned in passing
  (a law, a neighborhood's housing stock).

Answer "unclear" only when the text is too short or garbled to decide.""",
}
READER_PROMPT = """\
You are reading New York City rental ads for one question. Read the file {inp}. Each line is
a JSON object with an "id" and the ad's description "text".

{rubric}

Judge each ad by reading its text yourself. Do not write or run code to classify the ads, and
do not open any other file. For every ad, in the order given, write one JSON line to {out}:

{{"id": "<id>", "label": "yes" | "no" | "unclear", "evidence": "<a quote of 15 words or fewer from the ad that decides it, or empty>"}}

Write exactly one line per ad and nothing else to that file. When done, reply with the count
of each label only."""


def plain(text):
    return cautions.plain(text) if isinstance(text, str) else ""


def match_all(patterns: dict) -> pd.DataFrame:
    """For every listing of L1's dataset, `known` and a column per compiled pattern in
    `patterns` (a dict name -> pattern) saying whether its known description matches."""
    rows = pd.read_parquet(ROWS)
    parts = []
    file = pq.ParquetFile(TEXTS)
    for g in range(file.num_row_groups):
        t = file.read_row_group(g).to_pandas()
        low = [plain(x) for x in t.text]
        part = pd.DataFrame({"listing_id": t.listing_id})
        part["known"] = np.array([len(x.lower()) > MIN_DESCRIPTION for x in t.text])
        for name, rx in patterns.items():
            part[name] = part.known & np.array([bool(rx.search(x)) for x in low])
        parts.append(part)
        del t, low
    m = pd.concat(parts, ignore_index=True)
    return rows.merge(m, on="listing_id", how="left", validate="one_to_one")


def texts_for(ids) -> pd.Series:
    """The descriptions of the listings `ids`, by listing_id."""
    want = set(map(str, ids))
    out = {}
    file = pq.ParquetFile(TEXTS)
    for g in range(file.num_row_groups):
        t = file.read_row_group(g).to_pandas()
        t = t[t.listing_id.isin(want)]
        out.update(zip(t.listing_id, t.text))
    return pd.Series(out)


def write_batches(sample: pd.DataFrame, tag: str, size: int, cap: int = 8000) -> list:
    """Shuffle `sample` (listing_id, flag, stratum, text) within each flag, give each ad an
    id, write reader batches of `size` ads per flag under READS, and the key from ids to
    listings. Each batch also gets its reader's prompt, in a `.prompt.txt` file beside it. A
    text over `cap` characters is cut there, with a note at the end."""
    READS.mkdir(parents=True, exist_ok=True)
    keys, batches = [], []
    for flag, part in sample.groupby("flag", sort=False):
        part = part.sample(frac=1, random_state=7).reset_index(drop=True)
        part["id"] = [f"{tag}-{flag[:3]}-{i:04d}" for i in range(len(part))]
        keys.append(part.drop(columns="text"))
        for b0 in range(0, len(part), size):
            chunk = part.iloc[b0 : b0 + size]
            inp = READS / f"{tag}-{flag}-{b0 // size:02d}.in.jsonl"
            with open(inp, "w") as f:
                for i, text in zip(chunk.id, chunk.text):
                    if len(text) > cap:
                        text = text[:cap] + " [text cut here]"
                    f.write(json.dumps({"id": i, "text": text}) + "\n")
            out = str(inp).replace(".in.", ".out.")
            prompt = READER_PROMPT.format(inp=inp, rubric=RUBRICS[flag], out=out)
            Path(str(inp).replace(".in.jsonl", ".prompt.txt")).write_text(prompt + "\n")
            batches.append((flag, str(inp), out))
    pd.concat(keys).to_csv(READS / f"{tag}-key.csv", index=False)
    return batches


def read_labels(tag: str) -> pd.DataFrame:
    """The readers' labels for the batches of `tag`, joined to their key."""
    key = pd.read_csv(READS / f"{tag}-key.csv", dtype={"listing_id": str})
    got = []
    for p in sorted(READS.glob(f"{tag}-*.out.jsonl")):
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("{"):
                got.append(json.loads(line))
    lab = pd.DataFrame(got).drop_duplicates("id", keep="last")
    return key.merge(lab, on="id", how="left")
