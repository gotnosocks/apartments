"""The building subsample of the sampler rehearsals of 2026-11-14.

The script permutes L1's buildings at random with a fixed seed and takes the first 1 in K of
them. Few buildings hold an ad with `income_restricted_v2` (506 of 67,972), so it then
permutes those buildings with the same generator and adds the first 1 in R of them. It
writes a copy of each of the three datasets the unfit drift models read, cut to the
buildings' rows:

    base               L1's dataset, read by L2, the segment paths and the line model
    duplex-penthouse   L1's rows with `duplex` and `penthouse`, read by the duplex factor
    textflags          L1's rows with `income_restricted_v2`, read by the income factor

The three sources hold L1's rows in L1's order, and the script checks that before it cuts
them. Each copy keeps its rows in the source's order and adds `carried_heldout`: the latest
split drawn on the full data, so that `--split carried` holds out the subsample's rows the
full fit holds out. With the permutations, the subsample of a larger K or R lies inside the
subsample of a smaller one.

    python docs/notes/rehearsals-2026-11-14/subsample.py K R OUT
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import data, splits  # noqa: E402

BASE = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
COPIES = {
    "base": "",
    "duplex-penthouse": "-duplex-penthouse",
    "textflags": "-textflags",
}
SEED = 20261114

K, R, OUT = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
base = pd.read_parquet(BASE + "/rows.parquet")
held = splits.latest_split(base)
building = base.building.astype(str)
audit = base.audit_id.to_numpy()
del base
flag = pd.read_parquet(
    BASE + "-textflags/rows.parquet", columns=["income_restricted_v2"]
)
marked = flag.income_restricted_v2.eq(True).to_numpy(bool)
buildings = np.sort(building.unique())
income = np.sort(building[marked].unique())
rng = np.random.default_rng(SEED)
pick = set(rng.permutation(buildings)[: len(buildings) // K])
pick |= set(rng.permutation(income)[: len(income) // R])
keep = building.isin(pick).to_numpy()
print(f"{len(pick)} of {len(buildings)} buildings, {keep.sum()} rows", flush=True)

for name, suffix in COPIES.items():
    src = Path(BASE + suffix)
    frame = pd.read_parquet(src / "rows.parquet")
    if not np.array_equal(frame.audit_id.to_numpy(), audit):
        raise SystemExit(f"{src} does not hold L1's rows in L1's order")
    cut = frame[keep].assign(carried_heldout=held[keep])
    del frame
    out = OUT / name
    out.mkdir(parents=True, exist_ok=False)
    cut.to_parquet(out / "rows.parquet", index=False)
    manifest = json.loads((src / "manifest.json").read_text())
    manifest |= {
        "rows": len(cut),
        "rows_sha256": data.sha256(out / "rows.parquet"),
        "rehearsal": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": f"the rows of the first 1 in {K} buildings of a permutation of the sorted "
            f"building ids by numpy's default_rng({SEED}), and of the first 1 in {R} of a "
            "second permutation, by the same generator, of the sorted ids of the buildings "
            "with an income_restricted_v2 row; carried_heldout is the full data's latest "
            "split",
            "buildings": len(pick),
            "carried_heldout": int(cut.carried_heldout.sum()),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        name, len(cut), "rows", int(cut.carried_heldout.sum()), "held out", flush=True
    )
