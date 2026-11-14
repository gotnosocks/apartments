"""A diagnostic rehearsal with a wider slice for the zones' building spreads.

The collapsed building step of `rentfrontier.drift` draws each zone's log spread, bld_sd, by
slice sampling in a window of `drift.SPREAD_WIDTH` (0.05) with no stepping out, so a draw
moves at most 0.05 from the last. The script sets that width to WIDTH in this process alone,
prints it, and then runs `rentfrontier.run` with the remaining arguments. It changes no file,
and the run's `result.json` does not record the width.

    python docs/notes/rehearsals-2026-11-14/width.py WIDTH [rentfrontier.run arguments]
"""

import sys

from rentfrontier import drift, run

drift.SPREAD_WIDTH = float(sys.argv[1])
print(f"drift.SPREAD_WIDTH set to {drift.SPREAD_WIDTH} for this run", flush=True)
run.main(sys.argv[2:])
