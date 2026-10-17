"""A run's design: its rows after the split and data rules, the held-out mask, the
feature matrix and the prepared arrays.

`prepared` builds the design the way `run` and `loo` always have. With
FRONTIER_DESIGN_CACHE set, it also keeps the design in a pickle under
OUTPUT_ROOT/cache, so a second reader of the same design loads it in seconds
instead of repeating the prep. The Modal fit container sets the variable: there
`rentfrontier.loo` follows `rentfrontier.run` on the same container disk, and on
the all-scraped data each prep takes about an hour.

The cache key is a sha256 over:

1. the source of every module in the package and every file under the repo's
   config directory, which hold the data rules, corrections and reviews
2. the observations file's sha256, the split, the data rules and the feature set
3. the FRONTIER_* environment, which picks external roots and description
   sources, and the JAX float64 setting `model.prepare` runs under

External snapshots enter through their dated paths in the code. Writers put the
pickle in place with `os.replace`, so a reader finds a whole file or none.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import uuid
from pathlib import Path

import pandas as pd

from . import data, features

CACHE_VERSION = "v1"
PACKAGE = Path(__file__).resolve().parent


def _key(frame: pd.DataFrame, split: str, rules, feature_set: str) -> str:
    import jax

    digest = hashlib.sha256(CACHE_VERSION.encode())
    config = data.REPO / "config"
    for path in sorted(PACKAGE.glob("*.py")) + sorted(
        p for p in config.rglob("*") if p.is_file()
    ):
        digest.update(str(path.relative_to(data.REPO)).encode())
        digest.update(data.sha256(path).encode())
    env = sorted((k, v) for k, v in os.environ.items() if k.startswith("FRONTIER_"))
    digest.update(
        repr(
            (
                frame.attrs["source_sha256"],
                split,
                tuple(rules),
                feature_set,
                env,
                bool(jax.config.jax_enable_x64),
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
    if not os.environ.get("FRONTIER_DESIGN_CACHE"):
        return _build(frame, split, rules, feature_set)
    key = _key(frame, split, rules, feature_set)
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
    except (
        Exception
    ):  # a failed write (disk, memory, pickling) still returns the design
        tmp.unlink(missing_ok=True)
    return design
