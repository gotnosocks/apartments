import numpy as np, json

R = "/data1/apartments/frontier/runs/"
A = R + "building-zones-floor-b0-latest-6b5a5b4a-dense-w1000"
B = R + "building-zones-mundlak-b0-latest-a6d25054-dense-w1000"


def load(p):
    z = np.load(p + "/posterior.npz")
    n = [str(x) for x in z["names"]]
    return z, n


za, na = load(A)
zb, nb = load(B)


def term(z, n, i):
    b = z["kept/beta"][..., i] * 100
    return {
        "median": round(float(np.median(b)), 3),
        "q05": round(float(np.percentile(b, 5)), 3),
        "q95": round(float(np.percentile(b, 95)), 3),
        "chains": [round(float(np.median(c)), 3) for c in b],
    }


terms = []
for i, n in enumerate(nb):
    t = {"term": n, "means_fit": term(zb, nb, i)}
    if n in na:
        t["floor_fit"] = term(za, na, na.index(n))
    terms.append(t)


def hyp(z, k):
    return np.round(
        np.median(z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:]), 0), 4
    ).tolist()


out = {
    "units": "log rent x100",
    "floor_fit": A.split("/")[-1],
    "means_fit": B.split("/")[-1],
    "diagnostics": {
        k: v
        for k, v in json.load(open(B + "/result.json"))["diagnostics"].items()
        if k != "per_quantity"
    },
    "hyper": {
        k: {"floor": hyp(za, k), "means": hyp(zb, k)}
        for k in ("bld_sd", "amp", "gp_ls", "tau", "nu")
    },
    "terms": terms,
}
p = "/home/ben/code/apartments/.claude/worktrees/bridge-cse_01CgsaUKWt6aj17QQgLXDbAJ/docs/notes/building-zones-mundlak-real-2026-10-22/summary.json"
import os

os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(out, open(p, "w"), separators=(",", ":"))
d = [
    (t["term"], t["means_fit"]["median"] - t["floor_fit"]["median"])
    for t in terms
    if "floor_fit" in t
]
cur = [x for x in d if x[0].startswith(("unit:elev_f", "unit:walkup_f"))]
print(
    "curve max abs",
    max(cur, key=lambda x: abs(x[1])),
    "elev range",
    min(x[1] for x in cur if "elev" in x[0]),
    max(x[1] for x in cur if "elev" in x[0]),
)
oth = [x for x in d if not x[0].startswith(("bld:", "unit:"))]
print("other max", sorted(oth, key=lambda x: -abs(x[1]))[:4])
