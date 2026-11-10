"""`drift_score.score_run` over a pool of forked workers, with the same chunks and seeds.

    python pscore.py score RUN               writes RUN/pred_scores.npz and prints the summary
    python pscore.py deals RUN --ads A --registry R --out DIR
    python pscore.py validate RUN --ads A --out FILE.json
    python pscore.py publish ...             as `rentfrontier.drift_deals publish`

`patch()` swaps the parallel version into `drift_score`, so `drift_deals` and `extract`
use it too.
"""

import json
import os
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from rentfrontier import drift_score

WORKERS = int(os.environ.get("PSCORE_WORKERS", "6"))
_serial = drift_score.score_run
_G = {}


def _chunk(a):
    g = _G
    sl = slice(a, a + drift_score.CHUNK)
    return drift_score.score_rows(
        g["loc"][:, sl],
        g["usd"][:, sl],
        g["sig"][:, g["group"][sl]],
        g["nu"],
        g["y"][sl],
        g["seed"] + a,
        at=None if g["at"] is None else g["at"][sl],
    )


def score_run(run_dir: Path, seed: int = 0, at=None) -> dict:
    z = np.load(run_dir / "posterior.npz")
    if "kept/pred_loc" not in z:
        raise SystemExit(f"{run_dir} predicted no rows")

    def flat(k):
        return z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:])

    _G.update(
        loc=flat("pred_loc"),
        usd=flat("pred_unit_sd"),
        sig=flat("sigma"),
        nu=flat("nu"),
        y=z["kept/pred_y"],
        group=z["kept/pred_group"],
        seed=seed,
        at=None if at is None else np.asarray(at, float),
    )
    starts = range(0, len(_G["y"]), drift_score.CHUNK)
    with get_context("fork").Pool(WORKERS) as pool:
        parts = pool.map(_chunk, starts, chunksize=8)
    res = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    res |= dict(
        y=_G["y"],
        group=_G["group"],
        quantiles=np.array(drift_score.Q),
        heldout=z["heldout"],
    )
    _G.clear()
    dataset = drift_score.dataset_dir(run_dir)
    if dataset is not None:
        import pandas as pd

        frame = pd.read_parquet(
            dataset / "rows.parquet", columns=["listing_id", "building", "latest_day"]
        )[z["heldout"]]
        res |= dict(
            listing=frame.listing_id.astype(str).to_numpy().astype("U"),
            building=frame.building.astype(str).to_numpy().astype("U"),
            day=frame.latest_day.astype(str).to_numpy().astype("U"),
        )
    return res


def patch():
    drift_score.score_run = score_run


if __name__ == "__main__":
    patch()
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "score":
        run_dir = drift_score.run_module.RUNS / rest[0]
        res = score_run(run_dir)
        np.savez_compressed(run_dir / "pred_scores.npz", **res)
        print(json.dumps(drift_score.summary(res), indent=1))
    else:
        from rentfrontier import drift_deals

        drift_deals.main([cmd, *rest])
