"""Write a B0 dataset with each row's unit as the pipeline's label rule `unit-labels-v18` gives
it.

    python -m rentfrontier.b0labeljoin SRC UNITS OUT

A broker can move a StreetEasy property record from one apartment to the next, and the
record's history then lists the ads of both. The history layer of `unit-labels-v17` joins the
two unit pages of such a pair. `unit-labels-v18` joins them only when their labels agree up to
spelling (`pipeline/models/analysis/label_units.py`). The note
`docs/notes/label-join-2026-11-13.md` reruns both rules on the pipeline build behind SRC and
writes UNITS, a parquet file with a row for each of SRC's rows: its `listing_id`, `split17`, the
unit v17 and `unit-splits-v4` give it, and `split18`, the unit v18 and `unit-splits-v4` give it.

For each row the script

1. finds the row's line in UNITS by `listing_id`;
2. gives the row `split18` as its `unit_id` when its `unit_id` in SRC equals `split17`, and
   keeps SRC's `unit_id` otherwise;
3. marks the row `carried_heldout` when SRC's latest split holds it out and the row is still
   the single latest row of a unit with two or more rows, as `b0chains.carried` does, so a fit
   with `--split carried` scores held-out ads that SRC's fit also held out.

Rows the pipeline's `analysis.label_months` drops under v17 and keeps under v18 are missing
from SRC, and the script adds none of them.

OUT gets:

- `rows.parquet`: SRC's rows in SRC's order, with `unit_id` replaced and `carried_heldout`
  (bool) added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `label_join` entry giving
  SRC's path and rows SHA-256, the UNITS file with its SHA-256, the rule and counts of the rows
  and units changed and of the held-out rows.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from . import splits
from .b0chains import carried
from .b0data import sha256


def joined_units(frame: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """For each row of `frame` (`listing_id`, `unit_id`): `unit_id`, the row's unit in `units`
    (`listing_id`, `split17`, `split18`) under v18 where SRC's unit matches `split17`, or its
    unit in `frame` otherwise; `found`, whether `units` lists the row; and `matched`, whether
    SRC's unit equals `split17`."""
    if units.listing_id.astype(str).duplicated().any():
        raise SystemExit("UNITS lists a listing twice")
    line = units.assign(listing_id=units.listing_id.astype(str)).set_index("listing_id")
    lid = frame.listing_id.astype(str)
    split17 = lid.map(line.split17)
    split18 = lid.map(line.split18)
    matched = split17.notna() & split17.eq(frame.unit_id)
    return pd.DataFrame(
        {
            "unit_id": frame.unit_id.where(~matched, split18),
            "found": split17.notna().to_numpy(),
            "matched": matched.to_numpy(),
        },
        index=frame.index,
    )


def label_join(src: Path, units_path: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    units = pd.read_parquet(units_path, columns=["listing_id", "split17", "split18"])
    joined = joined_units(frame, units)
    held = splits.latest_split(frame)
    before = frame.unit_id
    frame["unit_id"] = joined.unit_id
    frame["carried_heldout"] = carried(frame, held)
    changed = (before.ne(frame.unit_id) & before.notna()).to_numpy()
    # OUT is made after every read, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "label_join": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "units": {"path": str(units_path), "sha256": sha256(units_path)},
            "rule": "unit_id is split18 of UNITS (unit-labels-v18 then unit-splits-v4) where "
            "SRC's unit_id equals split17 (unit-labels-v17 then unit-splits-v4), and SRC's "
            "unit_id otherwise; carried_heldout is SRC's latest split on rows still the "
            "single latest row of a unit with two or more rows",
            "rows": len(frame),
            "rows_missing_from_units": int((~joined.found).sum()),
            "rows_unmatched": int((joined.found & ~joined.matched).sum()),
            "rows_changing_unit": int(changed.sum()),
            "source_units_changed": int(before[changed].nunique()),
            "units_after_change": int(frame.unit_id[changed].nunique()),
            "heldout": int(held.sum()),
            "carried_heldout": int(frame.carried_heldout.sum()),
            "heldout_changing_unit": int((held & changed).sum()),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("units", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(
        json.dumps(label_join(args.src, args.units, args.out)["label_join"], indent=2)
    )


if __name__ == "__main__":
    main()
