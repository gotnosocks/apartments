"""Look for the coded `months_free` in the other records of the listings where it disagrees
with `months_free_text`.

    python records.py

Takes the rows of L1's freetext copy where `months_free` is above zero and differs from
`months_free_text` by more than 0.1, and splits them by the latest description's offers:

- other offer: the coded value is one of the offers in the latest description, weeks at 4 to
  the month;
- up_to: the text keeps the upper end of an up-to offer;
- rest: neither.

For each listing it then reads every record in the records file, picks the latest as
`b0freetext` does, and prints, for each group, how often the coded value equals the latest
record's own `pricing.monthsFree`, another record's `pricing.monthsFree`, or an offer in another
record's description, and the groups of the rows coded 1 with text 2 and coded 2 with text 1. It
prints the same for the 39 reader-sample ads still in disagreement. Run it in a 3G scope.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0freetext as ft  # noqa: E402

SRC = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
OUT = SRC + "-freetext"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
RECORDS = "/data1/apartments/pipeline/datasets/records-086e22e48969b098.parquet"
SCRATCH = "/data1/apartments/tmp/sprint-20261113/free-months/"

rows = pd.read_parquet(
    OUT + "/rows.parquet", columns=["listing_id", "months_free_text", "free_text_kind"]
)
rows["lid"] = rows.listing_id.astype(str)
ads = pd.read_parquet(ADS, columns=["listing_id", "months_free"])
ads["lid"] = ads.listing_id.astype(str)
rows = rows.merge(ads[["lid", "months_free"]], on="lid", how="left")
dis = rows[
    (rows.months_free > 0)
    & rows.months_free_text.notna()
    & ((rows.months_free - rows.months_free_text).abs() > 0.1)
].set_index("lid")
print("disagreeing rows", len(dis))
ids = set(dis.index)

# Every record of those listings: time, monthsFree and the description's offers.
file = pq.ParquetFile(RECORDS)
records: dict[str, list[tuple]] = {}
for group in range(file.num_row_groups):
    head = file.read_row_group(
        group, columns=["listing_id", "collected_at", "last_collected_at"]
    )
    lid = [str(x) for x in head["listing_id"].to_pylist()]
    at = [
        max((t for t in ts if t is not None), default=None)
        for ts in zip(
            head["collected_at"].to_pylist(), head["last_collected_at"].to_pylist()
        )
    ]
    keep = [i in ids for i in lid]
    if not any(keep):
        continue
    raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
        pa.array(keep)
    )
    for (i, t), raw in zip(
        [(i, t) for i, t, k in zip(lid, at, keep) if k],
        raws["raw_listing_json"].to_pylist(),
    ):
        listing = json.loads(raw) if raw else {}
        field = (listing.get("pricing") or {}).get("monthsFree")
        text = str(listing.get("description") or "")
        offers = (
            [o.months for o in ft.statements(text)] if ft.PREFILTER.search(text) else []
        )
        records.setdefault(i, []).append((t, field, offers))
    del raws


def near(values, x):
    return any(v is not None and abs(float(v) - x) <= 0.1 for v in values)


out = []
for i, r in dis.iterrows():
    recs = records.get(i, [])
    # The latest record as b0freetext picks it: the first record with the latest time.
    timed = [k for k, rec in enumerate(recs) if rec[0] is not None]
    last = max(timed, key=lambda k: (recs[k][0], -k)) if timed else None
    others = [rec for k, rec in enumerate(recs) if k != last]
    latest = recs[last] if last is not None else (None, None, [])
    out.append(
        {
            "lid": i,
            "coded": round(r.months_free, 2),
            "text": round(r.months_free_text, 2),
            "records": len(recs),
            "other_offer": near(latest[2], r.months_free),
            "up_to": r.free_text_kind == "up_to",
            "latest_field": near([latest[1]], r.months_free),
            "other_field": near([o[1] for o in others], r.months_free),
            "other_text": any(near(o[2], r.months_free) for o in others),
        }
    )
res = pd.DataFrame(out).set_index("lid")
res["group"] = "rest"
res.loc[res.up_to & ~res.other_offer, "group"] = "up_to"
res.loc[res.other_offer, "group"] = "other offer"


def report(res, label):
    print(f"\n{label}: {len(res)} rows")
    for g, x in res.groupby("group"):
        print(
            f"  {g}: {len(x)}, with more than one record {int((x.records > 1).sum())}; "
            f"coded = latest record's monthsFree {int(x.latest_field.sum())}, "
            f"= another record's monthsFree {int(x.other_field.sum())}, "
            f"among another record's offers {int(x.other_text.sum())}, "
            f"in none of these {int((~x.latest_field & ~x.other_field & ~x.other_text).sum())}"
        )
    for c, t in ((1, 2), (2, 1)):
        x = res[(res.coded == c) & (res.text == t)]
        print(
            f"  coded {c}, text {t}: {len(x)}, by group {x.group.value_counts().to_dict()}"
        )


report(res, "disagreeing rows")
truth = pd.read_parquet(SCRATCH + "read_truth.parquet")
sample = set(truth.index[truth.set == "disagree"].astype(str))
report(res[res.index.isin(sample)], "reader sample, still disagreeing")
