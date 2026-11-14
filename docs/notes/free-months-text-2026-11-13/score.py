"""Score the reader labels of the 350 sampled ads against `rentfrontier.b0freetext`.

    python score.py

compare.py --samples drew the ads from the first build and wrote them, with that build's
values and the coded `months_free`, to SCRATCH. Sonnet readers wrote one `label_*.json`
per batch. This script parses each ad's text again with the module as it stands, and prints,
for the first build's values (v1) and the current parse (v2):

- found: ads with a text value and no coded value; the share the readers also read as a
  rent offer above zero, and the share whose value agrees within 0.1;
- missed: ads with no value whose text has "free", "concession" or "net effective"; the
  ones the readers give a count;
- disagree: ads where the text value and the coded value differ by more than 0.1; the side
  the readers agree with.
"""

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0freetext as ft  # noqa: E402

SCRATCH = "/data1/apartments/tmp/sprint-20261113/free-months/"
truth = pd.read_parquet(SCRATCH + "read_truth.parquet")
truth.index = truth.index.astype(str)
texts, labels = {}, []
for p in sorted(glob.glob(SCRATCH + "read_*.json")):
    texts |= {str(o["id"]): o["text"] for o in json.load(open(p))}
for p in sorted(glob.glob(SCRATCH + "label_*.json")):
    labels += json.load(open(p))
lab = pd.DataFrame(labels)
lab.index = lab["id"].astype(str)
df = truth.join(lab[["months", "lease", "kind", "all_months", "price"]], how="inner")
df["reader"] = pd.to_numeric(df.months, errors="coerce")
df["reader_lease"] = pd.to_numeric(df.lease, errors="coerce")
v2 = pd.DataFrame(
    [ft.parse(texts[i])[:3] for i in df.index],
    index=df.index,
    columns=["v2", "v2_lease", "v2_kind"],
)
df = df.join(v2).rename(
    columns={
        "months_free_text": "v1",
        "free_lease_months": "v1_lease",
        "free_text_kind": "v1_kind",
    }
)
print("ads labelled", len(df), df.set.value_counts().to_dict())


def close(a, b):
    return (a - b).abs() <= 0.1


f = df[df.set == "found"]
print(
    f"\nfound ({len(f)}): reader reads a rent offer above zero on {int((f.reader > 0).sum())}"
)
for v in ("v1", "v2"):
    agree = close(f.reader, f[v])
    print(
        f"  {v}: value > 0 on {int((f[v] > 0).sum())}, agrees with the reader within 0.1 "
        f"on {int(agree.sum())}, kind agrees on {int((f[v + '_kind'] == f.kind).sum())}"
    )
    leases = f[f.reader_lease.notna() & f[v + "_lease"].notna()]
    print(
        f"  {v}: lease stated by both {len(leases)}, equal "
        f"{int((leases.reader_lease == leases[v + '_lease']).sum())}"
    )
print("  reader's price basis:", f.price.value_counts(dropna=False).to_dict())
print("  reader kind by v2 kind:\n", pd.crosstab(f.v2_kind, f.kind.fillna("-")))
pd.set_option("display.width", 200)
cols = ["v1", "v2", "v2_kind", "reader", "kind"]
print(f[~close(f.reader, f.v2)][cols])

m = df[df.set == "missed"]
print(f"\nmissed ({len(m)}): reader kinds", m.kind.fillna("-").value_counts().to_dict())
print(m[(m.reader > 0) | m.v2.notna()][["v1_kind", "v2", "v2_kind", "reader", "kind"]])

d = df[df.set == "disagree"]
print(f"\ndisagree ({len(d)}):")
for v in ("v1", "v2"):
    rt, rc = close(d.reader, d[v]), close(d.reader, d.months_free)
    print(
        f"  {v}: reader = text {int(rt.sum())}, reader = coded {int(rc.sum())}, "
        f"neither {int((~rt & ~rc).sum())}, text = coded {int(close(d[v], d.months_free).sum())}"
    )
coded_in = d.apply(
    lambda r: any(abs(float(x) - r.months_free) <= 0.1 for x in (r.all_months or [])),
    axis=1,
)
print("  coded value among the reader's offers:", int(coded_in.sum()))
weeks = d.v2 * ft.WEEKS_PER_MONTH
is_weeks = (np.abs(weeks - weeks.round()) < 0.01) & (
    np.abs(d.v2 * 2 - (d.v2 * 2).round()) > 0.01
)
print(
    f"  week offers: {int(is_weeks.sum())}, coded = weeks / 4 on "
    f"{int(close(d.months_free[is_weeks], weeks[is_weeks].round() / 4).sum())}"
)
print(
    d[
        [
            "months_free",
            "lease_term",
            "v1",
            "v2",
            "v2_lease",
            "reader",
            "reader_lease",
            "kind",
        ]
    ]
)
