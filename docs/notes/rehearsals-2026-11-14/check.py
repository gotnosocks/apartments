"""The sampler checks of a rehearsal run: the gate and the new parameters' chains.

The script reads a run's `result.json` and `posterior.npz` under RUN and prints:

1. the convergence table that `b0.main_run` computed with the model's own `diagnostics`,
   worst R-hat and least ESS first, and whether it passes the gate;
2. the split R-hat of each building's level over the kept draws, which the drift models'
   table leaves out, with the counts that independent draws of the same shape give;
3. for each of the model's new parameters, its split R-hat and bulk ESS from `run.split_rhat`
   and `run.ess` on every post-warmup sweep, then each chain's median and 95% interval, the
   two chains' gap in medians in units of the pooled sd, the larger of the two chains' moves
   in median from their first half to their second in the same units, and the share of draws
   under 1% of the parameter's median, for a scale or a factor.

The new parameters are L2's phase levels (`phase:*`), the segments' amplitudes, lengthscales,
levels (`level:*`) and hat coefficients (`seg:*`), the duplex and income factors k, and the line model's
line_sd and unit_sd.

    python docs/notes/rehearsals-2026-11-14/check.py RUN MODEL
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import (  # noqa: E402
    drift_building_phase_duplex,
    drift_building_phase_income,
    drift_building_phase_segment,
    run,
)

RUN, MODEL = Path(sys.argv[1]), sys.argv[2]
result = json.loads((RUN / "result.json").read_text())
post = np.load(RUN / "posterior.npz", allow_pickle=True)
trace = {k[len("trace/") :]: post[k] for k in post.files if k.startswith("trace/")}
names = list(post["names"])

diag = result["diagnostics"]
rows = diag["per_quantity"]
print(
    f"gate: max R-hat {diag['max_rhat']:.4f} ({diag['max_rhat_name']}), "
    f"min ESS {diag['min_ess']:.0f} ({diag['min_ess_name']}), passes {diag['passes']}, "
    f"{len(rows)} quantities, {trace['sigma'].shape[1]} draws a chain"
)
for n in sorted(rows, key=lambda n: -rows[n]["rhat"])[:8]:
    print(f"  worst R-hat  {n}: {rows[n]['rhat']:.4f}, ESS {rows[n]['ess']:.0f}")
for n in sorted(rows, key=lambda n: rows[n]["ess"])[:8]:
    print(f"  least ESS    {n}: {rows[n]['rhat']:.4f}, ESS {rows[n]['ess']:.0f}")
bld = post["kept/bld"]
r = run.split_rhat(bld)
print(
    f"building levels on the kept draws ({bld.shape[1]} a chain): max R-hat {r.max():.4f}, "
    f"{int((r > 1.01).sum())} of {r.size} over 1.01, {int((r > 1.05).sum())} over 1.05"
)
# The same counts for independent normal draws of the same shape, averaged over 200 sets.
rng = np.random.default_rng(0)
iid = [run.split_rhat(rng.normal(size=bld.shape)) for _ in range(200)]
print(
    f"  independent draws of that shape: {np.mean([(x > 1.01).sum() for x in iid]):.1f} "
    f"over 1.01, {np.mean([(x > 1.05).sum() for x in iid]):.1f} over 1.05, "
    f"median max R-hat {np.median([x.max() for x in iid]):.4f}"
)

new = {}
beta = trace["beta"]
if MODEL.endswith("-level"):
    new |= {n: beta[..., i] for i, n in enumerate(names) if n.startswith("phase:")}
if MODEL.endswith("-segment"):
    new |= drift_building_phase_segment._segment_extras(trace, names)
    new |= {n: beta[..., i] for i, n in enumerate(names) if n.startswith("level:")}
    hats = [i for i, n in enumerate(names) if n.startswith("seg:")]
    r = [run.split_rhat(beta[..., i]) for i in hats]
    e = [run.ess(beta[..., i]) for i in hats]
    print(
        f"hat coefficients: {len(hats)}, max R-hat {max(r):.4f} "
        f"({names[hats[int(np.argmax(r))]]}), min ESS {min(e):.0f} "
        f"({names[hats[int(np.argmin(e))]]})"
    )
if MODEL.endswith("-duplex"):
    new["k"] = drift_building_phase_duplex.factors(trace["phase_scale"])[1]
if MODEL.endswith("-income"):
    new["k"] = drift_building_phase_income.factors(trace["phase_scale"])[1]
if MODEL.endswith("-line"):
    new |= {k: trace[k] for k in ("line_sd", "unit_sd")}

positive = ("gp_amp", "gp_ls", "k", "line_sd", "unit_sd")
print(
    "| parameter | R-hat | ESS | chain 1 | chain 2 | gap / sd | drift / sd | near edge |"
)
print("|---|---|---|---|---|---|---|---|")
for n, x in new.items():
    x = np.asarray(x, float)
    chains = [
        f"{np.median(c):.4g} [{np.quantile(c, 0.025):.4g}, {np.quantile(c, 0.975):.4g}]"
        for c in x
    ]
    gap = abs(np.median(x[0]) - np.median(x[1])) / x.std()
    half = x.shape[1] // 2
    drift = max(abs(np.median(c[:half]) - np.median(c[half:])) for c in x) / x.std()
    edge = (
        f"{np.mean(x < 0.01 * np.median(x)):.3f}" if n.startswith(positive) else "n/a"
    )
    print(
        f"| {n} | {run.split_rhat(x):.4f} | {run.ess(x):.0f} | {chains[0]} | {chains[1]} "
        f"| {gap:.2f} | {drift:.2f} | {edge} |"
    )
