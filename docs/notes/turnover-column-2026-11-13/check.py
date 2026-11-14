"""Checks for the note on the turnover column: the column against the screen's count on L1's
dataset, the rate's spread, the as-of units against the single 26v2 file the screen read, j9's
held-out bands with each ad's units read from its own release, and the bands against the co-op
and condo tenure.

j9's dataset differs from L1's, so the j9 part computes both columns on j9's rows in memory and
writes no dataset. Apart from the held-out ads' own gaps it reads opening days, units and
classes, never a rent.

Run from the repo root inside a memory scope:

    systemd-run --user --scope -q -p MemoryMax=3G env JAX_PLATFORMS=cpu \
        /data1/apartments/venvs/nj-frontier/bin/python \
        docs/notes/turnover-column-2026-11-13/check.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "frontier/src"))
from rentfrontier import b0coop  # noqa: E402
from rentfrontier import b0turnover as bt  # noqa: E402
from rentfrontier.b0data import sha256  # noqa: E402

sys.path.insert(1, str(HERE.parents[1] / "causal-screens-2026-11-13"))
import common as c  # noqa: E402

DS = Path("/data1/apartments/frontier/datasets")
SRC = DS / "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
OUT = SRC.with_name(SRC.name + "-turnover")
COOP = SRC.with_name(SRC.name + "-coop")
L1 = Path(c.RUN)
J9 = Path("/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9")
J9_SPLIT_DAY = "2025-11-10"
SCREEN = Path(c.OUT) / "turnover-screen.json"
SAVE = Path(c.OUT) / "turnover-column.json"
SPAN = 100_000
COUNT_BINS = [-1, 0, 4, 19, 99, 10**7]
COUNT_LABELS = ["0", "1-4", "5-19", "20-99", "100+"]
BANDS = ["none", "Q1", "Q2", "Q3", "Q4", "units unknown"]


def screen_count(keys, opened, q_keys, q_day):
    """The screen's `window_count`, copied: rows of each query's key opened in
    [q_day - 730, q_day)."""
    codes, _ = pd.factorize(pd.Series(np.r_[keys, q_keys]).astype(str))
    ca, cq = codes[: len(keys)].astype(np.int64), codes[len(keys) :].astype(np.int64)
    sorted_ = np.sort(ca * SPAN + opened)
    hi = np.searchsorted(sorted_, cq * SPAN + q_day, side="left")
    lo = np.searchsorted(sorted_, cq * SPAN + q_day - 730, side="left")
    return hi - lo


def screen_others(d, opened, rows):
    """The screen's count for the rows `rows` of `d`."""
    day = bt.days(d.price_at)
    b = d.building.astype(str).to_numpy(object)
    u = bt.unit_keys(d)
    return screen_count(b, opened, b[rows], day[rows]) - screen_count(
        u, opened, u[rows], day[rows]
    )


def lots_26v2():
    """Each building's lot in the single PLUTO file of `common` (26v2), joined through the
    registry as the screen joins it: `unitsres` and `yearbuilt` as numbers, `bldgclass` and
    `address`."""
    reg = pd.read_parquet(c.REG, columns=["building", "bbl"]).drop_duplicates(
        "building"
    )
    plu = pd.read_parquet(
        c.PLUTO, columns=["bbl", "unitsres", "yearbuilt", "bldgclass", "address"]
    ).drop_duplicates("bbl")
    plu["unitsres"] = pd.to_numeric(plu.unitsres, errors="coerce")
    plu["yearbuilt"] = pd.to_numeric(plu.yearbuilt, errors="coerce")
    plu["bbl"] = plu.bbl.astype("string")
    reg["bbl"] = reg.bbl.astype("string")
    return reg.merge(plu, on="bbl", how="left").set_index("building")


def screen_units(buildings, lots26):
    """The screen's units: `unitsres` above zero in 26v2."""
    return buildings.map(lots26.unitsres).where(lambda u: u > 0).to_numpy(float)


def rate(others, units):
    """Ads per residential unit and year, 0 with no other ads, NaN with units unknown."""
    r = others / 2 / np.where(units > 0, units, np.nan)
    return np.where(others == 0, 0.0, r)


def bands(others, r, edges):
    q1, q2, q3 = edges
    return np.select(
        [others == 0, np.isnan(r), r <= q1, r <= q2, r <= q3],
        ["none", "units unknown", "Q1", "Q2", "Q3"],
        "Q4",
    )


def halves(r, edges):
    return np.select([np.isnan(r), r <= edges[1]], ["units unknown", "low"], "high")


def edges_of(others, r):
    nonzero = r[(others > 0) & ~np.isnan(r)]
    return [float(x) for x in np.quantile(nonzero, [0.25, 0.5, 0.75])]


def cluster_se(x, b):
    """SE of the sum of `x` about its mean, clustered by `b`, as in
    `docs/notes/coop-column-2026-11-13/count.py`. Divided by the count of `x`, it gives the SE
    of the mean."""
    x = np.asarray(x, dtype=float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


def cell(v):
    n = len(v)
    return {
        "n": n,
        "buildings": int(v.building.nunique()),
        "gap_pct": 100 * float(v.gap.mean()) if n else None,
        "se_pct": 100 * cluster_se(v.gap.to_numpy(), v.building.to_numpy()) / n
        if v.building.nunique() > 1
        else None,
    }


def contrast(h):
    """The screen's pooled low-less-high contrast within count bins."""
    out, num, den, var = {}, 0.0, 0, 0.0
    for k in COUNT_LABELS:
        v = h[(h["count"] == k) & (h.half != "units unknown")]
        low, high = v.half == "low", v.half == "high"
        if low.sum() < 20 or high.sum() < 20:
            continue
        diff, se = c.cluster_mean_diff(
            v.gap.to_numpy(), low.to_numpy(), v.building.to_numpy()
        )
        out[k] = {"n": len(v), "diff_pct": 100 * diff, "se_pct": 100 * se}
        num, den, var = num + len(v) * diff, den + len(v), var + (len(v) * se) ** 2
    if den:
        out["pooled"] = {
            "n": den,
            "diff_pct": 100 * num / den,
            "se_pct": 100 * var**0.5 / den,
        }
    return out


def q1_less_q4(h):
    v = h[h.band.isin(["Q1", "Q4"])]
    diff, se = c.cluster_mean_diff(
        v.gap.to_numpy(), (v.band == "Q1").to_numpy(), v.building.to_numpy()
    )
    return {"n": len(v), "diff_pct": 100 * diff, "se_pct": 100 * se}


def by_band(h):
    return {b: cell(h[h.band == b]) for b in BANDS if (h.band == b).any()}


def shares(band, tenure):
    t = pd.crosstab(band, tenure)
    return {
        b: {"n": int(t.loc[b].sum())}
        | {k: float(t.loc[b, k] / t.loc[b].sum()) for k in t.columns}
        for b in BANDS
        if b in t.index
    }


def tenure_of(cls):
    condo, coop = b0coop.tenure(cls)
    return np.select([coop, condo], ["co-op", "condo"], "rental")


def gaps(h, edges):
    """Bands, halves, the gap by band and the pooled contrast for the held-out frame `h`."""
    h = h.copy()
    h["band"] = bands(h.others.to_numpy(), h.rate.to_numpy(), edges)
    h["half"] = halves(h.rate.to_numpy(), edges)
    return h, {
        "by_band": by_band(h),
        "q1_less_q4": q1_less_q4(h),
        "contrast": contrast(h),
    }


res = {}
screen = json.loads(SCREEN.read_text())
lots26 = lots_26v2()
edges_screen = screen["edges_ads_per_unit_year"]

# j9: the market split's held-out ads, as in the screen, with both columns computed here.
z9 = np.load(J9 / "posterior.npz")
ds9 = Path(json.loads((J9 / "result.json").read_text())["dataset"])
ads9 = json.loads((ds9 / "manifest.json").read_text())["build"]["ads"]
assert sha256(Path(ads9["path"])) == ads9["sha256"]
d = pd.read_parquet(
    ds9 / "rows.parquet",
    columns=["listing_id", "building", "unit_id", "price_at", "latest_ask"],
)
held = z9["heldout"]
assert len(held) == len(d)
opened = bt.opening_days(
    d, bt.read_on_days(Path(ads9["path"]), set(d.listing_id.astype(str)))
)
count = bt.other_ads(d, opened)
res["j9_rows"] = len(d)
res["j9_count_equals_screen_heldout"] = bool(
    (count[held] == screen_others(d, opened, held)).all()
)
n_train = (~pd.Series(held)).groupby(d.building.to_numpy()).transform("sum").to_numpy()
lots = b0coop.registry_lots(Path(c.REG), d.building)
h = d[held].reset_index(drop=True)
h["others"] = count[held]
h["n_train"] = n_train[held]
h["count"] = pd.cut(h.n_train, COUNT_BINS, labels=COUNT_LABELS).astype(str)
del d, opened, count
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h.latest_ask.to_numpy(float)), y9, atol=1e-6)
h["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
del z9

h["units_screen"] = screen_units(h.building.astype(str), lots26)
u = bt.units_asof(h, lots, b0coop.read_releases(b0coop.RELEASES, set(lots), "unitsres"))
h["units_asof"] = u.units.to_numpy()
h["status"] = u.status.to_numpy()
h["release"] = u.release.to_numpy()
cls = b0coop.classes(h, lots, b0coop.read_releases(b0coop.RELEASES, set(lots)))
h["tenure"] = tenure_of(cls.bldgclass.to_numpy())

s_known = h.units_screen > 0
a_known = h.units_asof > 0
both = s_known & a_known
ratio = np.log(h.units_asof[both] / h.units_screen[both])
res["j9_units"] = {
    "heldout": len(h),
    "status": h.status.value_counts().to_dict(),
    "asof_zero": int((h.units_asof == 0).sum()),
    "known_both": int(both.sum()),
    "equal": int((h.units_asof[both] == h.units_screen[both]).sum()),
    "asof_higher": int((ratio > 0).sum()),
    "asof_lower": int((ratio < 0).sum()),
    "abs_log_ratio_quantiles_differing": [
        float(x) for x in np.quantile(np.abs(ratio[ratio != 0]), [0.5, 0.9])
    ]
    if (ratio != 0).any()
    else None,
    "screen_known_asof_unknown": int((s_known & ~a_known).sum()),
    "screen_unknown_asof_known": int((~s_known & a_known).sum()),
    "releases_read": h.release.value_counts().sort_index().to_dict(),
}

h["rate"] = rate(h.others.to_numpy(), h.units_screen.to_numpy())
assert np.allclose(edges_of(h.others.to_numpy(), h.rate.to_numpy()), edges_screen)
hs, res["j9_screen_units"] = gaps(h, edges_screen)
assert {b: v["n"] for b, v in res["j9_screen_units"]["by_band"].items()} == {
    b: v["n"] for b, v in screen["j9"]["by_band"].items()
}
# The screen's note gives SEs from `common.cluster_se`, which sums the gaps by building without
# first taking out their mean. Both forms, by band, in percent:
res["j9_screen_se_published_vs_demeaned"] = {
    b: [screen["j9"]["by_band"][b]["se_pct"], v["se_pct"]]
    for b, v in res["j9_screen_units"]["by_band"].items()
}

h["rate"] = rate(h.others.to_numpy(), h.units_asof.to_numpy())
edges_asof = edges_of(h.others.to_numpy(), h.rate.to_numpy())
res["edges_screen"] = edges_screen
res["edges_asof"] = edges_asof
ha, res["j9_asof_units"] = gaps(h, edges_asof)
hf, res["j9_asof_units_screen_edges"] = gaps(h, edges_screen)
for k, v in (("asof_edges", ha), ("screen_edges", hf)):
    t = pd.crosstab(hs.band, v.band)
    res[f"j9_band_moves_{k}"] = {
        "changed": int((hs.band != v.band).sum()),
        "crosstab": {f"{a} -> {b}": int(n) for (a, b), n in t.stack().items() if n},
    }

# Tenure from each ad's own release, as the co-op column reads it, against the as-of bands.
res["j9_tenure_share_by_band"] = shares(ha.band, ha.tenure)
res["j9_tenure_share_all"] = ha.tenure.value_counts(normalize=True).to_dict()
res["j9_by_tenure"] = {k: cell(v) for k, v in ha.groupby("tenure")}
rent = ha[ha.tenure == "rental"]
res["j9_rentals"] = {
    "by_band": by_band(rent),
    "q1_less_q4": q1_less_q4(rent),
    "contrast": contrast(rent),
}
res["j9_all_q1_less_q4"] = res["j9_asof_units"]["q1_less_q4"]
j9_counts = pd.DataFrame(
    {
        "count": h.others.to_numpy(),
        "day": bt.days(h.price_at),
        "building": h.building.astype(str).to_numpy(),
    },
    index=h.listing_id.astype(str).to_numpy(),
)
del h, hs, ha, hf, rent

# L1: the new dataset's columns against the screen's count, the rate's spread, the units
# against the single release, and the tenure columns.
m = json.loads((SRC / "manifest.json").read_text())
res["src_rows_unchanged"] = sha256(SRC / "rows.parquet") == m["rows_sha256"]
mo = json.loads((OUT / "manifest.json").read_text())
res["out_rows_sha256_matches"] = sha256(OUT / "rows.parquet") == mo["rows_sha256"]
d = pd.read_parquet(
    OUT / "rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        bt.COUNT,
        bt.UNITS,
    ],
)
src_ids = pd.read_parquet(SRC / "rows.parquet", columns=["listing_id"]).listing_id
res["l1_order_kept"] = bool((src_ids.to_numpy() == d.listing_id.to_numpy()).all())
del src_ids
co = pd.read_parquet(COOP / "rows.parquet", columns=["listing_id", "coop", "condo"])
assert (co.listing_id.to_numpy() == d.listing_id.to_numpy()).all()
d["tenure"] = np.select([co.coop, co.condo], ["co-op", "condo"], "rental")
del co
ads1 = Path(m["build"]["ads"]["path"])
opened = bt.opening_days(d, bt.read_on_days(ads1, set(d.listing_id.astype(str))))
everyone = np.ones(len(d), bool)
res["l1_count_equals_screen"] = bool(
    (d[bt.COUNT].to_numpy() == screen_others(d, opened, everyone)).all()
)
del opened
# j9's held-out ads in L1's dataset: the count from L1's column against j9's own rows, over
# all of them and over those L1 prices on the same day in the same building.
l1_counts = pd.DataFrame(
    {
        "count": d[bt.COUNT].to_numpy(),
        "day": bt.days(d.price_at),
        "building": d.building.astype(str).to_numpy(),
    },
    index=d.listing_id.astype(str).to_numpy(),
)
shared = j9_counts.index.intersection(l1_counts.index)
a, b = l1_counts.loc[shared], j9_counts.loc[shared]
same = (a.day.to_numpy() == b.day.to_numpy()) & (
    a.building.to_numpy() == b.building.to_numpy()
)
# The ads L1 doesn't price on j9's day in j9's building: whether L1 puts them in another
# building, or prices them later, after the day of j9's market split.
same_building = a.building.to_numpy() == b.building.to_numpy()
later = a.day.to_numpy() > b.day.to_numpy()
split_day = bt.days(pd.Series(pd.to_datetime([J9_SPLIT_DAY], utc=True)))[0]
res["j9_heldout_in_l1"] = {
    "not_same_day_building": {
        "n": int((~same).sum()),
        "other_building": int((~same_building).sum()),
        "same_building_l1_later": int((same_building & later).sum()),
        "same_building_l1_earlier": int((same_building & ~later & ~same).sum()),
        "l1_later": int((~same & later).sum()),
        "l1_after_split_day": int((~same & (a.day.to_numpy() > split_day)).sum()),
        "j9_after_split_day": int((b.day.to_numpy() > split_day).sum()),
    }
}
for k, keep in (("all", np.ones(len(shared), bool)), ("same_day_building", same)):
    diff = a["count"].to_numpy()[keep] - b["count"].to_numpy()[keep]
    res["j9_heldout_in_l1"][k] = {
        "n": int(keep.sum()),
        "same_count": int((diff == 0).sum()),
        "l1_higher": int((diff > 0).sum()),
        "l1_lower": int((diff < 0).sum()),
        "abs_diff_quantiles": [float(x) for x in np.quantile(np.abs(diff), [0.5, 0.9])],
        "j9_count_median": float(np.median(b["count"].to_numpy()[keep])),
    }
del l1_counts, j9_counts, a, b
s = np.load(L1 / "pred_scores.npz", allow_pickle=True)
d["held"] = s["heldout"]
d["units_screen"] = screen_units(d.building.astype(str), lots26)

# The as-of units against 26v2's. A factor counts both ways, so 3 units against 30 is a
# factor of 10.
building = d.building.astype(str)
asof = d[bt.UNITS].to_numpy()
now = building.map(lots26.unitsres).to_numpy(float)
both = (asof > 0) & (now > 0)
with np.errstate(divide="ignore", invalid="ignore"):
    factor = np.where(both, np.maximum(asof / now, now / asof), np.nan)
x10 = factor >= 10
condo_26v2 = building.map(lots26.bldgclass).fillna("").astype(str).str.startswith("R")
big = pd.DataFrame(
    {"building": building[x10], "asof": asof[x10], "now": now[x10]}
).groupby("building")
top = big.agg(
    rows=("asof", "size"),
    asof_min=("asof", "min"),
    asof_max=("asof", "max"),
    now=("now", "first"),
).sort_values("rows", ascending=False)
res["l1_units_vs_26v2"] = {
    "known_both": int(both.sum()),
    "differ": int((both & (asof != now)).sum()),
    "factor_2_or_more": int((factor >= 2).sum()),
    "factor_10_or_more": int(x10.sum()),
    "factor_10_asof_lower": int((x10 & (asof < now)).sum()),
    "factor_10_condo_own_release": float((d.tenure[x10] == "condo").mean()),
    "factor_10_condo_26v2": float(condo_26v2[x10].mean()),
    "factor_10_condo_either": float(((d.tenure == "condo") | condo_26v2)[x10].mean()),
    "factor_10_buildings": len(top),
    "factor_10_top_buildings": {
        k: {**{f: float(x) for f, x in v.items()}, "address": lots26.address.get(k)}
        for k, v in top.head(10).iterrows()
    },
    "asof_zero": int((asof == 0).sum()),
    "asof_zero_26v2_above_zero": int(((asof == 0) & (now > 0)).sum()),
}
del big, top

# The release each row reads, against the year 26v2 gives for the lot's building. Unlike
# `features.released_lots`, the column keeps a release published before that year.
lots1 = b0coop.registry_lots(Path(c.REG), d.building)
table1 = b0coop.read_releases(b0coop.RELEASES, set(lots1), "unitsres")
u1 = bt.units_asof(d, lots1, table1)
assert np.array_equal(u1.units.to_numpy(), asof, equal_nan=True)
published = pd.to_datetime(
    table1.dropna(subset=["published"])
    .drop_duplicates("release")
    .set_index("release")
    .published
)
read_year = u1.release.map(published.dt.year).to_numpy(float)
built = building.map(lots26.yearbuilt).to_numpy(float)
early = (u1.status == bt.STATUSES[0]).to_numpy() & (built > read_year)
held1 = d.held.to_numpy()
res["l1_release_before_year_built"] = {
    "rows": int(early.sum()),
    "share": float(early.mean()),
    "heldout": int((early & held1).sum()),
    "heldout_share": float(early[held1].mean()),
    "buildings": int(building[early].nunique()),
    "units_zero": int((early & (asof == 0)).sum()),
    "units_below_26v2": int((early & (asof < now)).sum()),
    "units_equal_26v2": int((early & (asof == now)).sum()),
    "share_of_asof_zero": float(early[asof == 0].mean()),
}
del u1, table1, lots1, read_year, built, early, factor, now, asof, building

others = d[bt.COUNT].to_numpy()
units = d[bt.UNITS].to_numpy()
d["rate"] = rate(others, units)
d["band"] = bands(others, d.rate.to_numpy(), edges_screen)
d["band_screen_units"] = bands(
    others, rate(others, d.units_screen.to_numpy()), edges_screen
)


def spread(v):
    r = v.rate[(v[bt.COUNT] > 0) & v.rate.notna()]
    return {
        "rows": len(v),
        "count_zero": int((v[bt.COUNT] == 0).sum()),
        "count_quantiles": [
            float(x) for x in v[bt.COUNT].quantile([0.25, 0.5, 0.75, 0.9])
        ],
        "units_missing": int(v[bt.UNITS].isna().sum()),
        "units_zero": int((v[bt.UNITS] == 0).sum()),
        "units_differ_from_screen": int(
            (
                (v[bt.UNITS] > 0)
                & (v.units_screen > 0)
                & (v[bt.UNITS] != v.units_screen)
            ).sum()
        ),
        "units_known_both": int(((v[bt.UNITS] > 0) & (v.units_screen > 0)).sum()),
        "rate_nonzero_quantiles": [
            float(x) for x in r.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        ],
        "bands_screen_edges": v.band.value_counts().to_dict(),
        "band_changed_vs_screen_units": int((v.band != v.band_screen_units).sum()),
    }


res["l1_all"] = spread(d)
res["l1_heldout"] = spread(d[d.held])
res["l1_tenure_share_by_band"] = shares(d.band, d.tenure)
res["l1_tenure_share_all"] = d.tenure.value_counts(normalize=True).to_dict()
units_by_tenure = d[d[bt.UNITS] > 0].groupby("tenure")[bt.UNITS].median()
res["l1_units_median_by_tenure"] = units_by_tenure.to_dict()
rate_by_tenure = d[(d[bt.COUNT] > 0) & d.rate.notna()].groupby("tenure").rate.median()
res["l1_rate_median_by_tenure"] = rate_by_tenure.to_dict()

# L1's held-out gaps by band with the as-of units, for comparison with the screen's L1 part.
h = d[d.held].reset_index(drop=True)
assert (h.listing_id.astype(str).to_numpy() == s["listing"]).all()
h["gap"] = s["y"] - s["pred"]
n_train = (~d.held).groupby(d.building).transform("sum").to_numpy()[d.held.to_numpy()]
h["count"] = pd.cut(n_train, COUNT_BINS, labels=COUNT_LABELS).astype(str)
h["others"] = h[bt.COUNT]
h["half"] = halves(h.rate.to_numpy(), edges_screen)
res["l1_heldout_gaps"] = {
    "by_band": by_band(h),
    "q1_less_q4": q1_less_q4(h),
    "contrast": contrast(h),
}

SAVE.write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
