"""A diagnostic rehearsal of a segment model with each path's lengthscale held near a year.

`drift.update_gp` draws every process's log lengthscale by slice sampling under the Normal
prior its spec carries. The script sets the sd of the segment paths' prior,
`drift_building_phase_segment.SEG_LS[1]`, to SD in this process alone, prints it, and then
runs `rentfrontier.run` with the remaining arguments. At an sd of 0.001 the slice step
brings each path's lengthscale from its starting value to within about 0.3% of a year
during warmup and keeps it there, so the run shows the sweep's mixing on the amplitudes and
the paths' coefficients with the lengthscales out of play. It changes no file, and the
run's `result.json` records the prior as the module's (0.0, 0.5).

    python docs/notes/unitkn-rehearsals-2026-11-14/hold.py SD [rentfrontier.run arguments]
"""

import sys

from rentfrontier import drift_building_phase_segment, run

drift_building_phase_segment.SEG_LS = (0.0, float(sys.argv[1]))
print(
    f"drift_building_phase_segment.SEG_LS set to {drift_building_phase_segment.SEG_LS}"
    " for this run",
    flush=True,
)
run.main(sys.argv[2:])
