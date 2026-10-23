"""Export the base run's laundry feature for sol61's frozen endpoint manifest.

    python export_laundry_snapshot.py

I read `listing_id` and `laundry` from the unit-features snapshot the base run
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000` names in its result.json, and left join
them onto every row of `members/sol61/checks/laundry_audit_endpoints.parquet`. Each manifest row
keeps its order and gets:

- `snapshot_rows`: the number of snapshot rows with its listing_id (0, 1 or more);
- `laundry_raw`: the snapshot's value for the first of those rows, null when there is none;
- `laundry_model`: the value the model's design used, which is `laundry_raw` with a missing
  row read as unstated, as `building_zones_unit.columns` does at commit 6b5a5b4a.

The counts and the provenance go to manifest.json beside the output.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

SNAP = Path("/data1/apartments/external/unit-features/20261021-16cea7c/unit_features.parquet")
ENDPOINTS = Path(
    "/data1/apartments/research-group/members/sol61/checks/laundry_audit_endpoints.parquet"
)
HERE = Path(__file__).resolve().parent


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


m = pd.read_parquet(ENDPOINTS)
s = pd.read_parquet(SNAP, columns=["listing_id", "laundry"])
n = s.listing_id.value_counts()
first = s.drop_duplicates("listing_id").set_index("listing_id").laundry
key = m.listing_id.astype(str)
out = pd.DataFrame(
    {
        "listing_id": m.listing_id,
        "snapshot_rows": key.map(n).fillna(0).astype(int).to_numpy(),
        "laundry_raw": key.map(first).to_numpy(),
    }
)
out["laundry_model"] = out.laundry_raw.fillna("unstated")
out.to_parquet(HERE / "laundry_snapshot_endpoints.parquet", index=False)
manifest = {
    "snapshot": str(SNAP),
    "snapshot_sha256": sha256(SNAP),
    "snapshot_bytes": SNAP.stat().st_size,
    "snapshot_rows": int(len(s)),
    "snapshot_duplicate_listing_ids": int((n > 1).sum()),
    "snapshot_null_laundry": int(s.laundry.isna().sum()),
    "snapshot_laundry_counts": s.laundry.value_counts(dropna=False).astype(int).to_dict(),
    "endpoints": str(ENDPOINTS),
    "endpoints_sha256": sha256(ENDPOINTS),
    "endpoint_rows": int(len(m)),
    "endpoint_snapshot_rows_counts": out.snapshot_rows.value_counts().sort_index().astype(int).to_dict(),
    "snapshot_writer": "commit 16cea7c2, frontier/src/rentfrontier/unit_features.py: laundry() "
    "takes each listing's first pipeline row (drop_duplicates on listing_id) and keeps "
    "laundry_type in_unit or in_building, else unstated",
    "snapshot_input": "pipeline rows of rows-edc83b49f9bacd8c (as the writer's docstring names)",
    "model_reader": "commit 6b5a5b4a, frontier/src/rentfrontier/building_zones_unit.py: "
    "columns() takes the first snapshot row per listing_id, reads a missing listing as "
    "unstated, and sets unit:laundry_in_unit and unit:laundry_in_building as indicators "
    "against unstated",
}
(HERE / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
print(json.dumps({k: manifest[k] for k in manifest if "counts" in k or "duplicate" in k or "null" in k}, indent=1, default=str))
