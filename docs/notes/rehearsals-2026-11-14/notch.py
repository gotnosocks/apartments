"""Each segment's path about its reference quarter, 2024q1, in a segment model's run.

For each chain the script prints the path's mean over the quarter starts, its two neighbors of
2024q1, the notch (the path at 2024q1 less its neighbors' mean), the chain's median amplitude
and lengthscale, and the segment's level column where the design has one.

    python docs/notes/rehearsals-2026-11-14/notch.py RUN
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
segs: dict[str, dict[str, int]] = {}
for j, n in enumerate(names):
    if n.startswith("seg:"):
        s, q = n[4:].rsplit(":", 1)
        segs.setdefault(s, {})[q] = j
for s, cols in segs.items():
    qs = sorted(cols)
    i = qs.index("2024q1")
    med = np.median(beta[:, :, [cols[q] for q in qs]], axis=1)  # chains, quarters
    lvl = f"level:{s}"
    lv = (
        " level "
        + "/".join(f"{np.median(c):+.3f}" for c in beta[:, :, names.index(lvl)])
        if lvl in names
        else ""
    )
    a = extras[f"gp_amp[seg:{s}]"]
    ls = extras[f"gp_ls[seg:{s}]"]
    out = []
    for c in range(med.shape[0]):
        notch = med[c, i] - med[c, [i - 1, i + 1]].mean()
        out.append(
            f"c{c + 1}: mean {med[c].mean():+.3f} nbrs {med[c, i - 1]:+.3f}/{med[c, i + 1]:+.3f}"
            f" notch {notch:+.3f} amp {np.median(a[c]):.3f} ls {np.median(ls[c]):.2f}"
        )
    print(
        f"{s}: R-hat amp {run.split_rhat(a):.3f} ls {run.split_rhat(ls):.3f};{lv} | "
        + " | ".join(out)
    )
