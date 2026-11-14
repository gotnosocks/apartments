"""Every scalar's split R-hat and bulk ESS in several rehearsal runs, side by side.

The script reads the convergence table in each RUN's `result.json`, the one `b0.main_run`
computed with the model's own `diagnostics`. It prints a markdown table with a row for each
quantity outside `beta[...]` and a column for each run, holding the quantity's R-hat and
ESS, with `*` on a cell over the gate (R-hat above 1.01 or ESS at or under 400) and a dash
where the run's model lacks the quantity. Below the table it prints, for each run, the
gate's verdict, the number of coefficients over the gate with the worst of them, and the
seconds a sweep took.

    python docs/notes/unitkn-rehearsals-2026-11-14/gate.py RUN [RUN ...]
"""

import json
import sys
from pathlib import Path

RHAT, ESS = 1.01, 400
runs = [Path(a) for a in sys.argv[1:]]
results = [json.loads((r / "result.json").read_text()) for r in runs]
tables = [r["diagnostics"]["per_quantity"] for r in results]
scalars = []
for t in tables:
    scalars += [n for n in t if not n.startswith("beta[") and n not in scalars]


def cell(row) -> str:
    """A quantity's R-hat and ESS in one run, starred over the gate."""
    if row is None:
        return "-"
    miss = "*" if row["rhat"] > RHAT or row["ess"] <= ESS else ""
    return f"{row['rhat']:.4f}, {row['ess']:.0f}{miss}"


print("| quantity | " + " | ".join(r.name for r in runs) + " |")
print("|---|" + "---|" * len(runs))
for n in scalars:
    print(f"| {n} | " + " | ".join(cell(t.get(n)) for t in tables) + " |")
for run, result, t in zip(runs, results, tables):
    d = result["diagnostics"]
    beta = {n: v for n, v in t.items() if n.startswith("beta[")}
    over = [n for n, v in beta.items() if v["rhat"] > RHAT or v["ess"] <= ESS]
    worst = max(beta, key=lambda n: beta[n]["rhat"])
    least = min(beta, key=lambda n: beta[n]["ess"])
    sweep = [s for s in result["log"] if "a sweep" in s]
    print(
        f"{run.name}: passes {d['passes']}, max R-hat {d['max_rhat']:.4f} "
        f"({d['max_rhat_name']}), min ESS {d['min_ess']:.0f} ({d['min_ess_name']}); "
        f"{len(over)} of {len(beta)} coefficients over the gate, worst R-hat "
        f"{beta[worst]['rhat']:.4f} ({worst}), least ESS {beta[least]['ess']:.0f} "
        f"({least}); {sweep[-1] if sweep else 'no sweep time in the log'}"
    )
