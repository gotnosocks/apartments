"""Leak-free explanation ceiling of the served fit C's building terms by data already held.

    python docs/analysis/scripts/held_data_ceiling.py target     # C's building part per row
    python docs/analysis/scripts/held_data_ceiling.py features   # the as-of feature table
    python docs/analysis/scripts/held_data_ceiling.py gate       # v1 screen reproduction
    python docs/analysis/scripts/held_data_ceiling.py static     # ceiling + family shares
    python docs/analysis/scripts/held_data_ceiling.py residual PER_ROW_FILE

No refit, no Modal. The steps write to OUT (below) and read each other's files.

1. `target` runs C's kept draws through `explain.log_terms` in row chunks and sums
   the building terms (`newbuilding.BUILDING_TERMS`: level, walk, bedroom premium,
   feature slopes) for every training row. Each building's static target is the
   precision-weighted mean of its rows' building part, taken draw by draw, with
   weights 1 / (posterior variance of the row's building part); the posterior mean
   and variance over draws give the target and its noise.
2. `features` builds one row per listing (all rows, training or not) with
     - building facts as of the listing: PLUTO as-of, elevfill, lines, hpd,
       stabilized share, retail, noise, trees, crime, and the listing's lister;
     - predicted size for case a rows (no stated size anywhere in the building);
     - for every ad-level column of the base set (coded fields, description flags,
       unit traits) its mean over the building's ads dated strictly before this
       one (`asof:` columns), and the mean over all of the building's ads, own and
       later included (`all:` columns, the leaky control);
     - coordinates.
   Nothing in it reads a rent.
3. `gate` scores the hpd-v1 and elevfill-v1 families on the old target (the
   2010-anchored level `kept["building"]`) with random building folds and all-row
   means, as `rentfrontier.explained` did for v1 (1.38% and 2.42%).
4. `static` aggregates the row features to buildings with the target's weights and
   fits WLS and LightGBM on folds grouped by tax lot, with and without coordinates,
   as-of and leaky, and scores families against a permutation null.
5. `residual` does the same on a per-row new-building residual file and converts the
   gain to points of the board's new-building miss.
"""

from __future__ import annotations

import json
import sys
import time
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import data, explain, explained, features, model, newbuilding

C = (
    "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-"
    "nb8-nostuy-v1-rows-5c1e5c7e-a100-4500k9cb1-nb8-ul15r1s4q12ad3"
)
BASE = "nb8-nostuy-v1"
OUT = Path("/data1/apartments/frontier/ceiling/2026-10-13")
FOLDS = 5
PERMUTATIONS = 50
BOOT = 500
SEED = 20261013

# Families whose columns come from a candidate set's difference to the base.
SETS = {
    "hpd": "nb8-nostuy-hpd-v1",
    "elevfill": "nb8-nostuy-elevfill-v1",
    "lines": "nb8-nostuy-lines-v1",
    "lister": "nb8-nostuy-lister-v1",
    "retail": "nb8-nostuy-retail-v1",
    "noise": "nb8-nostuy-noise-v1",
    "trees": "nb8-nostuy-trees-v1",
    "crime": "nb8-nostuy-crime-v1",
    "petsfill": "nb8-nostuy-petsfill-v1",
}
# Base groups that describe the building as of the listing (PLUTO as-of and
# landmark status): taken at the row's own value.
BUILDING_GROUPS = ("building era", "building size", "building class", "building status")
# Base groups that describe the ad or the unit: averaged over the building's ads.
AD_GROUPS = (
    "bedrooms",
    "bathrooms",
    "size",
    "floor",
    "elevator",
    "doorman",
    "laundry",
    "hvac",
    "pets",
    "views",
    "windows",
    "unit label",
    "description",
    "outdoor space",
    "rooms beyond bedrooms",
    "facing",
)
# The desc-v1 flags that describe the apartment's finish.
FINISH = ("renovated", "luxury", "high_ceilings", "exposed_brick", "fireplace")


def _register_stabilized():
    """Register `stabilized_v1` on the base under a scratch id with the base's
    snapshots, so `features.build` reads the nb8 registry for it."""
    name = "ceiling-stabilized"
    features.FEATURE_SETS[name] = partial(features.stabilized_v1, id=name, base=BASE)
    for value in vars(features).values():
        if isinstance(value, set) and BASE in value:
            value.add(name)
        elif isinstance(value, dict) and BASE in value and name not in value:
            value[name] = value[BASE]
    return name


def _load_frame():
    """C's result record, frame and held-out mask, without its draws."""
    result = json.loads((explain.RUNS / C / "result.json").read_text())
    frame = data.load(Path(result["dataset"]))
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    frame, heldout = data.split_and_rules(
        frame, result["split"], data.recorded_rules(result)
    )
    return result, frame, heldout


def _load_kept():
    """C's kept draws as float32, (draws, ...)."""
    post = np.load(explain.RUNS / C / "posterior.npz", allow_pickle=True)
    return {
        k[len("kept/") :]: post[k].reshape(-1, *post[k].shape[2:]).astype(np.float32)
        for k in post.files
        if k.startswith("kept/")
    }


# ---------------------------------------------------------------- target


def target():
    from scipy import sparse

    result, frame, heldout = _load_frame()
    kept = _load_kept()
    config = model.MODELS[result["model"]["name"]]
    run_dir = explain.RUNS / C
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    newbuilding._check_draws(run_dir, prep)
    names = [str(n) for n in feats.names]
    spacing = model.walk_spacing(config)
    fslope_index = np.asarray([names.index(n) for n in config.feature_slopes], int)
    train = ~heldout
    idx = np.flatnonzero(train)
    draws, n_b = kept["alpha"].shape[0], len(prep.buildings)
    chunks = np.array_split(idx, max(1, len(idx) // 2048))
    sums = np.zeros((n_b, draws))
    weight = np.zeros(n_b)
    rows = []
    t0 = time.perf_counter()
    for i, c in enumerate(chunks):
        m = np.zeros(len(frame), bool)
        m[c] = True
        a = model.row_arrays(prep, frame, m)
        terms = explain.log_terms(
            kept,
            a,
            prep.features.groups,
            spacing,
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
            unit_line=prep.unit_line,
        )
        b = sum(terms[k] for k in newbuilding.BUILDING_TERMS if k in terms).astype(
            np.float64
        )
        mean, var = b.mean(0), b.var(0)
        w = 1 / np.maximum(var, 1e-8)
        agg = sparse.csr_matrix((w, (a.building, np.arange(len(w)))), (n_b, len(w)))
        sums += agg @ b.T
        weight += np.bincount(a.building, weights=w, minlength=n_b)
        rows.append(
            pd.DataFrame(
                {
                    "audit_id": frame.audit_id.to_numpy()[c],
                    "bidx": a.building,
                    "bpart_mean": mean,
                    "bpart_var": var,
                }
            )
        )
        if i % 20 == 0:
            print(
                f"chunk {i}/{len(chunks)} {time.perf_counter() - t0:.0f}s", flush=True
            )
    per_draw = sums / np.maximum(weight, 1e-12)[:, None]
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_parquet(OUT / "rows-bpart.parquet")
    np.savez(
        OUT / "targets.npz",
        buildings=np.asarray(prep.buildings),
        static_mean=per_draw.mean(1),
        static_var=per_draw.var(1),
        weight=weight,
        level_mean=kept["building"].mean(0).astype(np.float64),
        level_var=kept["building"].astype(np.float64).var(0),
    )
    print("wrote", OUT, f"{time.perf_counter() - t0:.0f}s")


# ---------------------------------------------------------------- features


def _earlier_means(values, building, when):
    """Per row: the mean of each column over the same building's rows dated
    strictly earlier (NaN where there are none), and the count of those rows."""
    order = np.lexsort((when, building))
    v, b, t = values[order], building[order], when[order]
    out = np.full_like(v, np.nan, dtype=float)
    count = np.zeros(len(v))
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], len(b)]
    for s, e in zip(starts, ends):
        tt = t[s:e]
        cum = np.vstack([np.zeros(v.shape[1]), np.cumsum(v[s:e], 0)])
        # rows before the first row of each row's date
        first = np.searchsorted(tt, tt, side="left")
        n = first.astype(float)
        count[s:e] = n
        with np.errstate(invalid="ignore", divide="ignore"):
            out[s:e] = cum[first] / n[:, None]
    res = np.empty_like(out)
    res[order] = out
    cnt = np.empty_like(count)
    cnt[order] = count
    return res, cnt


def _all_means(values, building):
    codes, inv = np.unique(building, return_inverse=True)
    sums = np.zeros((len(codes), values.shape[1]))
    np.add.at(sums, inv, values)
    return (sums / np.bincount(inv)[:, None])[inv]


def build_features():
    _, frame, heldout = _load_frame()
    train = ~heldout
    base = features.build(BASE, frame, train)
    names = [str(n) for n in base.names]
    groups = list(base.groups)
    cols, fam = {}, {}

    def put(family, name, value):
        cols[name] = np.asarray(value, dtype=float)
        fam[name] = family

    for j, (g, n) in enumerate(zip(groups, names)):
        if g in BUILDING_GROUPS:
            put("pluto", f"pluto:{n}", base.values[:, j])
    for family, set_name in SETS.items():
        cand = features.build(set_name, frame, train)
        cnames = [str(n) for n in cand.names]
        for j, n in enumerate(cnames):
            if n not in names:
                put(family, f"{family}:{n}", cand.values[:, j])
            elif not np.allclose(cand.values[:, j], base.values[:, names.index(n)]):
                put(family, f"{family}:changed:{n}", cand.values[:, j])
        print(family, sum(f == family for f in fam.values()), "columns", flush=True)
    stab = features.build(_register_stabilized(), frame, train)
    put("stabilized", "stabilized share", stab.values[:, -1])

    # Predicted size, case a only: the row's size is unknown and the building
    # has no stated size to borrow from.
    pred = pd.read_parquet(features.PREDICTED_SIZE_FILE).set_index("audit_id")
    pred = pred.reindex(frame.audit_id.to_numpy())
    unknown = base.values[:, names.index("sqft_unknown")] > 0.5
    case_a = unknown & (pred["case"].to_numpy() == "a")
    psize = features.build("nb8-nostuy-predsize-v1", frame, train)
    col = names.index("log_sqft_vs_bedroom_median")
    put("predsize", "predsize:case a size", np.where(case_a, psize.values[:, col], 0.0))
    put("predsize", "predsize:case a", case_a)

    # Ad-level columns: as-of and all-row building means.
    ad = [j for j, g in enumerate(groups) if g in AD_GROUPS]
    ad_values = base.values[:, ad].astype(float)
    building = frame.building.to_numpy()
    when = frame.period.to_numpy().astype("datetime64[D]").astype(np.int64)
    earlier, count = _earlier_means(ad_values, building, when)
    every = _all_means(ad_values, building)
    for k, j in enumerate(ad):
        n = names[j]
        family = (
            "finish"
            if n.removeprefix("text:") in FINISH
            else ("coded" if groups[j] != "description" else "description")
        )
        put(family, f"asof:{n}", earlier[:, k])
        put(f"leaky-{family}", f"all:{n}", every[:, k])
    put("history", "asof:log1p earlier ads", np.log1p(count))
    put(
        "leaky-history",
        "all:log1p ads",
        np.log1p(
            pd.Series(building).map(pd.Series(building).value_counts()).to_numpy()
        ),
    )

    reg = (
        pd.read_parquet(features.NB8_REGISTRY_FILE)
        .drop_duplicates("building")
        .set_index("building")
        .reindex(building)
    )
    lat, lon = reg.latitude.to_numpy(), reg.longitude.to_numpy()
    put("coords", "coords:lat", lat)
    put("coords", "coords:lon", lon)
    put("coords", "coords:lat+lon", lat + lon)
    put("coords", "coords:lat-lon", lat - lon)
    table = pd.DataFrame(cols)
    table.insert(0, "audit_id", frame.audit_id.to_numpy())
    table.insert(1, "building", building)
    table.insert(2, "bbl", reg.bbl.astype(str).where(reg.bbl.notna()).to_numpy())
    table.insert(3, "train", train)
    table.insert(4, "period", frame.period.to_numpy())
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUT / "features.parquet")
    (OUT / "families.json").write_text(json.dumps(fam, indent=1))
    print("features", table.shape)


# ---------------------------------------------------------------- scoring


def lot_folds(buildings, lots, rng, k=FOLDS):
    """Fold per building, whole tax lots together (a building with no lot is its own)."""
    key = np.where(pd.isna(lots), "b:" + pd.Series(buildings).astype(str), lots)
    uniq, inv = np.unique(key, return_inverse=True)
    return rng.permutation(np.arange(len(uniq)) % k)[inv], inv


def _fill(x):
    """WLS design: NaN -> column mean plus a missing indicator for columns with NaN."""
    x = np.asarray(x, float)
    miss = np.isnan(x)
    out = np.where(miss, np.nanmean(np.where(miss.all(0), 0, x), 0), x)
    out = np.nan_to_num(out)
    extra = miss[:, miss.any(0) & ~miss.all(0)].astype(float)
    return np.column_stack([out, extra]) if extra.size else out


def wls_oof(y, sd2, x, folds):
    X = explained._design(_fill(x))
    pred = np.empty_like(y)
    for f in np.unique(folds):
        tr = folds != f
        tau2 = explained.residual_variance(X[tr], y[tr], sd2[tr])
        beta = explained._wls(X[tr], y[tr], 1 / (sd2[tr] + tau2))
        pred[~tr] = X[~tr] @ beta
    return pred


def gbm_oof(y, sd2, x, folds, groups, seed=0):
    import lightgbm as lgb

    pred = np.empty_like(y)
    tau2 = explained.residual_variance(np.ones((len(y), 1)), y, sd2)
    w = 1 / (sd2 + tau2)
    params = dict(
        objective="regression",
        learning_rate=0.03,
        num_leaves=15,
        min_data_in_leaf=40,
        feature_fraction=0.8,
        bagging_fraction=0.8,
        bagging_freq=1,
        lambda_l2=1.0,
        verbose=-1,
        seed=seed,
        num_threads=4,
    )
    for f in np.unique(folds):
        tr = np.flatnonzero(folds != f)
        # inner lot-grouped early-stopping split of the training folds
        inner = (groups[tr] * 7919 + seed) % 5 == 0
        fit, val = tr[~inner], tr[inner]
        dtr = lgb.Dataset(x[fit], y[fit], weight=w[fit])
        dva = lgb.Dataset(x[val], y[val], weight=w[val], reference=dtr)
        booster = lgb.train(
            params,
            dtr,
            2000,
            valid_sets=[dva],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        pred[folds == f] = booster.predict(
            x[folds == f], num_iteration=booster.best_iteration
        )
    return pred


def r2(y, sd2, pred, idx=None):
    w = 1 / (sd2 + explained.residual_variance(np.ones((len(y), 1)), y, sd2))
    if idx is not None:
        y, pred, w = y[idx], pred[idx], w[idx]
    mean = np.sum(w * y) / w.sum()
    return 1 - np.sum(w * (y - pred) ** 2) / np.sum(w * (y - mean) ** 2)


def boot(stat, groups, rng, n=BOOT):
    """Lot-cluster bootstrap of stat(idx): (estimate, 5%, 95%)."""
    uniq = np.unique(groups)
    members = pd.Series(np.arange(len(groups))).groupby(groups).apply(np.asarray)
    vals = []
    for _ in range(n):
        pick = rng.choice(uniq, len(uniq))
        vals.append(stat(np.concatenate(members.loc[pick].to_numpy())))
    vals = np.asarray(vals)
    return float(stat(np.arange(len(groups)))), *map(
        float, np.quantile(vals, [0.05, 0.95])
    )


def building_table(table, bidx_of, weight_rows, n_b, cols):
    """Weighted mean (NaN-aware) of row columns per building."""
    x = table[cols].to_numpy(float)
    w = weight_rows[:, None] * np.isfinite(x)
    num = np.zeros((n_b, len(cols)))
    den = np.zeros((n_b, len(cols)))
    np.add.at(num, bidx_of, np.nan_to_num(x) * w)
    np.add.at(den, bidx_of, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def gate():
    post = np.load(explain.RUNS / C / "posterior.npz", allow_pickle=True)
    draws = post["kept/building"]
    draws = draws.reshape(-1, draws.shape[-1]).astype(np.float64)
    level, sd2 = draws.mean(0), draws.var(0)
    table = pd.read_parquet(OUT / "features.parquet")
    run_buildings = pd.Index(post["buildings"])
    tr = table[table.train.to_numpy()]
    bidx = run_buildings.get_indexer(tr.building)
    fam = json.loads((OUT / "families.json").read_text())
    out = {}
    for family, v1 in (("hpd", 1.38), ("elevfill", 2.42)):
        # v1 screened only the columns the run's own set lacks
        cols = [c for c, f in fam.items() if f == family and ":changed:" not in c]
        x = explained.building_means(tr[cols].to_numpy(float), bidx, len(level))
        rng = np.random.default_rng(0)
        shares = []
        for s in range(5):
            fold = np.random.default_rng(s).permutation(np.arange(len(level)) % FOLDS)
            shares.append(100 * explained.cv_r2(level, sd2, x, fold))
        out[family] = {
            "v1": v1,
            "shares": shares,
            "mean": float(np.mean(shares)),
            "columns": cols,
        }
        print(
            family,
            f"v1 {v1}  now {np.mean(shares):.2f}  seeds {np.round(shares, 2)}",
            flush=True,
        )
        del rng
    (OUT / "gate.json").write_text(json.dumps(out, indent=1))


def _static_setup():
    t = np.load(OUT / "targets.npz", allow_pickle=True)
    table = pd.read_parquet(OUT / "features.parquet")
    fam = json.loads((OUT / "families.json").read_text())
    rows = pd.read_parquet(OUT / "rows-bpart.parquet")
    tr = table.set_index("audit_id").loc[rows.audit_id].reset_index()
    w_rows = 1 / np.maximum(rows.bpart_var.to_numpy(), 1e-8)
    n_b = len(t["buildings"])
    lots = tr.groupby(rows.bidx.to_numpy()).bbl.first().reindex(range(n_b)).to_numpy()
    return t, tr, fam, rows, w_rows, n_b, lots


def static():
    t, tr, fam, rows, w_rows, n_b, lots = _static_setup()
    y, sd2 = t["static_mean"], t["static_var"]
    rng = np.random.default_rng(SEED)
    folds, groups = lot_folds(t["buildings"], lots, rng)
    bidx = rows.bidx.to_numpy()

    def cols_of(*families):
        return [c for c, f in fam.items() if f in families]

    asof, leaky = AS_OF, LEAKY
    variants = {
        "as-of, no coords": cols_of(*asof),
        "as-of, coords": cols_of(*asof, "coords"),
        "leaky all-row means, no coords": cols_of(*leaky),
        "leaky all-row means, coords": cols_of(*leaky, "coords"),
        "coords only": cols_of("coords"),
    }
    w_b = 1 / (sd2 + explained.residual_variance(np.ones((n_b, 1)), y, sd2))
    mean_b = np.sum(w_b * y) / w_b.sum()
    result = {
        "buildings": int(n_b),
        "lots": int(len(np.unique(groups))),
        "ceiling": {},
        "families": {},
    }
    preds = {}
    for name, cols in variants.items():
        x = building_table(tr, bidx, w_rows, n_b, cols)
        for method, fn in (("wls", wls_oof), ("lightgbm", gbm_oof)):
            p = (
                fn(y, sd2, x, folds)
                if method == "wls"
                else fn(y, sd2, x, folds, groups)
            )
            preds[(name, method)] = p
            share = boot(
                lambda i: 100 * r2(y, sd2, p, i), groups, np.random.default_rng(1)
            )
            # squared log error of the building target, weighted, before and after
            sle = boot(
                lambda i: float(
                    np.sum(w_b[i] * ((y[i] - mean_b) ** 2 - (y[i] - p[i]) ** 2))
                    / w_b[i].sum()
                ),
                groups,
                np.random.default_rng(1),
            )
            result["ceiling"][f"{name} / {method}"] = {
                "columns": len(cols),
                "explained_pct": share,
                "sle_drop": sle,
            }
            print(
                f"{name:34s} {method:9s} cols {len(cols):3d} explained {share[0]:.2f}% [{share[1]:.2f}, {share[2]:.2f}]  SLE drop {sle[0]:.5f}",
                flush=True,
            )
    np.savez(OUT / "static-oof.npz", **{f"{a}|{b}": v for (a, b), v in preds.items()})

    # Families, WLS with lot folds against a permutation null.
    for family in (
        "finish",
        "coded",
        "description",
        "predsize",
        "elevfill",
        "lines",
        "hpd",
        "stabilized",
        "lister",
        "retail",
        "noise",
        "trees",
        "crime",
        "petsfill",
        "pluto",
        "history",
    ):
        cols = cols_of(family)
        x = building_table(tr, bidx, w_rows, n_b, cols)
        prng = np.random.default_rng(SEED + 1)
        p = wls_oof(y, sd2, x, folds)
        explained_pct = 100 * r2(y, sd2, p)
        null = np.array(
            [
                100 * r2(y, sd2, wls_oof(y, sd2, x[prng.permutation(n_b)], folds))
                for _ in range(PERMUTATIONS)
            ]
        )
        ci = boot(
            lambda i: 100 * r2(y, sd2, p, i), groups, np.random.default_rng(2), 200
        )
        result["families"][family] = {
            "columns": cols,
            "explained_pct": explained_pct,
            "interval_90": ci[1:],
            "null_mean": float(null.mean()),
            "null_95": float(np.quantile(null, 0.95)),
            "beats_chance": bool(explained_pct > max(0.0, np.quantile(null, 0.95))),
        }
        print(
            f"family {family:12s} {explained_pct:6.2f}% [{ci[1]:.2f}, {ci[2]:.2f}] null95 {np.quantile(null, 0.95):.2f}",
            flush=True,
        )
    (OUT / "static.json").write_text(json.dumps(result, indent=1))


HELD = (
    "pluto",
    "hpd",
    "elevfill",
    "lines",
    "lister",
    "stabilized",
    "predsize",
    "retail",
    "noise",
    "trees",
    "crime",
    "petsfill",
)
AS_OF = HELD + ("finish", "coded", "description", "history")
LEAKY = HELD + ("leaky-finish", "leaky-coded", "leaky-description", "leaky-history")
# Building terms' share of C's descriptive share (variance.py on C: building
# 10.2%, building over time 5.6%, building slopes 4.1%).
BUILDING_DESCRIPTIVE_PP = 10.2 + 5.6 + 4.1


def residual(per_row_file):
    """Ceiling on C's per-row new-building residual (log ask minus the log
    predictive median of the new-building rung), and the board miss before and
    after shifting each row's predictive median by the out-of-fold prediction.
    Also shifts by the static target's out-of-fold building predictions."""
    per = pd.read_parquet(per_row_file)
    per = per[per.rung == "new building"].reset_index(drop=True)
    table = pd.read_parquet(OUT / "features.parquet").set_index("audit_id")
    tr = table.loc[per.audit_id].reset_index()
    fam = json.loads((OUT / "families.json").read_text())
    y, med = per.y.to_numpy(), per["median"].to_numpy()
    r = y - med
    lots = per.bbl.where(per.bbl.notna() & (per.bbl != "")).to_numpy()
    rng = np.random.default_rng(SEED)
    folds, groups = lot_folds(per.building.to_numpy(), lots, rng)
    zero = np.zeros(len(r))

    def miss(p, i):
        return 100 * np.median(np.abs(np.exp(med[i] + p[i] - y[i]) - 1))

    def cols_of(*families):
        return [c for c, f in fam.items() if f in families]

    base_miss = miss(zero, np.arange(len(r)))
    print(f"board new-building miss {base_miss:.3f}%", flush=True)
    result = {
        "rows": int(len(r)),
        "lots": int(len(np.unique(groups))),
        "board_miss": base_miss,
    }
    unknown = ~per.size_stated.to_numpy()
    preds = {}

    def report(label, p):
        preds[label] = p
        d = boot(
            lambda i: miss(p, i) - miss(zero, i), groups, np.random.default_rng(3), 200
        )
        sle = boot(
            lambda i: float(np.mean(r[i] ** 2 - (r[i] - p[i]) ** 2)),
            groups,
            np.random.default_rng(3),
            200,
        )
        result[label] = {
            "miss_change_pp": d,
            "sle_drop": sle,
            "sle_before": float(np.mean(r**2)),
        }
        print(
            f"{label:52s} miss {d[0]:+.3f} pp [{d[1]:+.3f}, {d[2]:+.3f}]  SLE drop {sle[0]:.5f} [{sle[1]:.5f}, {sle[2]:.5f}]",
            flush=True,
        )

    variants = {
        "as-of, no coords": cols_of(*AS_OF),
        "as-of, coords": cols_of(*AS_OF, "coords"),
        "leaky all-row means, no coords": cols_of(*LEAKY),
        "leaky all-row means, coords": cols_of(*LEAKY, "coords"),
    }
    for name, cols in variants.items():
        x = tr[cols].to_numpy(float)
        report(f"row target / {name} / wls", wls_oof(r, zero, x, folds))
        report(f"row target / {name} / lightgbm", gbm_oof(r, zero, x, folds, groups))

    # The static target's out-of-fold building predictions, applied to rows.
    t = np.load(OUT / "targets.npz", allow_pickle=True)
    bidx = pd.Index(t["buildings"]).get_indexer(per.building)
    oof = np.load(OUT / "static-oof.npz")
    bpart = pd.read_parquet(OUT / "rows-bpart.parquet").set_index("audit_id")
    bp = bpart.bpart_mean.reindex(per.audit_id).to_numpy()
    result["bpart_check_corr"] = float(np.corrcoef(bp, per.building_part)[0, 1])
    result["bpart_check_max_abs"] = float(np.max(np.abs(bp - per.building_part)))
    for key in oof.files:
        p = oof[key][bidx]
        report(f"static target / {key.replace('|', ' / ')}", p)
        fall = boot(
            lambda i: (
                BUILDING_DESCRIPTIVE_PP * (1 - np.var(bp[i] - p[i]) / np.var(bp[i]))
            ),
            groups,
            np.random.default_rng(4),
            200,
        )
        result[f"static target / {key.replace('|', ' / ')}"]["descriptive_fall_pp"] = (
            fall
        )

    # predsize case a on the size-unknown rows.
    cols = cols_of("predsize")
    p = wls_oof(r, zero, tr[cols].to_numpy(float), folds)
    u = np.flatnonzero(unknown)
    d = boot(
        lambda i: miss(p, u[i]) - miss(zero, u[i]),
        groups[u],
        np.random.default_rng(5),
        200,
    )
    result["predsize case a, size-unknown rows / wls"] = {"miss_change_pp": d}
    print(
        f"predsize case a on size-unknown rows: {d[0]:+.3f} pp [{d[1]:+.3f}, {d[2]:+.3f}]"
    )
    (OUT / "residual.json").write_text(json.dumps(result, indent=1))


def control(per_row_file):
    """The row target re-regressed on C's own feature columns alone, then on
    them plus the as-of columns: the first measures what a re-estimate of C's
    fixed part would give the new-building board, so the as-of columns' own
    gain is the difference."""
    _, frame, heldout = _load_frame()
    base = features.build(BASE, frame, ~heldout)
    own = pd.DataFrame(base.values, columns=[f"own:{n}" for n in base.names])
    own.insert(0, "audit_id", frame.audit_id.to_numpy())
    own = own.set_index("audit_id")
    per = pd.read_parquet(per_row_file)
    per = per[per.rung == "new building"].reset_index(drop=True)
    table = pd.read_parquet(OUT / "features.parquet").set_index("audit_id")
    fam = json.loads((OUT / "families.json").read_text())
    tr = table.loc[per.audit_id].reset_index()
    x_own = own.loc[per.audit_id].to_numpy(float)
    y, med = per.y.to_numpy(), per["median"].to_numpy()
    r = y - med
    lots = per.bbl.where(per.bbl.notna() & (per.bbl != "")).to_numpy()
    folds, groups = lot_folds(
        per.building.to_numpy(), lots, np.random.default_rng(SEED)
    )
    zero = np.zeros(len(r))

    def miss(p, i):
        return 100 * np.median(np.abs(np.exp(med[i] + p[i] - y[i]) - 1))

    asof = [c for c, f in fam.items() if f in AS_OF]
    x_asof = tr[asof].to_numpy(float)
    result = {}
    fits = {
        "own columns / wls": wls_oof(r, zero, x_own, folds),
        "own + as-of / wls": wls_oof(r, zero, np.column_stack([x_own, x_asof]), folds),
        "own columns / lightgbm": gbm_oof(r, zero, x_own, folds, groups),
        "own + as-of / lightgbm": gbm_oof(
            r, zero, np.column_stack([x_own, x_asof]), folds, groups
        ),
    }
    pairs = [(k, k, None) for k in fits] + [
        ("as-of increment / wls", "own + as-of / wls", "own columns / wls"),
        (
            "as-of increment / lightgbm",
            "own + as-of / lightgbm",
            "own columns / lightgbm",
        ),
    ]
    for label, a, b in pairs:
        pa, pb = fits[a], (fits[b] if b else zero)
        d = boot(
            lambda i: miss(pa, i) - miss(pb, i), groups, np.random.default_rng(6), 200
        )
        sle = boot(
            lambda i: float(np.mean((r[i] - pb[i]) ** 2 - (r[i] - pa[i]) ** 2)),
            groups,
            np.random.default_rng(6),
            200,
        )
        result[label] = {"miss_change_pp": d, "sle_drop": sle}
        print(
            f"{label:28s} miss {d[0]:+.3f} pp [{d[1]:+.3f}, {d[2]:+.3f}]  SLE drop {sle[0]:.5f} [{sle[1]:.5f}, {sle[2]:.5f}]",
            flush=True,
        )
    np.savez(
        OUT / "control-oof.npz", **{k.replace(" / ", "|"): v for k, v in fits.items()}
    )
    (OUT / "control.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    step = sys.argv[1]
    {
        "target": target,
        "features": build_features,
        "gate": gate,
        "static": static,
        "residual": lambda: residual(sys.argv[2]),
        "control": lambda: control(sys.argv[2]),
    }[step]()
