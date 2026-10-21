"""Age run checks: held-out ads by the building's training ads for truck, gym, retail and new buildings, and building levels d of truck and gym buildings by era, size, ad count and alteration, against the unit and gym runs."""

import json, numpy as np, pandas as pd

U = pd.read_parquet("/data1/apartments/tmp/bzu/sites_unit.parquet")
G = pd.read_parquet("/data1/apartments/tmp/bzu/sites_gym.parquet")
A = pd.read_parquet("sites_age.parquet")
n_train = U.groupby("building").n_train.sum()
tr = (
    pd.read_parquet(
        "/data1/apartments/external/unit-features/20261021-16cea7c/truck.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
    .truck_through
)
gy = (
    pd.read_parquet(
        "/data1/apartments/external/building-gym/20261021-752c7d3d/gym.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
    .gym
)
reg = (
    pd.read_parquet(
        "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
)
pl = pd.read_parquet(
    "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet",
    columns=["bbl", "yearbuilt", "yearalter1", "yearalter2", "unitsres", "numfloors"],
)
pl = pl.assign(bbl=pd.to_numeric(pl.bbl, errors="coerce")).dropna(subset=["bbl"])
pl["bbl"] = pl.bbl.astype("int64").astype(str)
for c in ("yearbuilt", "yearalter1", "yearalter2", "unitsres", "numfloors"):
    pl[c] = pd.to_numeric(pl[c], errors="coerce")
pl = pl.drop_duplicates("bbl").set_index("bbl")

out = {}
# 1. held-out ads by training ads per building
h = pd.read_parquet("heldout_rows.parquet")
h["n"] = h.building.astype(str).map(n_train).fillna(0)
h["bin"] = pd.cut(h.n, [-1, 0, 4, 19, np.inf], labels=["0", "1-4", "5-19", "20+"])
rows = []
for grp, m in (
    ("truck", h.truck),
    ("gym", h.gym),
    ("retail", h.retail),
    ("built 2000 on", h.new),
    ("all", h.truck | ~h.truck),
):
    for b in ["0", "1-4", "5-19", "20+"]:
        s = h[m & (h.bin == b)]
        if not len(s):
            continue
        d = s.age_elpd - s.gym_elpd
        du = s.age_elpd - s.unit_elpd
        rows.append(
            {
                "ads": grp,
                "train_ads": b,
                "n": len(s),
                "rmse_age": np.sqrt((s.age_err**2).mean()),
                "rmse_gym": np.sqrt((s.gym_err**2).mean()),
                "rmse_unit": np.sqrt((s.unit_err**2).mean()),
                "bias_age": s.age_err.mean(),
                "bias_gym": s.gym_err.mean(),
                "elpd_age_minus_gym": d.sum(),
                "se_gym": d.std() * np.sqrt(len(s)) if len(s) > 1 else np.nan,
                "elpd_age_minus_unit": du.sum(),
                "se_unit": du.std() * np.sqrt(len(s)) if len(s) > 1 else np.nan,
            }
        )
t1 = pd.DataFrame(rows)
out["heldout_by_train_ads"] = t1.round(5).to_dict("records")


# building tables
def attach(S):
    S = (
        S.groupby("building")
        .agg(
            d=("d", "mean"),
            d_var=("d_var", "mean"),
            F=("F", "mean"),
            n=("n_train", "sum"),
        )
        .reset_index()
    )
    S["truck"] = S.building.map(tr).fillna(0) == 1
    S["gym"] = S.building.map(gy).fillna(0) == 1
    bbl = (
        pd.to_numeric(S.building.map(reg.bbl), errors="coerce")
        .astype("Int64")
        .astype(str)
    )
    S["year"] = bbl.map(pl.yearbuilt)
    S["alter"] = np.fmax(
        bbl.map(pl.yearalter1).fillna(0), bbl.map(pl.yearalter2).fillna(0)
    )
    S["units"] = bbl.map(pl.unitsres)
    lat, lon = S.building.map(reg.latitude), S.building.map(reg.longitude)
    S["cell"] = (
        (np.floor(lon * 84300 / 500)).astype("Int64").astype(str)
        + ":"
        + (np.floor(lat * 110540 / 500)).astype("Int64").astype(str)
    )
    S["era"] = pd.cut(
        S.year,
        [0, 1899, 1939, 1979, 1999, 2009, 3000],
        labels=["<1900", "1900-39", "1940-79", "1980-99", "2000-09", "2010+"],
    ).astype(str)
    S["size"] = pd.cut(
        S.units, [-1, 5, 19, 99, np.inf], labels=["1-5 units", "6-19", "20-99", "100+"]
    ).astype(str)
    S["nbin"] = pd.cut(
        S.n, [0, 4, 19, 99, np.inf], labels=["1-4 ads", "5-19", "20-99", "100+"]
    ).astype(str)
    S["alt"] = np.where(
        S.alter >= 2000,
        "altered 2000+",
        np.where(S.alter > 0, "altered before 2000", "no alteration"),
    )
    return S


U, G, A = attach(U), attach(G), attach(A)


def table(S, flag, by, shift=0.0):
    cells = set(S.cell[S[flag]])
    ctl = S[~S[flag] & S.cell.isin(cells)]
    rows = []
    for k in sorted(S[by].dropna().unique()):
        a = S[S[flag] & (S[by] == k)]
        c = ctl[ctl[by] == k]
        if len(a) < 5:
            continue
        rows.append(
            {
                by: k,
                "bldgs": len(a),
                "ads": int(a.n.sum()),
                "d_bldg": a.d.mean() + shift,
                "d_ads": np.average(a.d, weights=a.n) + shift,
                "ctl_bldgs": len(c),
                "ctl_d_bldg": c.d.mean() if len(c) else np.nan,
                "ctl_d_ads": np.average(c.d, weights=c.n) if len(c) else np.nan,
            }
        )
    a = S[S[flag]]
    rows.append(
        {
            by: "all",
            "bldgs": len(a),
            "ads": int(a.n.sum()),
            "d_bldg": a.d.mean() + shift,
            "d_ads": np.average(a.d, weights=a.n) + shift,
            "ctl_bldgs": len(ctl),
            "ctl_d_bldg": ctl.d.mean(),
            "ctl_d_ads": np.average(ctl.d, weights=ctl.n),
        }
    )
    return pd.DataFrame(rows).round(4)


# 2. truck buildings: d in the age run against the unit run
for by in ("era", "size", "nbin", "alt"):
    a = table(A, "truck", by)
    u = table(U, "truck", by)
    a = a.merge(
        u[[by, "d_ads", "ctl_d_ads"]].rename(
            columns={"d_ads": "unit_d_ads", "ctl_d_ads": "unit_ctl_d_ads"}
        ),
        on=by,
        how="left",
    )
    out[f"truck_d_by_{by}"] = a.to_dict("records")
# 3. gym buildings: d in the age run against the gym run
for by in ("era", "size"):
    a = table(A, "gym", by)
    g = table(G, "gym", by)
    a = a.merge(
        g[[by, "d_ads", "ctl_d_ads"]].rename(
            columns={"d_ads": "gym_d_ads", "ctl_d_ads": "gym_ctl_d_ads"}
        ),
        on=by,
        how="left",
    )
    out[f"gym_d_by_{by}"] = a.to_dict("records")
out["coverage"] = {"truck_bldgs": int(A.truck.sum()), "gym_bldgs": int(A.gym.sum())}
json.dump(out, open("truckgym.json", "w"), indent=1, default=float)
for k, v in out.items():
    print("##", k)
    print(pd.DataFrame(v).to_string(index=False) if isinstance(v, list) else v)
