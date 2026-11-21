"""Question 2: size the pattern on the history.

Rows: training rows of the live Deals run coded 0 bed that no active ledger entry names
(`z2_marks.py`). Forms of the mark, each read from counts and text only:
- `T`: the text states a size of 2 or more for the unit itself, by `rentfrontier.b0bedtext`
  (`bed_text_more` and `bed_text` >= 2: every own stated size above 0, none flex, no list of
  other units' sizes);
- `U_strict`: the unit has other ads with a typed count, and every one of them codes 2 or more;
- `U_clean`: some other ad of the unit codes 2 or more and none codes 1 (other zeros allowed);
- `U_any`: some other ad of the unit codes 2 or more.
The mark of the TODO is `T` or `U_any`. For marked rows I read the latest record's lister,
room count and description from the live build's records file, for the counts by lister
and for the reads. The 2026-11-12 class and decision of each row come from
`outlier-sprint/s2/Z`.
"""

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUT = Path("/data1/apartments/tmp/zero-bed")
REC = "/data1/apartments/pipeline/datasets/records-941f4a6588cbd8cc.parquet"
Z1112 = Path("/data1/apartments/tmp/outlier-sprint/s2/Z")
HERE = Path(__file__).resolve().parent


def records(ids: set[str]) -> pd.DataFrame:
    """Lister, room count and description of the latest record of each listing in `ids`."""
    seen = {}
    f = pq.ParquetFile(REC)
    for g in range(f.num_row_groups):
        h = f.read_row_group(g, columns=["listing_id", "collected_at"])
        lid = [str(x) for x in h["listing_id"].to_pylist()]
        at = h["collected_at"].to_pylist()
        keep = [i in ids and (i not in seen or seen[i][0] < t) for i, t in zip(lid, at)]
        if not any(keep):
            continue
        raws = f.read_row_group(g, columns=["raw_listing_json"]).filter(pa.array(keep))
        sel = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), raw in zip(sel, raws["raw_listing_json"].to_pylist()):
            if i in seen and seen[i][0] >= t:
                continue
            j = json.loads(raw) if raw else {}
            p = j.get("propertyDetails") or {}
            seen[i] = (
                t,
                (j.get("legacy") or {}).get("sourceGroupLabel"),
                p.get("roomCount"),
                p.get("fullBathroomCount"),
                p.get("livingAreaSize"),
                (p.get("address") or {}).get("displayUnit"),
                str(j.get("description") or ""),
            )
        del raws
    cols = ["at", "lister", "rooms", "rec_full", "rec_size", "label", "desc"]
    return pd.DataFrame(
        [(i, *v) for i, v in seen.items()], columns=["listing_id", *cols]
    )


def counts(g: pd.DataFrame) -> dict:
    return dict(
        rows=len(g),
        units=g.unit_id.nunique(),
        buildings=g.building.nunique(),
        listers=g.lister.nunique(),
        half_A=int((g.half == "A").sum()),
        half_B=int((g.half == "B").sum()),
    )


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    Z = pd.read_parquet(OUT / "zeros.parquet")
    t = Z[Z.train & ~Z.in_ledger].copy()
    t["U_strict"] = (t.u2 > 0) & (t.u1 == 0) & (t.u0 == 0)
    t["mark"] = t["T"] | t.U_any
    print(
        "training rows coded 0 bed, no ledger entry",
        len(t),
        "marked",
        int(t.mark.sum()),
    )
    m = t[t.mark].copy()
    R = records(set(m.listing_id))
    print("records read", len(R))
    R.to_parquet(OUT / "marked_records.parquet")
    m = m.merge(R.drop(columns=["desc"]), on="listing_id", how="left")
    K = pd.read_parquet(Z1112 / "classes.parquet", columns=["listing_id", "cls"])
    K["listing_id"] = K.listing_id.astype(str)
    F = pd.read_parquet(
        Z1112 / "decisions_final.parquet", columns=["listing_id", "g", "act", "u_fail"]
    )
    F["listing_id"] = F.listing_id.astype(str)
    m = m.merge(K, on="listing_id", how="left").merge(F, on="listing_id", how="left")
    m["stratum"] = [
        "text and unit"
        if a and b
        else "text only"
        if a
        else "unit, all 2+"
        if c
        else "unit, mixed"
        for a, b, c in zip(m["T"], m.U_any, m.U_strict)
    ]
    m.to_parquet(OUT / "marked.parquet")
    forms = {
        "T": m["T"],
        "U_strict": m.U_strict,
        "U_clean": m.U_clean,
        "U_any": m.U_any,
        "T or U_any (the mark)": m.mark,
        "T and U_any": m["T"] & m.U_any,
        "T or U_strict": m["T"] | m.U_strict,
    }
    out = pd.DataFrame({k: counts(m[v]) for k, v in forms.items()}).T
    print("\ncounts by form\n" + out.to_string())
    print(
        "\nstrata\n"
        + pd.DataFrame({s: counts(g) for s, g in m.groupby("stratum")}).T.to_string()
    )
    print("\ntop listers of the mark")
    print(m.lister.value_counts().head(12).to_string())
    print("\ntop listers of T or U_strict")
    print(m[m["T"] | m.U_strict].lister.value_counts().head(8).to_string())
    print(
        "\nunit's other ads coded 2+ (U_any): distinct counts",
        m[m.U_any].u2_kinds.value_counts().sort_index().to_dict(),
    )
    print("lowest such count", m[m.U_any].u2_min.value_counts().sort_index().to_dict())
    print("\n2026-11-12 class of marked rows")
    print(m.cls.value_counts(dropna=False).to_string())
    print("\n2026-11-12 decision group / act / page fail")
    print(m.groupby(["g", "act", "u_fail"], dropna=False).size().to_string())
    print(
        "\nfirst year",
        pd.to_datetime(m.first_day).dt.year.value_counts().sort_index().to_dict(),
    )
    print(
        "rooms",
        pd.to_numeric(m.rooms, errors="coerce")
        .clip(upper=6)
        .value_counts(dropna=False)
        .sort_index()
        .to_dict(),
    )
    r53 = pd.read_parquet(OUT / "rows165.parquet")
    r53 = set(r53.listing_id[r53.cite])
    print(
        "\nthe ratio read's 53 among the mark",
        len(r53 & set(m.listing_id)),
        "T",
        len(r53 & set(m.listing_id[m["T"]])),
        "U_any",
        len(r53 & set(m.listing_id[m.U_any])),
    )
