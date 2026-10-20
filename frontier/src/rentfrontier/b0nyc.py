"""Write a B0 dataset holding only SRC's New York City rows.

    python -m rentfrontier.b0nyc SRC OUT

The all-data datasets since 2026-10-19 carry Jersey City and Hoboken rows (about 72,600 of
1,969,084 in `b0-30b3edae310c2fae-alldata-v36-dense`). A fit on NYC alone needs them out.

I read SRC's `rows.parquet` and mark a row as NJ when its building appears in the NJ building
registry (`building_attrs.REGISTRY_NJ`). In the v36 dense dataset that marks exactly the rows
in the Hoboken, Historic Downtown, Waterfront, Newport and Paulus Hook neighbourhoods. I then
write OUT with:

- `rows.parquet`: SRC's other rows, in SRC's order.
- `set_aside.parquet`: the NJ rows, kept for the record.
- `manifest.json`: SRC's manifest with `rows`, `latest_day_how`, `flags` and `rows_sha256`
  updated for the kept rows, and a `region` entry giving SRC's path and rows SHA-256, the
  registry's path and SHA-256, and how many rows I set aside.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .b0data import sha256
from .building_attrs import REGISTRY_NJ


def nyc_only(src: Path, out: Path, registry: Path = REGISTRY_NJ) -> dict:
    frame = pd.read_parquet(src / "rows.parquet")
    manifest = json.loads((src / "manifest.json").read_text())
    nj = pd.read_parquet(registry, columns=["building"]).building
    keep = ~frame.building.isin(nj).to_numpy()
    out.mkdir(parents=True, exist_ok=False)
    kept = frame[keep]
    kept.to_parquet(out / "rows.parquet", index=False)
    frame[~keep].to_parquet(out / "set_aside.parquet", index=False)
    manifest |= {
        "rows": int(keep.sum()),
        "latest_day_how": kept.latest_day_how.value_counts().to_dict(),
        "flags": {name: int(kept[name].sum()) for name in manifest.get("flags", {})},
        "rows_sha256": sha256(out / "rows.parquet"),
        "region": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "drop rows whose building is in the NJ building registry",
            "registry": str(registry),
            "registry_sha256": sha256(registry),
            "set_aside": int((~keep).sum()),
            "set_aside_sha256": sha256(out / "set_aside.parquet"),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(nyc_only(args.src, args.out), indent=2))


if __name__ == "__main__":
    main()
