"""The lister mark against the building's earlier ads of the same bedroom count (review).

Usage: xtab.py. Added in review of the note. For each held-out ad of the Deals backtest it
counts the building's earlier ads of the same bedroom count (any lister, any label), then
prints (1) two-group forms for first-ad units as in forms.py, with lister-free marks beside
the note's lister mark, and (2) the scale factor of the quiet and busy first ads by that
count. Counts read only ads opened before the ad's first day, and no ask.

These forms were written with both halves of the buildings in view, like the note's own.
"""

import duckdb
import numpy as np
import pandas as pd
from common import OUT, half
from scipy.stats import t as student

G = "/data1/apartments/tmp/outlier-sprint/s2/G"
DF = 7  # heldout.py's match to the stored log density of crj
SAME = "p.bedrooms = b.bedrooms"
CLOSED = "p.off_day between b.on_day - 30 and b.on_day"

c = duckdb.connect()
c.execute(f"set memory_limit='1500MB'; set threads=3; set temp_directory='{OUT}/tmp'")
c.execute(f"attach '{G}/work/w.duckdb' as g (read_only)")
x = c.execute(f"""
    with t as (select listing_id, d from read_parquet('{OUT}/inputs.parquet') where held),
    b as (
      select t.listing_id, t.d, a.on_day, a.building_id, a.bedrooms, a.lister, a.nlab
      from t join g.ads a on a.listing_id::varchar = t.listing_id)
    select b.listing_id, any_value(b.on_day <> b.d) day_differs,
      count(p.listing_id) filter (where {SAME}) bb_ads,
      count(p.listing_id) filter (where {SAME} and {CLOSED}) bb_closed30,
      count(p.listing_id) filter (where {SAME} and {CLOSED} and p.nlab <> b.nlab) bb_other30,
      count(p.listing_id) filter (where {SAME} and p.on_day >= b.on_day - 365) bb_open365,
      count(p.listing_id) filter (where {CLOSED}) b_closed30
    from b left join g.ads p
      on p.building_id = b.building_id and p.on_day < b.on_day
     and p.listing_id::varchar <> b.listing_id
    group by 1""").df()
h = pd.read_parquet(f"{OUT}/scores-crj.parquet")
t = pd.read_parquet(f"{OUT}/inputs.parquet")
h = h.merge(t[t.held], on="listing_id", validate="1:1", suffixes=("", "_t"))
h = h.merge(x, on="listing_id", validate="1:1")
h["half"] = half(h.building)
res = (h.y - h.pred).to_numpy()
s = ((h.q750 - h.q250) / (2 * student.ppf(0.75, DF))).to_numpy()
MS = np.round(np.arange(0.5, 3.001, 0.01), 2)
ll = np.stack([student.logpdf(res / (s * m), DF) - np.log(s * m) for m in MS], 1)
ll -= ll[:, [np.flatnonzero(MS == 1.0)[0]]]
first, hf, bld = h.no_unit.to_numpy(), h.half.to_numpy(), h.building.to_numpy()
cdf = h.cdf.to_numpy()
quiet = ~(h.gap_same <= 30).fillna(False).to_numpy()
bb = h.bb_ads.to_numpy()


def cse(per, idx):
    g = pd.Series(per).groupby(bld[idx]).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


def form(name, busy):
    """Two factors for first-ad units, fitted on one half and scored on the other."""
    pick = {}
    for f in (0, 1):
        q = np.flatnonzero(first & ~busy & (hf == f))
        b = np.flatnonzero(first & busy & (hf == f))
        pick[f] = (ll[q].sum(0).argmax(), ll[b].sum(0).argmax(), q, b)
    for f in (0, 1):
        jq, jb, q, b = pick[f]
        oq, ob = pick[1 - f][:2]
        per = np.concatenate([ll[q, oq], ll[b, ob]])
        ins = ll[q, jq].sum() + ll[b, jb].sum()
        print(
            f"{name:36} h{f} {len(q):5} {MS[jq]:.2f} {MS[jb]:.2f} {ins:6.1f}"
            f" {per.sum():6.1f} ({cse(per, np.concatenate([q, b])):4.1f})"
        )


def line(name, mask):
    for f in (0, 1):
        i = np.flatnonzero(mask & (hf == f))
        if len(i) < 30:
            print(f"{name:36} h{f} {len(i):5} too few")
            continue
        cover = 100 * ((cdf[i] > 0.1) & (cdf[i] < 0.9)).mean()
        print(
            f"{name:36} h{f} {len(i):5} {len(set(bld[i])):5}"
            f" {MS[ll[i].sum(0).argmax()]:.2f} {cover:5.1f}"
        )


print("held-out ads", len(h), "first-ad", int(first.sum()))
print("ads whose table first day differs from the input's:", int(h.day_differs.sum()))
print("same beds = the building's earlier ads of the same bedroom count, any lister")
print("FORMS for first-ad units. Marked = the ads the form does not call busy.")
print("columns: busy form, half, marked ads, m marked, m busy, gain inside the half,")
print("gain with the other half's factors (SE)")
form("note: lister closed same counts 30d", ~quiet)
form("same beds closed 30d", (h.bb_closed30 > 0).to_numpy())
form("same beds closed 30d, other label", (h.bb_other30 > 0).to_numpy())
form("building closed any ad 30d", (h.b_closed30 > 0).to_numpy())
form("same beds opened in 365d", (h.bb_open365 > 0).to_numpy())
form("same beds 1+", bb >= 1)
form("same beds 5+", bb >= 5)
form("same beds 20+", bb >= 20)
print("CROSS-TAB of first-ad units: the note's mark by same beds")
print("columns: group, half, ads, buildings, m, 80% cover")
for qn, qm in (("quiet", quiet), ("busy", ~quiet)):
    for bn, bm in (
        ("0", bb == 0),
        ("1-4", (bb >= 1) & (bb < 5)),
        ("5-19", (bb >= 5) & (bb < 20)),
        ("20+", bb >= 20),
        ("under 20", bb < 20),
        ("none opened 365d", (h.bb_open365 == 0).to_numpy()),
        ("some opened 365d", (h.bb_open365 > 0).to_numpy()),
    ):
        line(f"{qn}, same beds {bn}", first & qm & bm)
