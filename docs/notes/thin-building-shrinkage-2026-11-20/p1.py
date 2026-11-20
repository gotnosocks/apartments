import json, pandas as pd, numpy as np
from rentfrontier import run as R

for n in [
    "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt",
    "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3",
    "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j",
]:
    d = R.RUNS / n
    z = np.load(d / "posterior.npz")
    print(n)
    for k in z.files:
        a = z[k]
        print(
            "  ",
            k,
            a.shape,
            (
                np.round(a.reshape(-1, a.shape[-1]).mean(0)[:6], 4)
                if a.ndim >= 2 and a.shape[-1] < 20
                else (
                    round(float(a.mean()), 4)
                    if a.size < 1e6 and a.dtype.kind == "f"
                    else ""
                )
            ),
        )
    rec = json.loads((d / "result.json").read_text())
    print("  settings", rec["sampler_settings"])
    print("  cost", rec.get("cost_usd"), rec.get("seconds"), rec.get("pooled_from"))
