"""The site's Estimates table: what a drift fit expected for ads it never saw.

    python -m rentfrontier.drift_estimates publish LATEST_RUN --market MARKET_RUN \
        --registry REGISTRY.parquet --out DIR

A fit on the latest split (`drift_score`, `docs/leak-free-scoring.md`) holds out the newest ad
of every unit with at least two, so its predictive distribution for such an ad was fitted
without that ad: the gap between the ad's final ask and the model's median is a fair
reading of how the ask compares with the model. A fit on the market split holds out the ads
on the market on its scoring day. `publish` writes one row per held-out ad of both,
an ad in both taking the market fit's row, with the ask, the predictive median, the 50%, 80%
and 95% intervals and `below_share`, the share of the predictive distribution under the ask.

Ads that no fit held out (a unit's earlier ads, units seen once) have no estimate here: the
fits saw their asks, so a prediction for them would not be a fair test.

The folder holds `estimates.parquet` and `meta.json`, written last with the table's
sha256, so a reader can refuse a table that is not the one its meta describes. Both runs must
be fits of one model that passed the convergence gate.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import drift_deals, drift_score
from . import run as run_module
from .b0data import sha256

# Columns of `drift_score.score_run`'s `q` (its `Q` quantiles) for each interval bound.
BOUNDS = {"lo95": 0, "lo80": 2, "lo50": 3, "hi50": 4, "hi80": 5, "hi95": 7}
COLUMNS = (
    "listing_id",
    "audit_id",
    "source",
    "building",
    "address",
    "latitude",
    "longitude",
    "neighbourhood",
    "unit_id",
    "bedrooms",
    "full_baths",
    "half_baths",
    "day",
    "status",
    "ask",
    "model_median",
    *(f"model_{b}" for b in BOUNDS),
    "discount_pct",
    "below_share",
    "unit_ads",
)


def _result(run_dir: Path, split: str) -> dict:
    result = json.loads((run_dir / "result.json").read_text())
    if result.get("split") != split:
        raise SystemExit(f"{run_dir.name} is not a run on the {split} split")
    gate = drift_deals._gate(result)
    if not gate["passes"]:
        raise SystemExit(
            f"{run_dir.name} did not pass the convergence gate (max R-hat "
            f"{gate['max_rhat']}, min ESS {gate['min_ess']}); estimates are published "
            "only from fits that did"
        )
    return result


def _scores(run_dir: Path, held_ids: pd.Series) -> dict:
    """The run's held-out scores: its saved `pred_scores.npz` when that is the run's own,
    or `drift_score.score_run`."""
    path = run_dir / "pred_scores.npz"
    if path.exists():
        z = np.load(path)
        if "listing" in z:
            ids = z["listing"].astype(str)
            if len(ids) != len(held_ids) or (ids != held_ids.to_numpy(str)).any():
                raise SystemExit(f"{path} does not score {run_dir.name}'s held-out ads")
            return {k: z[k] for k in ("q", "pred", "cdf", "y", "elpd")}
    return drift_score.score_run(run_dir)


def table(
    run_dir: Path, source: str, registry: pd.DataFrame | None
) -> tuple[pd.DataFrame, dict]:
    """One row per ad the run at `run_dir` held out, and the scores they came from."""
    frame, h, held = drift_deals._held_frame(run_dir)
    res = _scores(run_dir, h.listing_id.astype(str))
    q = np.exp(np.asarray(res["q"], float))
    median = np.exp(np.asarray(res["pred"], float))
    ask = h.latest_ask.to_numpy(float)
    if not np.allclose(np.exp(np.asarray(res["y"], float)), ask, rtol=1e-4):
        raise SystemExit(f"{run_dir.name}'s scores are not of its held-out asks")
    unit_key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    train_units = unit_key[~held & frame.unit_id.notna().to_numpy()].value_counts()
    text = lambda c: h[c].where(h[c].notna(), "").astype(str)  # noqa: E731
    out = pd.DataFrame(
        {
            "listing_id": h.listing_id.astype(str),
            "audit_id": text("audit_id") if "audit_id" in h else "",
            "source": source,
            "building": h.building.astype(str),
            "neighbourhood": text("neighbourhood"),
            "unit_id": text("unit_id"),
            "bedrooms": h.bedrooms.to_numpy(float),
            "full_baths": h.full_baths.to_numpy(float),
            "half_baths": h.half_baths.to_numpy(float),
            "day": pd.to_datetime(h.latest_day).dt.strftime("%Y-%m-%d").to_numpy(),
            "status": text("status") if "status" in h else "",
            "ask": ask,
            "model_median": median.round(0),
            **{f"model_{b}": q[:, i].round(0) for b, i in BOUNDS.items()},
            "discount_pct": (100 * (median / ask - 1)).round(1),
            "below_share": np.asarray(res["cdf"], float).round(4),
            "unit_ads": unit_key[held]
            .map(train_units)
            .fillna(0)
            .astype(int)
            .to_numpy(),
        }
    )
    if registry is None:
        out["address"], out["latitude"], out["longitude"] = "", np.nan, np.nan
    else:
        reg = registry.reindex(out.building)
        out["address"] = [drift_deals.title_address(v) for v in reg.label]
        out["latitude"] = reg.latitude.to_numpy(float).round(5)
        out["longitude"] = reg.longitude.to_numpy(float).round(5)
    return out[list(COLUMNS)], res


def _provenance(record: dict) -> dict:
    return {
        "dataset": Path(record["dataset"]).name,
        "rows_sha256": record.get("dataset_observations_sha256"),
    }


def _registry(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    reg = pd.read_parquet(path, columns=["building", "label", "latitude", "longitude"])
    return reg.drop_duplicates("building").set_index("building")


def estimates(
    latest: Path, market: Path | None = None, registry: Path | None = None
) -> tuple[pd.DataFrame, dict]:
    """The table and the meta of `publish`, written nowhere."""
    record = _result(latest, "latest")
    model = record["model"]["name"]
    reg = _registry(registry)
    past, res = table(latest, "latest", reg)
    parts = [past]
    meta = {
        "model": model,
        "runs": {"latest": latest.name},
        "datasets": {"latest": _provenance(record)},
        "gate": {"latest": drift_deals._gate(record)},
        "heldout": drift_score.summary(res),
    }
    if market is not None:
        # The market fit must be on the market split of a market dataset, not a backtest,
        # with its ads table unchanged since the dataset was built.
        other, manifest = drift_deals._checked(market, backtest=False, model=model)
        _result(market, "market")
        meta["runs"]["market"] = market.name
        meta["datasets"]["market"] = _provenance(other)
        meta["gate"]["market"] = drift_deals._gate(other)
        meta["scoring_day"] = manifest.get("scoring_day")
        now, _ = table(market, "market", reg)
        parts = [past[~past.listing_id.isin(now.listing_id)], now]
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["day", "listing_id"], kind="stable").reset_index(drop=True)
    meta["ads"] = {
        "all": int(len(out)),
        **{s: int((out.source == s).sum()) for s in ("latest", "market")},
    }
    return out, meta


def publish(
    latest: Path, out: Path, market: Path | None = None, registry: Path | None = None
) -> dict:
    """Write `estimates.parquet` and then `meta.json` to the folder `out`. Everything is
    computed before anything is written, and each file goes under a temporary name first."""
    frame, meta = estimates(latest, market, registry)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f"estimates.parquet.{os.getpid()}.tmp"
    frame.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, out / "estimates.parquet")
    meta["estimates_sha256"] = sha256(out / "estimates.parquet")
    meta["published"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    drift_deals._replace(out / "meta.json", json.dumps(meta, indent=2))
    return meta


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", choices=("publish",))
    p.add_argument("run", help="the run on the latest split")
    p.add_argument("--market", help="the run on the market split")
    p.add_argument("--registry", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--runs", default=str(run_module.RUNS))
    args = p.parse_args(argv)
    runs = Path(args.runs)
    meta = publish(
        runs / args.run,
        args.out,
        runs / args.market if args.market else None,
        args.registry,
    )
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
