"""T variance, each column group's contribution and Shapley rises, and the truck check on training ads (age run minus gym and unit runs)."""

import itertools, json
import numpy as np, pandas as pd
from rentfrontier import (
    b0,
    splits,
    building_zones_age as bzs,
    building_zones_unit as bzu,
)
from common import RUNS, DATASET, AGE

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
z = np.load(RUNS + AGE + "/posterior.npz")
names = [str(n) for n in z["names"]]
t = bzs.subset(bzs.design(frame), ~held)
assert list(t.names) == names
beta = z["kept/beta"].reshape(-1, len(names)).mean(0)
res = pd.read_parquet("resid_age.parquet")
zone = res.zone.to_numpy()
T0 = (res.r + res.bld + res.F).to_numpy()
G = {
    "size": ["unit:log_size_rel", "unit:size_imputed", "unit:size_unknown"],
    "laundry": ["unit:laundry_in_unit", "unit:laundry_in_building"],
    "dishwasher": ["unit:dishwasher"],
    "gym": ["bld:gym"],
    "truck": ["bld:truck_through"],
    "era": [n for n in names if n.startswith("bld:built_")],
    "altered": ["bld:altered_2000_on"],
    "retail": ["bld:retail", "bld:retail_unknown"],
}
G = {g: [n for n in cols if n in names] for g, cols in G.items()}
c = {
    g: t.x[:, [names.index(n) for n in cols]] @ beta[[names.index(n) for n in cols]]
    for g, cols in G.items()
}


def zvar(v):
    v = v - pd.Series(v).groupby(zone).transform("mean").to_numpy()
    return float(v.var()), {int(k): float(v[zone == k].var()) for k in (0, 1)}


base, base_z = zvar(T0)
out = {"T_age": base, "T_age_zone": base_z, "groups": {}}
for g, v in c.items():
    tot, bz_ = zvar(v)
    alone, alone_z = zvar(T0 + v)
    out["groups"][g] = {
        "contribution_var": tot,
        "contribution_var_zone": bz_,
        "rise_alone": alone - base,
        "rise_alone_zone": {k: alone_z[k] - base_z[k] for k in (0, 1)},
    }
gs = list(G)
cache = {}


def val(S):
    S = frozenset(S)
    if S not in cache:
        cache[S] = zvar(T0 + sum((c[g] for g in S), np.zeros_like(T0)))
    return cache[S]


for S in itertools.chain.from_iterable(
    itertools.combinations(gs, r) for r in range(len(gs) + 1)
):
    val(S)
perms = list(itertools.permutations(gs))
for k in ("all", 0, 1):
    sh = {g: 0.0 for g in gs}
    for p in perms:
        S = []
        for g in p:
            a, b = val(S), val(S + [g])
            sh[g] += ((b[0] - a[0]) if k == "all" else (b[1][k] - a[1][k])) / len(perms)
            S = S + [g]
    for g in gs:
        out["groups"][g][f"shapley_rise_{k}"] = sh[g]
out["T_all_added_back"] = val(gs)[0]
tr = (
    pd.read_parquet(bzu.SNAPSHOT / "truck.parquet")
    .drop_duplicates("building")
    .set_index("building")
    .truck_through
)
truck = frame.building[~held].astype(str).map(tr).fillna(0).to_numpy() == 1
for tag, f in (
    ("gym", "/data1/apartments/tmp/bzy/resid_gym.parquet"),
    ("unit", "/data1/apartments/tmp/bzu/resid_unit.parquet"),
):
    u = pd.read_parquet(f, columns=["mu", "bld", "F"])
    d = res.mu.to_numpy() - u.mu.to_numpy()
    out[f"truck_train_vs_{tag}"] = {
        "ads": int(truck.sum()),
        "pred_change_mean": float(d[truck].mean()),
        "pred_change_mean_abs": float(np.abs(d[truck]).mean()),
        "others_mean": float(d[~truck].mean()),
        "bld_change_mean": float((res.bld.to_numpy() - u.bld.to_numpy())[truck].mean()),
        "F_change_mean": float((res.F.to_numpy() - u.F.to_numpy())[truck].mean()),
    }
json.dump(out, open("contrib.json", "w"), indent=1)
print(json.dumps(out, indent=1))
