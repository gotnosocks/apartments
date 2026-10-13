"""How well do beds, baths, text and building fields predict stated size, and is
size missing selectively? Free, read-only diagnosis on the NB8 frame (current
rules). Writes results.json next to this file."""

import json
import re

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

RNG = np.random.default_rng(20261013)
B = 300  # cluster-bootstrap replicates (buildings)
f = pd.read_parquet("frame.parquet")
n = len(f)
desc = f.description.fillna("").str.lower()
stated = f.square_feet.between(150, 8000).to_numpy()
y = np.log(f.square_feet.where(stated)).to_numpy()
year = f.period.dt.year.to_numpy()
bed = f.bedrooms.clip(upper=4).fillna(-1).astype(int).to_numpy()
bed_label = np.array(["?", "studio", "1", "2", "3", "4+"])[bed + 1]
area = f.neighbourhood.to_numpy()

# ---- predictors -------------------------------------------------------------
base = [
    c
    for c in f.columns
    if c.startswith("x::")
    and c not in ("x::log_sqft_vs_bedroom_median", "x::sqft_unknown")
]
X = f[base].astype(float).copy()
X.columns = [c[3:] for c in base]
X["bedrooms_raw"] = f.bedrooms
X["bathrooms_raw"] = f.bathrooms
X["floor_raw"] = f.listed_floor.fillna(f.label_derived_floor)
X["year"] = year + (f.period.dt.month.to_numpy() - 1) / 12
WORDS = {
    "studio": r"\bstudio\b",
    "alcove": r"\balcove\b",
    "loft": r"\bloft\b",
    "townhouse": r"\btown ?house|brownstone",
    "terrace": r"\bterrace",
    "duplex": r"\bduplex|triplex",
    "renovated": r"renovat|gut ",
    "penthouse": r"penthouse",
    "junior": r"\bjunior\b|\bjr\.?\b",
    "convertible": r"convertible|\bflex\b",
    "walk_in_closet": r"walk.?in closet",
    "home_office": r"home office|\boffice\b|\bden\b",
    "dining": r"dining",
    "king": r"\bking\b",
    "queen": r"\bqueen\b",
    "big": r"huge|massive|spacious|oversized|sprawling|enormous|expansive",
    "small": r"\bcozy|\bcosy|charming|compact|petite|efficient",
    "sunny": r"sun.?(?:drenched|filled|lit)|sunny",
    "triple": r"three bedroom|3 ?br|3 bed",
}
for k, pat in WORDS.items():
    X["w:" + k] = desc.str.contains(pat, regex=True).astype(float).to_numpy()
X["log_desc_len"] = np.log1p(desc.str.len().to_numpy())
SQFT = re.compile(
    r"(\d{1,2},\d{3}|\d{3,4})\s*(?:\+\s*)?(?:-\s*)?(?:sq\.?\s*f(?:ee)?t|square\s*f(?:ee|oo)t|sqft|sf\b|ft2)"
)


def text_sqft(s):
    for m in SQFT.finditer(s):
        v = float(m.group(1).replace(",", ""))
        if 150 <= v <= 8000:
            return v
    return np.nan


tsq = desc.map(text_sqft).to_numpy()
X_text_sqft = np.log(tsq)  # NaN where no plausible mention

# ---- building leave-unit-out features ---------------------------------------
s = pd.DataFrame({"b": f.building, "u": f.unit_id, "bed": bed, "y": y})[stated]
unit_mean = s.groupby(["b", "u", "bed"]).y.mean().reset_index()
bsum = unit_mean.groupby("b").y.agg(["sum", "count"])
bbsum = unit_mean.groupby(["b", "bed"]).y.agg(["sum", "count"])
own = unit_mean.set_index(["b", "u"]).y.groupby(level=[0, 1]).mean()
key_bu = pd.MultiIndex.from_arrays([f.building, f.unit_id])
own_y = own.reindex(key_bu).to_numpy()
own_has = ~np.isnan(own_y)
tot = bsum.reindex(f.building)
sum_o = tot["sum"].fillna(0).to_numpy() - np.where(own_has, own_y, 0)
cnt_o = tot["count"].fillna(0).to_numpy() - own_has
own_bed = (
    unit_mean.set_index(["b", "u", "bed"])
    .y.reindex(pd.MultiIndex.from_arrays([f.building, f.unit_id, bed]))
    .to_numpy()
)
own_bed_has = ~np.isnan(own_bed)
tb = bbsum.reindex(pd.MultiIndex.from_arrays([f.building, bed]))
sumb_o = tb["sum"].fillna(0).to_numpy() - np.where(own_bed_has, own_bed, 0)
cntb_o = tb["count"].fillna(0).to_numpy() - own_bed_has
XB = pd.DataFrame(
    {
        "bldg_other_mean": np.where(cnt_o > 0, sum_o / np.maximum(cnt_o, 1), np.nan),
        "bldg_other_n": cnt_o,
        "bldg_bed_other_mean": np.where(
            cntb_o > 0, sumb_o / np.maximum(cntb_o, 1), np.nan
        ),
        "bldg_bed_other_n": cntb_o,
    }
)

groups = f.building.to_numpy()
folds = list(GroupKFold(n_splits=5).split(np.zeros(n), groups=groups))


def lgbm():
    return lgb.LGBMRegressor(
        n_estimators=600,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=40,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        n_jobs=6,
        verbose=-1,
    )


def ridge_matrix(M):
    M = M.copy()
    for c in M.columns:
        if M[c].isna().any():
            M[c + "_na"] = M[c].isna().astype(float)
            M[c] = M[c].fillna(M[c].median() if M[c].notna().any() else 0)
    return M


def oof(M, kind, target=y, train_mask=stated):
    """Out-of-fold predictions for every row (stated or not), folds by building."""
    if kind == "ridge":
        M = ridge_matrix(M)
    M = M.to_numpy(dtype=float)
    out = np.full(n, np.nan)
    for tr, te in folds:
        tr = tr[train_mask[tr]]
        if kind == "ridge":
            mu, sd = M[tr].mean(0), M[tr].std(0)
            sd[sd == 0] = 1
            m = Ridge(alpha=1.0).fit((M[tr] - mu) / sd, target[tr])
            out[te] = m.predict((M[te] - mu) / sd)
        else:
            m = lgbm().fit(M[tr], target[tr])
            out[te] = m.predict(M[te])
    return out


# ---- metrics with building cluster bootstrap ---------------------------------
bcodes, binv = np.unique(groups, return_inverse=True)
W = RNG.multinomial(len(bcodes), np.ones(len(bcodes)) / len(bcodes), size=B)


def metrics(pred, mask):
    idx = np.where(mask & stated & ~np.isnan(pred))[0]
    e, t = pred[idx] - y[idx], y[idx]
    ape = np.abs(np.expm1(e))
    order = np.argsort(ape)
    ape_s, bi = ape[order], binv[idx][order]

    def stat(w):
        wr = w[binv[idx]]
        sw = wr.sum()
        if sw == 0:
            return np.nan, np.nan
        tm = (wr * t).sum() / sw
        r2 = 1 - (wr * e**2).sum() / (wr * (t - tm) ** 2).sum()
        cw = np.cumsum(w[bi])
        md = ape_s[np.searchsorted(cw, cw[-1] / 2)]
        return r2, md

    point = stat(np.ones(len(bcodes)))
    boot = np.array([stat(w) for w in W])
    lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
    return {
        "rows": int(len(idx)),
        "buildings": int(len(np.unique(binv[idx]))),
        "r2": [round(point[0], 3), round(lo[0], 3), round(hi[0], 3)],
        "mdape_pct": [
            round(100 * point[1], 1),
            round(100 * lo[1], 1),
            round(100 * hi[1], 1),
        ],
    }


def breakdown(pred):
    out = {"all": metrics(pred, np.ones(n, bool))}
    out["by_bedrooms"] = {
        b: metrics(pred, bed_label == b) for b in ["studio", "1", "2", "3", "4+"]
    }
    out["by_area"] = {a: metrics(pred, area == a) for a in sorted(set(area))}
    return out


R = {}
XA0 = X  # (a) without text sqft
XA = X.assign(text_log_sqft=X_text_sqft)  # (a) with text sqft phrases
XBb = pd.concat([XA, XB], axis=1)  # (b) known building, leave-unit-out
preds = {}
for name, M in [("a_no_text_sqft", XA0), ("a", XA), ("b", XBb)]:
    for kind in ("ridge", "lgbm"):
        p = oof(M, kind)
        preds[f"{name}_{kind}"] = p
        R[f"{name}_{kind}"] = (
            breakdown(p) if kind == "lgbm" else {"all": metrics(p, np.ones(n, bool))}
        )
        print(name, kind, R[f"{name}_{kind}"]["all"], flush=True)
# Coverage of the known-building feature.
R["b_coverage"] = {
    "stated_rows_with_other_stated_unit": round(float((cnt_o[stated] > 0).mean()), 3),
    "unstated_rows_with_stated_unit_in_building": round(
        float((cnt_o[~stated] > 0).mean()), 3
    ),
    "stated_rows_same_bed_other": round(float((cntb_o[stated] > 0).mean()), 3),
    "unstated_rows_same_bed_other": round(float((cntb_o[~stated] > 0).mean()), 3),
}
# Text sqft: agreement on stated rows and availability on unstated rows.
both = stated & ~np.isnan(tsq)
R["text_sqft"] = {
    "stated_rows_with_text_sqft": round(float((~np.isnan(tsq[stated])).mean()), 3),
    "unstated_rows_with_text_sqft": round(float((~np.isnan(tsq[~stated])).mean()), 3),
    "unstated_rows_with_text_sqft_n": int((~np.isnan(tsq[~stated])).sum()),
    "agree_within_5pct_where_both": round(
        float((np.abs(tsq[both] / np.exp(y[both]) - 1) < 0.05).mean()), 3
    ),
}
np.save("pred_a_lgbm.npy", preds["a_no_text_sqft_lgbm"])

# ---- 2. selective missingness ----------------------------------------------------
lr = f.log_rent.to_numpy()
ym = f.period.dt.to_period("M").astype(str)
cell_mean = pd.Series(lr).groupby([area, ym.to_numpy()]).transform("mean").to_numpy()
resid_t = lr - cell_mean  # log rent net of neighbourhood x month


def boot_mean(vals, clusters):
    vals = np.asarray(vals, float)
    cu, ci = np.unique(clusters, return_inverse=True)
    sums = np.bincount(ci, vals, len(cu))
    cnts = np.bincount(ci, None, len(cu))
    reps = []
    for _ in range(B):
        w = RNG.multinomial(len(cu), np.ones(len(cu)) / len(cu))
        reps.append((w * sums).sum() / (w * cnts).sum())
    return [
        round(vals.mean(), 4),
        round(np.percentile(reps, 2.5), 4),
        round(np.percentile(reps, 97.5), 4),
    ]


def boot_median(vals, clusters):
    vals = np.asarray(vals, float)
    cu, ci = np.unique(clusters, return_inverse=True)
    reps = []
    for _ in range(B):
        pick = RNG.integers(0, len(cu), len(cu))
        w = np.bincount(pick, minlength=len(cu))[ci]
        o = np.argsort(vals)
        cw = np.cumsum(w[o])
        reps.append(vals[o][np.searchsorted(cw, cw[-1] / 2)])
    return [
        round(float(np.median(vals)), 4),
        round(np.percentile(reps, 2.5), 4),
        round(np.percentile(reps, 97.5), 4),
    ]


# (i) units stated in some listings and not others: within-unit differences
u = pd.DataFrame(
    {
        "u": f.unit_id,
        "b": f.building,
        "st": stated,
        "r": resid_t,
        "year": year + f.period.dt.month.to_numpy() / 12,
        "has_desc": (desc.str.len() > 0).astype(float),
        "log_len": X.log_desc_len,
        "big": X["w:big"],
        "small": X["w:small"],
        "renovated": X["w:renovated"],
        "text_sqft": (~np.isnan(tsq)).astype(float),
    }
)
mixed = u.groupby("u").st.transform(lambda s: s.any() and not s.all())
um = u[mixed].groupby(["u", "b", "st"]).mean(numeric_only=True).unstack("st")
diff = (um.xs(False, axis=1, level=1) - um.xs(True, axis=1, level=1)).reset_index()
R["2i_mixed_units"] = {
    "units": int(len(diff)),
    "rows": int(mixed.sum()),
    "unstated_minus_stated": {
        c: {"mean": boot_mean(diff[c], diff.b), "median": boot_median(diff[c], diff.b)}
        for c in [
            "r",
            "year",
            "has_desc",
            "log_len",
            "big",
            "small",
            "renovated",
            "text_sqft",
        ]
    },
}
print(
    "2i",
    R["2i_mixed_units"]["units"],
    R["2i_mixed_units"]["unstated_minus_stated"]["r"],
    flush=True,
)

# (ii) never-stated units vs stated units, same building and bedrooms, predicted size
pa = preds["a_no_text_sqft_lgbm"]
ever = pd.Series(stated).groupby(f.unit_id.to_numpy()).transform("any").to_numpy()
uu = pd.DataFrame(
    {"u": f.unit_id, "b": f.building, "bed": bed, "ever": ever, "p": pa, "y": y}
)
uu = (
    uu[bed >= 0]
    .groupby(["b", "bed", "u", "ever"])
    .agg(p=("p", "mean"), y=("y", "mean"))
    .reset_index()
)
cell = (
    uu.groupby(["b", "bed", "ever"])
    .agg(p=("p", "mean"), y=("y", "mean"), n=("u", "size"))
    .unstack("ever")
)
cell = cell.dropna(subset=[("p", False), ("p", True)])
d2 = (cell[("p", False)] - cell[("p", True)]).rename("d").reset_index()
bias = (cell[("p", True)] - cell[("y", True)]).rename("bias").reset_index()
raw = uu.groupby("ever").p.mean()
R["2ii_never_vs_stated"] = {
    "cells_building_x_bedrooms": int(len(d2)),
    "never_minus_stated_pred_log_size_within_cell": {
        "mean": boot_mean(d2.d, d2.b),
        "median": boot_median(d2.d, d2.b),
    },
    # Point values only (no bootstrap), over the cells whose stated units state a
    # size at that bedroom count.
    "stated_units_pred_minus_actual_in_those_cells": {
        "cells": int(bias.bias.notna().sum()),
        "mean": round(float(bias.bias.mean()), 4),
        "median": round(float(bias.bias.median()), 4),
    },
    "never_minus_stated_pred_log_size_overall_unit_mean": round(
        float(raw[False] - raw[True]), 4
    ),
    "never_stated_units": int((~uu.ever).sum()),
    "stated_units": int(uu.ever.sum()),
}
print(
    "2ii",
    R["2ii_never_vs_stated"]["never_minus_stated_pred_log_size_within_cell"],
    flush=True,
)

# (iii) rent gap of unknown-size rows vs what predicted size implies
XR = XA0.copy()
XR["log_size"] = y
rent_pred_true = np.full(n, np.nan)
rent_pred_hat = np.full(n, np.nan)
M = XR.to_numpy(dtype=float)
Mhat = XR.assign(log_size=pa).to_numpy(dtype=float)
for tr, te in folds:
    tr = tr[stated[tr]]
    m = lgbm().fit(M[tr], lr[tr])
    rent_pred_true[te] = m.predict(M[te])
    rent_pred_hat[te] = m.predict(Mhat[te])
res_hat = lr - rent_pred_hat
# A rent model with no size at all, for the raw gap.
XN = XA0.to_numpy(dtype=float)
rent_nosize = np.full(n, np.nan)
for tr, te in folds:
    m = lgbm().fit(XN[tr], lr[tr])
    rent_nosize[te] = m.predict(XN[te])
res_nosize = lr - rent_nosize
R["2iii_rent_gap"] = {
    "note": "residual = log rent - rent model (trained on stated rows with true size) fed predicted size; folds by building",
    "stated_mean_resid_using_pred_size": boot_mean(res_hat[stated], groups[stated]),
    "unstated_mean_resid_using_pred_size": boot_mean(res_hat[~stated], groups[~stated]),
    "stated_mean_resid_using_true_size": boot_mean(
        (lr - rent_pred_true)[stated], groups[stated]
    ),
    "no_size_model_resid_stated": boot_mean(res_nosize[stated], groups[stated]),
    "no_size_model_resid_unstated": boot_mean(res_nosize[~stated], groups[~stated]),
    "pred_log_size_mean_stated_vs_unstated": [
        round(float(np.nanmean(pa[stated])), 4),
        round(float(np.nanmean(pa[~stated])), 4),
    ],
    "by_bedrooms_unstated_minus_stated_resid": {},
}
for b in ["studio", "1", "2", "3", "4+"]:
    mb = bed_label == b
    a_ = res_hat[mb & ~stated]
    s_ = res_hat[mb & stated]
    R["2iii_rent_gap"]["by_bedrooms_unstated_minus_stated_resid"][b] = round(
        float(a_.mean() - s_.mean()), 4
    )
print(
    "2iii",
    {k: v for k, v in R["2iii_rent_gap"].items() if "mean_resid" in k},
    flush=True,
)

# ---- 3. stated share by year -------------------------------------------------
sy = pd.DataFrame({"year": year, "st": stated, "b": groups})
R["3_share_by_year"] = {
    int(k): [round(float(g.st.mean()), 3), int(len(g))] for k, g in sy.groupby("year")
}
R["3_share_by_area"] = {
    a: round(float(stated[area == a].mean()), 3) for a in sorted(set(area))
}
json.dump(R, open("results.json", "w"), indent=1, default=float)
print("done")
