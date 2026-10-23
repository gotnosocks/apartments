"""Every coded amenity and feature on each listing's latest raw StreetEasy record.

`building_gym` reads only the GYM code from a listing's amenity list. Here I read every code
list of the record, so a model can try them all:

1. `propertyDetails.amenities`: `list` (building amenities such as POOL or CONCIERGE),
   `parkingTypes`, `sharedOutdoorSpaceTypes` and `storageSpaceTypes`;
2. `propertyDetails.features`: `list` (unit features such as CENTRAL_AC), `fireplaceTypes`,
   `privateOutdoorSpaceTypes` and `views`;
3. `propertyDetails.roomCount`, the counts of photos, floor plans and videos under `media`,
   whether `media.tour3dUrl` is set, and `listingSource.sourceType`.

I keep each listing's latest record by `collected_at`. To hold 2.2 million listings in a few
hundred megabytes, I store each code list as a bit mask over the codes seen so far in that
list, and write the masks out as one 0/1 column per code, named `<list>:<code>`. A listing
with an empty amenity list gets `states_amenities` 0, and one with an empty feature list gets
`states_features` 0, since brokers often leave the lists out.

    python -m rentfrontier.listing_codes OUT_DIR [RECORDS]

writes OUT_DIR/listing-codes.parquet and OUT_DIR/provenance.json.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .unit_features import RECORDS

LISTS = {
    "amen": ("amenities", "list"),
    "parking": ("amenities", "parkingTypes"),
    "shared_outdoor": ("amenities", "sharedOutdoorSpaceTypes"),
    "storage": ("amenities", "storageSpaceTypes"),
    "feat": ("features", "list"),
    "fireplace": ("features", "fireplaceTypes"),
    "private_outdoor": ("features", "privateOutdoorSpaceTypes"),
    "views": ("features", "views"),
}
COUNTS = ("rooms", "photos", "floorplans", "videos", "tour3d")


class Codes:
    """The codes seen in one list, each with its bit."""

    def __init__(self):
        self.bit: dict[str, int] = {}

    def mask(self, codes) -> int:
        m = 0
        for c in codes or ():
            if not isinstance(c, str):
                continue
            if c not in self.bit:
                self.bit[c] = len(self.bit)
            m |= 1 << self.bit[c]
        return m


def parse(raw: str, codes: dict[str, Codes]) -> tuple | None:
    """The masks, counts and source type of one raw record, or None when it isn't JSON."""
    try:
        j = json.loads(raw)
    except (TypeError, ValueError):
        return None
    pd_ = j.get("propertyDetails") or {}
    masks = tuple(
        codes[k].mask((pd_.get(a) or {}).get(b)) for k, (a, b) in LISTS.items()
    )
    media = j.get("media") or {}
    counts = (
        pd_.get("roomCount"),
        len(media.get("photos") or ()),
        len(media.get("floorPlans") or ()),
        len(media.get("videos") or ()),
        int(bool(media.get("tour3dUrl"))),
    )
    source = (j.get("listingSource") or {}).get("sourceType")
    return masks, counts, source


def scan(records: Path = RECORDS) -> tuple[pd.DataFrame, dict[str, Codes]]:
    """Each listing's latest record, parsed: masks and counts by listing_id."""
    import pyarrow.parquet as pq

    codes = {k: Codes() for k in LISTS}
    latest: dict[str, tuple] = {}
    f = pq.ParquetFile(records)
    for i in range(f.num_row_groups):
        t = f.read_row_group(
            i, columns=["listing_id", "collected_at", "raw_listing_json"]
        ).to_pandas()
        for lid, at, raw in zip(
            t.listing_id.astype(str), t.collected_at, t.raw_listing_json
        ):
            if lid in latest and latest[lid][0] >= at:
                continue
            p = parse(raw, codes)
            if p is not None:
                latest[lid] = (at, *p)
    ids = list(latest)
    vals = [latest[k] for k in ids]
    out = {"listing_id": ids, "collected_at": [v[0] for v in vals]}
    for n, k in enumerate(LISTS):
        out[f"mask_{k}"] = [v[1][n] for v in vals]
    for n, k in enumerate(COUNTS):
        out[k] = [v[2][n] for v in vals]
    out["source_type"] = [v[3] for v in vals]
    return pd.DataFrame(out), codes


def expand(t: pd.DataFrame, codes: dict[str, Codes]) -> pd.DataFrame:
    """One 0/1 int8 column per code in place of the masks."""
    cols = {}
    for k, c in codes.items():
        m = t.pop(f"mask_{k}").to_numpy(object)
        for code, b in sorted(c.bit.items()):
            cols[f"{k}:{code}"] = np.fromiter(
                ((x >> b) & 1 for x in m), dtype=np.int8, count=len(m)
            )
    t = pd.concat([t, pd.DataFrame(cols, index=t.index)], axis=1)
    amen = [c for c in t.columns if c.split(":")[0] in ("amen", "parking", "storage")]
    feat = [c for c in t.columns if c.startswith("feat:")]
    t["states_amenities"] = (t[amen].sum(axis=1) > 0).astype(np.int8)
    t["states_features"] = (t[feat].sum(axis=1) > 0).astype(np.int8)
    return t


def main(argv=None) -> None:
    """Write OUT_DIR/listing-codes.parquet and its provenance."""
    argv = argv or sys.argv[1:]
    out = Path(argv[0])
    records = Path(argv[1]) if len(argv) > 1 else RECORDS
    out.mkdir(parents=True, exist_ok=True)
    t, codes = scan(records)
    t = expand(t, codes)
    t.to_parquet(out / "listing-codes.parquet")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    prov = {
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "commit": commit,
        "records": str(records),
        "listings": len(t),
        "codes": {k: sorted(c.bit) for k, c in codes.items()},
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=1))
    print(len(t), "listings;", {k: len(c.bit) for k, c in codes.items()})


if __name__ == "__main__":
    main()
