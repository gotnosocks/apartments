"""Compare `months_free_text` in L1's freetext copy with the coded `months_free`.

    python compare.py [--samples] [--check]

Prints the rows and held-out ads of L1's latest split that gain a value where `months_free`
is empty or zero, the agreement where both exist, the values and kinds by year, the rows by
`ask_basis_text` and by what `months_free` and the text give, and the ads whose text says the
building's concession leaves the unit out. With --samples it writes the reader samples to
SCRATCH; the samples in the note come from the first build. With --check it writes the ads
for the second reading: every ad leaving its unit out, and 40 ads marked gross.
Run it in a 3G scope.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0freetext as ft  # noqa: E402

SRC = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
OUT = SRC + "-freetext"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
L1 = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/pred_scores.npz"
SCRATCH = "/data1/apartments/tmp/sprint-20261113/free-months/"
# Made by extract.py: each L1 listing's latest description where it mentions free rent.
TEXTS = SCRATCH + "texts.parquet"

rows = pd.read_parquet(
    OUT + "/rows.parquet",
    columns=[
        "listing_id",
        "unit_id",
        "price_at",
        "latest_ask",
        "months_free_text",
        "free_lease_months",
        "free_text_kind",
        "ask_basis_text",
    ],
)
rows["heldout"] = np.load(L1, allow_pickle=True)["heldout"]
ads = pd.read_parquet(
    ADS, columns=["listing_id", "months_free", "lease_term", "page_price"]
)
ads["listing_id"] = ads.listing_id.astype(str)
rows["lid"] = rows.listing_id.astype(str)
rows = rows.merge(ads.rename(columns={"listing_id": "lid"}), on="lid", how="left")
assert len(rows) == 1_896_471 and rows.lid.is_unique
rows["year"] = pd.to_datetime(rows.price_at).dt.year
text, coded = rows.months_free_text, rows.months_free
print("rows", len(rows), "held out", int(rows.heldout.sum()))
print(
    "coded months_free: non-null",
    int(coded.notna().sum()),
    "zero",
    int((coded == 0).sum()),
)
print("kinds:", rows.free_text_kind.value_counts(dropna=False).to_dict())


def gains(mask, label):
    for what, m in (("months > 0", text > 0), ("stated zero", text == 0)):
        g = rows[mask & m]
        print(
            f"  {label}, {what}: rows {len(g)}, units {g.unit_id.nunique()}, "
            f"held-out ads {int(g.heldout.sum())}"
        )


print("Gains:")
gains(coded.isna(), "months_free empty")
gains(coded == 0, "months_free zero")
pos = rows[(text > 0) & coded.isna()]
print("  empty-coded gains by kind:", pos.free_text_kind.value_counts().to_dict())
print(
    "  of held-out ads with months:",
    round((rows.heldout & (text > 0)).sum() / rows.heldout.sum(), 4),
)

both = rows[(coded > 0) & text.notna()]
agree = (both.months_free - both.months_free_text).abs() <= 0.1
print(
    f"\nBoth exist (coded > 0, text value): {len(both)}, agree within 0.1: {agree.mean():.4f}"
)
print(
    "coded > 0 with no text value:",
    int(((coded > 0) & text.isna()).sum()),
    rows[(coded > 0) & text.isna()].free_text_kind.value_counts(dropna=False).to_dict(),
)
dis = both[~agree]
print(
    "disagreement direction: text > coded",
    int((dis.months_free_text > dis.months_free).sum()),
    "text < coded",
    int((dis.months_free_text < dis.months_free).sum()),
)
print(
    "agreement by kind:",
    both.assign(a=agree)
    .groupby("free_text_kind")
    .a.agg(["size", "mean"])
    .round(3)
    .to_dict("index"),
)


def r(x):
    return x.round(2).where(
        x.round(2).isin([0, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4]), -1
    )


tab = pd.crosstab(
    r(both.months_free).rename("coded"), r(both.months_free_text).rename("text")
)
print("cross-tab (rounded; -1 = other):\n", tab)
# Does the disagreement follow the lease? Coded months scaled to the text's lease.
print(
    "disagreeing rows with a text lease:",
    int(dis.free_lease_months.notna().sum()),
    "coded lease_term equals text lease:",
    int((dis.lease_term == dis.free_lease_months).sum()),
)

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print("\nBy year (rows with a value, share of rows, kinds):")
k = rows.assign(kind=rows.free_text_kind.fillna("-"))
by = pd.crosstab(k.year, k.kind)
by["rows"] = k.groupby("year").size()
by["text>0"] = k[text > 0].groupby("year").size()
by["coded>0"] = k[coded > 0].groupby("year").size()
by["text>0, coded empty"] = k[(text > 0) & coded.isna()].groupby("year").size()
print(by.fillna(0).astype(int))
vals = rows[text > 0].assign(v=r(rows.months_free_text))
print(pd.crosstab(vals.year, vals.v))

# What the texts say of the listed price, by what months_free and the text give.
group = pd.Series(
    np.select(
        [coded > 0, coded == 0, text > 0],
        ["months_free > 0", "months_free 0", "text only"],
        "neither",
    ),
    index=rows.index,
    name="group",
)
basis = rows.ask_basis_text.fillna("unstated").rename("basis")
print("\nRows by ask_basis_text:\n", pd.crosstab(group, basis, margins=True))
held = rows.heldout.astype(bool)
print(
    "held-out ads by ask_basis_text:\n",
    pd.crosstab(group[held], basis[held], margins=True),
)
only = group == "text only"
print(
    "text-only rows by kind and basis:\n",
    pd.crosstab(rows.free_text_kind[only], basis[only], margins=True),
)
# A basis with no concession mentioned: ask_basis_text set and free_text_kind empty.
print(
    "rows with a basis and no kind:",
    basis[rows.free_text_kind.isna()].value_counts().to_dict(),
)

# Ads whose text says the building's concession leaves the unit out.
t = pd.read_parquet(TEXTS, columns=["listing_id", "description"]).dropna()
t = t[t.description.str.contains(ft.UNIT_EXCLUDED)]
offer = t.description.map(lambda d: bool(ft.statements(d)))
excluded = pd.concat([t[offer], t[~offer]])
ex = rows[rows.lid.isin(set(excluded.listing_id))]
print(
    f"\nunit left out: listings {len(excluded)}, {int(offer.sum())} with an offer, "
    f"rows {len(ex)}, held-out {int(ex.heldout.sum())}, "
    f"months_free {ex.months_free.value_counts(dropna=False).to_dict()}"
)
# The coded rows: is latest_ask net of the coded months?
c = rows[(coded > 0) & rows.page_price.notna() & rows.lease_term.gt(0)]
netted = (c.page_price * (1 - c.months_free / c.lease_term) - c.latest_ask).abs() <= 2
print(
    f"coded rows with latest_ask = page_price x (1 - free/lease): {netted.mean():.4f} of {len(c)}"
)
p = rows[(text > 0) & coded.isna() & rows.page_price.notna()]
print(
    f"text-only rows with latest_ask == page_price: {(p.latest_ask - p.page_price).abs().le(2).mean():.4f} of {len(p)}"
)

if "--check" in sys.argv:
    # The second reading: the ads leaving their unit out, and ads marked gross.
    rng = np.random.default_rng(20261114)
    desc = pd.read_parquet(TEXTS, columns=["listing_id", "description"]).dropna()
    gross = desc[desc.listing_id.isin(set(rows.lid[rows.ask_basis_text == "gross"]))]
    pick = gross.iloc[np.sort(rng.choice(len(gross), 40, replace=False))]
    check = [
        {"id": i, "text": d[:4000]}
        for i, d in zip(
            [*excluded.listing_id, *pick.listing_id],
            [*excluded.description, *pick.description],
        )
    ]
    for b in range(0, len(check), 23):
        with open(f"{SCRATCH}read_check_{b // 23}.json", "w") as f:
            json.dump(check[b : b + 23], f, indent=1)
    print("check ads written:", len(check), "of", len(gross), "gross texts in TEXTS")
if "--samples" not in sys.argv:
    raise SystemExit
# Reader samples, blind to the parser's value.
rng = np.random.default_rng(20261113)
desc = (
    pd.read_parquet(TEXTS, columns=["listing_id", "description"])
    .dropna()
    .set_index("listing_id")
    .description
)


def sample(ids, n, name):
    ids = [i for i in ids if i in desc.index]
    pick = rng.choice(len(ids), size=min(n, len(ids)), replace=False)
    out = [{"id": ids[i], "text": desc[ids[i]][:4000]} for i in sorted(pick)]
    for b in range(0, len(out), 25):
        with open(f"{SCRATCH}read_{name}_{b // 25}.json", "w") as f:
            json.dump(out[b : b + 25], f, indent=1)
    return [o["id"] for o in out]


pre = re.compile(r"free|concession|net[\s-]*effective", re.I)
found = sample(list(pos.lid), 200, "found")
empty = rows[text.isna()].lid
empty = [i for i in empty if i in desc.index and pre.search(desc[i])]
print("rows with no value but free/concession/net effective in the text:", len(empty))
missed = sample(empty, 100, "missed")
disagree = sample(list(dis.lid), 50, "disagree")
keep = rows.set_index("lid").loc[
    found + missed + disagree,
    [
        "months_free_text",
        "free_lease_months",
        "free_text_kind",
        "months_free",
        "lease_term",
    ],
]
keep.assign(
    set=["found"] * len(found) + ["missed"] * len(missed) + ["disagree"] * len(disagree)
).to_parquet(SCRATCH + "read_truth.parquet")
