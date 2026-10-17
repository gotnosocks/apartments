"""A run's design: its rows after the split and data rules, the held-out mask, the
feature matrix and the prepared arrays.

`prepared` builds the design the way `run` and `loo` always have. With
FRONTIER_DESIGN_CACHE set, it also keeps the design in a pickle under
OUTPUT_ROOT/cache, so a second reader of the same design loads it in seconds
instead of repeating the prep. The Modal containers set the variable. In a fit,
`rentfrontier.loo` and the post-fit statistics follow `rentfrontier.run` on the
same container disk, and on the all-scraped data each prep takes about an hour.
In a publish (`fit.py --publish-only`), the kit and the rent map load the design
the summary built.

The cache key is a sha256 over:

1. the source of every module in the package and every file under the repo's
   config directory, which hold the data rules, corrections and reviews
2. the observations file's sha256, the split, the data rules and the feature set
3. the FRONTIER_* environment, which picks external roots and description
   sources, less the variables in `UNKEYED`, with the resolved output root in
   place of FRONTIER_OUTPUT_ROOT

`model.prepare` and the features build in numpy, so a reader running JAX in
float32 or float64 loads the same design.

External snapshots enter through their dated paths in the code. A few inputs
sit at undated paths and could change in place, and the key leaves their bytes
out, so the variable suits a cache that lives for a single container, as on
Modal, and stays unset on thelio. Writers put the pickle in place with
`os.replace`, so a reader finds a whole file or none.

A Modal fit started with `fit.py --save-design` copies its design to the
Volume, and the download puts it in OUTPUT_ROOT/designs on thelio, outside the
cache directory the Modal fits upload as an input. There the summary runs with
FRONTIER_DESIGN_CACHE=read: it loads the fit's own design from that directory
when the key matches and otherwise builds one without writing it, so thelio's
undated inputs never end up in a pickle. The key matches only when the
summary's checkout holds the same package and config files as the fit's.

`python -m rentfrontier.design NAME`, with FRONTIER_DESIGN_CACHE=1, prepares a
finished run's design as its summary loads it and leaves the pickle in the
cache. `ops/modal-fit --design-only` runs it in a Modal CPU container for a run
whose prep runs out of memory on thelio, at the commit the summary will run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import time
import uuid
from pathlib import Path

import pandas as pd

from . import data, features

CACHE_VERSION = "v1"
PACKAGE = Path(__file__).resolve().parent
# Variables that pick how a step runs or what it records, leaving the design as
# it is. Without them in the key, a fit on Modal and its summary on thelio come
# to the same key from their different environments.
UNKEYED = frozenset(
    {
        "FRONTIER_COMMIT",
        "FRONTIER_DESIGN_CACHE",
        "FRONTIER_OUTPUT_ROOT",
        "FRONTIER_RANGE_ATOMS",
        "FRONTIER_RANGE_SAMPLE",
    }
)


def _key(frame: pd.DataFrame, split: str, rules, feature_set: str) -> str:
    digest = hashlib.sha256(CACHE_VERSION.encode())
    config = data.REPO / "config"
    for path in sorted(PACKAGE.glob("*.py")) + sorted(
        p for p in config.rglob("*") if p.is_file()
    ):
        digest.update(str(path.relative_to(data.REPO)).encode())
        digest.update(data.sha256(path).encode())
    env = sorted(
        (k, v)
        for k, v in os.environ.items()
        if k.startswith("FRONTIER_") and k not in UNKEYED
    )
    digest.update(
        repr(
            (
                frame.attrs["source_sha256"],
                split,
                tuple(rules),
                feature_set,
                env,
                str(data.OUTPUT_ROOT.resolve()),
            )
        ).encode()
    )
    return digest.hexdigest()


def _build(frame, split, rules, feature_set):
    from . import model

    frame, heldout = data.split_and_rules(frame, split, rules)
    feats = features.build(feature_set, frame, ~heldout)
    return frame, heldout, feats, model.prepare(frame, heldout, feats)


def prepared(frame: pd.DataFrame, split: str, rules, feature_set: str) -> tuple:
    """(frame, heldout, feats, prep) for a loaded frame, as `split_and_rules`,
    `features.build` and `model.prepare` return them."""
    mode = os.environ.get("FRONTIER_DESIGN_CACHE")
    if not mode:
        return _build(frame, split, rules, feature_set)
    key = _key(frame, split, rules, feature_set)
    if mode == "read":
        saved = data.OUTPUT_ROOT / "designs" / f"design-{key[:16]}.pkl"
        try:
            with open(saved, "rb") as f:
                return pickle.load(f)
        except Exception:
            # No saved design, or one this environment can't unpickle.
            return _build(frame, split, rules, feature_set)
    cache = data.OUTPUT_ROOT / "cache" / f"design-{key[:16]}.pkl"
    if cache.exists():
        with open(cache, "rb") as f:
            return pickle.load(f)
    design = _build(frame, split, rules, feature_set)
    tmp = cache.with_name(f"{cache.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump(design, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cache)
    except Exception:
        # A failed write (disk, memory, pickling) still returns the design.
        tmp.unlink(missing_ok=True)
    return design


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Prepare a finished run's design and keep it in the cache."
    )
    p.add_argument("name")
    args = p.parse_args(argv)
    if os.environ.get("FRONTIER_DESIGN_CACHE") != "1":
        raise SystemExit("set FRONTIER_DESIGN_CACHE=1 to keep the design in the cache")
    from .run import RUNS

    result = json.loads((RUNS / args.name / "result.json").read_text())
    started = time.time()
    # As rentfrontier.summary loads it, so the key comes out the same.
    frame = data.load(Path(result["dataset"]))
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    rules = data.recorded_rules(result)
    key = _key(frame, result["split"], rules, result["feature_set"])
    frame, *_ = prepared(frame, result["split"], rules, result["feature_set"])
    path = data.OUTPUT_ROOT / "cache" / f"design-{key[:16]}.pkl"
    if not path.exists():
        raise SystemExit(f"the design was built but not written to {path}")
    print(
        json.dumps(
            {
                "name": args.name,
                "design": path.name,
                "key": key,
                "rows": len(frame),
                "bytes": path.stat().st_size,
                "seconds": round(time.time() - started, 1),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
