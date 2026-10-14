"""Builds the registry `west-coast-wings-v1` needs: a registry (the NB8 one
unless SOURCE names another, such as NB9's) plus a row for
the-west-coast-west-wing, copied from the-west-coast's (BBL 1006430001,
BIN 1012154, the same position). The lot's nine warehouses share the BIN 1012154
footprint, so both wings join the same lot, footprint and position.

Usage: westcoast_wing_registry.py OUTDIR [SOURCE]
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

SOURCE = Path("/data1/apartments/external/registry/20261010-b5c71cf")
WING = "the-west-coast-west-wing"


def main(out: Path, source: Path = SOURCE) -> None:
    registry = pd.read_parquet(source / "buildings.parquet")
    assert WING not in set(registry.building)
    row = registry[registry.building.eq("the-west-coast")].assign(
        building=WING, method="override"
    )
    assert len(row) == 1
    table = pd.concat([registry, row], ignore_index=True)
    out.mkdir(parents=True)
    path = out / "buildings.parquet"
    table.to_parquet(path, index=False)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    provenance = {
        "merged": [str(source)],
        "added": {WING: "copy of the-west-coast's row, method override"},
        "commit": commit,
        "buildings": len(table),
        "methods": table.method.value_counts().to_dict(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:3]))
