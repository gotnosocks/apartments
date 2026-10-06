"""Snapshots of external data, joined to our buildings through the registry.

    python -m rentfrontier.external pluto

Each source is a dated snapshot under
/data1/apartments/external/<source>/<date>-<commit>/ with the rows used and
provenance.json (URL, query, dataset version, retrieval time, sha256).
Feature sets (features.py) name the snapshot they read, so a run records
exactly which external data it saw. Refuses a dirty tree.

Sources:
- pluto: MapPLUTO (NYC Department of City Planning, NYC Open Data 64uk-42ks),
  one row per tax lot (BBL) in the registry. Assessed values are not kept:
  for rental buildings they are derived from rental income, which would make
  the feature partly circular.
- subway: MTA Subway Stations (data.ny.gov 39hk-dx4f), every station stop with
  its daytime routes and coordinates (transit access).
- basemap: the map under the rent map, around the registry's buildings (their
  bounding box plus BASEMAP_MARGIN_M): street centerlines with width, lanes,
  speed and roadway type (NYC Open Data inkn-q76z), parks (enfh-gkve) and
  Manhattan's shoreline (borough boundary, gthc-hcne). One row per feature,
  geometry as GeoJSON.
- hpd: HPD Housing Maintenance Code Violations (NYC Open Data wvxf-dwi5) of
  the registry's buildings, by BIN, and by tax lot (BBL) for placeholder BINs
  (n000000): class (A non-hazardous, B hazardous, C immediately hazardous, I
  information), when the inspection found it and when the notice was issued,
  and its current status.
- footprints: NYC Building Footprints (5zhs-2jue): every building in the
  registry's bounding box plus FOOTPRINTS_MARGIN_M (the neighbours that block a
  facade's view of a street), and the registry's buildings by BIN, and by tax
  lot (base BBL) for placeholder BINs (n000000): outline, roof height and
  construction year.
- lpc: LPC Designated and Calendared Buildings and Sites (NYC Open Data
  ncre-qhxs), the Landmarks Preservation Commission's record of each lot in
  the registry: individual or interior landmark, or a building in a historic
  district, with the designation date (MapPLUTO's landmark and historic
  district fields are today's status, with no date).
- places: points of interest around the registry's buildings (their bounding
  box plus PLACES_MARGIN_M), one row each with its kind: dog runs and
  off-leash areas (NYC Parks, hxx3-bwgv, the polygon's vertex mean; and
  OpenStreetMap's leisure=dog_park in Manhattan, ODbL, which has Hudson River
  Park's runs, not NYC Parks property), hospitals
  and ambulance or EMS stations (Facilities Database, ji82-xba5), homeless
  drop-in centers (DHS, bmxf-3rd4, and the Facilities Database's), NYCHA
  tax lots (MapPLUTO owner NYC Housing Authority) and Madison Square Garden
  (`MSG`, a fixed point). DHS publishes no shelter addresses.
- storefronts: the Storefront Registry (Department of Finance, NYC Open Data
  92iy-9c3n), every ground- and second-floor storefront filed for in the box,
  every reporting year (the first covers 2019 and 2020): its business
  activity and whether it stood vacant at the year's end.
- gtfs: the MTA's static subway GTFS feed (`GTFS_URL`), kept whole as
  gtfs_subway.zip: stations, timetables and transfers (subway time to midtown,
  `transit`).
- lodes: the Census LEHD Origin-Destination Employment Statistics (LODES8)
  workplace area characteristics for New York, all jobs (`LODES_WAC`), every
  year published (`LODES_YEARS`), by 2020 census block in New York City
  (`NYC_COUNTIES`), with each block's internal point from the LODES
  geography crosswalk: one row per block, a jobs column per year.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from .registry import EXTERNAL_ROOT
from .run import git

REGISTRY = EXTERNAL_ROOT / "registry" / "20260925-6b67137" / "buildings.parquet"
NYC_OPEN_DATA = "https://data.cityofnewyork.us"
SOCRATA = f"{NYC_OPEN_DATA}/resource"
PLUTO_ID = "64uk-42ks"
PLUTO_COLUMNS = (
    "bbl",
    "address",
    "version",
    "yearbuilt",
    "yearalter1",
    "yearalter2",
    "numfloors",
    "numbldgs",
    "unitsres",
    "unitstotal",
    "lotarea",
    "bldgarea",
    "resarea",
    "comarea",
    "retailarea",
    "lotfront",
    "lotdepth",
    "bldgfront",
    "bldgdepth",
    "bldgclass",
    "landuse",
    "landmark",
    "histdist",
    "zonedist1",
    "builtfar",
    "residfar",
    "proxcode",
    "irrlotcode",
    "lottype",
    "bsmtcode",
    "pfirm15_flag",
    "firm07_flag",
    "schooldist",
    "policeprct",
    "latitude",
    "longitude",
)


def _socrata(dataset: str, params: dict) -> list[dict]:
    url = f"{SOCRATA}/{dataset}.json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def fetch_pluto(bbls, batch: int = 100) -> tuple[pd.DataFrame, list[str]]:
    rows, queries = [], []
    bbls = sorted(set(bbls))
    for i in range(0, len(bbls), batch):
        where = f"bbl in ({', '.join(bbls[i : i + batch])})"
        params = {"$select": ", ".join(PLUTO_COLUMNS), "$where": where, "$limit": 5000}
        rows += _socrata(PLUTO_ID, params)
        queries.append(urllib.parse.urlencode(params))
    table = pd.DataFrame(rows, columns=list(PLUTO_COLUMNS))
    table["bbl"] = table.bbl.astype(float).astype("int64").astype(str)
    return table, queries


NY_SOCRATA = "https://data.ny.gov"
SUBWAY_ID = "39hk-dx4f"
SUBWAY_COLUMNS = (
    "gtfs_stop_id",
    "station_id",
    "complex_id",
    "stop_name",
    "line",
    "daytime_routes",
    "structure",
    "borough",
    "ada",
    "gtfs_latitude",
    "gtfs_longitude",
)


def fetch_subway() -> tuple[pd.DataFrame, list[str], dict]:
    params = {"$select": ", ".join(SUBWAY_COLUMNS), "$limit": 5000}
    url = f"{NY_SOCRATA}/resource/{SUBWAY_ID}.json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        rows = json.loads(r.read())
    with urllib.request.urlopen(
        f"{NY_SOCRATA}/api/views/{SUBWAY_ID}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    table = pd.DataFrame(rows, columns=list(SUBWAY_COLUMNS))
    for c in ("gtfs_latitude", "gtfs_longitude"):
        table[c] = table[c].astype(float)
    version = {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }
    return table, [urllib.parse.urlencode(params)], version


CENTERLINE_ID = "inkn-q76z"
PARKS_ID = "enfh-gkve"
BOROUGHS_ID = "gthc-hcne"
BASEMAP_MARGIN_M = 400.0
CENTERLINE_COLUMNS = (
    "physicalid",
    "full_street_name",
    "stname_label",
    "streetwidth",
    "number_travel_lanes",
    "posted_speed",
    "rw_type",
    "trafdir",
    "the_geom",
)


def basemap_box(registry: pd.DataFrame) -> tuple[float, float, float, float]:
    """(north, west, south, east) degrees around the registry's buildings."""
    lat, lon = registry.latitude.dropna(), registry.longitude.dropna()
    dlat = BASEMAP_MARGIN_M / 111_320.0
    dlon = dlat / math.cos(math.radians(lat.mean()))
    return lat.max() + dlat, lon.min() - dlon, lat.min() - dlat, lon.max() + dlon


def fetch_basemap(box) -> tuple[pd.DataFrame, list[str], dict]:
    n, w, s, e = box
    rows, queries, versions = [], [], {}
    for layer, dataset, params in (
        (
            "street",
            CENTERLINE_ID,
            {
                "$select": ", ".join(CENTERLINE_COLUMNS),
                "$where": f"within_box(the_geom, {n}, {w}, {s}, {e})",
                "$limit": 20000,
            },
        ),
        (
            "park",
            PARKS_ID,
            {
                "$select": "signname, typecategory, multipolygon",
                "$where": f"within_box(multipolygon, {n}, {w}, {s}, {e})",
                "$limit": 5000,
            },
        ),
        ("land", BOROUGHS_ID, {"$select": "boroname, the_geom", "borocode": 1}),
    ):
        for r in _socrata(dataset, params):
            geometry = r.pop("the_geom", None) or r.pop("multipolygon", None)
            name = r.pop("full_street_name", None) or r.pop("signname", None)
            rows.append(
                {
                    "layer": layer,
                    "name": name or r.get("boroname"),
                    "attributes": json.dumps(r, sort_keys=True),
                    "geometry": json.dumps(geometry),
                }
            )
        queries.append(f"{dataset}?{urllib.parse.urlencode(params)}")
        with urllib.request.urlopen(
            f"{NYC_OPEN_DATA}/api/views/{dataset}.json", timeout=60
        ) as r:
            meta = json.loads(r.read())
        versions[dataset] = {
            "name": meta.get("name"),
            "rows_updated_at": dt.datetime.fromtimestamp(
                meta["rowsUpdatedAt"], dt.UTC
            ).isoformat(),
        }
    return pd.DataFrame(rows), queries, versions


FOOTPRINTS_ID = "5zhs-2jue"
FOOTPRINT_COLUMNS = ("bin", "base_bbl", "height_roof", "construction_year", "the_geom")


FOOTPRINTS_MARGIN_M = 100.0


def fetch_footprints(registry: pd.DataFrame, batch: int = 100, page: int = 2000):
    bins = registry.bin.dropna().astype(str)
    placeholder = bins.str.fullmatch(r"[1-5]000000")
    rows, queries = [], []
    lat = registry.latitude.dropna()
    dlat = FOOTPRINTS_MARGIN_M / 111_320.0
    dlon = dlat / math.cos(math.radians(lat.mean()))
    n, w = lat.max() + dlat, registry.longitude.min() - dlon
    s, e = lat.min() - dlat, registry.longitude.max() + dlon
    for offset in itertools.count(0, page):
        params = {
            "$select": ", ".join(FOOTPRINT_COLUMNS),
            "$where": f"within_box(the_geom, {n}, {w}, {s}, {e})",
            "$order": "bin",
            "$limit": page,
            "$offset": offset,
        }
        got = _socrata(FOOTPRINTS_ID, params)
        rows += [
            {
                **{k: r.get(k) for k in FOOTPRINT_COLUMNS[:-1]},
                "geometry": json.dumps(r.get("the_geom")),
            }
            for r in got
        ]
        queries.append(f"{FOOTPRINTS_ID}?{urllib.parse.urlencode(params)}")
        if len(got) < page:
            break
    for field, values in (
        ("bin", sorted(set(bins[~placeholder]))),
        (
            "base_bbl",
            sorted(set(registry.bbl[placeholder.to_numpy()].dropna().astype(str))),
        ),
    ):
        for i in range(0, len(values), batch):
            where = f"{field} in ({', '.join(repr(v) for v in values[i : i + batch])})"
            params = {
                "$select": ", ".join(FOOTPRINT_COLUMNS),
                "$where": where,
                "$limit": 5000,
            }
            for r in _socrata(FOOTPRINTS_ID, params):
                rows.append(
                    {
                        **{k: r.get(k) for k in FOOTPRINT_COLUMNS[:-1]},
                        "geometry": json.dumps(r.get("the_geom")),
                    }
                )
            queries.append(f"{FOOTPRINTS_ID}?{urllib.parse.urlencode(params)}")
    table = pd.DataFrame(rows).drop_duplicates(subset=["bin", "base_bbl", "geometry"])
    with urllib.request.urlopen(
        f"{NYC_OPEN_DATA}/api/views/{FOOTPRINTS_ID}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    version = {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }
    return table.reset_index(drop=True), queries, version


HPD_ID = "wvxf-dwi5"
HPD_COLUMNS = (
    "violationid",
    "bin",
    "bbl",
    "class",
    "inspectiondate",
    "novissueddate",
    "currentstatus",
    "currentstatusdate",
    "violationstatus",
    "rentimpairing",
)


def fetch_hpd(registry: pd.DataFrame, batch: int = 100, page: int = 50_000):
    bins = registry.bin.dropna().astype(str)
    placeholder = bins.str.fullmatch(r"[1-5]000000")
    rows, queries = [], []
    for field, values in (
        ("bin", sorted(set(bins[~placeholder]))),
        ("bbl", sorted(set(registry.bbl[placeholder.to_numpy()].dropna().astype(str)))),
    ):
        for i in range(0, len(values), batch):
            where = f"{field} in ({', '.join(repr(v) for v in values[i : i + batch])})"
            for offset in itertools.count(0, page):
                params = {
                    "$select": ", ".join(HPD_COLUMNS),
                    "$where": where,
                    "$order": "violationid",
                    "$limit": page,
                    "$offset": offset,
                }
                got = _socrata(HPD_ID, params)
                rows += [{k: r.get(k) for k in HPD_COLUMNS} for r in got]
                queries.append(f"{HPD_ID}?{urllib.parse.urlencode(params)}")
                if len(got) < page:
                    break
    table = pd.DataFrame(rows, columns=list(HPD_COLUMNS)).drop_duplicates("violationid")
    with urllib.request.urlopen(
        f"{NYC_OPEN_DATA}/api/views/{HPD_ID}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    version = {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }
    return table.reset_index(drop=True), queries, version


LPC_ID = "ncre-qhxs"
LPC_COLUMNS = (
    "bbl",
    "bin_number",
    "lp_number",
    "lm_name",
    "lm_type",
    "hist_distr",
    "status",
    "last_actio",
    "most_curre",
    "desdate",
    "caldate",
)


def _version(dataset: str) -> dict:
    with urllib.request.urlopen(
        f"{NYC_OPEN_DATA}/api/views/{dataset}.json", timeout=60
    ) as r:
        meta = json.loads(r.read())
    return {
        "name": meta.get("name"),
        "rows_updated_at": dt.datetime.fromtimestamp(
            meta["rowsUpdatedAt"], dt.UTC
        ).isoformat(),
    }


def fetch_lpc(registry: pd.DataFrame, batch: int = 100):
    """Every LPC record of the registry's lots (one lot can have several: a
    landmark inside a historic district, or a district and its extension)."""
    rows, queries = [], []
    bbls = sorted(set(registry.bbl.dropna().astype(str)))
    for i in range(0, len(bbls), batch):
        where = f"bbl in ({', '.join(repr(v) for v in bbls[i : i + batch])})"
        params = {"$select": ", ".join(LPC_COLUMNS), "$where": where, "$limit": 50_000}
        rows += [{k: r.get(k) for k in LPC_COLUMNS} for r in _socrata(LPC_ID, params)]
        queries.append(f"{LPC_ID}?{urllib.parse.urlencode(params)}")
    table = pd.DataFrame(rows, columns=list(LPC_COLUMNS)).drop_duplicates()
    return table.reset_index(drop=True), queries, _version(LPC_ID)


# NYC 311 service requests: 2010-2019 and 2020 on are separate datasets.
NOISE_IDS = ("76ig-c548", "erm2-nwe9")
NOISE_COLUMNS = (
    "unique_key",
    "created_date",
    "complaint_type",
    "descriptor",
    "latitude",
    "longitude",
)


def fetch_noise(box, page: int = 50_000):
    """Every 311 noise complaint in the box (north, west, south, east), a
    calendar year per query (each year is well under a page)."""
    north, west, south, east = box
    area = (
        f"latitude between {south} and {north} and longitude between {west} and "
        f"{east} and starts_with(complaint_type, 'Noise')"
    )
    rows, queries, versions = [], [], {}
    for dataset, years in zip(NOISE_IDS, (range(2010, 2020), range(2020, 2031))):
        for year in years:
            params = {
                "$select": ", ".join(NOISE_COLUMNS),
                "$where": f"{area} and created_date >= '{year}-01-01T00:00:00' "
                f"and created_date < '{year + 1}-01-01T00:00:00'",
                "$order": "unique_key",
                "$limit": page,
            }
            url = f"{SOCRATA}/{dataset}.json?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=600) as r:
                got = json.loads(r.read())
            if len(got) >= page:
                raise SystemExit(f"{dataset} {year}: a full page; split the query")
            rows += [{k: r.get(k) for k in NOISE_COLUMNS} for r in got]
            queries.append(f"{dataset}?{urllib.parse.urlencode(params)}")
        with urllib.request.urlopen(
            f"{NYC_OPEN_DATA}/api/views/{dataset}.json", timeout=60
        ) as r:
            meta = json.loads(r.read())
        versions[dataset] = {
            "name": meta.get("name"),
            "rows_updated_at": dt.datetime.fromtimestamp(
                meta["rowsUpdatedAt"], dt.UTC
            ).isoformat(),
        }
    table = pd.DataFrame(rows, columns=list(NOISE_COLUMNS)).drop_duplicates(
        "unique_key"
    )
    table["latitude"] = pd.to_numeric(table.latitude, errors="coerce")
    table["longitude"] = pd.to_numeric(table.longitude, errors="coerce")
    return table.reset_index(drop=True), queries, versions


# Keys that identify one record when snapshots of overlapping areas are merged.
MERGE_KEYS = {"pluto": ["bbl"], "footprints": ["bin"], "basemap": None}


PLACES_MARGIN_M = 2000.0
DOG_RUNS_ID = "hxx3-bwgv"
FACDB_ID = "ji82-xba5"
DROP_IN_ID = "bmxf-3rd4"
FACDB_KINDS = {
    "HOSPITAL": "hospital",
    "ACUTE CARE HOSPITAL": "hospital",
    "AMBULANCE STATION": "ambulance station",
    "EMERGENCY MEDICAL STATION": "ambulance station",
    "EMERGENCY MEDICL STN": "ambulance station",
    "DROP-IN CENTER": "drop-in center",
    "DROP-IN CENTERS": "drop-in center",
}
OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_DOG_PARKS = (
    '[out:json][timeout:60];area["boundary"="administrative"]["name"="Manhattan"]'
    '["admin_level"="7"]->.m;nwr["leisure"="dog_park"](area.m);out center tags;'
)
# Madison Square Garden (opened 1968), 4 Pennsylvania Plaza.
MSG = (40.75051, -73.99341)


def _rows(dataset: str, params: dict) -> tuple[list[dict], str]:
    query = urllib.parse.urlencode({**params, "$limit": 50_000})
    with urllib.request.urlopen(f"{SOCRATA}/{dataset}.json?{query}", timeout=300) as r:
        rows = json.loads(r.read())
    if len(rows) >= 50_000:
        raise SystemExit(f"{dataset}: a full page; split the query")
    return rows, f"{dataset}?{query}"


def fetch_places(box) -> tuple[pd.DataFrame, list[str], dict]:
    """Points of interest in the box (north, west, south, east), widened by
    PLACES_MARGIN_M: kind, name, address, latitude, longitude, dataset."""
    north, west, south, east = box
    dlat = PLACES_MARGIN_M / 111_320.0
    dlon = dlat / math.cos(math.radians((north + south) / 2))
    north, west, south, east = north + dlat, west - dlon, south - dlat, east + dlon
    out, queries = [], []
    runs, q = _rows(DOG_RUNS_ID, {"borough": "M"})
    queries.append(q)
    for r in runs:
        geometry = r["the_geom"]
        polygons = geometry["coordinates"]
        polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
        ring = [p for polygon in polygons for p in polygon[0]]
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        out.append(("dog run", r.get("name"), None, lat, lon, DOG_RUNS_ID))
    request = urllib.request.Request(
        OVERPASS,
        data=urllib.parse.urlencode({"data": OSM_DOG_PARKS}).encode(),
        headers={"User-Agent": "apartments-research/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as r:
        osm = json.loads(r.read())
    queries.append(f"{OVERPASS}?data={OSM_DOG_PARKS}")
    for e in osm["elements"]:
        tags = e.get("tags", {})
        if tags.get("access") in ("private", "customers", "no"):
            continue
        at = e.get("center", e)
        name = tags.get("name")
        out.append(("dog run", name, None, at["lat"], at["lon"], "osm"))
    facilities, q = _rows(
        FACDB_ID,
        {
            "$select": "facname, address, factype, latitude, longitude",
            "$where": "boro = 'MANHATTAN' and factype in ("
            + ", ".join(f"'{k}'" for k in FACDB_KINDS)
            + ")",
        },
    )
    queries.append(q)
    for r in facilities:
        out.append(
            (
                FACDB_KINDS[r["factype"]],
                r.get("facname"),
                r.get("address"),
                r.get("latitude"),
                r.get("longitude"),
                FACDB_ID,
            )
        )
    drop_in, q = _rows(DROP_IN_ID, {"borough": "Manhattan"})
    queries.append(q)
    for r in drop_in:
        out.append(
            (
                "drop-in center",
                r.get("center_name"),
                r.get("address"),
                r.get("latitude"),
                r.get("longitude"),
                DROP_IN_ID,
            )
        )
    nycha, q = _rows(
        PLUTO_ID,
        {
            "$select": "bbl, address, latitude, longitude",
            "$where": "borough = 'MN' and ownername like 'NYC HOUSING AUTH%'",
        },
    )
    queries.append(q)
    for r in nycha:
        out.append(
            (
                "nycha",
                r.get("bbl"),
                r.get("address"),
                r.get("latitude"),
                r.get("longitude"),
                PLUTO_ID,
            )
        )
    out.append(("arena", "Madison Square Garden", "4 Pennsylvania Plaza", *MSG, None))
    table = pd.DataFrame(
        out, columns=["kind", "name", "address", "latitude", "longitude", "dataset"]
    )
    for c in ("latitude", "longitude"):
        table[c] = pd.to_numeric(table[c], errors="coerce")
    inside = table.latitude.between(south, north) & table.longitude.between(west, east)
    versions = {d: _version(d) for d in (DOG_RUNS_ID, FACDB_ID, DROP_IN_ID, PLUTO_ID)}
    versions["osm"] = osm["osm3s"]["timestamp_osm_base"]
    return table[inside].reset_index(drop=True), queries, versions


STOREFRONTS_ID = "92iy-9c3n"
STOREFRONT_COLUMNS = (
    "reporting_year",
    "borough_block_lot",
    "property_street_address_or",
    "unit",
    "primary_business_activity",
    "vacant_on_12_31",
    "latitude",
    "longitude",
)


def fetch_storefronts(box) -> tuple[pd.DataFrame, list[str], dict]:
    """Every Storefront Registry filing in the box (north, west, south, east)."""
    north, west, south, east = box
    rows, q = _rows(
        STOREFRONTS_ID,
        {
            "$select": ", ".join(STOREFRONT_COLUMNS),
            "$where": f"borough = 'MANHATTAN' and within_box(lat_long, {north}, "
            f"{west}, {south}, {east})",
            "$order": "reporting_year, borough_block_lot",
        },
    )
    table = pd.DataFrame(rows, columns=list(STOREFRONT_COLUMNS))
    for c in ("latitude", "longitude"):
        table[c] = pd.to_numeric(table[c], errors="coerce")
    return table, [q], _version(STOREFRONTS_ID)


GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"


def fetch_gtfs(path: Path) -> dict:
    """Download the subway GTFS zip to path; its feed_info as the version."""
    import io
    import zipfile

    with urllib.request.urlopen(GTFS_URL, timeout=120) as r:
        body = r.read()
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        info = pd.read_csv(z.open("feed_info.txt"), dtype=str).iloc[0].to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {
        "source": GTFS_URL,
        "dataset": "MTA New York City Transit static subway GTFS",
        "version": info,
    }


LODES_ROOT = "https://lehd.ces.census.gov/data/lodes/LODES8/ny"
LODES_WAC = LODES_ROOT + "/wac/ny_wac_S000_JT00_{year}.csv.gz"
LODES_XWALK = LODES_ROOT + "/ny_xwalk.csv.gz"
LODES_YEARS = range(2002, 2024)
NYC_COUNTIES = ("36005", "36047", "36061", "36081", "36085")


def fetch_lodes() -> tuple[pd.DataFrame, dict]:
    """Jobs (C000) per New York City census block and year, with the block's
    internal point."""
    blocks = pd.read_csv(
        LODES_XWALK,
        dtype={"tabblk2020": str, "cty": str},
        usecols=["tabblk2020", "cty", "blklatdd", "blklondd"],
    )
    blocks = blocks[blocks.cty.isin(NYC_COUNTIES)].rename(
        columns={"tabblk2020": "block", "blklatdd": "latitude", "blklondd": "longitude"}
    )
    table = blocks.set_index("block")[["latitude", "longitude"]]
    for year in LODES_YEARS:
        wac = pd.read_csv(
            LODES_WAC.format(year=year),
            dtype={"w_geocode": str},
            usecols=["w_geocode", "C000"],
        ).set_index("w_geocode")
        table[f"jobs_{year}"] = wac.C000.reindex(table.index).fillna(0).astype(int)
    jobs = table.filter(like="jobs_")
    table = table[jobs.sum(axis=1) > 0].reset_index()
    details = {
        "source": LODES_ROOT,
        "dataset": "LEHD LODES8 workplace area characteristics, all jobs (S000, JT00)",
        "years": [LODES_YEARS.start, LODES_YEARS.stop - 1],
        "blocks": len(table),
    }
    return table, details


def merge(source: str, snapshots: list) -> tuple[pd.DataFrame, dict]:
    """One snapshot from several of the same source (neighbourhoods' boxes):
    concatenated, a record kept once (MERGE_KEYS; whole rows for the basemap).
    MapPLUTO snapshots must share a version."""
    parts = [pd.read_parquet(Path(d) / f"{source}.parquet") for d in snapshots]
    if source == "pluto":
        versions = {v for p in parts for v in p.version.dropna().unique()}
        if len(versions) > 1:
            raise SystemExit(f"MapPLUTO versions differ: {sorted(versions)}")
    table = pd.concat(parts, ignore_index=True)
    before = len(table)
    table = table.drop_duplicates(MERGE_KEYS[source]).reset_index(drop=True)
    details = {
        "merged": [str(d) for d in snapshots],
        "rows_in": [len(p) for p in parts],
        "duplicates_dropped": before - len(table),
    }
    return table, details


def main(argv=None):
    import sys

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "merge":
        # python -m rentfrontier.external merge <source> <snapshot dir> <snapshot dir> ...
        source, snapshots = argv[1], argv[2:]
        if git("status", "--porcelain"):
            raise SystemExit("Refusing to run on a dirty working tree")
        commit = git("rev-parse", "HEAD")
        started = dt.datetime.now(dt.UTC)
        table, details = merge(source, snapshots)
        out_dir = EXTERNAL_ROOT / source / f"{started:%Y%m%d}-{commit[:7]}"
        out_dir.mkdir(parents=True, exist_ok=False)
        path = out_dir / f"{source}.parquet"
        table.to_parquet(path)
        provenance = {
            **details,
            "retrieved_at": started.isoformat(),
            "commit": commit,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
        print(
            f"wrote {path}: {len(table)} rows, {details['duplicates_dropped']} duplicates dropped"
        )
        return
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "source",
        choices=(
            "pluto",
            "subway",
            "basemap",
            "hpd",
            "footprints",
            "noise311",
            "lpc",
            "gtfs",
            "places",
            "storefronts",
            "lodes",
        ),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY,
        help="registry buildings.parquet to join through (default: the first snapshot)",
    )
    args = parser.parse_args(argv)
    registry_path = args.registry
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    out_dir = EXTERNAL_ROOT / args.source / f"{started:%Y%m%d}-{commit[:7]}"
    path = out_dir / f"{args.source}.parquet"
    if args.source == "gtfs":
        path = out_dir / "gtfs_subway.zip"
        details = fetch_gtfs(path)
        provenance = {
            **details,
            "retrieved_at": started.isoformat(),
            "commit": commit,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
        print(f"wrote {path}: feed {details['version'].get('feed_version')}")
        return
    if args.source == "lodes":
        table, details = fetch_lodes()
        out_dir.mkdir(parents=True, exist_ok=False)
        table.to_parquet(path)
        provenance = {
            **details,
            "retrieved_at": started.isoformat(),
            "commit": commit,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
        print(f"wrote {path}: {len(table)} blocks")
        return
    if args.source == "pluto":
        registry = pd.read_parquet(registry_path)
        table, queries = fetch_pluto(registry.bbl.dropna())
        missing = sorted(set(registry.bbl.dropna()) - set(table.bbl))
        details = {
            "source": f"{SOCRATA}/{PLUTO_ID}",
            "dataset": "MapPLUTO (NYC DCP) via NYC Open Data",
            "versions": sorted(table.version.dropna().unique().tolist()),
            "registry": str(registry_path),
            "lots": len(table),
            "registry_lots_missing": missing,
        }
        summary = f"{len(table)} lots, {len(missing)} registry lots missing"
    elif args.source == "hpd":
        registry = pd.read_parquet(registry_path)
        table, queries, version = fetch_hpd(registry)
        details = {
            "source": f"{SOCRATA}/{HPD_ID}",
            "dataset": "HPD Housing Maintenance Code Violations via NYC Open Data",
            "version": version,
            "registry": str(registry_path),
            "violations": len(table),
            "buildings": int(table.bin.nunique()),
        }
        summary = f"{len(table)} violations in {table.bin.nunique()} buildings"
    elif args.source == "lpc":
        registry = pd.read_parquet(registry_path)
        table, queries, version = fetch_lpc(registry)
        details = {
            "source": f"{SOCRATA}/{LPC_ID}",
            "dataset": "LPC Designated and Calendared Buildings and Sites via NYC Open Data",
            "version": version,
            "registry": str(registry_path),
            "records": len(table),
            "lots": int(table.bbl.nunique()),
        }
        summary = f"{len(table)} LPC records on {table.bbl.nunique()} lots"
    elif args.source == "footprints":
        registry = pd.read_parquet(registry_path)
        table, queries, version = fetch_footprints(registry)
        found = set(table.bin.astype(str))
        missing = sorted(set(registry.bin.astype(str)) - found)
        details = {
            "source": f"{SOCRATA}/{FOOTPRINTS_ID}",
            "dataset": "NYC Building Footprints via NYC Open Data",
            "version": version,
            "registry": str(registry_path),
            "footprints": len(table),
            "registry_bins_missing": missing,
        }
        summary = f"{len(table)} footprints, {len(missing)} registry BINs without one"
    elif args.source == "places":
        box = basemap_box(pd.read_parquet(registry_path))
        table, queries, versions = fetch_places(box)
        counts = table.kind.value_counts().to_dict()
        details = {
            "source": [f"{SOCRATA}/{d}" for d in versions if d != "osm"] + [OVERPASS],
            "dataset": "NYC Open Data: dog runs, facilities, drop-in centers, NYCHA "
            "lots; OpenStreetMap dog parks (ODbL)",
            "versions": versions,
            "registry": str(registry_path),
            "box_north_west_south_east": box,
            "margin_m": PLACES_MARGIN_M,
            "places": counts,
        }
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    elif args.source == "storefronts":
        box = basemap_box(pd.read_parquet(registry_path))
        table, queries, version = fetch_storefronts(box)
        counts = table.reporting_year.value_counts().sort_index().to_dict()
        details = {
            "source": f"{SOCRATA}/{STOREFRONTS_ID}",
            "dataset": "Storefronts Reported Vacant or Not via NYC Open Data",
            "version": version,
            "registry": str(registry_path),
            "box_north_west_south_east": box,
            "filings_by_year": counts,
        }
        summary = f"{len(table)} filings"
    elif args.source == "noise311":
        box = basemap_box(pd.read_parquet(registry_path))
        table, queries, versions = fetch_noise(box)
        counts = table.complaint_type.value_counts().to_dict()
        details = {
            "source": [f"{SOCRATA}/{d}" for d in NOISE_IDS],
            "dataset": "NYC 311 Service Requests (2010-2019 and 2020 on), noise complaints",
            "versions": versions,
            "registry": str(registry_path),
            "box_north_west_south_east": box,
            "complaints": counts,
        }
        summary = f"{len(table)} noise complaints"
    elif args.source == "basemap":
        box = basemap_box(pd.read_parquet(registry_path))
        table, queries, versions = fetch_basemap(box)
        counts = table.layer.value_counts().to_dict()
        details = {
            "source": SOCRATA,
            "dataset": "NYC Open Data: street centerlines, parks, borough boundary",
            "versions": versions,
            "registry": str(registry_path),
            "box_north_west_south_east": box,
            "features": counts,
        }
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    else:
        table, queries, version = fetch_subway()
        details = {
            "source": f"{NY_SOCRATA}/resource/{SUBWAY_ID}",
            "dataset": "MTA Subway Stations via data.ny.gov",
            "version": version,
            "stops": len(table),
        }
        summary = f"{len(table)} station stops"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)
    provenance = {
        **details,
        "queries": queries,
        "retrieved_at": started.isoformat(),
        "commit": commit,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(f"wrote {path}: {summary}")


if __name__ == "__main__":
    main()
