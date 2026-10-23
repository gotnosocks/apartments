"""A fit on final or latest asks against the fit on first asks, on the same held-out rows.

    python -m rentfrontier.finalask <final-or-latest-ask-run> <base-run>

The first run is the base run's model and features with one of the rules in
`PRICES`. `tune-finalask-v1` prices each row at its listing's last ask
(`rentfrontier.listing_outcomes`), and leaves out listings still live at the
last capture, with no captured record, or whose last ask is more than twice or
under half the first (sale prices and typos). `tune-latestask-v1` and its
served successor `latest-ask-v2` keep every row, priced at its listing's latest
available ask. Both runs are scored on the
held-out rows they share, against the first run's price, from each fit's
posterior as is (a new unit's terms drawn from the population): the median
absolute % miss of the predictive median and the 80%/95% coverage, overall
and by size stated or unknown. The base run is also scored against its own
ask on those rows. Not PSIS-LOO: the two fits price different things.

Writes /data1/apartments/frontier/finalask/<run>-<commit>/result.json.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, design, explain, model, newbuilding
from .run import git, hardware

FINALASK_ROOT = data.OUTPUT_ROOT / "finalask"
RULE = "tune-finalask-v1"
# The price each rule fits, by name, for the record's labels.
PRICES = {
    RULE: "final ask",
    "tune-latestask-v1": "latest ask",
    "tune-finalask-v2": "final ask",
    "tune-latestask-v2": "latest ask",
    "latest-ask-v2": "latest ask",
    "latest-ask-v3": "latest ask",
}


def _prepared(name):
    run_dir, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    frame, heldout, _, prep = design.prepared(
        frame, result["split"], data.recorded_rules(result), result["feature_set"]
    )
    newbuilding._check_draws(run_dir, prep)
    return result, kept, config, frame, heldout, prep


def score(name, audit_ids, y=None):
    """{"all": ..., "size stated": ..., "size unknown": ...} for the run's
    held-out rows in `audit_ids`, against log price `y` (a Series by audit_id;
    None: the run's own price)."""
    result, kept, config, frame, heldout, prep = _prepared(name)
    mask = heldout & frame.audit_id.isin(audit_ids).to_numpy()
    names = [str(n) for n in prep.features.names]
    spacing = model.walk_spacing(config)
    ctx = {
        "spacing": spacing,
        "fslope_index": np.asarray(
            [names.index(n) for n in config.feature_slopes], int
        ),
        "rows": np.zeros(len(prep.buildings), int),
    }

    def rows(m):
        a = model.row_arrays(prep, frame, m)
        if y is not None:
            a.y = y.loc[frame.audit_id[m].to_numpy()].to_numpy() - prep.offset
        return a, a.building

    out, _ = newbuilding._score(
        kept,
        config,
        prep,
        frame,
        mask,
        ("held out",),
        ctx,
        rows,
        newbuilding.SEED,
    )
    return {k: v for k, v in out["held out"].items() if not k.startswith("building")}


def compare(final: str, base: str) -> dict:
    _, _, _, _, f_frame, f_held = newbuilding._load(final)
    rules = data.recorded_rules(newbuilding.explain.load_run(final)[1])
    rule = next((r for r in PRICES if r in rules), None)
    if rule is None:
        raise SystemExit(f"{final} was not fit with any of {', '.join(PRICES)}")
    price = PRICES[rule]
    _, _, _, _, b_frame, b_held = newbuilding._load(base)
    shared = sorted(set(f_frame.audit_id[f_held]) & set(b_frame.audit_id[b_held]))
    y = pd.Series(f_frame.log_rent.to_numpy(), index=f_frame.audit_id.to_numpy())
    out = {
        f"{price} fit vs {price}": score(final, shared),
        f"base fit vs {price}": score(base, shared, y),
        "base fit vs its own ask": score(base, shared),
    }
    return {
        "final_run": final,
        "rule": rule,
        "base_run": base,
        "rows": len(shared),
        "scores": out,
        "method": (
            "held-out rows both runs share; each fit's posterior as is, a new unit's "
            "terms drawn from the population; predictive median and PIT of the "
            "mixture of Student-t noise over draws"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("final")
    parser.add_argument("base")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    t0 = time.perf_counter()
    record = compare(args.final, args.base)
    record.update(commit=commit, seconds=time.perf_counter() - t0, hardware=hardware())
    out_dir = FINALASK_ROOT / f"{args.final}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(record, indent=2))
    for k, v in record["scores"].items():
        a = v["all"]
        print(
            f"{k}: miss {a['median_abs_pct_miss']:.1f}%, 80% {100 * a['cover_80']:.1f},"
            f" 95% {100 * a['cover_95']:.1f} ({a['rows']} rows)"
        )


if __name__ == "__main__":
    main()
