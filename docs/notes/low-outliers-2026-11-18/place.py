"""Where a backtest run places the open ads whose coded bedrooms or baths differ from the
apartment's previous ad, and how a second run compares on them.

    python docs/notes/low-outliers-2026-11-18/place.py ADS BASE_RUN [NEW_RUN]

ADS is the pipeline's ads file. The marks are `drift_building_bedtext_layout.changes` on the
rows of BASE_RUN's dataset, with the run's held-out ads compared against training rows only.
For each mark and each run I print the mean place of the first ask in the run's predictive
distribution, the share of ads in the lowest tenth of places, the median days on market
and the share later cut for those ads, and the elpd at the final ask. With NEW_RUN I also
print the paired elpd difference with its SE clustered by building.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np

from rentfrontier import drift_building_bedtext_layout as layout
from rentfrontier import drift_deals, drift_score

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "place", HERE.parent / "bedtext-base-2026-11-17" / "place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)


def clustered(d, building):
    _, cl = np.unique(building, return_inverse=True)
    sums = np.bincount(cl, weights=d - d.mean())
    return float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))


def main(argv):
    ads, runs = Path(argv[0]), [Path(r) for r in argv[1:]]
    frame, h, held = drift_deals._held_frame(runs[0])
    x = layout.changes(frame, ~held)[held] > 0
    sets = {"all": np.ones(len(h), bool), "any mark": x.any(1), "no mark": ~x.any(1)}
    sets |= {n: x[:, j] for j, n in enumerate(layout.COLUMNS)}
    out = []
    for run in runs:
        lid, p, ok, days, change = place.places(run, ads)
        assert np.array_equal(lid, h.listing_id.astype(str).to_numpy())
        out.append((p, ok, days, change, drift_score.score_run(run)["elpd"]))
    for name, m in sets.items():
        print(f"{name:20s} open ads {m.sum():5d}")
        for run, (p, ok, days, change, elpd) in zip(runs, out):
            k = m & ok
            low = k & (p < 0.1)
            line = (
                f"    {run.name[-12:]:12s} mean place {p[k].mean():.3f}"
                f"  lowest tenth {low.sum():4d} ({100 * low.sum() / max(k.sum(), 1):.1f}%)"
                f"  elpd {elpd[m].sum():9.1f}"
            )
            if low.any():
                line += (
                    f"  their median days {np.median(days[low]):.0f},"
                    f" cut {100 * (change[low] < -0.001).mean():.1f}%,"
                    f" raised {100 * (change[low] > 0.001).mean():.1f}%"
                )
            print(line)
        if len(runs) == 2:
            d = out[1][4] - out[0][4]
            bld = h.building.astype(str).to_numpy()
            both = m & out[0][1] & (out[0][0] < 0.1) & (out[1][0] < 0.1)
            print(
                f"    new minus base elpd {d[m].sum():+.1f} (SE {clustered(d[m], bld[m]):.1f});"
                f" in both lowest tenths {both.sum()}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
