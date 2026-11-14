"""How far the data narrow each segment's path from its prior, in a segment model's run.

For each segment and chain the script takes each hat coefficient's sd over the chain's draws,
with 2024q1 left out, and divides the median of those sds by the chain's median amplitude, the
prior sd of a coefficient. Near 1, the path stays close to its prior. Near 0, the data fix
it. The script prints the ratios beside the R-hat and ESS of the path's lengthscale and
amplitude.

    python docs/notes/rehearsals-2026-11-14/inform.py RUN
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import drift_building_phase_segment as segment  # noqa: E402
from rentfrontier import run  # noqa: E402

RUN = Path(sys.argv[1])
post = np.load(RUN / "posterior.npz", allow_pickle=True)
names = list(post["names"])
beta = post["trace/beta"]
trace = {k[len("trace/") :]: post[k] for k in post.files if k.startswith("trace/")}
extras = segment._segment_extras(trace, names)
segs: dict[str, list[int]] = {}
for j, n in enumerate(names):
    if n.startswith("seg:"):
        s, q = n[4:].rsplit(":", 1)
        if q != "2024q1":
            segs.setdefault(s, []).append(j)
for s, cols in segs.items():
    a = extras[f"gp_amp[seg:{s}]"]
    ls = extras[f"gp_ls[seg:{s}]"]
    ratio = [
        np.median(beta[c, :, cols].std(axis=1)) / np.median(a[c])
        for c in range(a.shape[0])
    ]
    print(
        f"{s}: sd / amplitude {ratio[0]:.2f}/{ratio[1]:.2f}; ls R-hat {run.split_rhat(ls):.3f} "
        f"ESS {run.ess(ls):.0f}; amp R-hat {run.split_rhat(a):.3f} ESS {run.ess(a):.0f}"
    )
