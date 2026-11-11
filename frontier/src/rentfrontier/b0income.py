"""Write a B0 dataset whose `income_restricted` flag uses the Deals caution's pattern.

    python -m rentfrontier.b0income SRC OUT

`b0data` flags an ad as income-restricted with the older list in `features.DESCRIPTION_FLAGS`
("income restrict", "affordable housing", "housing lottery", "ami"). The `income` caution in
`cautions.TEXT` was chosen by reading 237 market ads on 2026-11-10, and the old list missed 33
of the 55 those readers classed as income-restricted. The outlier sprint of 2026-11-11 found
the same: of the 13 ads far under the served model that its readers called income-restricted
("HPD income requirements apply", "this unit is an hpd lottery", "maximum income 154k"), the
flag covered 4.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256), take each listing's capture with the latest `last_collected_at`, as
`b0data` does, and set the flag where the row's `description_known` is true:

    income_restricted = "income" in cautions.from_text(description)

A row with no known description keeps SRC's flag, which is false. I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with `income_restricted` replaced.
- `set_aside.parquet`: SRC's, copied.
- `manifest.json`: SRC's manifest with `rows_sha256` updated, and an `income` entry giving
  SRC's path and rows SHA-256, the pattern, and how many rows the flag gains and loses.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import cautions
from .b0data import sha256


def income_flags(path: Path, ids: set[str]) -> pd.Series:
    """For each rental listing in `ids`, whether the description of its last capture in the
    records file `path` gives the `income` caution. I read a row group at a time, and its
    record texts only for the rows I keep."""
    seen: dict[str, tuple] = {}
    file = pq.ParquetFile(path)
    for group in range(file.num_row_groups):
        head = file.read_row_group(
            group, columns=["listing_id", "listing_type", "last_collected_at"]
        )
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = head["last_collected_at"].to_pylist()
        keep = [
            kind == "rental" and i in ids and (i not in seen or seen[i][0] < t)
            for i, kind, t in zip(lid, head["listing_type"].to_pylist(), at)
        ]
        if not any(keep):
            continue
        raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
            pa.array(keep)
        )
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), raw in zip(rows, raws["raw_listing_json"].to_pylist()):
            if not raw or (i in seen and seen[i][0] >= t):
                continue
            text = json.loads(raw).get("description")
            seen[i] = (t, "income" in cautions.from_text(text))
        del raws
    return pd.Series({i: flag for i, (_, flag) in seen.items()}, dtype=bool)


def income(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    ids = pd.read_parquet(src / "rows.parquet", columns=["listing_id"]).listing_id
    flags = income_flags(Path(records["path"]), set(ids.astype(str)))
    frame = pd.read_parquet(src / "rows.parquet")
    old = frame.income_restricted.to_numpy(bool)
    new = frame.listing_id.astype(str).map(flags).fillna(False).to_numpy(bool)
    new = np.where(frame.description_known.to_numpy(bool), new, old)
    frame["income_restricted"] = new
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    shutil.copy(src / "set_aside.parquet", out / "set_aside.parquet")
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "income": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "pattern": cautions.TEXT["income"],
            "flagged_before": int(old.sum()),
            "flagged": int(new.sum()),
            "gained": int((new & ~old).sum()),
            "lost": int((old & ~new).sum()),
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
    print(json.dumps(income(args.src, args.out)["income"], indent=2))


if __name__ == "__main__":
    main()
