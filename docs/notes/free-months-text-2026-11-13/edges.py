"""Count phrasings the reader handles poorly among the texts with months in L1's freetext copy.

    python edges.py

Reads the descriptions written by extract.py and keeps those of rows with `months_free_text`
above zero. For each phrasing it prints the number of texts matching and their values of
`months_free_text`, and a few matches for reading. The phrasings are:

- first_last: "first month free and last month free", read as 1 month since `choose` keeps a
  single offer;
- broker: a count of free months before a broker's fee ("1 month free broker fee");
- deposit: a count of free months before a security deposit ("1 month free security
  deposit");
- negation: a negation after an offer ("1 month free not available") or before it ("no longer
  1 month free");
- tied_both: a text calling the price gross while an offer's sentence ties the offer to the
  price ("Price shown is gross; 1 month free"), so `ask_basis` gives null while `choose` still
  ranks the offer as tied to the price; also counted among texts with offers of different
  counts, where the rank can change the months.

Run it in a 3G scope.
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0freetext as ft  # noqa: E402

OUT = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-freetext"
)
TEXTS = "/data1/apartments/tmp/sprint-20261113/free-months/texts.parquet"

rows = pd.read_parquet(
    OUT + "/rows.parquet", columns=["listing_id", "months_free_text"]
)
rows["lid"] = rows.listing_id.astype(str)
texts = pd.read_parquet(TEXTS, columns=["listing_id", "description"]).dropna()
texts["lid"] = texts.listing_id.astype(str)
t = texts.merge(rows[rows.months_free_text > 0][["lid", "months_free_text"]], on="lid")
print("texts with months in the extract:", len(t))

COUNT = r"(?:\d+(?:\.\d+)?|one|two|three|half|a)"
FREE = r"(?:of\s+)?free(?:\s+rent)?"
PATTERNS = {
    "first_last": r"\bfirst\s+month(?:['’]s)?(?:\s+rent)?\s+(?:is\s+)?free\b[^.!\n]{0,20}?"
    r"\b(?:and|&|\+|plus)\s+(?:the\s+)?last\s+month(?:['’]s)?(?:\s+rent)?\s+(?:is\s+)?free",
    "broker": rf"\b{COUNT}\s+months?\s+free\s+(?:broker['’]?s?['’]?|brokerage)\b",
    "deposit": rf"\b{COUNT}\s+months?\s+free\s+(?:security|deposit)\b",
    "negation": rf"\bmonths?\s+{FREE}[^.!\n;]{{0,25}}?\b(?:no\s+longer|not\s+available|"
    r"unavailable|expired|has\s+ended|ended|not\s+valid)\b"
    rf"|\b(?:no\s+longer|expired)\s+(?:offering\s+|offers?\s+)?(?:a\s+|the\s+)?{COUNT}?\s*"
    r"(?:free\s+months?|months?\s+free)",
}
for name, p in PATTERNS.items():
    hit = t[t.description.str.contains(p, flags=re.I, regex=True)]
    print(
        f"\n{name}: {len(hit)} texts, months_free_text",
        hit.months_free_text.round(2).value_counts().to_dict(),
    )
    for d in hit.description.head(6):
        m = re.search(p, d, re.I)
        print("   ...", d[max(0, m.start() - 60) : m.end() + 60].replace("\n", " "))

tied_both = several = 0
for d in t.description:
    offers = ft.statements(d)
    if any(o.basis for o in offers) and ft.basis_stated(d, offers) == "both":
        tied_both += 1
        several += len({o.months for o in offers}) > 1
print(
    f"\ntied_both: {tied_both} texts, {several} of them with offers of different counts"
)
