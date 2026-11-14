"""Score the reader labels of the 350 sampled ads against `rentfrontier.b0freetext`.

    python score.py

compare.py --samples drew the ads from the first build and wrote them, with that build's
values and the coded `months_free`, to SCRATCH. Sonnet readers wrote one `label_*.json`
per batch. This script parses each ad's text again with the module as it stands, and prints,
for the first build's values (v1) and the current parse (now):

- found: ads with a text value and no coded value; the share the readers also read as a
  rent offer above zero, and the share whose value agrees within 0.1;
- missed: ads with no value whose text has "free", "concession" or "net effective"; the
  ones the readers give a count;
- disagree: ads where the text value and the coded value differ by more than 0.1; the side
  the readers agree with;
- basis: `ask_basis` of each text against the readers' price basis, on all 350 ads;
- check: the second reading, of the ads whose text leaves the unit out of the building's
  offer and of 40 ads marked gross, drawn by compare.py --check from the current build.

The readers converted weeks at 12/52 of a month, as the first build did. The current parse
counts 4 weeks to the month, so before comparing with it the script rescales a reader value
by 13/12 when the value is a whole count of weeks at 12/52 and not a whole or half month.
"""

import glob
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0freetext as ft  # noqa: E402

SCRATCH = "/data1/apartments/tmp/sprint-20261113/free-months/"
truth = pd.read_parquet(SCRATCH + "read_truth.parquet")
truth.index = truth.index.astype(str)
texts, labels = {}, []
for p in sorted(glob.glob(SCRATCH + "read_[dfm]*.json")):
    texts |= {str(o["id"]): o["text"] for o in json.load(open(p))}
for p in sorted(glob.glob(SCRATCH + "label_[dfm]*.json")):
    labels += json.load(open(p))
lab = pd.DataFrame(labels)
lab.index = lab["id"].astype(str)
df = truth.join(lab[["months", "lease", "kind", "all_months", "price"]], how="inner")


def at_four(x):
    """A reader value in weeks at 12/52, as weeks at 4 to the month."""
    x = float(x)
    if x != x:
        return x
    weeks = x * 52 / 12
    whole_weeks = abs(weeks - round(weeks)) < 0.01
    return round(weeks) / 4 if whole_weeks and abs(x * 2 - round(x * 2)) > 0.01 else x


df["reader_v1"] = pd.to_numeric(df.months, errors="coerce")
df["reader"] = df.reader_v1.map(at_four)
df["reader_weeks"] = (df.reader - df.reader_v1).abs() > 0.001
df["reader_lease"] = pd.to_numeric(df.lease, errors="coerce")


def current(text):
    offers = ft.statements(text) if ft.PREFILTER.search(text) else []
    return (*ft.parse(text, offers)[:3], ft.ask_basis(text, offers))


now = pd.DataFrame(
    [current(texts[i]) for i in df.index],
    index=df.index,
    columns=["now", "now_lease", "now_kind", "now_basis"],
)
df = df.join(now).rename(
    columns={
        "months_free_text": "v1",
        "free_lease_months": "v1_lease",
        "free_text_kind": "v1_kind",
    }
)
print("ads labelled", len(df), df.set.value_counts().to_dict())
print("reader values in weeks, rescaled:", int(df.reader_weeks.sum()))


def close(a, b):
    return (a - b).abs() <= 0.1


f = df[df.set == "found"]
print(
    f"\nfound ({len(f)}): reader reads a rent offer above zero on {int((f.reader > 0).sum())}"
)
for v, reader in (("v1", f.reader_v1), ("now", f.reader)):
    agree = close(reader, f[v])
    print(
        f"  {v}: value > 0 on {int((f[v] > 0).sum())}, agrees with the reader within 0.1 "
        f"on {int(agree.sum())}, kind agrees on {int((f[v + '_kind'] == f.kind).sum())}"
    )
    leases = f[f.reader_lease.notna() & f[v + "_lease"].notna()]
    print(
        f"  {v}: lease stated by both {len(leases)}, equal "
        f"{int((leases.reader_lease == leases[v + '_lease']).sum())}"
    )
print("  reader kind by current kind:\n", pd.crosstab(f.now_kind, f.kind.fillna("-")))
pd.set_option("display.width", 200)
cols = ["v1", "now", "now_kind", "reader", "kind"]
print(f[~close(f.reader, f.now)][cols])

m = df[df.set == "missed"]
print(f"\nmissed ({len(m)}): reader kinds", m.kind.fillna("-").value_counts().to_dict())
print(
    m[(m.reader > 0) | m.now.notna()][["v1_kind", "now", "now_kind", "reader", "kind"]]
)

d = df[df.set == "disagree"]
print(f"\ndisagree ({len(d)}):")
for v, reader in (("v1", d.reader_v1), ("now", d.reader)):
    rt, rc = close(reader, d[v]), close(reader, d.months_free)
    print(
        f"  {v}: reader = text {int(rt.sum())}, reader = coded {int(rc.sum())}, "
        f"neither {int((~rt & ~rc).sum())}, text = coded {int(close(d[v], d.months_free).sum())}"
    )
coded_in = d.apply(
    lambda r: any(abs(at_four(x) - r.months_free) <= 0.1 for x in (r.all_months or [])),
    axis=1,
)
print("  coded value among the reader's offers:", int(coded_in.sum()))
w = d[d.reader_weeks]
print(
    f"  week offers: {len(w)}, coded = weeks / 4 on {int(close(w.months_free, w.reader).sum())}, "
    f"current value = coded on {int(close(w.now, w.months_free).sum())}"
)
print(
    d[
        [
            "months_free",
            "lease_term",
            "v1",
            "now",
            "now_lease",
            "reader",
            "reader_lease",
            "kind",
        ]
    ]
)

print("\nbasis, all ads: reader price basis by ask_basis")
b = df.assign(reader_basis=df.price.fillna("-"), basis=df.now_basis.fillna("-"))
print(pd.crosstab(b.basis, b.reader_basis, margins=True))
stated = b[b.basis != "-"]
print(
    f"  ask_basis stated on {len(stated)}, reader agrees on "
    f"{int((stated.basis == stated.reader_basis).sum())}"
)
print(b[(b.basis != b.reader_basis)][["set", "basis", "reader_basis"]])

# The second reading. Its readers converted weeks at 4 to the month.
check = {}
for p in sorted(glob.glob(SCRATCH + "read_check_*.json")):
    check |= {str(o["id"]): o["text"] for o in json.load(open(p))}
lab = pd.DataFrame(
    [
        x
        for p in sorted(glob.glob(SCRATCH + "label_check_*.json"))
        for x in json.load(open(p))
    ]
)
lab.index = lab["id"].astype(str)
lab = lab.join(
    pd.DataFrame(
        [current(check[i]) for i in lab.index],
        index=lab.index,
        columns=["now", "now_lease", "now_kind", "now_basis"],
    )
)
out = lab[[ft.UNIT_EXCLUDED.search(check[i]) is not None for i in lab.index]]
print(f"\ncheck, unit left out ({len(out)}):")
print(out[["months", "unit_excluded", "now", "now_kind", "price", "now_basis"]])
g = lab.drop(out.index)
reader = pd.to_numeric(g.months)
print(
    f"check, marked gross ({len(g)}): reader price",
    g.price.fillna("-").value_counts().to_dict(),
)
print(
    f"  reader months > 0 on {int((reader > 0).sum())}, parse > 0 on {int((g.now > 0).sum())}, "
    f"agree within 0.1 on {int(close(reader, g.now).sum())}"
)
print(g[g.price != "gross"][["months", "now", "price", "quote"]].to_string())
