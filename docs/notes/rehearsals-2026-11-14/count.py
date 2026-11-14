"""The counts behind each unfit model's new parameters on a subsample of `subsample.py`.

The script reads the three copies under DIR and counts the training rows of the carried
split with the models' own code: units and lines (`drift_line.line_index`), lease phases
(`drift_building_phase.phase_index`), the duplex and income marks of each phase (each model's
`mark_index`), and each segment's rows and hat weight at each quarter start
(`drift_building_phase_segment`). It prints them as JSON.

    python docs/notes/rehearsals-2026-11-14/count.py DIR
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import (  # noqa: E402
    b0,
    drift_building_phase,
    drift_building_phase_duplex,
    drift_building_phase_income,
    drift_building_phase_segment,
    drift_line,
    splits,
)

DIR = Path(sys.argv[1])
frame = b0.load_frame(DIR / "base")
held = splits.carried_split(frame)
train = ~held
out = {
    "buildings": int(frame.building.nunique()),
    "rows": len(frame),
    "training_rows": int(train.sum()),
    "heldout_rows": int(held.sum()),
    "training_buildings": int(frame.building[train].nunique()),
}

unit = pd.factorize(drift_line.unit_keys(frame))[0]
line, lines = drift_line.line_index(frame, held)
units_of_line = pd.Series(unit[train]).groupby(line[train]).nunique()
out["units"] = int(pd.Series(unit[train]).nunique())
out["lines"] = int(lines)
out["lines_with_2_units"] = int((units_of_line >= 2).sum())
out["units_per_line_median"] = float(units_of_line.median())

phase = drift_building_phase.phase_index(frame)
names = drift_building_phase.PHASES
out["phase_rows"] = {
    names[p]: int((train & (phase == p)).sum()) for p in range(len(names))
}

for copy, module, key in (
    ("duplex-penthouse", drift_building_phase_duplex, "duplex"),
    ("textflags", drift_building_phase_income, "income"),
):
    marked = b0.load_frame(DIR / copy)
    if not np.array_equal(marked.audit_id.to_numpy(), frame.audit_id.to_numpy()):
        raise SystemExit(f"{copy} does not hold the base copy's rows in order")
    mark = module.mark_index(marked).astype(bool)
    out[key] = {
        "training_rows": int((train & mark).sum()),
        "heldout_rows": int((held & mark).sum()),
        "training_buildings": int(marked.building[train & mark].nunique()),
        "training_rows_by_phase": {
            names[p]: int((train & mark & (phase == p)).sum())
            for p in range(len(names))
        },
    }
    del marked

d = drift_building_phase.design(frame, held=held)
seg = drift_building_phase_segment.segment_index(d)
segments = drift_building_phase_segment.segment_names(d)
q = drift_building_phase_segment.quarter_starts(d)
knots = np.asarray((q - pd.Timestamp(d.start)).days, float) / 365.25
H = drift_building_phase_segment.hat_weights(drift_building_phase.years(d), knots)
weight = np.stack([H[train & (seg == k)].sum(axis=0) for k in range(len(segments))])
out["segments"] = {
    "quarter_starts": len(q),
    "first": str(q[0].date()),
    "last": str(q[-1].date()),
    "training_rows": {
        s: int((train & (seg == k)).sum()) for k, s in enumerate(segments)
    },
    "least_quarter_weight": {
        s: round(float(weight[k].min()), 1) for k, s in enumerate(segments)
    },
    "quarters_under_20": {
        s: int((weight[k] < 20).sum()) for k, s in enumerate(segments)
    },
}
print(json.dumps(out, indent=1))
