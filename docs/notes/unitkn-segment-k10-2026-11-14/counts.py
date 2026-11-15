"""Gate misses by parameter group in rehearsal runs.

For each RUN the script reads the convergence table in `result.json` and sorts its
quantities into five groups: the segment lengthscales (`gp_ls[seg:...]`), the segment
amplitudes (`gp_amp[seg:...]`), the segment quarter coefficients (`beta[seg:...]`), the
other coefficients, and the other scalars. It prints, for each group, how many quantities
miss the gate (R-hat above 1.01 or ESS at or under 400) with the worst R-hat and the least
ESS, and it breaks the quarter coefficients' misses down by segment.

    python docs/notes/unitkn-segment-k10-2026-11-14/counts.py RUN [RUN ...]
"""

import json
import sys
from pathlib import Path


def misses(entry):
    return entry["rhat"] > 1.01 or entry["ess"] <= 400


def groups(table):
    names = list(table)
    return {
        "lengthscales": [n for n in names if n.startswith("gp_ls[seg:")],
        "amplitudes": [n for n in names if n.startswith("gp_amp[seg:")],
        "quarter coefficients": [n for n in names if n.startswith("beta[seg:")],
        "other coefficients": [
            n for n in names if n.startswith("beta[") and not n.startswith("beta[seg:")
        ],
        "other scalars": [
            n for n in names if not n.startswith("beta[") and "[seg:" not in n
        ],
    }


def main(runs):
    for run in runs:
        diagnostics = json.loads((Path(run) / "result.json").read_text())["diagnostics"]
        table = diagnostics["per_quantity"]
        print(
            f"{Path(run).name}: max R-hat {diagnostics['max_rhat']:.4f}"
            f" ({diagnostics['max_rhat_name']}), min ESS {diagnostics['min_ess']:.0f}"
            f" ({diagnostics['min_ess_name']})"
        )
        for group, names in groups(table).items():
            missed = [n for n in names if misses(table[n])]
            worst = max(names, key=lambda n: table[n]["rhat"])
            least = min(names, key=lambda n: table[n]["ess"])
            print(
                f"  {group}: {len(missed)} of {len(names)} miss;"
                f" worst R-hat {table[worst]['rhat']:.4f} {worst};"
                f" least ESS {table[least]['ess']:.0f} {least}"
            )
            if group == "quarter coefficients":
                by_segment = {}
                for name in missed:
                    segment = ":".join(name.split(":")[1:3])
                    by_segment[segment] = by_segment.get(segment, 0) + 1
                print(f"    {by_segment}")


if __name__ == "__main__":
    main(sys.argv[1:])
