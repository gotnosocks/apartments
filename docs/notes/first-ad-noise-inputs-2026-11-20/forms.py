"""Forms of the lister's turnover in the building as a two-group scale factor.

Usage: forms.py TAG. A form marks an ad `busy` from rows before its first day. For each
form the factors of the busy and quiet first-ad ads are fitted on one half of the buildings
and scored on the other, as in heldout.py. The form is picked by the gain inside half 0,
but the list of forms was written with both halves in view, since both are printed.
"""

import sys

import numpy as np
import pandas as pd
from common import OUT, half
from scipy.stats import norm
from scipy.stats import t as student

h = pd.read_parquet(f"{OUT}/scores-{sys.argv[1]}.parquet")
t = pd.read_parquet(f"{OUT}/inputs.parquet")
h = h.merge(t[t.held], on="listing_id", validate="1:1", suffixes=("", "_t"))
h["half"] = half(h.building)
res = (h.y - h.pred).to_numpy()
iqr = (h.q750 - h.q250).to_numpy()
df = {"crj": 7, "l2j": 4}[sys.argv[1]]  # heldout.py's match to the stored log density
s = iqr / (2 * student.ppf(0.75, df))
MS = np.round(np.arange(0.5, 3.001, 0.01), 2)
ll = np.stack([student.logpdf(res / (s * m), df) - np.log(s * m) for m in MS], 1)
ll -= ll[:, [np.flatnonzero(MS == 1.0)[0]]]
first, hf, bld = h.no_unit.to_numpy(), h.half.to_numpy(), h.building.to_numpy()
FORMS = {
    "same counts, 7 days": h.gap_same <= 7,
    "same counts, 30 days": h.gap_same <= 30,
    "any counts, 7 days": h.gap_any <= 7,
    "any counts, 30 days": h.gap_any <= 30,
    "lister ad here, 90 days": h.lb_90 >= 1,
    "lister ads here 1+": h.lb_ads >= 1,
    "lister ads here 5+": h.lb_ads >= 5,
    "lister ads here 20+": h.lb_ads >= 20,
    "building ads 5+": h.b_ads >= 5,
    "building ads 20+": h.b_ads >= 20,
}
FORMS = {k: v.fillna(False).to_numpy(bool) for k, v in FORMS.items()}


def best(idx):
    tot = ll[idx].sum(0)
    return int(tot.argmax()), float(tot.max())


def cover(idx, m, p):
    return 100 * (np.abs(res[idx]) < s[idx] * m * student.ppf(0.5 + p / 2, df)).mean()


def cse(per, idx):
    g = pd.Series(per).groupby(bld[idx]).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


print(sys.argv[1], "first-ad held-out ads", int(first.sum()))
print("columns: form, half, quiet ads, m quiet, m busy, gain inside the half,")
print("gain with the other half's factors (SE), 80% and 95% cover of quiet ads then")
inside = {}
for name, busy in FORMS.items():
    pick = {}
    for f in (0, 1):
        q = np.flatnonzero(first & ~busy & (hf == f))
        b = np.flatnonzero(first & busy & (hf == f))
        pick[f] = (best(q), best(b), q, b)
    inside[name] = pick[0][0][1] + pick[0][1][1]
    for f in (0, 1):
        (jq, gq), (jb, gb), q, b = pick[f]
        (oq, _), (ob, _), _, _ = pick[1 - f]
        idx = np.concatenate([q, b])
        per = np.concatenate([ll[q, oq], ll[b, ob]])
        print(
            f"{name:24} h{f} {len(q):5} {MS[jq]:.2f} {MS[jb]:.2f} {gq + gb:6.1f}"
            f" {per.sum():6.1f} ({cse(per, idx):4.1f})"
            f" {cover(q, MS[oq], 0.8):5.1f} {cover(q, MS[oq], 0.95):5.1f}"
        )
name = max(inside, key=inside.get)
print("picked on half 0:", name)
busy = FORMS[name]
print("the picked form in other groups: ads, buildings, sd z, 80% cover, m")
z = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6).to_numpy())
c = h.cdf.to_numpy()
for label, mask in (
    ("earlier ad, quiet", ~first & ~busy),
    ("earlier ad, busy", ~first & busy),
    ("first-ad, quiet", first & ~busy),
    ("first-ad, busy", first & busy),
    ("first-ad, quiet, building ads 20+", first & ~busy & (h.b_ads >= 20).to_numpy()),
    ("first-ad, quiet, building ads < 20", first & ~busy & (h.b_ads < 20).to_numpy()),
    ("first-ad, busy, building ads 100+", first & busy & (h.b_ads >= 100).to_numpy()),
    ("first-ad, busy, building ads < 100", first & busy & (h.b_ads < 100).to_numpy()),
):
    for f in (0, 1):
        i = np.flatnonzero(mask & (hf == f))
        j, _ = best(i)
        print(
            f"{label:36} h{f} {len(i):5} {len(set(bld[i])):5} {z[i].std():.2f}"
            f" {100 * ((c[i] > 0.1) & (c[i] < 0.9)).mean():5.1f} {MS[j]:.2f}"
        )
