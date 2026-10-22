"""Compare a location fit with the floor base fit and write summary.json.

python loc_summary.py NEW_RUN OUT_JSON
"""

import json
import os
import sys

import numpy as np

R = "/data1/apartments/frontier/runs/"
BASE = R + "building-zones-floor-b0-latest-6b5a5b4a-dense-w1000"
NEW = R + sys.argv[1]
OUT = sys.argv[2]


def load(p):
    z = np.load(p + "/posterior.npz")
    return z, [str(x) for x in z["names"]]


za, na = load(BASE)
zb, nb = load(NEW)


def term(z, i):
    b = z["kept/beta"][..., i] * 100
    return {
        "median": round(float(np.median(b)), 3),
        "q05": round(float(np.percentile(b, 5)), 3),
        "q95": round(float(np.percentile(b, 95)), 3),
        "chains": [round(float(np.median(c)), 3) for c in b],
    }


terms = []
for i, n in enumerate(nb):
    t = {"term": n, "new_fit": term(zb, i)}
    if n in na:
        t["floor_fit"] = term(za, na.index(n))
    terms.append(t)


def hyp(z, k):
    v = z["kept/" + k]
    return np.round(np.median(v.reshape(-1, *v.shape[2:]), 0), 4).tolist()


res = json.load(open(NEW + "/result.json"))
out = {
    "units": "log rent x100",
    "floor_fit": BASE.split("/")[-1],
    "new_fit": NEW.split("/")[-1],
    "seconds": res.get("seconds"),
    "diagnostics": {k: v for k, v in res["diagnostics"].items() if k != "per_quantity"},
    "hyper": {
        k: {"floor": hyp(za, k), "new": hyp(zb, k)}
        for k in ("bld_sd", "amp", "gp_ls", "tau", "nu")
    },
    "terms": terms,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w"), separators=(",", ":"))

print("diagnostics", out["diagnostics"])
for k, v in out["hyper"].items():
    print(k, v)
for t in terms:
    if "floor_fit" not in t:
        print("NEW", t["term"], t["new_fit"])
d = sorted(
    (
        (t["term"], t["new_fit"]["median"] - t["floor_fit"]["median"])
        for t in terms
        if "floor_fit" in t
    ),
    key=lambda x: -abs(x[1]),
)
print("largest moves", [(n, round(x, 2)) for n, x in d[:12]])
print(
    "unit premiums",
    [
        (n, round(x, 2))
        for n, x in d
        if n
        in (
            "unit:log_size_rel",
            "unit:laundry_in_unit",
            "unit:laundry_in_building",
            "unit:dishwasher",
            "unit:size_unknown",
        )
    ],
)
