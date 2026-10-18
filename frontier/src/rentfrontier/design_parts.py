"""The parts of a run's design that the estimate kit and the rent map read.

The kit and the rent map read little of a design: the buildings, units and
months it indexes, the offset, the feature names and groups, and a few
averages over the fit's rows, a row per building or per bedroom group. On the
served all-scraped run the whole design took 6.3 GB to load (the feature
matrix twice, once for every row and once for the rows in the fit), against
about 100 MB for these parts.

The summary already prepares and checks the whole design, so it writes the
parts into its bundle as FILE (`from_design`, `write`). `rentfrontier.kit`
and `rentfrontier.rentmap` load them from the bundle they are given
(`for_run`), after checking them against the run as `summary.verify_run`
checks a design:

1. the dataset's sha256 equals the run's recorded one
2. the held-out rows' audit ids equal the ones in the run's heldout.npz
3. the buildings and units equal the ones in the run's saved draws

The parts also carry the hash of the rows after the split and data rules
(`data.rows_sha256`), and `for_run` records whether it equals the run's. It
can differ while the rows are the same: the hash covers `log_rent`, and on the
served all-scraped run the design prepared on Modal held 8 of 1.75M log rents
1 ulp away from thelio's `np.log` of the same asks, so its hash differed from
the fit's while every other column hashed the same. Without a bundle, or with
parts that fail the check, `for_run` prepares the whole design. The kit then
checks it with `summary.verify_run`, as it always did, and the rent map uses it
unchecked, as it always did.

The averages come from the same functions in both cases (`rentmap.x_means`,
`rentmap.building_years`, `rentmap.building_hoods`), so a kit or a map from
the parts matches one from the whole design.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

FILE = "design-parts.npz"
VERSION = "design-parts-v1"


@dataclasses.dataclass
class Parts:
    """The design's indexes and averages. `features` holds the names and
    groups, so a Parts reads as both `prep` and `feats` where the kit and the
    rent map take them."""

    buildings: np.ndarray
    units: np.ndarray
    periods: pd.DatetimeIndex
    offset: float
    features: SimpleNamespace
    # Per building: the average x over its rows in the fit, its rows in the
    # fit, and the first and last calendar year of those rows (NaN without).
    building_x: np.ndarray
    building_rows: np.ndarray
    building_first: np.ndarray
    building_last: np.ndarray
    # Per rentmap.BEDROOMS group: the average x and centred bedroom count.
    bedroom_x: np.ndarray
    bedroom_beds: np.ndarray
    # Each building's neighbourhood, and the neighbourhoods the fit covers.
    hood: np.ndarray
    area: str
    # `ids_sha256` of the held-out rows' audit ids.
    heldout_sha256: str


def ids_sha256(audit_ids) -> str:
    """A hash of audit ids in their order."""
    return hashlib.sha256(json.dumps([str(a) for a in audit_ids]).encode()).hexdigest()


def from_design(frame, heldout, feats, prep) -> Parts:
    from . import rentmap

    building_x, bedroom_x, bedroom_beds = rentmap.x_means(prep)
    rows, first, last = rentmap.building_years(prep)
    return Parts(
        buildings=prep.buildings,
        units=prep.units,
        periods=prep.periods,
        offset=float(prep.offset),
        features=SimpleNamespace(names=list(feats.names), groups=list(feats.groups)),
        building_x=building_x,
        building_rows=rows,
        building_first=first,
        building_last=last,
        bedroom_x=bedroom_x,
        bedroom_beds=bedroom_beds,
        hood=rentmap.building_hoods(frame, heldout, prep.buildings),
        area=rentmap.fit_area(frame, heldout),
        heldout_sha256=ids_sha256(frame.audit_id.to_numpy()[heldout]),
    )


def write(parts: Parts, path: Path, dataset_sha256: str, rows_sha256: str) -> dict:
    """Write the parts to `path` with the hashes they were checked against,
    and return the bundle's record of them."""
    meta = {
        "version": VERSION,
        "dataset_observations_sha256": dataset_sha256,
        "rows_sha256": rows_sha256,
        "offset": parts.offset,
        "names": parts.features.names,
        "groups": parts.features.groups,
        "area": parts.area,
        "heldout_sha256": parts.heldout_sha256,
    }
    with open(path, "wb") as f:
        np.savez_compressed(
            f,
            meta=np.array(json.dumps(meta)),
            buildings=np.asarray(parts.buildings).astype(str),
            units=np.asarray(parts.units).astype(str),
            periods=parts.periods.to_numpy(),
            building_x=parts.building_x,
            building_rows=parts.building_rows,
            building_first=parts.building_first,
            building_last=parts.building_last,
            bedroom_x=parts.bedroom_x,
            bedroom_beds=parts.bedroom_beds,
            hood=np.asarray(parts.hood).astype(str),
        )
    return {"file": path.name, "rows_sha256": rows_sha256}


def load(path: Path) -> tuple[Parts, dict]:
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(str(z["meta"]))
        if meta.get("version") != VERSION:
            raise ValueError(f"{path} is {meta.get('version')}, not {VERSION}")
        parts = Parts(
            buildings=z["buildings"].astype(object),
            units=z["units"].astype(object),
            periods=pd.DatetimeIndex(z["periods"]),
            offset=meta["offset"],
            features=SimpleNamespace(names=meta["names"], groups=meta["groups"]),
            building_x=z["building_x"],
            building_rows=z["building_rows"],
            building_first=z["building_first"],
            building_last=z["building_last"],
            bedroom_x=z["bedroom_x"],
            bedroom_beds=z["bedroom_beds"],
            hood=z["hood"].astype(object),
            area=meta["area"],
            heldout_sha256=meta["heldout_sha256"],
        )
    return parts, meta


def mismatch(parts: Parts, meta: dict, result: dict, run_dir: Path, post) -> str | None:
    """Why the parts do not go with the run, or None when they do."""
    if meta["dataset_observations_sha256"] != result["dataset_observations_sha256"]:
        return "dataset differs from the run's recorded dataset"
    recorded = np.load(run_dir / "heldout.npz", allow_pickle=True)["audit_id"]
    if parts.heldout_sha256 != ids_sha256(recorded):
        return "held-out rows differ from the run's recorded rows"
    if not (
        np.array_equal(parts.units, post["units"])
        and np.array_equal(parts.buildings, post["buildings"])
    ):
        return "units or buildings differ from the run's saved draws"
    return None


def for_run(
    result: dict, run_dir: Path, summary_dir: Path | None, verify: bool = True
) -> tuple:
    """(parts, source) for a recorded run: the parts in its summary bundle
    when they go with the run, else the parts of its whole design, checked
    with `summary.verify_run` when `verify` is set. `source` says which, and
    why the bundle's were passed over."""
    from . import data, design, summary

    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    reason = "no summary bundle given"
    if summary_dir is not None:
        path = summary_dir / FILE
        if path.exists():
            parts, meta = load(path)
            reason = mismatch(parts, meta, result, run_dir, post)
            if reason is None:
                return parts, {
                    "design": "summary bundle",
                    "file": str(path),
                    "rows_sha256_matches_run": meta["rows_sha256"]
                    == result.get("rows_sha256"),
                }
            print(f"not using {path}: {reason}", file=sys.stderr)
        else:
            reason = f"the bundle has no {FILE}"
    frame = data.load(Path(result["dataset"]))
    frame, heldout, feats, prep = design.prepared(
        frame, result["split"], data.recorded_rules(result), result["feature_set"]
    )
    if verify:
        summary.verify_run(
            result, frame, heldout, prep, run_dir, post["units"], post["buildings"]
        )
    return from_design(frame, heldout, feats, prep), {
        "design": "prepared",
        "bundle_parts_unused": reason,
    }
