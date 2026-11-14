"""Compare the page price of text-only rows with the net and gross amounts their text states.

    python amounts.py

Takes the rows of L1's freetext copy with `months_free_text` above zero and `months_free`
empty, joins the descriptions written by extract.py, and finds dollar amounts after "net",
"net effective" or "gross" ("net effective rent of $2,900", "Gross Rent: $3,200"). For each
value of `ask_basis_text` it prints the rows stating a net amount, a gross amount or both, and,
where the text states both, how often `page_price` equals the net amount or the gross amount
within $2. This is a check on the basis column, and no column carries the amounts. Run it in
a 3G scope.
"""

import re

import pandas as pd

OUT = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-freetext"
)
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
TEXTS = "/data1/apartments/tmp/sprint-20261113/free-months/texts.parquet"

rows = pd.read_parquet(
    OUT + "/rows.parquet", columns=["listing_id", "months_free_text", "ask_basis_text"]
)
rows["lid"] = rows.listing_id.astype(str)
ads = pd.read_parquet(ADS, columns=["listing_id", "months_free", "page_price"])
ads["lid"] = ads.listing_id.astype(str)
rows = rows.merge(ads[["lid", "months_free", "page_price"]], on="lid", how="left")
rows = rows[
    (rows.months_free_text > 0) & rows.months_free.isna() & rows.page_price.notna()
]
texts = pd.read_parquet(TEXTS, columns=["listing_id", "description"]).dropna()
texts["lid"] = texts.listing_id.astype(str)
r = rows.merge(texts[["lid", "description"]], on="lid")
print("text-only rows with a page price and a text in the extract:", len(r))

AMOUNT = r"\$\s?(\d{1,2},?\d{3}(?:\.\d\d)?)"
NOUN = r"(?:\s+(?:monthly\s+)?(?:rent|price|rate|pricing))?"
LINK = r"(?:\s+(?:of|is|at|would\s+be|=))?\s*:?\s*(?:only\s+|just\s+)?"
NET = re.compile(r"\bnet(?:[\s-]*effective)?" + NOUN + LINK + AMOUNT, re.I)
GROSS = re.compile(r"\bgross" + NOUN + LINK + AMOUNT, re.I)


def amounts(pattern, text):
    return [float(x.replace(",", "")) for x in pattern.findall(text)]


def equals(values, price):
    return any(abs(v - price) <= 2 for v in values)


r["net"] = r.description.map(lambda d: amounts(NET, d))
r["gross"] = r.description.map(lambda d: amounts(GROSS, d))
r["page_net"] = [equals(a, p) for a, p in zip(r.net, r.page_price)]
r["page_gross"] = [equals(a, p) for a, p in zip(r.gross, r.page_price)]
has_net, has_gross = r.net.map(bool), r.gross.map(bool)
for basis, g in r.groupby(r.ask_basis_text.fillna("null")):
    both = g[has_net[g.index] & has_gross[g.index]]
    print(
        f"\n{basis}: rows {len(g)}, net amount {int(has_net[g.index].sum())}, "
        f"gross amount {int(has_gross[g.index].sum())}, both {len(both)}"
    )
    print(
        f"  with both: page = net {int(both.page_net.sum())}, "
        f"page = gross {int(both.page_gross.sum())}, "
        f"neither {int((~both.page_net & ~both.page_gross).sum())}"
    )
