"""Building turnover against j9's and L1's held-out gaps.

For each held-out ad the script counts its building's other ads opened in the 730 days before
its price day, divides by two and by the lot's residential units, and splits the gap by that
rate, alone and within bins of the building's training-ad count. It reads opening days and
counts, never a rent, apart from the held-out ads' own gaps. The predictions are in
`docs/notes/turnover-screen-2026-11-13.md`.

Run from the repo root inside a memory scope:

    systemd-run --user --scope -q -p MemoryMax=3G env JAX_PLATFORMS=cpu \
        /data1/apartments/venvs/nj-frontier/bin/python \
        docs/notes/turnover-screen-2026-11-13/screen.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "frontier/src"))
from rentfrontier import b0amenitycarry as ac  # noqa: E402
from rentfrontier.b0data import sha256  # noqa: E402

sys.path.insert(1, str(HERE.parents[1] / "causal-screens-2026-11-13"))
import common as c  # noqa: E402

J9 = Path("/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9")
L1 = Path(c.RUN)
SAVE = Path(c.OUT) / "turnover-screen.json"
WINDOW = 730
SPAN = 100_000
COUNT_BINS = [-1, 0, 4, 19, 99, 10**7]
COUNT_LABELS = ["0", "1-4", "5-19", "20-99", "100+"]
BANDS = ["none", "Q1", "Q2", "Q3", "Q4", "units unknown"]


def window_count(keys, opened, q_keys, q_day):
    """Rows of each query's key opened in [q_day - WINDOW, q_day)."""
    codes, _ = pd.factorize(pd.Series(np.r_[keys, q_keys]).astype(str))
    ca, cq = codes[: len(keys)].astype(np.int64), codes[len(keys) :].astype(np.int64)
    sorted_ = np.sort(ca * SPAN + opened)
    hi = np.searchsorted(sorted_, cq * SPAN + q_day, side="left")
    lo = np.searchsorted(sorted_, cq * SPAN + q_day - WINDOW, side="left")
    return hi - lo


def last_before(keys, opened, q_keys, q_day):
    """The latest opening day among rows of each query's key opened before q_day, or NaN."""
    codes, _ = pd.factorize(pd.Series(np.r_[keys, q_keys]).astype(str))
    ca, cq = codes[: len(keys)].astype(np.int64), codes[len(keys) :].astype(np.int64)
    sorted_ = np.sort(ca * SPAN + opened)
    at = np.searchsorted(sorted_, cq * SPAN + q_day, side="left") - 1
    found = sorted_[np.maximum(at, 0)]
    hit = (at >= 0) & (found // SPAN == cq)
    return np.where(hit, found % SPAN, np.nan)


def load(dataset: Path, held: np.ndarray) -> pd.DataFrame:
    """The dataset's rows with opening days, unit keys, lots and residential units, the
    building's training-ad count and first opening day, and the held-out mask."""
    manifest = json.loads((dataset / "manifest.json").read_text())
    ads = manifest["build"]["ads"]
    if sha256(Path(ads["path"])) != ads["sha256"]:
        sys.exit(f"{ads['path']} differs from the file {dataset} was built from")
    d = pd.read_parquet(
        dataset / "rows.parquet",
        columns=["listing_id", "building", "unit_id", "price_at", "latest_ask"],
    )
    assert len(d) == len(held)
    ids = set(d.listing_id.astype(str))
    on = ac.read_on_days(Path(ads["path"]), ids)
    on = on[~on.index.duplicated()]
    d["opened"] = ac.opening_days(d, on)
    d["price_day"] = ac.days(d.price_at)
    d["held"] = held
    d["ukey"] = np.where(
        d.unit_id.isna(),
        "row:" + d.listing_id.astype(str),
        d.building.astype(str) + "|" + d.unit_id.astype(str),
    )
    d["n_train"] = (~d.held).groupby(d.building).transform("sum").to_numpy()
    d["first_open"] = d.groupby("building").opened.transform("min")
    reg = pd.read_parquet(c.REG, columns=["building", "bbl"]).drop_duplicates(
        "building"
    )
    plu = pd.read_parquet(c.PLUTO, columns=["bbl", "unitsres"]).drop_duplicates("bbl")
    plu["unitsres"] = pd.to_numeric(plu.unitsres, errors="coerce")
    plu["bbl"] = plu.bbl.astype("string")
    reg["bbl"] = reg.bbl.astype("string")
    units = reg.merge(plu, on="bbl", how="left").set_index("building").unitsres
    d["units"] = d.building.map(units).where(lambda u: u > 0)
    return d


def tag(d: pd.DataFrame) -> pd.DataFrame:
    """The held-out rows with the building's other ads in the window and their rate per
    residential unit and year."""
    h = d[d.held].reset_index(drop=True)
    q_day = h.price_day.to_numpy()
    building = window_count(
        d.building.to_numpy(), d.opened.to_numpy(), h.building.to_numpy(), q_day
    )
    own = window_count(d.ukey.to_numpy(), d.opened.to_numpy(), h.ukey.to_numpy(), q_day)
    h["others"] = building - own
    h["rate"] = h.others / 2 / h.units
    h.loc[h.others == 0, "rate"] = 0.0
    # Checks added after the first results: the same count over training rows alone, which
    # leaves out the other held-out ads open at the time, and the unit's own training rows.
    t = d[~d.held]
    building = window_count(
        t.building.to_numpy(), t.opened.to_numpy(), h.building.to_numpy(), q_day
    )
    own = window_count(t.ukey.to_numpy(), t.opened.to_numpy(), h.ukey.to_numpy(), q_day)
    h["others_train"] = building - own
    h["rate_train"] = (h.others_train / 2 / h.units).where(h.others_train > 0, 0.0)
    h["unit_trained"] = h.ukey.isin(set(t.ukey))
    last = last_before(t.ukey.to_numpy(), t.opened.to_numpy(), h.ukey.to_numpy(), q_day)
    h["months_since_unit_ad"] = (q_day - last) / 30.44
    h["count"] = pd.cut(h.n_train, COUNT_BINS, labels=COUNT_LABELS).astype(str)
    h["first_year"] = (h.opened - h.first_open) / 30.44 <= 12
    return h


def band(h: pd.DataFrame, edges) -> pd.DataFrame:
    q1, q2, q3 = edges
    r = h.rate
    h["band"] = np.select(
        [h.others == 0, r.isna(), r <= q1, r <= q2, r <= q3],
        ["none", "units unknown", "Q1", "Q2", "Q3"],
        "Q4",
    )
    h["half"] = np.select([r.isna(), r <= q2], ["units unknown", "low"], "high")
    return h


def cell(v: pd.DataFrame) -> dict:
    return {
        "n": len(v),
        "buildings": int(v.building.nunique()),
        "gap_pct": 100 * float(v.gap.mean()),
        "se_pct": 100 * c.cluster_se(v.gap.to_numpy(), v.building.to_numpy()) / len(v)
        if v.building.nunique() > 1
        else None,
    }


def contrast(h: pd.DataFrame) -> dict:
    """Low less high turnover within each count bin, pooled with weights proportional to the
    bin's ads. A building sits in a single count bin, so the bins' SEs add in quadrature."""
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


def report(h: pd.DataFrame) -> dict:
    by_band = {}
    for b in BANDS:
        v = h[h.band == b]
        if len(v):
            by_band[b] = cell(v) | {
                "n_train_median": float(v.n_train.median()),
                "share_under_5_training_ads": float((v.n_train < 5).mean()),
                "rate_median": float(v.rate.median()),
            }
    cross = {
        f"{k} {b}": cell(v) for (k, b), v in h.groupby(["count", "band"]) if len(v)
    }
    halves = {
        f"{k} {b}": cell(v) for (k, b), v in h.groupby(["count", "half"]) if len(v)
    }
    known = h.rate.notna()
    rho = spearmanr(h.rate[known], h.n_train[known])
    return {
        "n": len(h),
        "first_year": int(h.first_year.sum()),
        "spearman_rate_n_train": float(rho.statistic),
        "under_5_training_ads": int((h.n_train < 5).sum()),
        "under_5_in_none": int(((h.n_train < 5) & (h.band == "none")).sum()),
        "by_band": by_band,
        "by_count": {k: cell(v) for k, v in h.groupby("count")},
        "by_count_band": cross,
        "by_count_half": halves,
        "contrast": contrast(h),
        "contrast_after_first_year": contrast(h[~h.first_year]),
        "checks": checks(h),
    }


def checks(h: pd.DataFrame) -> dict:
    """The pooled contrast with the rate counted over training rows alone (cut at the median
    of its nonzero values), and within ads whose unit has training rows and ads whose unit
    has none."""
    t = h.copy()
    cut = float(t.rate_train[t.others_train > 0].median())
    t["half"] = np.select(
        [t.rate_train.isna(), t.rate_train <= cut], ["units unknown", "low"], "high"
    )
    out = {
        "training_rate_median": cut,
        "contrast_training_rate": contrast(t),
        "unit_trained": int(h.unit_trained.sum()),
    }
    for k, v in (("unit_trained", h[h.unit_trained]), ("unit_new", h[~h.unit_trained])):
        out[f"by_band {k}"] = {b: cell(w) for b, w in v.groupby("band") if len(w) > 1}
        out[f"contrast {k}"] = contrast(v)
    # Among ads whose unit has an earlier training ad, the low-turnover slope with fixed
    # effects for the count bin alone, then for the count bin and the months since the
    # unit's latest earlier training ad.
    v = h[h.months_since_unit_ad.notna() & (h.half != "units unknown")]
    months = pd.cut(
        v.months_since_unit_ad, [-1, 12, 36, 10**4], labels=["<12", "12-36", "36+"]
    )
    low = (v.half == "low").to_numpy(float)
    for k, key in (
        ("slope_within_count", v["count"]),
        ("slope_within_count_and_months", v["count"] + " " + months.astype(str)),
    ):
        slope, se, _ = c.wls_slope(
            c.within(v.gap, key), c.within(low, key), v.building.to_numpy()
        )
        out[k] = {"n": len(v), "diff_pct": 100 * slope, "se_pct": 100 * se}
    # The ads priced from 2025-01-01 (day 20089) on, the year j9's held-out ads come from.
    out["contrast_priced_2025_on"] = contrast(h[h.price_day >= 20089])
    out["months_band_low_share"] = {
        str(m): [int((months == m).sum()), float(low[(months == m).to_numpy()].mean())]
        for m in months.cat.categories
    }
    return out


res = {"window_days": WINDOW}

# j9: the market split's held-out ads, with the gap from the mean location over kept draws.
z9 = np.load(J9 / "posterior.npz")
r9 = json.loads((J9 / "result.json").read_text())
d = load(Path(r9["dataset"]), z9["heldout"])
h9 = tag(d)
del d
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
nonzero = h9.rate[(h9.others > 0) & h9.rate.notna()]
edges = [float(x) for x in nonzero.quantile([0.25, 0.5, 0.75])]
res["edges_ads_per_unit_year"] = edges
res["j9"] = report(band(h9, edges))
del h9, z9

# L1: the latest split's held-out ads priced at least WINDOW days after the dataset's first
# opening day, with the gap from L1's median.
s = np.load(L1 / "pred_scores.npz", allow_pickle=True)
d = load(Path(c.DATA).parent, s["heldout"])
start = int(d.opened.min())
h1 = tag(d)
del d
assert (h1.listing_id.astype(str).to_numpy() == s["listing"]).all()
assert np.allclose(np.log(h1.latest_ask.to_numpy(float)), s["y"], atol=1e-6)
h1["gap"] = s["y"] - s["pred"]
inside = h1.price_day >= start + WINDOW
res["l1_heldout"] = len(h1)
res["l1_dropped_window_before_data"] = int((~inside).sum())
res["l1_first_opening_day"] = str(np.datetime64(start, "D"))
res["l1_heldout_first_price_day"] = str(np.datetime64(int(h1.price_day.min()), "D"))
res["l1_heldout_priced_before_2016"] = int((h1.price_day < 16801).sum())
res["l1"] = report(band(h1[inside].copy(), edges))

for k in ("j9", "l1"):
    r = res[k]
    print(k, r["n"], "rho", round(r["spearman_rate_n_train"], 3))
    print(pd.DataFrame(r["by_band"]).T.round(3).to_string())
    print(pd.DataFrame(r["by_count_half"]).T.round(3).to_string())
    print("contrast", json.dumps(r["contrast"]))
    print("after first year", json.dumps(r["contrast_after_first_year"]), flush=True)
    print("checks", json.dumps(r["checks"], indent=1), flush=True)
print("edges", edges)
SAVE.write_text(json.dumps(res, indent=1))
