"""Per-item effects of a feature test: each column a feature set adds to its base, with its
posterior mean and credible intervals, from a recorded run's kept draws.

    python -m rentfrontier.effects <run-name> [<run-name> ...]

No refit. Ben, 2026-10-08 07:06Z: split "ad states one of 15 attributes" and "walk to dog run /
hospital / EMS / drop-in center / NYCHA / MSG" into per-item coefficients, so the story can use
the per-item effects with credible intervals. The model already gives every column its own
coefficient (`model.build_model`, beta with a per-column prior); a test's single PSIS-LOO line
pools them, and this reads them apart.

Each item is the change in rent, in percent, holding everything else fixed:

    indicator   (0/1 column)        100 (exp(beta) - 1), the ad saying it against not
    log         ("log ..." column)  100 (2^beta - 1), per doubling (walking distance twice as far)
    other                           100 (exp(beta) - 1) per unit of the column

with the 90% and 95% intervals, the probability the effect is positive, and how many training
rows carry the item (indicator) or the column's training median (other). Items are the columns
not in the set's `base`; a set with no base reports every column.

Writes /data1/apartments/frontier/effects/<run>-<commit>/result.json. Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from . import data, explain, features
from .run import git, hardware

EFFECTS_ROOT = data.OUTPUT_ROOT / "effects"
LOG2 = np.log(2.0)


def base_of(feature_set: str) -> str | None:
    """The set a feature set adds its columns to, or None."""
    return getattr(features.FEATURE_SETS[feature_set], "keywords", {}).get("base")


def kind_of(name: str, values: np.ndarray) -> str:
    if np.isin(values, (0.0, 1.0)).all():
        return "indicator"
    # "log m to dog run" (natural log); not log1p counts or hinges like log_floor_above_6
    return "log" if name.startswith("log ") else "other"


def item_effects(beta, names, groups, values, items) -> list[dict]:
    """One record per item column: beta (draws, columns), values (training rows, columns)."""
    out = []
    for j in items:
        kind = kind_of(names[j], values[:, j])
        b = beta[:, j]
        pct = 100.0 * np.expm1(b * (LOG2 if kind == "log" else 1.0))
        q = np.quantile(pct, [0.025, 0.05, 0.95, 0.975])
        record = {
            "feature": names[j],
            "group": groups[j],
            "kind": kind,
            "pct": float(pct.mean()),
            "pct_lower_90": float(q[1]),
            "pct_upper_90": float(q[2]),
            "pct_lower_95": float(q[0]),
            "pct_upper_95": float(q[3]),
            "probability_positive": float((b > 0).mean()),
        }
        if kind == "indicator":
            record["rows"] = int(values[:, j].sum())
        else:
            record["median"] = float(np.median(values[:, j]))
        out.append(record)
    return out


def effects_run(name: str) -> dict:
    _, result, kept = explain.load_run(name)
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    frame, heldout = data.split_and_rules(
        frame, result["split"], data.recorded_rules(result)
    )
    feature_set = result["feature_set"]
    feats = features.build(feature_set, frame, ~heldout)
    base = base_of(feature_set)
    base_names = set(features.build(base, frame, ~heldout).names) if base else set()
    names = [str(n) for n in feats.names]
    items = [j for j, n in enumerate(names) if n not in base_names]
    return {
        "source_run": name,
        "source_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": feature_set,
        "base": base,
        "rows": int((~heldout).sum()),
        "draws": int(kept["beta"].shape[0]),
        "items": item_effects(
            kept["beta"],
            names,
            list(feats.groups),
            np.asarray(feats.values)[~heldout],
            items,
        ),
        "method": "kept draws of each item column's coefficient; no refit",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for name in args.runs:
        out_dir = EFFECTS_ROOT / f"{name}-{commit[:7]}"
        if (out_dir / "result.json").exists():
            print(f"skip {name}: {out_dir} exists")
            continue
        t0 = time.perf_counter()
        record = effects_run(name)
        record.update(
            commit=commit,
            dirty=False,
            seconds=time.perf_counter() - t0,
            hardware=hardware(),
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        for item in record["items"]:
            print(
                f"{item['feature']}: {item['pct']:+.1f}% "
                f"[{item['pct_lower_90']:+.1f}, {item['pct_upper_90']:+.1f}]",
                flush=True,
            )


if __name__ == "__main__":
    main()
