"""Export draws-derived quantities of a building-zones-attrs run for a visual explainer.

Read-only: reads the run's posterior.npz, the dataset and the registries, writes OUT.

    python -I export.py SRC RUN OUT SPEC_MODULE
"""

import json
import math
import sys
from pathlib import Path

import importlib

sys.path.insert(0, sys.argv[1])
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from rentfrontier import b0, b0_4, building_zones, whitened_zones

spec = importlib.import_module(f"rentfrontier.{sys.argv[4]}")

RUNS = Path("/data1/apartments/frontier/runs")
RUN = RUNS / sys.argv[2]
PREV = RUNS / "building-zones-attrs-b0-latest-9bd8c1a3-dense-w650"
ATTRS = RUNS / "building-attrs-b0-latest-041e6aa9-dense-w1500"
UNIT = RUNS / "building-zones-unit-b0-latest-a3aec3ff-dense-w650"
GYM = RUNS / "building-zones-gym-b0-latest-f2d01c92-dense-w650"
OUT = Path(sys.argv[3])
ZNAME = ["manhattan", "outer"]


def sig(v, n=4):
    """Round to n significant digits, NaN to None, recursively over arrays."""
    a = np.asarray(v, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.where(a == 0, 0, np.floor(np.log10(np.abs(np.where(a == 0, 1, a)))))
        r = np.round(a / 10**mag, n - 1) * 10**mag
    r = np.where(np.isfinite(a), r, np.nan)
    out = r.tolist()
    return _clean(out)


def _clean(x):
    if isinstance(x, list):
        return [_clean(v) for v in x]
    if isinstance(x, float):
        if math.isnan(x):
            return None
        return float(f"{x:.4g}")
    return x


def coord(v):
    return [None if not np.isfinite(t) else round(float(t), 5) for t in np.asarray(v)]


def q(draws, axis=0):
    """Median and 5/95% quantiles."""
    return np.quantile(draws, [0.5, 0.05, 0.95], axis=axis)


def chain_spread(x):
    """x: (chains, draws, ...) -> max minus min of the chain medians."""
    m = np.median(x, axis=1)
    return m.max(0) - m.min(0)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


z = np.load(RUN / "posterior.npz")
kept = {k[5:]: z[k] for k in z.files if k.startswith("kept/")}
names = [str(n) for n in z["names"]]
heldout = z["heldout"]
C, D = kept["beta"].shape[:2]
log("draws", C, D)

frame = b0.load_frame(Path(json.loads((RUN / "result.json").read_text())["dataset"]))
assert len(frame) == len(heldout)
full = spec.design(frame)
train = spec.subset(full, ~heldout)
for s, r in zip(
    full.surfaces, json.loads((RUN / "result.json").read_text())["surfaces"]
):
    assert s["sites"] == r["sites"] and abs(s["angle"] - r["angle"]) < 1e-9, s["name"]
assert names == list(full.names)

# Building order and positions, as the design builds them.
reg = pd.read_parquet(
    whitened_zones.REGISTRY,
    columns=["building", "bbl", "latitude", "longitude", "label"],
)
njr = pd.read_parquet(
    whitened_zones.NJ_REGISTRY, columns=["building", "latitude", "longitude", "label"]
)
sites = whitened_zones.sites_of(
    frame,
    reg[["building", "bbl", "latitude", "longitude"]],
    njr[["building", "latitude", "longitude"]],
)
order = pd.concat([sites[sites.zone == k] for k in range(len(ZNAME))])
S = len(order)
assert S == kept["bld"].shape[-1]
bid = order.index.to_numpy()
bx, by = order.x.to_numpy(float), order.y.to_numpy(float)
blat = by / b0_4.KM_PER_LAT + b0_4.LAT0
blon = bx / b0_4.KM_PER_LON + b0_4.LON0
bzone = building_zones.site_zone(full)
label = pd.concat(
    [
        reg.drop_duplicates("building").set_index("building").label,
        njr.drop_duplicates("building").set_index("building").label,
    ]
)
label = label[~label.index.duplicated()]
nbhd = frame.groupby("building").neighbourhood.agg(lambda s: s.value_counts().index[0])
n_train = np.bincount(train.site, minlength=S)
n_all = np.bincount(full.site, minlength=S)

# Surface F at buildings per draw (training share centring, as in the fit).
F = whitened_zones.surface_draws(train, kept)  # (C, D, S)
share = whitened_zones.site_share(train)
w = kept["gp_w"]
# The centring constant per draw: share-weighted mean of the uncentred surface.
parts, at = [], 0
for s in train.surfaces:
    nb = s["basis"].shape[1]
    parts.append(w[..., at : at + nb] @ s["basis"].T)
    at += nb
const = np.concatenate(parts, axis=-1) @ share  # (C, D)
bld = kept["bld"].astype(float)  # d = eta - F - x_s gamma
GN = [n for n in names if n.startswith("bld:")]
GJ = [names.index(n) for n in GN]
first_row = np.full(S, -1)
first_row[full.site[::-1]] = np.arange(len(full.site))[::-1]
xs = np.where(first_row[:, None] >= 0, full.x[np.maximum(first_row, 0)][:, GJ], np.nan)
attr_draws = kept["beta"][..., GJ].astype(float)  # (C, D, G)
A_med = xs @ np.median(attr_draws.reshape(-1, len(GJ)), 0)
log("F, d ready")


def basis_at(s, x, y):
    t = math.radians(s["angle"])
    u = x * math.cos(t) - y * math.sin(t)
    v = x * math.sin(t) + y * math.cos(t)
    (cu, cv), (Lu, Lv), (mu_, mv) = s["centre_km"], s["half_width_km"], s["waves"]
    u = np.clip(u - cu, -Lu, Lu)
    v = np.clip(v - cv, -Lv, Lv)
    pu, _ = b0_4.waves(u, Lu, mu_)
    pv, _ = b0_4.waves(v, Lv, mv)
    return (pu[:, :, None] * pv[:, None, :]).reshape(len(u), -1)


# Check the basis rebuild against the design at the buildings.
s0 = train.surfaces[0]
chk = basis_at(s0, bx[: s0["sites"]][:50], by[: s0["sites"]][:50])
assert np.allclose(chk, s0["basis"][:50]), "basis rebuild mismatch"

# 1. Grid.
STEP_KM = 0.25
grid = {}
at = 0
for k, s in enumerate(train.surfaces):
    nb = s["basis"].shape[1]
    sl = slice(s["first"], s["first"] + s["sites"])
    lat0, lat1 = blat[sl].min(), blat[sl].max()
    lon0, lon1 = blon[sl].min(), blon[sl].max()
    dlat, dlon = STEP_KM / b0_4.KM_PER_LAT, STEP_KM / b0_4.KM_PER_LON
    ny = int(math.ceil((lat1 - lat0) / dlat)) + 1
    nx = int(math.ceil((lon1 - lon0) / dlon)) + 1
    glat = lat0 + dlat * np.arange(ny)
    glon = lon0 + dlon * np.arange(nx)
    LA, LO = np.meshgrid(glat, glon, indexing="ij")
    gx = (LO.ravel() - b0_4.LON0) * b0_4.KM_PER_LON
    gy = (LA.ravel() - b0_4.LAT0) * b0_4.KM_PER_LAT
    dist, _ = cKDTree(np.c_[bx[sl], by[sl]]).query(np.c_[gx, gy])
    on = dist <= 0.5
    Bg = basis_at(s, gx[on], gy[on])
    Fg = w[..., at : at + nb] @ Bg.T - const[..., None]  # (C, D, cells)
    at += nb
    flat = Fg.reshape(C * D, -1)
    med, lo, hi = q(flat)
    cs = chain_spread(Fg)

    def put(v):
        o = np.full(ny * nx, np.nan)
        o[on] = v
        return sig(o.reshape(ny, nx))

    grid[s["name"]] = {
        "origin": {"lat": round(float(lat0), 5), "lon": round(float(lon0), 5)},
        "step": {"lat": round(dlat, 7), "lon": round(dlon, 7), "km": STEP_KM},
        "shape": [ny, nx],
        "layout": "rows go north from origin lat, columns go east from origin lon; null = over 500 m from any building",
        "median_F": put(med),
        "width90": put(hi - lo),
        "chain_spread": put(cs),
    }
    log("grid", s["name"], ny, nx, int(on.sum()))

# 2. Buildings.
Fm = np.median(F.reshape(C * D, S), 0)
dq = q(bld.reshape(C * D, S))
d_cs = chain_spread(bld)

# Medians of the fixed terms and the walk, for the residual and the examples.
beta_draws = kept["beta"].reshape(C * D, -1)
L_draws = kept["L"].reshape(C * D, -1)
beta_med = np.median(beta_draws, 0)
L_med = np.median(L_draws, 0)
a = names.index("alpha")


def walk(Lv, wk, fr):
    return (1 - fr) * Lv[..., wk] + fr * Lv[..., wk + 1]


beta_rows = beta_med.copy()
beta_rows[GJ] = 0
fix_train = train.x @ beta_rows + walk(L_med, train.week, train.frac)
raw = np.bincount(train.site, weights=train.y - fix_train, minlength=S) / np.maximum(
    n_train, 1
)
raw[n_train == 0] = np.nan

buildings = {
    "note": "column arrays over buildings in the model's site order; n_ads counts training rows; F, d, A on log scale; A = x_s' gamma at gamma's posterior medians (the building's attribute premium); d is net of attributes, so the building level is F + A + d; raw_resid = mean over the building's training ads of y minus the row-level fixed terms (bld:* columns excluded) and walk at posterior medians (comparable to F + A + d)",
    "attr_columns": GN,
    "attrs_x": [
        [None if not np.isfinite(v) else round(float(v), 3) for v in col]
        for col in xs.T
    ],
    "A_med": sig(A_med),
    "lat": coord(blat),
    "lon": coord(blon),
    "zone": bzone.tolist(),
    "n_ads": n_train.tolist(),
    "F_med": sig(Fm),
    "d_med": sig(dq[0]),
    "d_width90": sig(dq[2] - dq[1]),
    "d_chain_spread": sig(d_cs),
    "raw_resid": sig(raw),
}
# Unit columns: mean over the building's training rows.
UN = [n for n in names if n.startswith("unit:")]
UJ = [names.index(n) for n in UN]
cnt = np.maximum(n_train, 1)
buildings["unit_columns"] = UN
buildings["unit_x_mean"] = [
    sig(np.bincount(train.site, weights=train.x[:, j], minlength=S) / cnt) for j in UJ
]
buildings["unit_note"] = (
    "unit_x_mean: mean of each unit column over the building's training ads; log_size_rel is 0 where size is unknown"
)


# 3. Named buildings.
def brow(i):
    b = bid[i]
    return {
        "building": b,
        "address": str(label.get(b, "")) or None,
        "neighbourhood": nbhd.get(b),
        "zone": ZNAME[bzone[i]],
        "n_ads": int(n_train[i]),
        "d_med": sig(dq[0][i]),
        "d_90": sig([dq[1][i], dq[2][i]]),
        "F_med": sig(Fm[i]),
        "premium_pct_d": sig(100 * (math.exp(dq[0][i]) - 1)),
        "A_med": sig(A_med[i]),
        "attrs": {
            n: (None if not np.isfinite(xs[i, k]) else round(float(xs[i, k]), 3))
            for k, n in enumerate(GN)
        },
    }


elig = np.flatnonzero(n_train >= 15)
o = elig[np.argsort(dq[0][elig])]
most = np.argsort(-n_train)
named = {
    "top15": [brow(i) for i in o[::-1][:15]],
    "bottom15": [brow(i) for i in o[:15]],
    "most_ads": [
        brow(i)
        for k in range(len(ZNAME))
        for i in [j for j in most if bzone[j] == k][:6]
    ],
}

# 4. Examples.
nu = kept["nu"].reshape(-1)
sigma = kept["sigma"].reshape(C * D, -1)
Fflat = F.reshape(C * D, S)
dflat = bld.reshape(C * D, S)
zl = kept["zone_level"].reshape(C * D, -1)
rng = np.random.default_rng(0)


def example(row):
    i = int(row)
    x = full.x[i]
    s = int(full.site[i])
    comp = {}
    comp["walk_at_week (alpha + L)"] = beta_draws[:, a] + walk(
        L_draws, full.week[i], full.frac[i]
    )
    season = sum(
        beta_draws[:, names.index(n)] * x[names.index(n)]
        for n in ("sin1", "cos1", "sin2", "cos2")
    )
    comp["season"] = season
    for j, n in enumerate(names):
        if n == "alpha" or n[:3] in ("sin", "cos"):
            continue
        if x[j] != 0:
            comp[n] = beta_draws[:, j] * x[j]
    comp["zone_level (share-weighted mean of F in zone; already inside F)"] = zl[
        :, bzone[s]
    ]
    comp["surface_F_at_building"] = Fflat[:, s]
    comp["building_d"] = dflat[:, s]
    mu = sum(v for k, v in comp.items() if not k.startswith("zone_level"))
    comp["residual"] = full.y[i] - mu
    g = int(full.group[i])
    yrep = mu + sigma[:, g] * rng.standard_t(nu)
    fr = frame.iloc[i]
    return {
        "listing_id": str(fr.listing_id),
        "building": fr.building,
        "address": str(label.get(fr.building, "")) or None,
        "unit": None if pd.isna(fr.unit_id) else str(fr.unit_id),
        "neighbourhood": fr.neighbourhood,
        "zone": ZNAME[bzone[s]],
        "date": str(pd.Timestamp(fr.latest_day).date()),
        "latest_ask": float(fr.latest_ask),
        "bedrooms": float(fr.bedrooms),
        "full_baths": None if pd.isna(fr.full_baths) else float(fr.full_baths),
        "half_baths": None if pd.isna(fr.half_baths) else float(fr.half_baths),
        "heldout": bool(heldout[i]),
        "building_train_ads": int(n_train[s]),
        "components_log": {
            k: {
                "med": sig(np.median(v)),
                "q05": sig(np.quantile(v, 0.05)),
                "q95": sig(np.quantile(v, 0.95)),
            }
            for k, v in comp.items()
        },
        "location_mu_log": sig(q(mu)),
        "predicted_median_ask_usd": sig(np.exp(np.median(mu))),
        "predicted_ask_90_usd (predictive, with Student-t noise)": sig(
            np.exp(np.quantile(yrep, [0.05, 0.95]))
        ),
        "location_90_usd": sig(np.exp(np.quantile(mu, [0.05, 0.95]))),
    }


day = pd.to_datetime(frame.latest_day)
bedr = frame.bedrooms.round().to_numpy()
site_of_row = full.site
rowz = bzone[site_of_row]
big = n_train[site_of_row] >= 10
nb = frame.neighbourhood.to_numpy()
cands = [
    ("manhattan_2bed", (rowz == 0) & (bedr == 2) & big),
    (
        "brooklyn_1bed",
        (rowz == 1)
        & (bedr == 1)
        & big
        & ~pd.Series(nb).isin(["Ridgewood", "Glendale"]).to_numpy(),
    ),
    (
        "manhattan_doorman_1bed",
        (rowz == 0)
        & (bedr == 1)
        & big
        & (full.x[:, names.index("bld:doorman_full")] == 1),
    ),
]
examples = {}
for key, m in cands:
    idx = np.flatnonzero(m)
    i = idx[np.argmax(day.to_numpy()[idx])]
    examples[key] = example(i)
    log("example", key, examples[key]["address"], examples[key]["date"])

# 5. Warmup: not saved per sweep.
warmup = None

# 6. Compare.
steps = [n for n in names if n.startswith(("bed>=", "bed=", "half"))]


def steps_of(path):
    zz = np.load(path / "posterior.npz")
    nm = [str(n) for n in zz["names"]]
    bb = zz["kept/beta"].reshape(-1, len(nm))
    out = {n: sig(np.median(bb[:, nm.index(n)])) for n in steps if n in nm}
    gap = None
    if "kept/zone_level" in zz.files:
        zl_ = zz["kept/zone_level"].reshape(-1, zz["kept/zone_level"].shape[-1])
        gq = 100 * (np.exp(np.quantile(zl_[:, 0] - zl_[:, 1], [0.5, 0.05, 0.95])) - 1)
        gap = {"med": sig(gq[0]), "q05": sig(gq[1]), "q95": sig(gq[2])}
    bldq = {
        n: sig(100 * np.expm1(np.median(bb[:, nm.index(n)])))
        for n in nm
        if n.startswith("bld:")
    }
    var = {}
    if "kept/bld_sd" in zz.files:
        bs = zz["kept/bld_sd"].reshape(-1, zz["kept/bld_sd"].shape[-1])
        vf_, vb_ = (
            zz[f"kept/{k}"].reshape(-1, zz[f"kept/{k}"].shape[-1])
            for k in ("zone_var_f", "zone_var_b")
        )
        amp_ = zz["kept/amp"].reshape(-1, zz["kept/amp"].shape[-1])
        for k, zn in enumerate(ZNAME):
            var[zn] = {
                "bld_sd_med": sig(np.median(bs[:, k])),
                "share_med": sig(np.median(vb_[:, k] / (vf_[:, k] + vb_[:, k]))),
                "amp_med": sig(np.median(amp_[:, k])),
            }
    if "kept/nu" in zz.files:
        var["nu_med"] = sig(np.median(zz["kept/nu"]))
        var["sigma_med"] = sig(
            np.median(zz["kept/sigma"].reshape(-1, zz["kept/sigma"].shape[-1]), 0)
        )
    return out, gap, bldq, var


compare = {}
for tag, path in (
    ("this_run", RUN),
    ("building_zones_gym", GYM),
    ("building_zones_unit", UNIT),
    ("building_zones_attrs_1km", PREV),
    ("building_attrs_no_location", ATTRS),
):
    st, gap, bq, var = steps_of(path)
    compare[tag] = {
        "run": path.name,
        "steps_med": st,
        "zone_gap_manhattan_vs_outer_pct": gap,
        "building_coef_pct_med": bq,
        "zones": var,
    }
compare["building_zones_gym"]["note"] = (
    "the gym run: this run without the truck, year built, alteration and retail columns"
)
compare["building_zones_unit"]["note"] = (
    "the unit run: this run without the gym, year built, alteration and retail columns"
)
compare["building_zones_attrs_1km"]["note"] = (
    "the base run: same data, sampler and settings, building attributes, no unit or truck columns, and the 2-bed 4-bath step still in"
)
compare["building_attrs_no_location"]["note"] = (
    "no location term in that model, so no zone gap; its height column is MapPLUTO floors, not roof height"
)

# 6b. gamma.
res = json.loads((RUN / "result.json").read_text())
pq = res["diagnostics"]["per_quantity"]
gamma = {
    "note": "percent premium = 100 (exp(gamma) - 1); log_height per e-fold of roof height (about 2.7x as tall), centred at 78 ft; unit:log_size_rel per unit of log(size / bedroom median); laundry against unstated; gym against a building without one (or with no amenities stated); built_* against year built 1900 to 1939; altered_2000_on is a MapPLUTO alteration year from 2000 up to the ad's year; retail against no MapPLUTO retail area (commercial area where retail is blank); traces are the kept draws per chain in sweep order (every 5th sweep after warmup)"
}
ALLN = GN + [n for n in names if n.startswith("unit:")]
for n in ALLN:
    g = kept["beta"][..., names.index(n)].astype(float)
    pct = 100 * np.expm1(g)
    d = pq.get(f"beta[{n}]", {})
    gamma[n] = {
        "pct": {
            "med": sig(np.median(pct)),
            "q05": sig(np.quantile(pct, 0.05)),
            "q95": sig(np.quantile(pct, 0.95)),
        },
        "log": {
            "med": sig(np.median(g)),
            "q05": sig(np.quantile(g, 0.05)),
            "q95": sig(np.quantile(g, 0.95)),
        },
        "chain_medians_pct": sig(np.median(pct, axis=1)),
        "rhat": d.get("rhat", d.get("r_hat")),
        "ess_bulk": d.get("ess_bulk", d.get("ess")),
        "diag": d,
        "rows_set": int(res.get("counts", {}).get(n, 0)),
        "trace_pct": sig(pct),
    }

# 7. Variance.
vf = kept["zone_var_f"].reshape(C * D, -1)
vb = kept["zone_var_b"].reshape(C * D, -1)
zsd = kept["zone_sd"].reshape(C * D, -1)
bsd = kept["bld_sd"].reshape(C * D, -1)


def qd(v):
    m, lo, hi = q(v)
    return {"med": sig(m), "q05": sig(lo), "q95": sig(hi)}


variance = {
    "note": "row-weighted over the zone's buildings (training rows) unless marked unweighted; log scale"
}
for k, nm in enumerate(ZNAME):
    variance[nm] = {
        "amp": qd(kept["amp"].reshape(C * D, -1)[:, k]),
        "surface_sd_row_weighted": qd(np.sqrt(vf[:, k])),
        "surface_sd_unweighted": qd(zsd[:, k]),
        "building_spread_param_b_z": qd(bsd[:, k]),
        "building_sd_realised_row_weighted": qd(np.sqrt(vb[:, k])),
        "share_building_to_building": qd(vb[:, k] / (vf[:, k] + vb[:, k])),
        "buildings": int((bzone == k).sum()),
        "train_ads": int(n_train[bzone == k].sum()),
    }
variance["sigma_by_bedroom_band (0,1,2,3+; shared across zones)"] = [
    qd(sigma[:, g]) for g in range(sigma.shape[1])
]
variance["nu"] = qd(nu)

out = {
    "run": RUN.name,
    "zones": {"0": "manhattan", "1": "outer (Brooklyn + Queens Ridgewood/Glendale)"},
    "lengthscale_km": res.get("surfaces", [{}])[0].get("lengthscale_km"),
    "draws": {
        "chains": C,
        "kept_per_chain": D,
        "note": "kept every 5th of 1,000 sweeps after 300 warmup",
    },
    "pair_gap": json.loads(Path("/data1/apartments/tmp/bzy/pair_gap.json").read_text())
    if Path("/data1/apartments/tmp/bzy/pair_gap.json").exists()
    else None,
    "convergence": {
        k: res["diagnostics"].get(k) for k in res["diagnostics"] if k != "per_quantity"
    },
    "gamma": gamma,
    "grid": grid,
    "buildings": buildings,
    "named": named,
    "examples": examples,
    "warmup": warmup,
    "warmup_note": "per-sweep warmup states were not saved; result.json log has chain 0-1 snapshots of nu, amp, bld_sd every 30 warmup sweeps",
    "compare": compare,
    "variance": variance,
}
dump = lambda o: json.dumps(
    o,
    separators=(",", ":"),
    default=lambda v: v.item() if hasattr(v, "item") else str(v),
)
OUT.with_name("explainer-data-full.json").write_text(dump(out))
buildings.pop("raw_resid")
buildings["dropped"] = (
    "raw_resid dropped to keep the file near 4 MB; it is in explainer-data-full.json on thelio"
)
OUT.write_text(dump(out))
log("wrote", OUT, OUT.stat().st_size)
# Candidates for well-known picks.
top = np.argsort(-n_train)
for k in range(len(ZNAME)):
    ii = [i for i in top if bzone[i] == k][:12]
    log(ZNAME[k], [(bid[i], int(n_train[i])) for i in ii])
