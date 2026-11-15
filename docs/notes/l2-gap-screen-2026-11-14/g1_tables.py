"""Tables for the screen of L2's held-out gap: the gap (log ask less the predictive median) of
each held-out ad, by cells for the five candidate accounts, with building-clustered SEs.

The script joins L2's saved held-out predictions with the dataset's rows, the `prev_ending`
column, the pipeline's price columns and the per-ad process table of the raw status and price
histories. It writes the held-out ads with their cells to `h.parquet` for `g2_elpd.py`, and the
tables to `g1.json`. Inputs are read only.

    systemd-run --user --scope -q -p MemoryMax=3G \
        --setenv=PYTHONPATH=<worktree>/frontier/src \
        /data1/apartments/venvs/bridge-frontier/bin/python g1_tables.py <worktree>
"""

import json
import sys
import zlib

import numpy as np
import pandas as pd

WT = sys.argv[1]
sys.path.insert(0, WT + "/docs/notes/causal-screens-2026-11-13")
import common as c  # noqa: E402

RUN = (
    "/data1/apartments/frontier/runs/"
    "drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn/"
)
c.RUN = RUN
OUT = "/data1/apartments/tmp/sprint-20261114/gap-screen/"
PROC = "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet"
ENDING = c.DATA.replace("/rows.parquet", "-ending/rows.parquet")
PHASES = ["10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+"]
SNAP = pd.Timestamp("2026-11-09")
res = {}


def stats(v, b):
    """Count, median and mean of `v` in percent, the mean's building-clustered SE."""
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    v, b = v[ok], np.asarray(b)[ok]
    if len(v) < 2:
        return {"n": int(len(v))}
    s = pd.Series(v - v.mean()).groupby(b).sum()
    se = np.sqrt(len(s) / max(len(s) - 1, 1) * (s**2).sum()) / len(v)
    return {
        "n": int(len(v)),
        "median": round(100 * float(np.median(v)), 3),
        "mean": round(100 * float(v.mean()), 3),
        "se": round(100 * float(se), 3),
        "under": round(float((v < 0).mean()), 4),
    }


def table(h, key, col="gap"):
    return {str(k): stats(v[col], v.building) for k, v in h.groupby(key, observed=True)}


# rows, in dataset order
d = c.rows()
d = d.drop(
    columns=[
        "neighbourhood",
        "elevator",
        "doorman_type",
        "square_feet",
        "bbl",
        "boro",
        "manhattan",
        "rent_stabilized",
        "description_known",
        "latest_day",
        "day",
        "price_at",
        "full_baths",
    ]
)
d["listing_id"] = d.listing_id.astype(str)
BNAMES = d.building.astype(str).astype("category")
d["bname"] = BNAMES
d["building"] = BNAMES.cat.codes.to_numpy()
d["ukey"] = pd.factorize(d.ukey)[0]
d["unit_id"] = d.unit_id.notna()
d["prev_ending"] = (
    pd.read_parquet(ENDING, columns=["prev_ending"]).prev_ending.astype(str).to_numpy()
)
d["how"] = (
    pd.read_parquet(c.DATA, columns=["latest_ask_how"])
    .latest_ask_how.astype(str)
    .to_numpy()
)
d["ly"] = np.log(d.latest_ask.astype(float))
d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
nxt = d.ukey.eq(d.ukey.shift(-1))
d["prev_id"] = np.where(same, d.listing_id.shift(), None)
d["prev_at"] = d.priced.shift().where(same)
d["prev_ly"] = d.ly.shift().where(same)
d["next_at"] = d.priced.shift(-1).where(nxt)
d["is_last"] = ~nxt
d = d.sort_index()

# (b) which price a row carries, held-out against training
pp = pd.read_parquet(
    c.PIPE,
    columns=["listing_id", "asking_rent", "latest_ask", "latest_gross", "months_free"],
).drop_duplicates("listing_id")
pp["listing_id"] = pp.listing_id.astype(str)
pp = pp.rename(columns={"latest_ask": "pipe_latest"})
d = d.merge(pp, on="listing_id", how="left")
pr = pd.read_parquet(
    PROC,
    columns=[
        "listing_id",
        "final_st",
        "end_st",
        "t_on",
        "t_off",
        "run_days",
        "n_cut",
        "n_raise",
        "p0",
        "p1",
        "pmax",
    ],
).drop_duplicates("listing_id")
pr["listing_id"] = pr.listing_id.astype(str)
pr["t_on"] = pr.t_on.dt.tz_convert(None)
pr["t_off"] = pr.t_off.dt.tz_convert(None)
d = d.merge(pr, on="listing_id", how="left")
assert len(d) == len(np.load(RUN + "pred_scores.npz")["heldout"])
price = {}
for name, m in (("held", d.held.to_numpy()), ("train", ~d.held.to_numpy())):
    v = d[m]
    tr = v[v.is_last.to_numpy()] if name == "train" else v
    price[name] = {
        "rows": int(len(v)),
        "how": v.how.value_counts(normalize=True).round(4).to_dict(),
        "latest_equals_pipeline_latest": float(
            np.isclose(v.latest_ask, v.pipe_latest).mean()
        ),
        "latest_equals_asking_rent": float(
            np.isclose(v.latest_ask, v.asking_rent).mean()
        ),
        "latest_under_asking_rent": float(
            (v.latest_ask < v.asking_rent * 0.999).mean()
        ),
        "latest_over_asking_rent": float((v.latest_ask > v.asking_rent * 1.001).mean()),
        "latest_equals_last_price_p1": float(np.isclose(v.latest_ask, v.p1).mean()),
        "latest_equals_first_price_p0": float(np.isclose(v.latest_ask, v.p0).mean()),
        "months_free_coded": float(v.months_free.gt(0).mean()),
        "with_cut": float(v.n_cut.gt(0).mean()),
        "with_raise": float(v.n_raise.gt(0).mean()),
        "mean_log_last_over_first": float(
            np.log(v.p1 / v.p0).replace([np.inf, -np.inf], np.nan).mean()
        ),
        "median_run_days": float(v.run_days.median()),
        "no_off_time": float(v.t_off.isna().mean()),
        "final_st": v.final_st.value_counts(normalize=True).round(4).head(8).to_dict(),
    }
    if name == "train":
        price["train_latest_of_unit_with_2+"] = {
            "rows": int((tr.prev_id.notna()).sum()),
            "with_cut": float(tr[tr.prev_id.notna()].n_cut.gt(0).mean()),
            "no_off_time": float(tr[tr.prev_id.notna()].t_off.isna().mean()),
        }
res["price_rule"] = price
d = d.drop(
    columns=["asking_rent", "pipe_latest", "latest_gross", "months_free", "final_st"]
)
del pp
print(json.dumps(price, indent=1), flush=True)

# the unit's training record (h1_history.py's stand-in), from training rows alone
t = d.loc[
    ~d.held.to_numpy() & (d.latest_ask > 0),
    ["ukey", "building", "bedrooms", "ly", "priced"],
].copy()
t["mon"] = t.priced.dt.year * 12 + t.priced.dt.month
t["yr"] = t.priced.dt.year
dev = t.ly - t.groupby("ukey").ly.transform("mean")
idx = dev.groupby(t.mon).mean()
idx = idx.reindex(range(t.mon.min(), t.mon.max() + 1)).interpolate().bfill().ffill()
t["adj"] = t.ly - idx.reindex(t.mon).to_numpy()
cell = ["building", "bedrooms", "yr"]
G = t.groupby(cell).adj.agg(["sum", "size"])
U = (
    t.groupby(["ukey", *cell])
    .adj.agg(["sum", "size"])
    .reset_index()
    .join(G, on=cell, rsuffix="_g")
)
U["others"] = U.size_g - U["size"]
U = U[U.others >= 3].copy()
U["w_dev"] = U["sum"] - U["size"] * (U.sum_g - U["sum"]) / U.others
m = U.groupby("ukey")[["w_dev", "size"]].sum()
m["m"] = m.w_dev / m["size"]
unit = t.groupby("ukey").agg(n_train=("ly", "size")).join(m[["m"]])
del t, U, G

# pairs of consecutive ads, net of the mean change of all pairs with the same two quarters
p = d.loc[
    d.prev_id.notna() & d.unit_id,
    [
        "ukey",
        "building",
        "held",
        "is_last",
        "ly",
        "prev_ly",
        "priced",
        "prev_at",
        "next_at",
    ],
].copy()
p["chg"] = (p.ly - p.prev_ly).clip(-0.4, 0.4)
p["q0"] = p.prev_at.dt.to_period("Q").astype(str)
p["q1"] = p.priced.dt.to_period("Q").astype(str)
p["adj"] = p.chg - p.groupby(["q0", "q1"]).chg.transform("mean")
# the unit's last training change, netted against training pairs alone, since a feature may
# not read held-out rents
tq = p[~p.held.to_numpy()].groupby(["q0", "q1"]).chg.mean()
tq_key = pd.MultiIndex.from_frame(p[["q0", "q1"]])
p["adj_train"] = p.chg - tq.reindex(tq_key).fillna(tq.mean()).to_numpy()
p["since"] = (p.priced - p.prev_at).dt.days / 30.44
p["until"] = (p.next_at - p.priced).dt.days / 30.44
p["kind"] = np.where(
    p.held, "held-out latest", np.where(p.is_last, "training latest", "has successor")
)
p["yr"] = p.priced.dt.year
p["yrs"] = pd.cut(
    p.yr,
    [2013, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
    labels=["2014-18", "2019-20", "2021", "2022", "2023", "2024", "2025", "2026"],
).astype(str)
p["until_bin"] = pd.cut(
    p.until,
    [-1, 2.5, 9.5, 13.5, 21.5, 25.5, 37.5, 1e4],
    labels=["0-2", "3-9", "10-13", "14-21", "22-25", "26-37", "38+"],
).astype(str)
p["since_bin"] = pd.cut(
    p.since,
    [-1, 2.5, 9.5, 13.5, 21.5, 25.5, 1e4],
    labels=["0-2", "3-9", "10-13", "14-21", "22-25", "26+"],
).astype(str)
sel = {
    "pairs": int(len(p)),
    "by_kind": table(p, "kind", "adj"),
    "by_kind_year": {},
    "by_until": {},
}
for y, v in p.groupby("yrs"):
    sel["by_kind_year"][y] = table(v, "kind", "adj")
succ = p[p.kind == "has successor"]
sel["by_until"] = table(succ, "until_bin", "adj")
sel["by_until_ads_to_2022"] = table(succ[succ.yr <= 2022], "until_bin", "adj")
sel["by_until_since_10_13"] = table(succ[succ.since_bin == "10-13"], "until_bin", "adj")
sel["by_kind_since"] = {s: table(v, "kind", "adj") for s, v in p.groupby("since_bin")}
sel["latest_train_less_successor"] = c.cluster_mean_diff(
    p.adj[p.kind != "held-out latest"].to_numpy(),
    (p.kind[p.kind != "held-out latest"] == "training latest").to_numpy(),
    p.building[p.kind != "held-out latest"].to_numpy(),
)
sel["latest_held_less_successor"] = c.cluster_mean_diff(
    p.adj[p.kind != "training latest"].to_numpy(),
    (p.kind[p.kind != "training latest"] == "held-out latest").to_numpy(),
    p.building[p.kind != "training latest"].to_numpy(),
)
sel["latest_held_less_latest_train"] = c.cluster_mean_diff(
    p.adj[p.kind != "has successor"].to_numpy(),
    (p.kind[p.kind != "has successor"] == "held-out latest").to_numpy(),
    p.building[p.kind != "has successor"].to_numpy(),
)
res["selection"] = sel
print(json.dumps(sel, indent=1), flush=True)
# the change over the unit's last two training ads, for (c)
tp = (
    p[~p.held.to_numpy()]
    .sort_values(["ukey", "priced"])
    .groupby("ukey")
    .tail(1)[["ukey", "adj_train"]]
)
tp = tp.rename(columns={"adj_train": "last_train_chg"}).set_index("ukey")
del p, succ

# the held-out ads
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
h = d[d.held.to_numpy()].reset_index(drop=True)
del d
h["bcode"] = h.building
h["building"] = h.bname.astype(str)
assert (h.listing_id.to_numpy() == a["listing"].astype(str)).all()
assert np.allclose(h.ly, a["y"], atol=1e-6)
h["y"], h["pred"], h["usd"] = a["y"], a["pred"], a["unit_sd"]
h["gap"] = h.y - h.pred
h["phase"] = np.array(PHASES)[np.load(RUN + "posterior.npz")["kept/pred_phase"]]
h["fold"] = np.array([zlib.crc32(b.encode()) % 2 for b in h.building.astype(str)])
h = h.join(unit, on="ukey").join(tp, on="ukey")
prv = pr.rename(
    columns={k: "prev_" + k for k in pr.columns if k != "listing_id"}
).rename(columns={"listing_id": "prev_id"})
h = h.merge(prv, on="prev_id", how="left")
assert len(h) == len(a["y"])
res["all"] = stats(h.gap, h.building)
res["by_phase"] = table(h, "phase")

# (a) the previous ad
opens = h.t_on.fillna(h.priced).where(h.t_on.fillna(h.priced) < h.priced, h.priced)
known = h.prev_t_off.notna() & (h.prev_t_off < opens)
h["path"] = np.where(
    ~(known & h.prev_p0.notna()),
    "unknown",
    np.where(
        h.prev_pmax > h.prev_p0 * 1.001,
        "raised",
        np.where(h.prev_p1 < h.prev_p0 * 0.95, "cut5", "flat"),
    ),
)
h["end2"] = h.prev_ending.replace(
    {"delisted": "delisted or paused", "temp_off_market": "delisted or paused"}
)
res["a_by_ending"] = table(h, "prev_ending")
res["a_by_phase_ending"] = {ph: table(v, "prev_ending") for ph, v in h.groupby("phase")}
res["a_by_path"] = table(h, "path")
res["a_delisted_or_paused_less_rented"] = c.cluster_mean_diff(
    h.gap[h.end2.isin(["delisted or paused", "rented"])].to_numpy(),
    (
        h.end2[h.end2.isin(["delisted or paused", "rented"])] == "delisted or paused"
    ).to_numpy(),
    h.building[h.end2.isin(["delisted or paused", "rented"])].to_numpy(),
)

# (b) inside the held-out ad
h["cuts"] = np.where(
    h.n_cut.isna(),
    "unknown",
    np.where(h.n_cut == 0, "0", np.where(h.n_cut == 1, "1", "2+")),
)
h["raises"] = np.where(h.n_raise.isna(), "unknown", np.where(h.n_raise == 0, "0", "1+"))
h["dom"] = pd.cut(
    h.run_days,
    [-1, 7, 14, 30, 60, 120, 1e5],
    labels=["0-7", "8-14", "15-30", "31-60", "61-120", "121+"],
).astype(str)
h["own_end"] = h.end_st.fillna("none").replace({"IN_CONTRACT": "RENTED"})
h["open"] = h.t_off.isna()
h["gap_first"] = h.gap + np.log(h.p0 / h.p1)
h["gap_max"] = h.gap + np.log(h.pmax / h.p1)
res["b_by_cuts"] = table(h, "cuts")
res["b_by_raises"] = table(h, "raises")
res["b_by_cuts_raises"] = table(h, ["cuts", "raises"])
res["b_by_dom"] = table(h, "dom")
res["b_by_own_end"] = table(h, "own_end")
res["b_by_open"] = table(h, "open")
res["b_first_price_target"] = stats(
    h.gap_first.replace([np.inf, -np.inf], np.nan), h.building
)
res["b_highest_price_target"] = stats(
    h.gap_max.replace([np.inf, -np.inf], np.nan), h.building
)
res["b_first_price_by_cuts"] = table(
    h.assign(gap_first=h.gap_first.replace([np.inf, -np.inf], np.nan)),
    "cuts",
    "gap_first",
)
res["b_how"] = table(h, "how")
res["b_cut_less_none"] = c.cluster_mean_diff(
    h.gap[h.n_cut.notna()].to_numpy(),
    h.n_cut[h.n_cut.notna()].gt(0).to_numpy(),
    h.building[h.n_cut.notna()].to_numpy(),
)

# (c) the unit's record
h["m_bin"] = pd.cut(
    h.m,
    [-9, -0.15, -0.05, -0.015, 0.015, 0.05, 0.15, 9],
    labels=[
        "<-.15",
        "-.15:-.05",
        "-.05:-.015",
        "-.015:.015",
        ".015:.05",
        ".05:.15",
        ">.15",
    ],
).astype(str)
h["chg_bin"] = pd.cut(
    h.last_train_chg,
    [-9, -0.1, -0.03, -0.005, 0.005, 0.03, 0.1, 9],
    labels=[
        "<-.10",
        "-.10:-.03",
        "-.03:-.005",
        "-.005:.005",
        ".005:.03",
        ".03:.10",
        ">.10",
    ],
).astype(str)
res["c_by_m"] = table(h, "m_bin")
res["c_by_last_train_chg"] = table(h, "chg_bin")
x = h[h.m.notna()]
res["c_slope_on_m"] = c.wls_slope(x.gap, x.m.clip(-0.4, 0.4), x.building)[:2]
x = h[h.last_train_chg.notna()]
res["c_slope_on_last_chg"] = c.wls_slope(x.gap, x.last_train_chg, x.building)[:2]

# (d) the split
h["n_bin"] = pd.cut(
    h.n_train, [0, 1, 2, 4, 9, 1e4], labels=["1", "2", "3-4", "5-9", "10+"]
).astype(str)
h["usd_bin"] = pd.qcut(h.usd, 5, labels=["q1", "q2", "q3", "q4", "q5"]).astype(str)
h["since"] = (h.priced - h.prev_at).dt.days / 30.44
h["since_bin"] = pd.cut(
    h.since,
    [-1, 2.5, 9.5, 13.5, 21.5, 25.5, 37.5, 61.5, 1e4],
    labels=["0-2", "3-9", "10-13", "14-21", "22-25", "26-37", "38-61", "62+"],
).astype(str)
res["d_by_n_train"] = table(h, "n_bin")
res["d_by_unit_sd"] = table(h, "usd_bin")
res["d_by_since"] = table(h, "since_bin")

# (e) the date
h["yr"] = h.priced.dt.year
h["yrs"] = pd.cut(
    h.yr,
    [2013, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
    labels=["2014-18", "2019-20", "2021", "2022", "2023", "2024", "2025", "2026"],
).astype(str)
h["expo"] = (SNAP - h.priced).dt.days / 365.25
h["expo_bin"] = pd.cut(
    h.expo,
    [-1, 0.25, 0.5, 1, 2, 3, 5, 8, 99],
    labels=["0-3mo", "3-6mo", "6-12mo", "1-2y", "2-3y", "3-5y", "5-8y", "8y+"],
).astype(str)
h["half"] = (
    h.priced.dt.year.astype(str) + "H" + ((h.priced.dt.month > 6) + 1).astype(str)
)
res["e_by_year"] = table(h, "yr")
res["e_by_exposure"] = table(h, "expo_bin")
res["e_by_exposure_cuts"] = {k: table(v, "expo_bin") for k, v in h.groupby("cuts")}
res["e_by_exposure_open"] = {str(k): table(v, "expo_bin") for k, v in h.groupby("open")}
res["e_by_exposure_n_train"] = {k: table(v, "expo_bin") for k, v in h.groupby("n_bin")}

json.dump(res, open(OUT + "g1.json", "w"), indent=1)
keep = [
    "listing_id",
    "building",
    "fold",
    "gap",
    "phase",
    "prev_ending",
    "end2",
    "path",
    "cuts",
    "raises",
    "dom",
    "own_end",
    "open",
    "m_bin",
    "chg_bin",
    "n_bin",
    "usd_bin",
    "since_bin",
    "yr",
    "yrs",
    "half",
    "expo_bin",
    "expo",
    "n_cut",
    "run_days",
    "m",
    "last_train_chg",
    "n_train",
    "since",
]
h[keep].to_parquet(OUT + "h.parquet")
for k, v in res.items():
    if k not in ("price_rule", "selection"):
        print(k, json.dumps(v, indent=1), flush=True)
