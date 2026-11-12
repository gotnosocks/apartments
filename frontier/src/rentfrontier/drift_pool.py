"""One fit from several containers: pool the chains of runs that differ only in their seed.

    python -m rentfrontier.drift_pool NAME PART PART [PART...]

A Modal container holds a fit for an hour, and at about a second a sweep that is too few
draws of the building model for the gate. So a fit can be launched as several containers of
the same commit, dataset, split, model and settings, each with its own `--seed`. This reads
their runs and writes the run `NAME` with every part's chains side by side: the same
`posterior.npz` and `result.json` a single run has, so the scoring and the deals read it as
any other run. Every part warms up and tunes on its own, and each is a sampler of the same
posterior, so its chains are as good as chains in one container.

The convergence table is computed afresh over all the chains together. That is a harder
test than any part's own: split R-hat now compares chains that never shared a tuning
window. The parts are named in the record under `pooled_from`.

A part stops when its time is up, so the parts hold different numbers of draws. Each is cut
to the shortest part's count, from the front, so every chain covers the same sweeps after
its warmup.

The number of parts is fixed before launch, in the fit's note. Adding a part to a fit that
has missed the gate is rerunning it on another seed, which the project does not do.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import drift
from . import run as runmod

# A run's record fields that every part must share.
SAME = (
    "commit",
    "dirty",
    "dataset_observations_sha256",
    "split",
    "split_seed",
    "feature_set",
    "model",
    "sampler",
    "tier",
    "sizes",
)
# Kept arrays that are the predicted rows' data, with no chain axis.
ROWS = ("pred_y", "pred_group", "pred_phase")
# How far apart two parts' copies of a predicted row's log rent may be (b6a and b6b
# differed by 1.8e-15 in 2 of 189,647 rows).
TOLERANCE = 1e-9
# Sampler settings a part may differ in.
OWN = ("seed",)


def check(records: list[dict]) -> None:
    """Refuse parts that are not the same fit on different seeds."""
    first = records[0]
    for r in records[1:]:
        for k in SAME:
            if r.get(k) != first.get(k):
                raise SystemExit(
                    f"{r['name']} and {first['name']} differ in {k}: "
                    f"{r.get(k)!r} against {first.get(k)!r}"
                )
        a, b = (
            {k: v for k, v in x["sampler_settings"].items() if k not in OWN}
            for x in (r, first)
        )
        if a != b:
            raise SystemExit(
                f"{r['name']} and {first['name']} differ in their settings"
            )
    seeds = [r["sampler_settings"]["seed"] for r in records]
    if len(set(seeds)) < len(seeds):
        raise SystemExit(f"the parts share a seed: {seeds}")
    failed = [r["name"] for r in records if r["dirty"]]
    if failed:
        raise SystemExit(f"parts from a dirty tree: {failed}")


def same(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether two parts' copies of an array agree. Each container builds the design
    itself, and a logarithm can differ in its last bit from one machine to the next, so
    floats are compared to within `TOLERANCE` and everything else exactly."""
    if a.shape != b.shape:
        return False
    if a.dtype.kind == "f":
        return bool(np.allclose(a, b, rtol=0.0, atol=TOLERANCE, equal_nan=True))
    return bool(np.array_equal(a, b))


def pool(parts: list[dict]) -> dict:
    """The arrays of one run from the parts' arrays (each a dict as `np.load` gives): chains
    stacked along axis 0, every part cut to the shortest part's draws."""
    first = parts[0]
    for p in parts[1:]:
        if sorted(p) != sorted(first):
            raise SystemExit("the parts hold different arrays")
        for k in ("names", "heldout", *(f"kept/{r}" for r in ROWS if f"kept/{r}" in p)):
            if not same(p[k], first[k]):
                raise SystemExit(f"the parts differ in {k}")
    out = {}
    for k in first:
        group, _, name = k.partition("/")
        if group not in ("kept", "trace") or name in ROWS:
            out[k] = np.asarray(first[k])
            continue
        draws = min(p[k].shape[1] for p in parts)
        out[k] = np.concatenate([np.asarray(p[k])[:, :draws] for p in parts], axis=0)
    return out


def record(name: str, records: list[dict], arrays: dict) -> dict:
    """The pooled run's record: the first part's, with the chains, the convergence table and
    the timings of the whole, and the parts named."""
    first = records[0]
    trace = {
        k.partition("/")[2]: v for k, v in arrays.items() if k.startswith("trace/")
    }
    kept = next(v for k, v in arrays.items() if k.startswith("kept/") and v.ndim > 1)
    chains = sum(r["sampler_settings"]["chains"] for r in records)
    seconds = {
        k: sum(r["seconds"].get(k, 0.0) for r in records) for k in first["seconds"]
    }
    return first | {
        "name": name,
        "started_at": min(r["started_at"] for r in records),
        "sampler_settings": first["sampler_settings"] | {"chains": chains},
        "seconds": seconds,
        "cost_usd": (
            None
            if any(r.get("cost_usd") is None for r in records)
            else sum(r["cost_usd"] for r in records)
        ),
        "diagnostics": drift.diagnostics(trace, [str(n) for n in arrays["names"]]),
        "log": [f"{r['name']}: {line}" for r in records for line in r.get("log", [])],
        "pooled_from": [
            {
                "name": r["name"],
                "seed": r["sampler_settings"]["seed"],
                "chains": r["sampler_settings"]["chains"],
                "sweeps": r.get("gibbs", {}).get("sweeps"),
                "seconds_per_sweep": r.get("gibbs", {}).get("seconds_per_sweep"),
                "passes": r["diagnostics"]["passes"],
                "max_rhat": r["diagnostics"]["max_rhat"],
                "min_ess": r["diagnostics"]["min_ess"],
                "hardware": r.get("hardware"),
            }
            for r in records
        ],
        "pooled_draws": {
            "traced": int(next(iter(trace.values())).shape[1]),
            "kept": int(kept.shape[1]),
        },
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="rentfrontier.drift_pool", description=__doc__
    )
    parser.add_argument("name", help="the pooled run's name")
    parser.add_argument("parts", nargs="+", help="the runs to pool, by name or folder")
    parser.add_argument("--runs", type=Path, default=runmod.RUNS)
    args = parser.parse_args(argv)
    if len(args.parts) < 2:
        raise SystemExit("pooling takes at least two parts")
    out_dir = args.runs / args.name
    if (out_dir / "result.json").exists():
        raise SystemExit(f"{out_dir} already has a result; choose a new name")
    dirs = [Path(p) if Path(p).is_dir() else args.runs / p for p in args.parts]
    records = [json.loads((d / "result.json").read_text()) for d in dirs]
    check(records)
    arrays = pool([dict(np.load(d / "posterior.npz")) for d in dirs])
    result = record(args.name, records, arrays)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "posterior.npz", **arrays)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    diag, n = result["diagnostics"], result["pooled_draws"]
    print(
        f"wrote {out_dir}: {result['sampler_settings']['chains']} chains of "
        f"{n['traced']} draws ({n['kept']} kept) from {len(dirs)} parts; "
        f"gate {'PASS' if diag['passes'] else 'FAIL'}, "
        f"max split R-hat {diag['max_rhat']:.4f} ({diag['max_rhat_name']}), "
        f"min ESS {diag['min_ess']:.0f} ({diag['min_ess_name']})"
    )


if __name__ == "__main__":
    main()
