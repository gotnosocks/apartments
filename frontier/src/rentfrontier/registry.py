"""Building registry: every building in the dataset -> BBL (tax lot) and BIN.

    python -m rentfrontier.registry

The join key for external sources (MapPLUTO, HPD, DOB, 311, ...). Each
building's address comes from its slug when the slug is an address
("136-west-17-street-new_york" -> "136 West 17 Street, Manhattan") and is
geocoded with NYC Planning's GeoSearch (the city's PAD address database).
Named buildings ("ava-high-line") and addresses that do not match within
MAX_DISTANCE_M of the building's archived coordinates are looked up by
reverse geocoding those coordinates instead. Every row records the method,
the matched label and the distance to the archived point.

Writes /data1/apartments/external/registry/<date>-<commit>/buildings.parquet
and provenance.json (URL, PAD version, retrieval time, sha256). Refuses a
dirty tree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from . import data
from .run import git

EXTERNAL_ROOT = Path(
    os.environ.get("FRONTIER_EXTERNAL_ROOT", "/data1/apartments/external")
)
COVARIATES = Path(
    os.environ.get(
        "FRONTIER_BUILDING_COVARIATES",
        "/home/ben/code/apartments/data/model/building-covariates-20260923/buildings.csv",
    )
)
GEOSEARCH = "https://geosearch.planninglabs.nyc/v2"
MAX_DISTANCE_M = 150.0
STREET_WORDS = (
    r"street|st|avenue|ave|place|road|square|plaza|boulevard|lane|terrace|court|way"
)


def slug_address(slug: str) -> str | None:
    """The street address in a building slug, or None for a named building.

    Takes the first "<number> ... <street word>" run, so an address embedded
    after a name ("beatrice-105-west-29th-street-new_york") is found too.
    """
    words = slug.removesuffix("-new_york").split("-")

    def fmt(parts):
        return " ".join(p if p[0].isdigit() else p.capitalize() for p in parts)

    for i, w in enumerate(words):
        if not re.fullmatch(r"\d+[a-z]?", w):
            continue
        if i + 1 < len(words) and words[i + 1] == "broadway":
            return f"{w} Broadway"
        for j in range(i + 1, min(i + 6, len(words))):
            if re.fullmatch(STREET_WORDS, words[j]):
                return fmt(
                    words[i:j]
                    + [{"st": "street", "ave": "avenue"}.get(words[j], words[j])]
                )
        # "505-west-19th", "515-west-29": a crosstown street without the word.
        if (
            i + 2 < len(words)
            and words[i + 1] in ("west", "east")
            and re.fullmatch(r"\d+(st|nd|rd|th)?", words[i + 2])
        ):
            return fmt(words[i : i + 3] + ["street"])
    return None


def distance_m(lat1, lon1, lat2, lon2) -> float:
    k = math.pi / 180
    x = (lon2 - lon1) * k * math.cos((lat1 + lat2) / 2 * k)
    y = (lat2 - lat1) * k
    return 6_371_000.0 * math.hypot(x, y)


def _get(path: str, params: dict) -> dict:
    url = f"{GEOSEARCH}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def _best(features, lat, lon):
    """The feature with a BBL closest to the archived point."""
    best = None
    for f in features:
        pad = (f["properties"].get("addendum") or {}).get("pad") or {}
        if not pad.get("bbl"):
            continue
        glon, glat = f["geometry"]["coordinates"]
        d = distance_m(lat, lon, glat, glon)
        if best is None or d < best[0]:
            best = (d, f, pad, glat, glon)
    return best


def locate(slug: str, lat: float, lon: float) -> dict:
    address = slug_address(slug)
    rows = []
    if address:
        hit = _best(
            _get("search", {"text": f"{address}, Manhattan", "size": 5})["features"],
            lat,
            lon,
        )
        if hit and hit[0] <= MAX_DISTANCE_M:
            rows.append(("address", address, hit))
    if not rows:
        hit = _best(
            _get("reverse", {"point.lat": lat, "point.lon": lon, "size": 5})[
                "features"
            ],
            lat,
            lon,
        )
        if hit:
            rows.append(("reverse", address, hit))
    if not rows:
        return {"building": slug, "method": "none", "query": address}
    method, query, (d, f, pad, glat, glon) = rows[0]
    return {
        "building": slug,
        "method": method,
        "query": query,
        "label": f["properties"].get("label"),
        "bbl": str(pad["bbl"]),
        "bin": str(pad.get("bin") or ""),
        "pad_version": pad.get("version"),
        "latitude": glat,
        "longitude": glon,
        "distance_m": d,
    }


def build(pause: float = 0.1) -> pd.DataFrame:
    frame = data.load()
    covariates = pd.read_csv(COVARIATES).set_index("building")
    out = []
    for slug in sorted(frame.building.unique()):
        c = covariates.loc[slug]
        out.append(locate(slug, float(c.latitude), float(c.longitude)))
        time.sleep(pause)
    return pd.DataFrame(out)


def main(argv=None):
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table = build()
    out_dir = EXTERNAL_ROOT / "registry" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "buildings.parquet"
    table.to_parquet(path)
    counts = table.method.value_counts().to_dict()
    provenance = {
        "source": GEOSEARCH,
        "pad_versions": sorted(table.pad_version.dropna().unique().tolist()),
        "retrieved_at": started.isoformat(),
        "commit": commit,
        "buildings": len(table),
        "methods": counts,
        "max_distance_m": MAX_DISTANCE_M,
        "median_distance_m": float(table.distance_m.median()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(
        f"wrote {path}: {counts}, median distance {provenance['median_distance_m']:.0f} m"
    )


if __name__ == "__main__":
    main()
