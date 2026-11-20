"""A report on the kept quantities of a drift fit that the convergence gate does not read.

    python -m rentfrontier.drift_kept_report RUN [--out FILE.json] [--runs DIR]

The gate reads the traced scalars and coefficients. A drift fit also keeps, at every 20th
sweep, each scored ad's predicted location (`kept/pred_loc`), from which the Deals order is
made, and each building's level (`kept/bld`). This command lists the items of both that
deserve a look after a fit (`docs/notes/kept-rhat-audit-2026-11-20.md`,
`docs/notes/building-level-read-2026-11-20.md`):

- `ads`: the scored ads whose `pred_loc` has split R-hat over `RHAT`, with their place in
  the order of `below_share` that `drift_deals.deals` uses.
- `buildings`: the buildings whose level has split R-hat over `RHAT` (`rhat_over`), and
  those whose level's posterior mean is beyond `FAR_LEVEL` in size on fewer than `FEW_ADS`
  training rows (`far_thin`). R-hat does not see a level that every chain holds at the
  same wrong value, and a level that far from zero on so few ads often comes from odd rows
  (a commercial space, a placeholder ad). Each has its count of training rows, its level,
  its R-hat and its count of scored ads.

It only reports. No gate, publish or caution reads it. The kept draws are few (360 on the
market fits), so R-hat is noisy: independent draws of that shape give no item over 1.05 in
20,000 and 4% over 1.01, which is why the bound is `run.GROUP_RHAT_GATE` and not the gate's.
The report is written beside the run's posterior as `kept_report.json` unless `--out` names
another file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import drift_diagnostics, drift_score
from . import run as run_module

RHAT = run_module.GROUP_RHAT_GATE
# A level this far from zero, in log rent, on fewer training rows than `FEW_ADS`.
FAR_LEVEL, FEW_ADS = 0.5, 10


def places(below_share) -> np.ndarray:
    """Each ad's place, from 1, in the Deals order: `below_share` to four places, lowest
    first, ties in the rows' order, as `drift_deals.deals` sorts its table."""
    order = np.argsort(np.round(np.asarray(below_share, float), 4), kind="stable")
    place = np.empty(len(order), int)
    place[order] = np.arange(1, len(order) + 1)
    return place


def ads_over(listing, place, below_share, rhat) -> pd.DataFrame:
    """The scored ads whose `pred_loc` has R-hat over `RHAT`, worst first. An ad whose
    draws are constant has no R-hat and is not listed."""
    table = pd.DataFrame(
        {
            "listing_id": np.asarray(listing).astype(str),
            "place": np.asarray(place, int),
            "below_share": np.asarray(below_share, float),
            "rhat": np.asarray(rhat, float),
        }
    )
    over = table[np.nan_to_num(table.rhat.to_numpy()) > RHAT]
    return over.sort_values("rhat", ascending=False, kind="stable").reset_index(
        drop=True
    )


def buildings_listed(
    levels: pd.DataFrame, rhat, train_rows, scored_ads
) -> pd.DataFrame:
    """The buildings to look at: those whose level has R-hat over `RHAT` and those whose
    level is beyond `FAR_LEVEL` in size on fewer than `FEW_ADS` training rows. `levels` is
    `drift_diagnostics.levels`' table and the three arrays are in its order. The largest
    levels come first."""
    table = pd.DataFrame(
        {
            "building": levels.index.astype(str),
            "zone": levels.zone.to_numpy(),
            "train_rows": np.asarray(train_rows, int),
            "level": levels.level.to_numpy(float),
            "rhat": np.asarray(rhat, float),
            "scored_ads": np.asarray(scored_ads, int),
        }
    )
    table["rhat_over"] = np.nan_to_num(table.rhat.to_numpy()) > RHAT
    table["far_thin"] = (table.level.abs() > FAR_LEVEL) & (table.train_rows < FEW_ADS)
    listed = table[table.rhat_over | table.far_thin]
    order = np.argsort(-listed.level.abs().to_numpy(), kind="stable")
    return listed.iloc[order].reset_index(drop=True)


def report(run_dir: Path) -> dict:
    """The two lists for the run at `run_dir`, with the counts that sum them up."""
    z = np.load(run_dir / "posterior.npz")
    missing = [k for k in ("kept/pred_loc", "kept/bld") if k not in z]
    if missing:
        raise SystemExit(f"{run_dir.name} does not keep {', '.join(missing)}")
    dataset = drift_score.dataset_dir(run_dir)
    if dataset is None:
        raise SystemExit(
            f"the dataset of {run_dir} is not on this machine, or its rows changed"
        )
    held = np.asarray(z["heldout"], bool)
    frame = pd.read_parquet(
        dataset / "rows.parquet", columns=["listing_id", "building"]
    ).astype(str)
    record = json.loads((run_dir / "result.json").read_text())
    levels, why = drift_diagnostics.levels(run_dir, record, frame.building.to_numpy())
    if levels is None:
        raise SystemExit(f"no building levels for {run_dir.name}: {why}")

    share = drift_score.score_run(run_dir)["cdf"]
    loc = run_module.building_diagnostics(z["kept/pred_loc"])["rhat"]
    ads = ads_over(frame.listing_id[held].to_numpy(), places(share), share, loc)

    count = lambda rows: (  # noqa: E731
        frame.building[rows].value_counts().reindex(levels.index).fillna(0).to_numpy()
    )
    bld = run_module.building_diagnostics(z["kept/bld"])["rhat"]
    scored = count(held)
    buildings = buildings_listed(levels, bld, count(~held), scored)
    high = (levels.level.to_numpy() > FAR_LEVEL) & (scored > 0)
    with_ads = buildings.scored_ads > 0
    return {
        "run": run_dir.name,
        "bounds": {"rhat": RHAT, "far_level": FAR_LEVEL, "few_ads": FEW_ADS},
        "kept_draws": list(z["kept/pred_loc"].shape[:2]),
        "counts": {
            "scored_ads": int(held.sum()),
            "ads_rhat_over": len(ads),
            "buildings": len(levels),
            "buildings_rhat_over": int(buildings.rhat_over.sum()),
            "buildings_rhat_over_with_scored_ads": int(
                (buildings.rhat_over & with_ads).sum()
            ),
            "buildings_far_thin": int(buildings.far_thin.sum()),
            "buildings_far_thin_with_scored_ads": int(
                (buildings.far_thin & with_ads).sum()
            ),
            "scored_ads_in_far_thin_buildings": int(
                buildings.scored_ads[buildings.far_thin].sum()
            ),
            # Every count of training rows: the buildings a high level lifts in the order.
            "buildings_level_over_far_with_scored_ads": int(high.sum()),
            "scored_ads_in_buildings_level_over_far": int(scored[high].sum()),
        },
        "ads": json.loads(ads.to_json(orient="records")),
        "buildings": json.loads(buildings.to_json(orient="records")),
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("run")
    p.add_argument("--out", type=Path)
    p.add_argument("--runs", default=str(run_module.RUNS))
    args = p.parse_args(argv)
    run_dir = Path(args.runs) / args.run
    out = report(run_dir)
    path = args.out or run_dir / "kept_report.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["counts"], indent=1))
    for name in ("ads", "buildings"):
        table = pd.DataFrame(out[name])
        print(f"\n{name}: {len(table)}")
        if len(table):
            print(table.to_string(index=False))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
