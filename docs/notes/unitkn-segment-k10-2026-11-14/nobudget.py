"""A rehearsal with the sweeps' time budget lifted.

`drift.Settings` stops a run once its sweeps have taken `budget_seconds` (2,520 s by
default, for Modal's container limit). The script makes None the default in this process
alone, prints that, and runs `rentfrontier.run` with the remaining arguments, so the run
takes every draw asked for. It also turns on the checkpoints and writes one every
eighth of the draws, so a run killed partway leaves partial.npz and partial.json. It
changes no file. `rehearse.sh` passes its WIDTH argument
first, and the script ignores it.

    python nobudget.py IGNORED [rentfrontier.run arguments]
"""

import sys

from rentfrontier import drift, run

_init = drift.Settings.__init__


def _unbudgeted(self, *args, **kwargs):
    kwargs.setdefault("budget_seconds", None)
    kwargs.setdefault("checkpoints", True)
    kwargs.setdefault("chunks", 8)
    _init(self, *args, **kwargs)


drift.Settings.__init__ = _unbudgeted
print(
    f"budget_seconds defaults to {drift.Settings().budget_seconds} for this run",
    flush=True,
)
run.main(sys.argv[2:])
