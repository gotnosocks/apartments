"""Brooklyn ads on Manhattan buildings.

StreetEasy links some Brooklyn listings to a Manhattan building page. The agent
types a Brooklyn address such as "316 7th Avenue", StreetEasy files it under
the Manhattan building with the same number and street name, and the ad itself
places the apartment in Park Slope, Clinton Hill or by Barclays Center.
`quarantine-v17` holds out the rows found so far, with the reason code
`brooklyn_misjoin`, and `MISJOINS` records each one's evidence for a later remap
to the right Brooklyn building.

`screen` looks for the Brooklyn place names in each row's ad text. It reads no
rent, estimate or residual. Before matching, it blanks out the phrases known to
raise false alarms: Kensington House in Chelsea, Brooklyn Fare, a broker's or
sponsor's office address, a broker's mention of other listings or of where the
agent lives. In Hell's Kitchen and Hudson Yards it also skips "Clinton Hill",
which there means Clinton. `frontier/scripts/brooklyn_screen.py` runs it on a
new dataset and writes the hits nobody has read yet to a review list. A row
joins `MISJOINS` and the next quarantine version only after someone reads its
whole ad.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

REVIEWS = Path(__file__).resolve().parents[3] / "config" / "reviews"
# Each confirmed row's evidence (listing, our building and unit, the address
# StreetEasy shows, the address the agent typed, the ad phrase, the agent and
# the date) for the remap once Brooklyn is collected.
MISJOINS = REVIEWS / "brooklyn-misjoins-20261014.jsonl"
# Audit ids already read, confirmed or not, so a screen run lists only new hits.
READ = (
    REVIEWS / "quarantine-v16-read-20261014.txt",
    REVIEWS / "quarantine-v17-read-20261014.txt",
)
# Dataset cohorts the screen has run on, one per line; a test checks that each
# registered dataset is among them.
SCREENED = REVIEWS / "brooklyn-screened.txt"

PLACES = (
    r"prospect park|parade grounds?|cortelyou|beverly road|ditmas|\bplg\b"
    r"|prospect[- ]lefferts|flatbush|park slope|windsor terrace|crown heights"
    r"|fort greene|clinton hill|bed[- ]?stuy|bushwick|greenpoint|sunset park|bay ridge"
    r"|williamsburg|boerum hill|cobble hill|carroll gardens|gowanus|prospect heights"
    r"|kensington|dumbo|brooklyn heights|botanic(?:al)? gardens?|barclays"
    r"|atlantic terminal|downtown brooklyn"
)
NEAR = re.compile(
    r"(?:located|situated|nestled|heart of|in|near|minutes? (?:to|from|away from)"
    r"|mins? (?:to|from)|steps (?:to|from|away from)|close to|blocks? (?:to|from)"
    r"|walk to|across from|around the corner from)\s+(?:the |beautiful |prime "
    r"|historic |trendy |vibrant )?(?:north |south )?(?:brooklyn )?(?:"
    + PLACES
    + r")\b"
    r"|(?:" + PLACES + r") (?:block|location)\b"
    r"|\b112\d\d\b"
)
FALSE_ALARMS = re.compile(
    r"kensington house|brooklyn fare"
    # an office address: "184 noll street suite 2 brooklyn ny 11237"
    r"|\d+[a-z]* [\w .]{2,40}?,?\s+brooklyn,? ny,? 112\d\d"
    # the agent's other listings, or where the agent lives
    r"|(?:i also have|also ask about|other apartments|other listings|lives in)[^.!\n]*"
)
CLINTON_HOODS = {"Hell's Kitchen", "Hudson Yards"}


def screen(frame: pd.DataFrame, text: pd.Series) -> pd.DataFrame:
    """The rows of `frame` whose ad text (`text`, lower-cased, on `frame`'s
    index) places the apartment in Brooklyn, with the matched phrase and the
    text around it."""
    rows = []
    for i, ad in text.items():
        ad = FALSE_ALARMS.sub(" ", ad)
        for m in NEAR.finditer(ad):
            if (
                "clinton hill" in m.group(0)
                and frame.at[i, "neighbourhood"] in CLINTON_HOODS
            ):
                continue
            rows.append(
                dict(
                    audit_id=frame.at[i, "audit_id"],
                    source_listing_id=str(frame.at[i, "source_listing_id"]),
                    building=frame.at[i, "building"],
                    unit_id=frame.at[i, "unit_id"],
                    neighbourhood=frame.at[i, "neighbourhood"],
                    period=str(frame.at[i, "price_at"])[:7],
                    phrase=m.group(0),
                    snippet=ad[max(0, m.start() - 200) : m.end() + 160],
                )
            )
            break
    return pd.DataFrame(rows)


def read_ids() -> frozenset:
    """Audit ids in the read lists and in `MISJOINS`."""
    ids = set()
    for path in READ:
        ids |= set(path.read_text().split())
    with open(MISJOINS) as f:
        ids |= {json.loads(line)["audit_id"] for line in f if line.strip()}
    return frozenset(ids)
