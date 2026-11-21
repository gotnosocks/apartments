"""Counts of the TODO's three marks over every ad of the live build, by status.

Marks:
- `ratio`: coded 0 or 1 bed and an ask over three times the area median (`sw1_ads.py`);
- `text`: any of the TODO's words (`sw2_texts.py`), raw and narrowed. The narrowing was fixed
  from `sw3a_context.log` alone, with no ask or gap loaded: an "office" counts only outside
  the residential phrases below, and a "retail" only in a phrase that offers retail space;
- `short`: a stripped text of five characters or fewer, or "Draft", "Desc" or "TBD".

Status (`sw1_ads.py`): `train` is a training row of the live Deals run that no ledger exclude
names; `live` is one of the run's Deals ads; `ledger` is excluded by an active ledger entry;
`rule` was dropped by another pipeline rule. Buildings are cut in halves by a hash of the
building id, as in `thin-level-caution-2026-11-20/b1.py`, with this note's seed.
"""

import hashlib
import re
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/commercial-sweep")
SEED = "commercial-sweep-2026-11-20"
OFFICE_BEFORE = (
    r"home|leasing|management|post|rental|rentals|sales|building|our|call|contact|box|"
    r"bedroom/home|room/home|den/home|den|deco|on-site|onsite|site|super's"
)
OFFICE_AFTER = r"hours|nook|today|area|alcove|corner|chair|desk|nursery|guest|or\s+den"
OFFICE_RES = re.compile(
    rf"(?:\b(?:{OFFICE_BEFORE})\W+offices?\b)|(?:\boffices?\W+(?:{OFFICE_AFTER})\b)",
    re.I,
)
OFFICE = re.compile(r"\boffices?\b", re.I)
RETAIL_OFFER = re.compile(
    r"\bretail\W+(?:space|spaces|unit|store|storefront|use|tenant|lease|for\s+rent|"
    r"available|opportunity)\b|\b(?:for|ideal\s+for|perfect\s+for|zoned\s+for)\W+retail\b|"
    r"\bretail\s*/\s*office\b|\boffice\s*/\s*retail\b",
    re.I,
)


def half(b: str) -> str:
    return "AB"[hashlib.sha1((SEED + b).encode()).digest()[0] & 1]


def office_narrow(d: str) -> bool:
    """An "office" that is not one of the residential phrases."""
    return len(OFFICE.findall(d)) > len(OFFICE_RES.findall(d))


if __name__ == "__main__":
    A = pd.read_parquet(OUT / "ads.parquet")
    T = pd.read_parquet(OUT / "texts.parquet")
    A = A.merge(T, on="listing_id", how="left")
    A["has_record"] = A.dlen.notna()
    for c in [c for c in A if c.startswith("t_")] + ["short"]:
        A[c] = A[c].fillna(False).astype(bool)
    d = A.desc.fillna("")
    A["n_office"] = A.t_office & d.map(office_narrow)
    A["n_retail"] = A.t_retail & d.str.contains(RETAIL_OFFER)
    A["m_ratio"] = A.bed.isin([0, 1]) & (A.ratio > 3)
    A["m_text_raw"] = A[
        ["t_retail", "t_storefront", "t_office", "t_per_sf", "t_warehouse"]
    ].any(axis=1)
    A["m_text"] = A[
        ["n_retail", "t_storefront", "n_office", "t_per_sf", "t_warehouse"]
    ].any(axis=1)
    A["m_short"] = A.short & A.has_record
    A["half"] = A.building.fillna("").map(half)
    A["any"] = A.m_ratio | A.m_text | A.m_short
    order = ["train", "live", "ledger", "rule"]
    marks = [
        "m_ratio",
        "m_text_raw",
        "m_text",
        "t_retail",
        "n_retail",
        "t_storefront",
        "t_office",
        "n_office",
        "t_per_sf",
        "t_warehouse",
        "m_short",
        "any",
    ]
    rows = []
    for m in marks:
        x = A[A[m]]
        r = {"mark": m, "all": len(x)}
        r.update(x.status.value_counts().reindex(order).fillna(0).astype(int).to_dict())
        r["train_bld"] = x.building[x.status == "train"].nunique()
        rows.append(r)
    pd.set_option("display.width", 200)
    print("ads", len(A), "with a record", int(A.has_record.sum()))
    print(pd.DataFrame(rows).to_string(index=False))
    print("\noverlaps among train rows")
    t = A[A.status == "train"]
    print(pd.crosstab([t.m_ratio, t.m_text], t.m_short))
    print("\nledger reasons of marked ads")
    for m in ("m_ratio", "m_text", "m_short"):
        print(m, A.ledger_reason[A[m]].value_counts().to_dict())
    print(
        "\nshort train rows by coded beds",
        t.bed[t.m_short].value_counts().sort_index().to_dict(),
    )
    print(
        "short train rows by text length",
        t.dlen[t.m_short].value_counts().sort_index().to_dict(),
    )
    print("ratio train rows by coded beds", t.bed[t.m_ratio].value_counts().to_dict())
    print("train rows by half", t.half.value_counts().to_dict())
    A.drop(columns=["desc"]).to_parquet(OUT / "marks.parquet")
