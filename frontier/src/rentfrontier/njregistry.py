"""Tax parcels for Hoboken and Jersey City, and a lot registry for the New Jersey buildings.

The NYC registry (`registry`, `registry_extend`) keys each building to a BBL through NYC
GeoSearch, which has no lots in New Jersey, so `registry_extend` leaves the NJ buildings out.
This module gives them the NJ counterpart of a BBL: the parcel's PAMS_PIN, municipality code,
block and lot (`0905_13_1` is Hoboken block 13 lot 1), from the statewide parcel composite of the
NJ Office of GIS with the Treasury's MOD-IV tax list joined (`PARCELS_URL`).

    python -m rentfrontier.njregistry parcels
    python -m rentfrontier.njregistry registry [--parcels DIR] [--catalog FILE]

`parcels` reads every parcel of MUNICIPALITIES, 2,000 to a query, with its outline in WGS84, and
writes EXTERNAL_ROOT/njparcels/<date>-<commit>/parcels.parquet with provenance.json. I keep the
MOD-IV fields describing the lot and its building (class, building and land descriptions, year
built, dwellings, acreage) and the release date of the parcel and tax data. As with MapPLUTO in
`external`, I leave out assessed values, taxes and sales: a rental building's assessment comes
from its rent roll, so a feature reading it would be partly circular. The layer holds the
current release only, so the snapshot dates each lot by its `PCL_PBDATE`.

`registry` reads the newest pipeline build's export building records (`registry_extend`), keeps
the NJ ones and places each StreetEasy `geoCenter` point in a parcel:

1. A parcel containing the point gives method `parcel`. Condominium units have their own
   small parcels (qualifier `C002A` and the like) inside the lot, so I key the building to the
   lot: `lot` is the PIN without its qualifier, and among several lots containing the point
   the one with the larger parcel wins.
2. A point in no parcel, as on a street, takes the nearest parcel vertex within NEAR_M, as
   method `near`, with the distance in `distance_m`.
3. Anything else gets method `none` and keeps its point.

It writes EXTERNAL_ROOT/registry-nj/<date>-<commit>/registry.parquet (building, building_id,
method, lot, pams_pin, label, latitude, longitude, distance_m) and provenance.json. The NYC
registry stays as it is, and no model reads this one until a fit names it. When the newest
snapshot already holds every NJ building of the build and read the same parcels, I write none.
`apartments-registry-extend.service` runs this step after `registry_extend`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import registry_extend
from .listing_extras import EXTERNAL_ROOT, _git

PARCELS_URL = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
    "Parcels_Composite_NJ_WM/FeatureServer/0/query"
)
MUNICIPALITIES = {"0905": "Hoboken", "0906": "Jersey City"}
PAGE = 2000
# MOD-IV and parcel fields kept, by their names in the layer.
FIELDS = {
    "PAMS_PIN": "pams_pin",
    "PCL_MUN": "mun",
    "PCLBLOCK": "block",
    "PCLLOT": "lot_number",
    "PCLQCODE": "qualifier",
    "PROP_LOC": "address",
    "PROP_CLASS": "prop_class",
    "BLDG_CLASS": "bldg_class",
    "PROP_USE": "prop_use",
    "BLDG_DESC": "bldg_desc",
    "LAND_DESC": "land_desc",
    "YR_CONSTR": "year_built",
    "DWELL": "dwellings",
    "COMM_DWELL": "comm_dwellings",
    "CALC_ACRE": "acres",
    "ZIP5": "zip",
    "PCL_PBDATE": "released",
    "PCLLASTUPD": "parcel_updated",
}
NEAR_M = 30.0
M_PER_DEG_LAT = 111_320.0


def _get(params: dict) -> dict:
    url = f"{PARCELS_URL}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return json.loads(response.read())
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError


def fetch_parcels() -> pd.DataFrame:
    """Every parcel of MUNICIPALITIES with the FIELDS and its outline as GeoJSON."""
    where = "PCL_MUN IN (" + ",".join(f"'{m}'" for m in MUNICIPALITIES) + ")"
    rows, offset = [], 0
    while True:
        page = _get(
            {
                "where": where,
                "outFields": ",".join(FIELDS),
                "outSR": 4326,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": PAGE,
                "f": "geojson",
            }
        )
        features = page["features"]
        for f in features:
            row = {FIELDS[k]: v for k, v in f["properties"].items() if k in FIELDS}
            row["geometry"] = json.dumps(f["geometry"]) if f["geometry"] else None
            rows.append(row)
        offset += len(features)
        if not features or not page.get("properties", {}).get("exceededTransferLimit"):
            break
    table = pd.DataFrame(rows, columns=[*FIELDS.values(), "geometry"])
    for col in ("released", "parcel_updated"):
        table[col] = pd.to_datetime(table[col], unit="ms", utc=True).dt.date.astype(str)
    table["lot"] = lot_of(table.pams_pin)
    return table


def lot_of(pins: pd.Series) -> pd.Series:
    """The PIN of the lot: municipality, block and lot, without the condominium qualifier."""
    return pins.str.split("_").str[:3].str.join("_")


def rings(geometry: str | None) -> list[np.ndarray]:
    """The rings of a Polygon or MultiPolygon as (n, 2) lon/lat arrays."""
    if not geometry:
        return []
    g = json.loads(geometry)
    polygons = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    return [np.asarray(r, dtype=float) for p in polygons for r in p]


def contains(parts: list[np.ndarray], x: float, y: float) -> bool:
    """Whether the point falls inside the polygon, by the even-odd rule over all its rings, so a
    hole takes the point back out."""
    inside = False
    for r in parts:
        x0, y0, x1, y1 = r[:-1, 0], r[:-1, 1], r[1:, 0], r[1:, 1]
        cross = (y0 > y) != (y1 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        inside ^= bool(np.count_nonzero(cross & (x < at)) % 2)
    return inside


def area(parts: list[np.ndarray]) -> float:
    """Shoelace area of the outer rings, in square degrees, for ranking parcels only."""
    return sum(
        abs(np.dot(r[:, 0], np.roll(r[:, 1], 1)) - np.dot(r[:, 1], np.roll(r[:, 0], 1)))
        / 2
        for r in parts[:1]
    )


SUFFIXES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "AV": "AVE",
    "BOULEVARD": "BLVD",
    "PLACE": "PL",
    "DRIVE": "DR",
    "ROAD": "RD",
    "COURT": "CT",
    "LANE": "LN",
    "TERRACE": "TER",
    "TERR": "TER",
    "PARKWAY": "PKWY",
    "PLAZA": "PLZ",
    "SQUARE": "SQ",
    "HIGHWAY": "HWY",
    "WEST": "W",
    "EAST": "E",
    "NORTH": "N",
    "SOUTH": "S",
}
ORDINALS = {
    w: str(k)
    for k, w in enumerate(
        "FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH"
        " THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH"
        " TWENTIETH".split(),
        start=1,
    )
}
# Spellings the tax list uses beside the right ones.
ORDINALS |= {"EIGHT": "8", "NINETH": "9", "TWELVTH": "12"}
HOUSE = re.compile(r"^(\d+)[A-Z]?(?:-(\d+)[A-Z]?)?\s+(.+)$")
# The house number ranges of a tax list address ("121-125 GARDEN ST", "330-32 VAN HORNE ST")
# expand to each number of the start's parity, up to this span.
MAX_SPAN = 40
# A building with no lot at its address takes a lot on the same side of the same street within
# STREET_NUMBERS house numbers and STREET_M meters of its point.
STREET_NUMBERS = 10
STREET_M = 60.0


# Street names StreetEasy and the tax list write differently.
STREET_ALIASES = {"CHRISTOPHER COLUMBUS": "COLUMBUS"}


def street_key(street: str) -> str:
    for long, short in STREET_ALIASES.items():
        street = street.replace(long, short)
    words = []
    for w in street.split():
        w = re.sub(r"^(\d+)(ST|ND|RD|TH)$", r"\1", w)
        words.append(ORDINALS.get(w) or SUFFIXES.get(w, w))
    return " ".join(words)


def address_keys(address: str | None) -> list[str]:
    """The `number street` keys of an address, one per house number. A tax list address
    joining two streets with a slash gives the keys of each."""
    if not address or not isinstance(address, str):
        return []
    keys = []
    for part in address.upper().split("/"):
        part = re.sub(r"[.,#]", " ", part).strip()
        m = HOUSE.match(part)
        if not m:
            continue
        start, end, street = m.groups()
        street = street_key(street)
        numbers = [int(start)]
        if end:
            stop = int(start[: max(len(start) - len(end), 0)] + end)
            if start[0] != "0" and 0 < stop - int(start) <= MAX_SPAN:
                numbers = list(range(int(start), stop + 1, 2))
                if stop not in numbers:
                    numbers.append(stop)
        keys += [f"{n} {street}" for n in numbers]
    return keys


def place(buildings: pd.DataFrame, parcels: pd.DataFrame) -> pd.DataFrame:
    """Each building's lot by its address, else by its point, as the module docstring
    describes."""
    shapes = [rings(g) for g in parcels.geometry]
    vertices = [np.concatenate(s) if s else np.empty((0, 2)) for s in shapes]
    box = np.array(
        [
            [v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max()]
            if len(v)
            else [np.nan] * 4
            for v in vertices
        ]
    )
    sizes = np.array([area(s) if s else 0.0 for s in shapes])
    pins, lots, labels, muns = (
        parcels[c].to_numpy() for c in ("pams_pin", "lot", "address", "mun")
    )
    by_key: dict[tuple[str, str], list[int]] = {}
    by_street: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for k, a in enumerate(labels):
        for key in address_keys(a):
            by_key.setdefault((muns[k], key), []).append(k)
            number, street = key.split(" ", 1)
            by_street.setdefault((muns[k], street), []).append((int(number), k))
    city_mun = {v.upper(): k for k, v in MUNICIPALITIES.items()}

    def distance(k: int, x: float, y: float) -> float:
        if box[k, 0] <= x <= box[k, 2] and box[k, 1] <= y <= box[k, 3]:
            if contains(shapes[k], x, y):
                return 0.0
        m_per_deg_lon = M_PER_DEG_LAT * np.cos(np.radians(y))
        v = vertices[k]
        return float(
            np.hypot((v[:, 0] - x) * m_per_deg_lon, (v[:, 1] - y) * M_PER_DEG_LAT).min()
        )

    out = []
    for b in buildings.itertuples():
        row = {
            "building": b.building,
            "building_id": b.building_id,
            "method": "none",
            "lot": None,
            "pams_pin": None,
            "label": None,
            "latitude": b.latitude,
            "longitude": b.longitude,
            "distance_m": np.nan,
        }
        out.append(row)
        located = not (pd.isna(b.latitude) or pd.isna(b.longitude))
        x, y = (float(b.longitude), float(b.latitude)) if located else (np.nan, np.nan)
        mun = city_mun.get(str(b.city or "").strip().upper())
        keys = address_keys(b.street)
        hits = sorted(
            {
                k
                for key in keys
                for m in ([mun] if mun else MUNICIPALITIES)
                for k in by_key.get((m, key), [])
            }
        )
        if hits:
            # The nearest lot of those with the address, and its largest parcel.
            d = {k: distance(k, x, y) if located else np.nan for k in hits}
            lot = min(hits, key=lambda k: (d[k] if located else 0.0, -sizes[k]))
            same = [k for k in hits if lots[k] == lots[lot]]
            k = max(same, key=lambda k: sizes[k])
            row.update(method="address", distance_m=min(d[j] for j in same))
            row.update(lot=lots[k], pams_pin=pins[k], label=labels[k])
            continue
        if not located:
            continue
        close = []
        for key in keys:
            number, street = key.split(" ", 1)
            for m in [mun] if mun else MUNICIPALITIES:
                for n, k in by_street.get((m, street), []):
                    gap = abs(n - int(number))
                    if gap <= STREET_NUMBERS and gap % 2 == 0:
                        close.append((gap, k))
        close = [(gap, distance(k, x, y), k) for gap, k in close]
        close = [c for c in close if c[1] <= STREET_M]
        if close:
            _, dist, k = min(close, key=lambda c: (c[0], c[1], -sizes[c[2]]))
            row.update(method="street", distance_m=dist)
            row.update(lot=lots[k], pams_pin=pins[k], label=labels[k])
            continue
        m_per_deg_lon = M_PER_DEG_LAT * np.cos(np.radians(y))
        pad_x, pad_y = NEAR_M / m_per_deg_lon, NEAR_M / M_PER_DEG_LAT
        near = np.flatnonzero(
            (box[:, 0] - pad_x <= x)
            & (x <= box[:, 2] + pad_x)
            & (box[:, 1] - pad_y <= y)
            & (y <= box[:, 3] + pad_y)
        )
        if not len(near):
            continue
        d = np.array([distance(k, x, y) for k in near])
        inside = near[d == 0]
        if len(inside):
            k = max(inside, key=lambda k: sizes[k])
            row.update(method="parcel", distance_m=0.0)
        elif d.min() <= NEAR_M:
            k = near[int(np.argmin(d))]
            row.update(method="near", distance_m=float(d.min()))
        else:
            continue
        row.update(lot=lots[k], pams_pin=pins[k], label=labels[k])
    return pd.DataFrame(out)


def nj_buildings(build: dict) -> pd.DataFrame:
    """The export's buildings with an NJ address, with their street address."""
    root = Path(build["export"])
    parts = [
        pd.read_parquet(root / f, columns=["building_id", "fetched", "record"])
        for f in sorted(build["buildings"]["files"])
    ]
    frame = pd.concat(parts, ignore_index=True).dropna(subset=["record"])
    frame = frame.sort_values("fetched").drop_duplicates("building_id", keep="last")
    rows = []
    for building_id, record in zip(frame.building_id, frame.record):
        r = json.loads(record)
        address = r.get("address") or {}
        if str(address.get("state") or "").strip().upper() != "NJ":
            continue
        point = r.get("geoCenter") or {}
        rows.append(
            (
                building_id,
                r.get("slug"),
                point.get("latitude"),
                point.get("longitude"),
                address.get("street"),
                address.get("city"),
            )
        )
    columns = ["building_id", "building", "latitude", "longitude", "street", "city"]
    return pd.DataFrame(rows, columns=columns)


def newest(root: Path, name: str) -> Path:
    paths = sorted(root.glob(f"*/{name}"), key=lambda p: p.stat().st_mtime)
    if not paths:
        raise SystemExit(f"no {name} under {root}")
    return paths[-1].parent


def write(table: pd.DataFrame, out_dir: Path, name: str, provenance: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=False)
    scratch = out_dir / f"{name}.tmp"
    table.to_parquet(scratch, index=False)
    provenance["sha256"] = hashlib.sha256(scratch.read_bytes()).hexdigest()
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, default=str)
    )
    path = out_dir / name
    os.replace(scratch, path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("step", choices=["parcels", "registry"])
    parser.add_argument("--parcels", type=Path, help="njparcels snapshot dir")
    parser.add_argument("--catalog", type=Path, default=registry_extend.CATALOG)
    args = parser.parse_args(argv)
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    stamp = f"{started:%Y%m%d}-{commit[:7]}"
    if args.step == "parcels":
        table = fetch_parcels()
        path = write(
            table,
            EXTERNAL_ROOT / "njparcels" / stamp,
            "parcels.parquet",
            {
                "source": PARCELS_URL,
                "dataset": "NJ Parcels Composite with MOD-IV (NJOGIS), Parcels_Composite_NJ_WM",
                "municipalities": MUNICIPALITIES,
                "retrieved_at": started.isoformat(),
                "commit": commit,
                "parcels": len(table),
                "lots": int(table.lot.nunique()),
                "released": table.released.value_counts().to_dict(),
            },
        )
        print(f"wrote {path}: {len(table)} parcels, {table.lot.nunique()} lots")
        return
    parcels_dir = args.parcels or newest(EXTERNAL_ROOT / "njparcels", "parcels.parquet")
    parcels = pd.read_parquet(parcels_dir / "parcels.parquet")
    build = registry_extend.latest_build(args.catalog)
    buildings = nj_buildings(build)
    last = sorted(
        (EXTERNAL_ROOT / "registry-nj").glob("*/registry.parquet"),
        key=lambda p: p.stat().st_mtime,
    )
    if last:
        previous = json.loads((last[-1].parent / "provenance.json").read_text())
        known = set(pd.read_parquet(last[-1], columns=["building"]).building)
        if previous["parcels"] == str(parcels_dir) and set(buildings.building) <= known:
            print(
                f"{last[-1].parent.name} has all {len(buildings)} NJ buildings; no new snapshot"
            )
            return
    table = place(buildings, parcels)
    path = write(
        table,
        EXTERNAL_ROOT / "registry-nj" / stamp,
        "registry.parquet",
        {
            "parcels": str(parcels_dir),
            "parcels_sha256": hashlib.sha256(
                (parcels_dir / "parcels.parquet").read_bytes()
            ).hexdigest(),
            "build": {"built": build["built"], "rows": build["rows"]["path"]},
            "retrieved_at": started.isoformat(),
            "commit": commit,
            "buildings": len(table),
            "methods": table.method.value_counts().to_dict(),
            "near_m": NEAR_M,
            "lots": int(table.lot.nunique()),
        },
    )
    print(
        f"wrote {path}: {len(table)} buildings, {table.method.value_counts().to_dict()}"
    )


if __name__ == "__main__":
    main()
