"""Rent-blind candidate detector for quarantine-v9: fixed ad-text checks over every
row in Greenwich Village, Gramercy Park and Flatiron. Reads no rent, estimate or
residual; the output carries no rent.

Usage: quarantine_v9_screen.py OUT.jsonl [CACHE_ROOT]"""

import re, json, sys
import numpy as np, pandas as pd
from pathlib import Path
from rentfrontier import data, descriptions, corrections as c

RULES = "baths-ad-v2,bedrooms-ad-v2,fields-review-v3,quarantine-v6,unit-labels-v11,unit-reviews-v1,unit-splits-v4".split(
    ","
)
f = data.load(
    data.DATASET_NB5, **({"cache_root": Path(sys.argv[2])} if len(sys.argv) > 2 else {})
)
out = data.apply_rules(f, np.zeros(len(f), bool), RULES)
f = (out[0] if isinstance(out, tuple) else out).reset_index(drop=True)
f = f[
    f.neighbourhood.isin(["Greenwich Village", "Gramercy Park", "Flatiron"])
].reset_index(drop=True)
tok = descriptions.SOURCES.set(
    (
        descriptions.SOURCE,
        descriptions.WV_SOURCE,
        descriptions.GV_SOURCE,
        descriptions.FGP_SOURCE,
    )
)
try:
    text = descriptions.attach(f)
finally:
    descriptions.SOURCES.reset(tok)
text = text.fillna("").map(c.plain).str.lower()

PLACE = (
    r"(?:harlem|upper (?:east|west) side|upper west|upper east|\buws\b|\bues\b|park slope|north slope|prospect park|"
    r"ditmas park|flatbush|clinton hill|fort greene|bed[- ]?stuy|bushwick|williamsburg|greenpoint|astoria|"
    r"long island city|\blic\b|the bronx|jersey city|hoboken|barclays center|columbia university|"
    r"battery park city|\bbpc\b|financial district|wall street|stock exchange|washington heights|inwood|"
    r"morningside|yorkville|lenox hill|riverside park|strivers'? row|myrtle ave|church ave)"
)
CUES = {
    "place_located": re.compile(
        r"(?:located|situated|nestled|in the heart of|heart of|in prime|prime|steps (?:away )?from|"
        r"blocks? (?:away )?from|right by|by|near|next to|close to|walk to|apartment in|unit in|bedroom in|studio in|"
        r"located (?:in|on|near)|location)\W{0,3}(?:the |beautiful |historic |central |south |north |west |east )?"
        + PLACE
    ),
    "place_named_first": re.compile(
        r"(?:^|[.!*\n]\s*)(?:great |amazing |gorgeous |beautiful |prime |unbeatable |excellent )?(?:central |south |north )?"
        + PLACE
        + r"\b[^.!\n]{0,40}(?:location|apartment|apt|unit|bedroom|studio|brownstone|renovated)"
    ),
    "central_park": re.compile(
        r"(?:blocks?|block away) (?:away )?from (?:both )?central park|from central park\b|central park (?:is )?(?:just )?(?:steps|blocks?) away"
    ),
    "far_street": re.compile(
        r"\b(?:e|w|east|west)\.? ?(?:4[0-9]|[5-9][0-9]|1[0-9][0-9])(?:st|nd|rd|th)?\.? (?:st|street)\b|\b(?:[4-9][0-9]|1[0-9][0-9])(?:st|nd|rd|th) (?:st|street) (?:&|and) "
    ),
    # Places no ad in the three neighbourhoods has reason to name: any mention.
    "far_place": re.compile(
        r"harlem|bushwick|prospect park|park slope|ditmas|flatbush|clinton hill|bed[- ]?stuy|"
        r"astoria|\bplg\b|prospect lefferts|lenox ave|adam clayton powell|beverly r(?:oa)?d|cortelyou|"
        r"church ave|strivers|myrtle|stock exchange|\bbpc\b|battery park city|crown heights|sunset park"
    ),
    "far_corner": re.compile(
        r"\b(?:e|w|east|west)\.? ?(?:4[0-9]|[5-9][0-9]|1[0-9][0-9])(?:st|nd|rd|th)? (?:st(?:reet)? )?(?:and|&|at) (?:\d(?:st|nd|rd|th)|\w+) ave"
    ),
    "address_not": re.compile(r"address is [^.\n]{0,40}\bnot\b"),
    "nonresidential": re.compile(
        r"commercial (?:space|unit|lease|use|tenant)|retail (?:space|use)|office space|office suite|"
        r"(?:intimate|private|executive) office|restaurant (?:space|owner)|used as (?:a )?restaurant|"
        r"medical (?:office|space)|professional office|showroom|show room|swing space|"
        r"not suitable for residential|professional space|non[- ]residential|sublease the space|skin spa|day spa (?:space|business)|"
        r"zoned (?:for )?commercial|storefront|ground floor retail"
    ),
    "shared_bath": re.compile(
        r"shared (?:bath|bathroom|toilet|restroom|shower)s?\b|(?:bath|bathroom|toilet)s? (?:is |are )?shared|share (?:a |the )?(?:bath|bathroom|toilet)"
    ),
    "room_share": re.compile(
        r"\broom in a\b|\broom for rent|private (?:bed)?room (?:in|available)|looking for (?:a |one )?(?:roommate|female|male|room ?mate)|"
        r"seeking (?:a )?(?:roommate|room ?mate)"
    ),
    "multi_unit": re.compile(
        r"rent both|both the [^.\n]{0,60} and the [^.\n]{0,40}(?:apartment|unit|house)|two (?:separate )?apartments (?:for|together)|"
        r"(?:entire|whole) (?:building|townhouse) for (?:rent|lease)|units? can be combined|combined with the adjacent"
    ),
    "short_stay": re.compile(
        r"minimum (?:stay|of \d+ (?:night|week|day))|nightly|per night|short[- ]term (?:rental|stay|lease)s? only|"
        r"only (?:available )?(?:for )?(?:a )?short[- ]term|corporate (?:housing|rental)|vacation rental|"
        r"summer (?:sublet|rental)|(?:\d|one|two|three|four|six) (?:week|month)s? (?:only|sublet|sublease)"
    ),
}
hits = pd.DataFrame({k: text.str.contains(rx) for k, rx in CUES.items()})


def wrong_side(building, t):
    m = re.match(r"(\d+)-(east|west)-(\d+)-street", str(building))
    if not m:
        return False
    side, street = m.group(2), m.group(3)
    for n, s2, st in re.findall(
        r"\b(\d{1,3}) (east|west|e|w)\.? (\d{1,2})(?:st|nd|rd|th)? (?:st\b|street)", t
    ):
        s2 = {"e": "east", "w": "west"}.get(s2, s2)
        if st == street and s2 != side:
            return True
    return False


hits["wrong_side"] = [wrong_side(b, t) for b, t in zip(f.building, text)]
hits["far_v3"] = text.str.contains(c.FAR_V3)
# A zip code outside lower Manhattan below 34th Street.
ZIPS = {
    "10001",
    "10002",
    "10003",
    "10009",
    "10010",
    "10011",
    "10012",
    "10013",
    "10014",
    "10016",
    "10038",
    "10007",
    "10004",
    "10005",
    "10006",
    "10280",
    "10282",
}
hits["zip"] = text.map(
    lambda t: any(
        z not in ZIPS
        for m in re.findall(r"\bnew york,? ny,? (1[01]\d{3})\b|\bny (1[01]\d{3})\b", t)
        for z in m
        if z
    )
)
anyhit = hits.any(axis=1)
print(
    "rows",
    len(f),
    "with text",
    int((text.str.len() > 20).sum()),
    "hits",
    int(anyhit.sum()),
)
print(hits[anyhit].sum().to_dict())


def snips(t, flags):
    out = []
    for k in flags:
        rx = CUES.get(k) or {
            "far_v3": c.FAR_V3,
            "wrong_side": re.compile(
                r"\b\d{1,3} (?:east|west|e|w)\.? \d{1,2}(?:st|nd|rd|th)? (?:st\b|street)"
            ),
            "zip": re.compile(r"\bny,? 1[01]\d{3}\b"),
        }.get(k)
        if rx is not None and (m := rx.search(t)):
            out.append(t[max(0, m.start() - 160) : m.end() + 160])
    return out


rows = []
for i in f.index[anyhit]:
    fl = [k for k in hits.columns if hits.at[i, k]]
    rows.append(
        dict(
            audit_id=f.at[i, "audit_id"],
            hood=f.at[i, "neighbourhood"],
            building=f.at[i, "building"],
            unit_id=f.at[i, "unit_id"],
            source_listing_id=str(f.at[i, "source_listing_id"]),
            unit_label=f.at[i, "unit_label"] if "unit_label" in f else None,
            period=str(f.at[i, "period"])[:7],
            flags=fl,
            snippets=snips(text[i], fl),
            text=text[i][:5000],
        )
    )
Path(sys.argv[1]).write_text("".join(json.dumps(r) + "\n" for r in rows))
