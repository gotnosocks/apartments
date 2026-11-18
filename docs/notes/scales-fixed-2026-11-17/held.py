"""Run `rentfrontier.run` with the scales held at a set read from a file.

    python held.py SET.json [rentfrontier.run arguments]

SET.json comes from `means.py`. The script adds it to `rentfrontier.drift_scales` under the
name `local` in this process alone, and runs `rentfrontier.run` with the remaining
arguments and `--scales-fixed local`. The run's `result.json` records the set's source and
values. `rehearse.sh` calls it through REHEARSAL_ENTRY, with SET.json as its last argument.
"""

import json
import sys
from pathlib import Path

from rentfrontier import drift_scales, run

held = json.loads(Path(sys.argv[1]).read_text())
drift_scales.SETS["local"] = held["values"]
drift_scales.SOURCES["local"] = held["source"]
run.main([*sys.argv[2:], "--scales-fixed", "local"])
