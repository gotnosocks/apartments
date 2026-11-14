"""Market disagreement, part 1: each held-out ad of L1 at its first ask, its days on the
market and its cuts, the cross-fitted fit of both outcomes on the gap, and the score D.

For each held-out ad I take the first ask and first day from the pipeline's ads file, put the
first ask on a net basis with `drift_deals.first_net`, and shift L1's predictive median from
the row's day to the first day by the change in the posterior mean of the weekly walk and of
the season curve. I keep the ads opened on or before CUTOFF, 90 days before the last fetch,
cap days at 90, and read a cut from the price history within 90 days of the first day.

The fit runs on one half of the buildings and predicts on the other: a shrunk cell mean
(borough by bedroom by quarter), then a piecewise-linear curve in z on the demeaned outcome.
`outcomes.parquet` holds the kept ads with both residuals and D, and `dose.json` the
dose-response by tenth of z."""

import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "causal-screens-2026-11-13")
)
import common as cm  # noqa: E402
from rentfrontier.drift_deals import first_net  # noqa: E402

OUT = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
ADS = "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet"
FETCH = pd.Timestamp("2026-10-19")
CAP = 90
CUTOFF = FETCH - pd.Timedelta(days=CAP)
SHRINK, CUT_TOL = 20, 0.001


def shift_of_median(day, first):
    """The change in L1's walk and season from `day` back to `first`, at posterior means."""
    z = np.load(cm.RUN + "posterior.npz", allow_pickle=True)
    start = pd.Timestamp(json.load(open(cm.RUN + "result.json"))["grid_start"])
    walk = z["kept/L"].reshape(-1, z["kept/L"].shape[-1]).mean(0)
    names = [str(n) for n in z["names"]]
    beta = z["kept/beta"].reshape(-1, len(names)).mean(0)
    waves = sorted(int(n[3:]) for n in names if n.startswith("sin") and n[3:].isdigit())

    def level(d):
        t = np.clip((d - start).dt.days.to_numpy() / 7, 0, len(walk) - 1 - 1e-9)
        wk = np.floor(t).astype(int)
        fr = t - wk
        out = (1 - fr) * walk[wk] + fr * walk[wk + 1]
        doy = d.dt.dayofyear.to_numpy() - 1 + 0.5
        for k in waves:
            angle = 2 * np.pi * k * doy / 365.25
            out = out + beta[names.index(f"sin{k}")] * np.sin(angle)
            out = out + beta[names.index(f"cos{k}")] * np.cos(angle)
        return out

    return level(first) - level(day)


def cuts_within(ids, first_day):
    """1 for a decrease in the price history within CAP days of the first day, NaN for an ad
    with no history in S3's records table."""
    f = pq.ParquetFile(cm.RECS)
    want = set(ids.astype(str))
    parts = []
    for g in range(f.num_row_groups):
        t = f.read_row_group(
            g, columns=["listing_id", "last_collected_at", "price_changes"]
        )
        t = t.filter(
            pc.is_in(
                t["listing_id"].cast("string"), value_set=pc.cast(list(want), "string")
            )
        )
        if t.num_rows:
            parts.append(t.to_pandas())
    r = pd.concat(parts)
    r["listing_id"] = r.listing_id.astype(str)
    r = r.sort_values("last_collected_at").drop_duplicates("listing_id", keep="last")
    first = dict(zip(ids.astype(str), first_day))
    out = {}
    for lid, text in zip(r.listing_id, r.price_changes):
        try:
            ch = json.loads(text) if text else []
        except ValueError:
            continue
        if not ch:
            continue
        ch = sorted(ch, key=lambda c: c["changedAt"])
        end = first[lid] + pd.Timedelta(days=CAP)
        cut = 0
        for a, b in zip(ch[:-1], ch[1:]):
            when = pd.Timestamp(b["changedAt"][:10])
            if b["price"] < a["price"] * (1 - CUT_TOL) and first[lid] <= when <= end:
                cut = 1
        out[lid] = cut
    return ids.astype(str).map(out)


def basis(z, knots):
    return np.column_stack(
        [np.ones(len(z)), z, *[np.clip(z - k, 0, None) for k in knots]]
    )


def crossfit(h, col):
    """The outcome less its cell mean less a curve in z, each fit on the other fold."""
    res = np.full(len(h), np.nan)
    fit = np.full(len(h), np.nan)
    for f in (0, 1):
        tr, te = h[h.fold != f], h[h.fold == f]
        mu = tr[col].mean()
        g = tr.groupby("cell")[col].agg(["sum", "count"])
        cell = (g["sum"] + SHRINK * mu) / (g["count"] + SHRINK)
        lo, hi = tr.z.quantile([0.005, 0.995])
        knots = tr.z.quantile(np.arange(1, 10) / 10).to_numpy()
        ztr, zte = tr.z.clip(lo, hi).to_numpy(), te.z.clip(lo, hi).to_numpy()
        base_tr = tr.cell.map(cell).to_numpy()
        base_te = te.cell.map(cell).fillna(mu).to_numpy()
        coef = np.linalg.lstsq(
            basis(ztr, knots), tr[col].to_numpy() - base_tr, rcond=None
        )[0]
        pred = base_te + basis(zte, knots) @ coef
        fit[h.fold.values == f] = pred
        res[h.fold.values == f] = te[col].to_numpy() - pred
    return fit, res


def main():
    os.makedirs(OUT, exist_ok=True)
    h = cm.heldout()
    a = np.load(cm.RUN + "pred_scores.npz", allow_pickle=True)
    qs = list(a["quantiles"])
    h["s"] = (a["q"][:, qs.index(0.75)] - a["q"][:, qs.index(0.25)]) / 1.349
    h["listing_id"] = h.listing_id.astype(str)
    ads = pd.read_parquet(
        ADS,
        columns=[
            "listing_id",
            "page_price",
            "months_free",
            "first_day",
            "first_ask",
            "status",
            "off_day",
        ],
    )
    ads["listing_id"] = ads.listing_id.astype(str)
    h = h.merge(ads.drop_duplicates("listing_id"), on="listing_id", how="left")
    h["first_day"] = pd.to_datetime(h.first_day, errors="coerce")
    h["off_day"] = pd.to_datetime(h.off_day, errors="coerce")
    n = {"held_out": len(h)}
    h["net_first"] = first_net(h.first_ask, h.latest_ask, h.page_price, h.months_free)
    h = h[h.first_day.notna() & (h.net_first > 0)]
    n["with_first_ask"] = len(h)
    h = h[(h.first_day - h.day).dt.days <= 7]
    n["first_day_not_after_row"] = len(h)
    h = h[h.first_day <= CUTOFF]
    n["opened_by_cutoff"] = len(h)
    h["days"] = (h.off_day.fillna(FETCH) - h.first_day).dt.days
    h = h[h.days >= 0].reset_index(drop=True)
    n["kept"] = len(h)
    h["on_at_fetch"] = h.off_day.isna()
    h["days90"] = h.days.clip(upper=CAP)
    h["moved"] = (np.abs(h.net_first / h.latest_ask - 1) > CUT_TOL) | (
        h.first_day != h.day
    )
    h["shift"] = shift_of_median(h.day, h.first_day)
    h["y1"] = np.log(h.net_first)
    h["pred1"] = h.pred + h["shift"]
    h["gap1"] = h.y1 - h.pred1
    h["z"] = h.gap1 / h.s
    hist = cuts_within(h.listing_id, h.first_day)
    fallback = (h.latest_ask / h.net_first - 1 < -CUT_TOL).astype(float)
    n["cut_from_history"] = int(hist.notna().sum())
    h["cut"] = hist.fillna(fallback).astype(float)
    beds = h.bedrooms.clip(upper=3).astype(int).astype(str)
    quarter = h.first_day.dt.to_period("Q").astype(str)
    h["cell"] = h.boro.fillna("?").astype(str) + "|" + beds + "|" + quarter
    h["ldays"] = np.log1p(h.days90)
    h["ldays_fit"], h["r_days"] = crossfit(h, "ldays")
    h["cut_fit"], h["r_cut"] = crossfit(h, "cut")
    h["D"] = (h.r_days / h.r_days.std() + h.r_cut / h.r_cut.std()) / 2
    h["tenth"] = pd.qcut(h.z, 10, labels=False) + 1

    def table(g):
        return {
            "ads": len(g),
            "z_lo": g.z.min(),
            "z_hi": g.z.max(),
            "gap_median": g.gap1.median(),
            "days_median": g.days.median(),
            "days90_mean": g.days90.mean(),
            "cut": g.cut.mean(),
            "gone_7": (g.days <= 7).mean(),
            "on_at_90": (g.days >= CAP).mean(),
            "rented": (g.status == "RENTED").mean(),
            "D_mean": g.D.mean(),
        }

    dose = pd.DataFrame({t: table(g) for t, g in h.groupby("tenth")}).T
    rho = h[["z", "days90", "cut"]].corr(method="spearman")
    info = {
        "counts": n,
        "moved_share": float(h.moved.mean()),
        "ask_moved_share": float(
            (np.abs(h.net_first / h.latest_ask - 1) > CUT_TOL).mean()
        ),
        "shift_abs_median_moved": float(h.loc[h.moved, "shift"].abs().median()),
        "spearman_z_days90": float(rho.loc["z", "days90"]),
        "spearman_z_cut": float(rho.loc["z", "cut"]),
        "status": h.status.value_counts().to_dict(),
        "cells": int(h.cell.nunique()),
        "r2_days": float(1 - h.r_days.var() / h.ldays.var()),
        "r2_cut": float(1 - h.r_cut.var() / h.cut.var()),
        "sd_r_days": float(h.r_days.std()),
        "sd_r_cut": float(h.r_cut.std()),
        "dose": dose.to_dict("index"),
    }
    json.dump(info, open(OUT + "dose.json", "w"), indent=1, default=float)
    keep = [
        "listing_id", "building", "unit_id", "neighbourhood", "boro", "bedrooms", "day",
        "first_day", "off_day", "status", "latest_ask", "net_first", "y", "pred", "s", "y1",
        "pred1", "gap", "gap1", "z", "days", "days90", "on_at_fetch", "cut", "cell", "fold",
        "r_days", "r_cut", "D", "tenth", "moved",
    ]  # fmt: skip
    h[keep].to_parquet(OUT + "outcomes.parquet")
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print({k: v for k, v in info.items() if k != "dose"})
    print(dose.round(3))


if __name__ == "__main__":
    main()
