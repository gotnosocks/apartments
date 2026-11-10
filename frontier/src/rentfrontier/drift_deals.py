"""The deals table of a drift fit on a market dataset, and a check of what a low ask means.

    python -m rentfrontier.drift_deals deals RUN --ads ADS.parquet --registry REGISTRY.parquet --out DIR
    python -m rentfrontier.drift_deals validate RUN --ads ADS.parquet --out FILE.json

`deals` reads a run on the `market` split of a `rentfrontier.market` dataset. Its held-out
rows are the ads on the market on the scoring day. For each one the table gives the ask, the
model's predictive median and intervals for the ad's final ask in dollars, and
- `below_share`: the share of the predictive distribution under the ask. An ask at 0.05
  is lower than 95% of what the model expects for this apartment on that day;
- `discount_pct`: how far the ask sits under the predictive median, in percent of the ask;
- `unit_ads`: the unit's ads in the training rows. A unit with earlier ads carries its own
  level, so its range is narrower than a new unit's.
The table is sorted by `below_share`. It is written as deals.parquet and deals.json.

A low ask can mark a bargain or a flaw the ad does not state. `validate` measures which, on
a run whose held-out rows have final asks (a backtest dataset, or the latest split): it places
each ad's first ask in the predictive distribution, a distribution fitted without that ad,
and reports by tenth of that position how long the ads stayed on the market and how their
asks changed before they closed. If ads placed low are taken quickly and seldom cut, the
market agrees that they were cheap.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import drift_score

AD_FIELDS = (
    "listing_id",
    "page",
    "square_feet",
    "months_free",
    "days_on_market",
    "first_day",
    "first_ask",
    "status",
    "off_day",
)
ORDINAL = {1: "st", 2: "nd", 3: "rd"}


def title_address(label) -> str:
    """'134 WEST 23 STREET, New York, NY, USA' as '134 West 23rd Street'."""
    if not isinstance(label, str) or not label:
        return ""
    words = label.split(",")[0].title().split()

    def ordinal(w, i):
        if i == 0 or not w.isdigit():
            return w
        n = int(w)
        return w + ("th" if 10 <= n % 100 <= 20 else ORDINAL.get(n % 10, "th"))

    return " ".join(ordinal(w, i) for i, w in enumerate(words))


def unit_label(page) -> str:
    """The unit's label from its page URL: '.../6b' as '6B'."""
    if not isinstance(page, str) or "/" not in page:
        return ""
    return re.sub(r"[?#].*$", "", page.rstrip("/").rsplit("/", 1)[1]).upper()


def _held_frame(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    result = json.loads((run_dir / "result.json").read_text())
    frame = pd.read_parquet(Path(result["dataset"]) / "rows.parquet")
    held = np.load(run_dir / "posterior.npz")["heldout"]
    return frame, frame[held].reset_index(drop=True), held


def _ads(ads: Path, listing_ids) -> pd.DataFrame:
    a = pd.read_parquet(ads, columns=list(AD_FIELDS))
    a = a.assign(listing_id=a.listing_id.astype(str)).drop_duplicates("listing_id")
    return a.set_index("listing_id").reindex(pd.Index(listing_ids).astype(str))


def deals(run_dir: Path, ads: Path, registry: Path | None = None) -> pd.DataFrame:
    """One row per ad on the market, lowest `below_share` first."""
    frame, h, held = _held_frame(run_dir)
    res = drift_score.score_run(run_dir)
    a = _ads(ads, h.listing_id)
    q = np.exp(res["q"].astype(float))
    ask = h.latest_ask.to_numpy(float)
    median = np.exp(res["pred"])
    train_units = frame.unit_id[~held].value_counts()
    out = pd.DataFrame(
        {
            "listing_id": h.listing_id.astype(str),
            "url": "https://streeteasy.com/rental/" + h.listing_id.astype(str),
            "building": h.building.astype(str),
            "unit": [unit_label(p) for p in a.page],
            "neighbourhood": h.neighbourhood.astype(str),
            "bedrooms": h.bedrooms.to_numpy(float),
            "full_baths": h.full_baths.to_numpy(float),
            "half_baths": h.half_baths.to_numpy(float),
            "square_feet": a.square_feet.to_numpy(float),
            "status": h.status.astype(str),
            "ask": ask,
            "first_ask": a.first_ask.to_numpy(float),
            "months_free": a.months_free.to_numpy(float),
            "first_day": a.first_day.astype(str).to_numpy(),
            "days_on_market": a.days_on_market.to_numpy(float),
            "model_median": median.round(0),
            "model_lo50": q[:, 3].round(0),
            "model_hi50": q[:, 4].round(0),
            "model_lo80": q[:, 2].round(0),
            "model_hi80": q[:, 5].round(0),
            "model_lo95": q[:, 0].round(0),
            "model_hi95": q[:, 7].round(0),
            "discount_pct": (100 * (median / ask - 1)).round(1),
            "below_share": res["cdf"].round(4),
            "unit_ads": h.unit_id.map(train_units).fillna(0).astype(int).to_numpy(),
            "unit_sd": res["unit_sd"].round(4),
        }
    )
    if registry is not None:
        reg = pd.read_parquet(
            registry, columns=["building", "label", "latitude", "longitude"]
        )
        reg = (
            reg.drop_duplicates("building").set_index("building").reindex(out.building)
        )
        out["address"] = [title_address(v) for v in reg.label]
        out["latitude"] = reg.latitude.to_numpy(float).round(5)
        out["longitude"] = reg.longitude.to_numpy(float).round(5)
    return out.sort_values("below_share", kind="stable").reset_index(drop=True)


def validate(run_dir: Path, ads: Path, bins: int = 10) -> dict:
    """By tenth of the first ask's place in the predictive distribution: the ads, their
    median days on the market, the shares whose ask was cut or raised before closing, and the
    median change from first to final ask. Also the final asks' scores (`drift_score.summary`)."""
    frame, h, held = _held_frame(run_dir)
    a = _ads(ads, h.listing_id)
    first = a.first_ask.to_numpy(float)
    final = h.latest_ask.to_numpy(float)
    ok = np.isfinite(first) & (first > 0)
    res = drift_score.score_run(run_dir, at=np.log(np.where(ok, first, final)))
    place = res["cdf_at"]
    day = pd.to_datetime(h.final_day if "final_day" in h else h.latest_day)
    off = pd.to_datetime(a.off_day).to_numpy()
    end = np.where(np.isnat(off), day.to_numpy(), off)
    days = (end - pd.to_datetime(a.first_day).to_numpy()) / np.timedelta64(1, "D")
    ok &= np.isfinite(days) & (days >= 0)
    change = final / np.where(ok, first, 1.0) - 1
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = ok & (place >= lo) & ((place < hi) | (hi == 1))
        if not m.any():
            continue
        rows.append(
            {
                "place": f"{lo:.1f} to {hi:.1f}",
                "ads": int(m.sum()),
                "median_days_on_market": float(np.median(days[m])),
                "mean_days_on_market": float(days[m].mean()),
                "share_within_14_days": float((days[m] <= 14).mean()),
                "share_cut": float((change[m] < -0.001).mean()),
                "share_raised": float((change[m] > 0.001).mean()),
                "median_change_pct": float(100 * np.median(change[m])),
                "mean_change_pct": float(100 * change[m].mean()),
            }
        )
    return {
        "run": run_dir.name,
        "ads_with_first_ask": int(ok.sum()),
        "final_ask_scores": drift_score.summary(res),
        "by_first_ask_place": rows,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", choices=("deals", "validate"))
    p.add_argument("run")
    p.add_argument("--ads", type=Path, required=True)
    p.add_argument("--registry", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--runs", default="/data1/apartments/frontier/runs")
    args = p.parse_args(argv)
    run_dir = Path(args.runs) / args.run
    if args.command == "validate":
        out = validate(run_dir, args.ads)
        args.out.write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return
    table = deals(run_dir, args.ads, args.registry)
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out / "deals.parquet", index=False)
    table.to_json(args.out / "deals.json", orient="records")
    print(table.head(20).to_string())
    print(f"wrote {len(table)} ads to {args.out}")


if __name__ == "__main__":
    main()
