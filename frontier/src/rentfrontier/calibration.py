"""Predictive coverage of a summarized run, by kind of row.

    python -m rentfrontier.calibration <summary-dir> [<summary-dir> ...]

No refit. Reads a summary's rows.parquet (`rentfrontier.summary`): each row's
PIT, where the ask falls in its predictive distribution with Student-t noise
included (leave-own-row-out for rows in the fit, the posterior as is for
held-out rows). A row is covered at 80% when its PIT lies in (0.10, 0.90)
and at 95% when it lies in (0.025, 0.975); a calibrated model covers about
those shares of every kind of row. The kinds:

    held out                  every held-out row
    held out, seen unit       its unit has rows in the fit
    held out, new unit        its unit has none, in a building that has
    held out, new building    its building has no rows in the fit either
    first listing             held-out rows that are their unit's first
                              listing as of their month (no earlier row of
                              the unit in the dataset), in a seen building:
                              the case the Fable research review (2026-10-08,
                              §10) asks the noise tests to be scored on
    single listing (LOO)      fit rows of units with one fit row: the unit
                              level comes from the prior alone

On a time-split run's summary the held-out kinds are the later months, so
"held out, new unit" is the truly-new-unit coverage of the review.

Writes /data1/apartments/frontier/calibration/<summary>/result.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data

CALIBRATION_ROOT = data.OUTPUT_ROOT / "calibration"
COLUMNS = ["unit_id", "building", "period", "in_fit", "unit_fit_rows", "pit"]
LEVELS = {"80": (0.10, 0.90), "95": (0.025, 0.975)}


def kinds(rows: pd.DataFrame) -> dict[str, np.ndarray]:
    """Boolean masks over rows for each kind of row."""
    held = ~rows.in_fit.to_numpy(bool)
    seen_unit = rows.unit_fit_rows.to_numpy() > 0
    fit_buildings = set(rows.building[rows.in_fit])
    seen_building = rows.building.isin(fit_buildings).to_numpy()
    first_period = rows.groupby("unit_id").period.transform("min")
    first = (rows.period == first_period).to_numpy()
    return {
        "held out": held,
        "held out, seen unit": held & seen_unit,
        "held out, new unit": held & ~seen_unit & seen_building,
        "held out, new building": held & ~seen_building,
        "first listing": held & first & seen_building,
        "single listing (LOO)": ~held & (rows.unit_fit_rows.to_numpy() == 1),
    }


def coverage(rows: pd.DataFrame) -> dict:
    pit = rows.pit.to_numpy(float)
    out = {}
    for name, mask in kinds(rows).items():
        m = mask & np.isfinite(pit)
        n = int(m.sum())
        entry = {"rows": n}
        for level, (lo, hi) in LEVELS.items():
            cov = float(((pit[m] > lo) & (pit[m] < hi)).mean()) if n else None
            entry[f"cover_{level}"] = cov
            # Binomial standard error at the nominal rate.
            p = hi - lo
            entry[f"se_{level}"] = float(np.sqrt(p * (1 - p) / n)) if n else None
        out[name] = entry
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("summaries", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for summary in args.summaries:
        rows = pd.read_parquet(summary / "rows.parquet", columns=COLUMNS)
        complete = json.loads((summary / "complete.json").read_text())
        record = {
            "summary": summary.name,
            "run": complete.get("run"),
            "nominal": {k: hi - lo for k, (lo, hi) in LEVELS.items()},
            "kinds": coverage(rows),
        }
        out_dir = CALIBRATION_ROOT / summary.name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        for name, e in record["kinds"].items():
            if e["rows"]:
                print(
                    f"{summary.name[:40]} {name}: {e['rows']} rows, "
                    f"80% {100 * e['cover_80']:.1f}, 95% {100 * e['cover_95']:.1f}"
                )


if __name__ == "__main__":
    main()
