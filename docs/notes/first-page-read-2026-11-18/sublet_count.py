"""Free check: sublet, short-term and end-date wording in the live Deals table.

Prints, for each of four patterns, the number of live ads whose description matches, how
many of them carry no caution, and how many are among the first 100 and first 500
uncautioned ads, then a snippet around each match for reading.

Run with: python docs/notes/first-page-read-2026-11-18/sublet_count.py TEXTS [DEALS_JSON]
"""

import json
import re
import sys

import pandas as pd

MONTH = r"(?:jan|feb|mar|apr|may|june?|july?|aug|sep|oct|nov|dec)[a-z]*\.?"
PATTERNS = {
    "sublet": r"\bsub-?(?:let|lease)",
    "short term": r"\bshort[- ]term",
    "until a date": (
        r"\b(?:until|through|thru|ending|ends?(?: on)?) (?:the end of )?"
        + MONTH
        + r" ?(?:\d{1,2}(?:st|nd|rd|th)?,? ?)?(?:20\d\d)?"
    ),
    "months of term": (
        r"\b(?:\d|\d\d|three|four|five|six|seven|eight|nine)[- ]months? "
        r"(?:lease|sublet|sublease|rental|term|only)"
    ),
}

if __name__ == "__main__":
    texts = pd.read_parquet(sys.argv[1])
    deals = (
        sys.argv[2] if len(sys.argv) > 2 else "/data1/apartments/site/deals/deals.json"
    )
    col = next(c for c in texts.columns if c != "listing_id")
    texts["listing_id"] = texts.listing_id.astype(str)
    table = pd.DataFrame(json.load(open(deals)))
    table["listing_id"] = table.listing_id.astype(str)
    plain = ~table.cautions.map(bool)
    table["place"] = plain.cumsum().where(plain)
    m = table.merge(texts, on="listing_id", how="left")
    m[col] = m[col].fillna("")
    for name, pattern in PATTERNS.items():
        r = re.compile(pattern, re.I)
        h = m[m[col].map(lambda s: bool(r.search(s)))]
        print(
            f"\n== {name}: {len(h)} ads, uncautioned {h.place.notna().sum()}, "
            f"first 100 {(h.place <= 100).sum()}, first 500 {(h.place <= 500).sum()}"
        )
        for _, x in h[h.place.notna()].sort_values("place").iterrows():
            s = x[col]
            k = r.search(s)
            print(
                f"  #{int(x.place)} {x.listing_id}: {s[max(0, k.start() - 90) : k.end() + 90]!r}"
            )
