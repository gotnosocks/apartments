import json
import os
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from .db import connect
from .scope import load_targets

PLUTO_ENDPOINT = "https://data.cityofnewyork.us/resource/64uk-42ks.json"


def _integer(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def fetch_pluto() -> list[dict[str, Any]]:
    """Fetch the target condo lot and primary-address lots on the street segment."""
    targets = load_targets()
    segment = targets["street"]
    headers = {}
    if token := os.getenv("NYC_OPEN_DATA_TOKEN"):
        headers["X-App-Token"] = token
    params = {
        "$limit": 500,
        "$where": "borough='MN' AND address like '%WEST 15 STREET'",
    }
    response = httpx.get(PLUTO_ENDPOINT, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    rows = response.json()
    selected = []
    for row in rows:
        match = re.match(r"^(\d+)", row.get("address", ""))
        if match and segment["minimum_house_number"] <= int(match.group(1)) <= segment["maximum_house_number"]:
            selected.append(row)

    # 130 W 15th is an alternate address on a condo lot whose PLUTO primary
    # address is 125 W 14th, so explicitly fetch its BBL.
    target_bbl = targets["building"]["bbl"]
    if not any(str(row.get("bbl", "")).split(".")[0] == target_bbl for row in selected):
        params = {"$limit": 1, "$where": f"bbl='{target_bbl}'"}
        response = httpx.get(PLUTO_ENDPOINT, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        selected.extend(response.json())
    return selected


def ingest_pluto(db_path: str = "data/apartments.duckdb") -> int:
    rows = fetch_pluto()
    db = connect(db_path)
    for row in rows:
        bbl = str(row.get("bbl", "")).split(".")[0]
        db.execute(
            """INSERT INTO buildings (
                source, source_id, bbl, canonical_address, borough, zipcode,
                latitude, longitude, year_built, residential_units, total_units,
                floors, building_class, raw_json, updated_at
            ) VALUES ('nyc_pluto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT (source, source_id) DO UPDATE SET
                canonical_address=excluded.canonical_address,
                zipcode=excluded.zipcode, latitude=excluded.latitude,
                longitude=excluded.longitude, year_built=excluded.year_built,
                residential_units=excluded.residential_units,
                total_units=excluded.total_units, floors=excluded.floors,
                building_class=excluded.building_class, raw_json=excluded.raw_json,
                updated_at=now()""",
            [
                bbl, bbl, row.get("address"), row.get("borough"), row.get("zipcode"),
                row.get("latitude"), row.get("longitude"), _integer(row.get("yearbuilt")),
                _integer(row.get("unitsres")), _integer(row.get("unitstotal")),
                row.get("numfloors"), row.get("bldgclass"), json.dumps(row),
            ],
        )
    db.close()
    return len(rows)
