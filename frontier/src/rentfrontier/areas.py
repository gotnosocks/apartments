"""The StreetEasy area of each building in the Flatiron + Gramercy Park crawl,
read from the building page's title ("... at 7 East 14th Street in Flatiron :
Sales, Rentals, ..."). The crawl covers both areas under one name; this splits
them. A building titled with an area outside the two (one Park Slope building
the search returned) is left out, as are buildings with no title:

    python -m rentfrontier.areas

writes EXTERNAL_ROOT/areas/<date>-<commit>/areas.parquet (building, area,
latitude, longitude) and provenance.json. Refuses a dirty tree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from rentfrontier.listing_extras import CRAWLS, EXTERNAL_ROOT, _git

CRAWL = CRAWLS["Flatiron + Gramercy Park"]
AREAS = ("Flatiron", "Gramercy Park")
TITLE = re.compile(r'"pageTitle":"[^"]* in ([^:"]+?) : ')


def page_area(raw) -> str | None:
    """The area a building page's title names, if any (`raw` may be missing)."""
    m = TITLE.search(raw if isinstance(raw, str) else "")
    return m.group(1) if m else None


def build(crawl: str = CRAWL) -> tuple[pd.DataFrame, dict]:
    """One row per building in `AREAS` (its last snapshot), and the count of
    buildings left out by the area their title names."""
    frame = (
        ds.dataset(Path(crawl) / "building_observations")
        .to_table(
            columns=[
                "snapshot_id",
                "building_slug",
                "latitude",
                "longitude",
                "raw_building_json",
            ]
        )
        .to_pandas()
        .sort_values("snapshot_id")
        .drop_duplicates("building_slug", keep="last")
    )
    frame["area"] = frame.raw_building_json.map(page_area)
    left_out = frame[~frame.area.isin(AREAS)].area.fillna("(no title)")
    table = (
        frame[frame.area.isin(AREAS)]
        .rename(columns={"building_slug": "building"})[
            ["building", "area", "latitude", "longitude"]
        ]
        .sort_values("building")
        .reset_index(drop=True)
    )
    return table, left_out.value_counts().to_dict()


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table, left_out = build()
    out_dir = EXTERNAL_ROOT / "areas" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "areas.parquet"
    table.to_parquet(path, index=False)
    complete = Path(CRAWL) / "complete.json"
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source": {
                    "path": CRAWL,
                    "complete_sha256": hashlib.sha256(
                        complete.read_bytes()
                    ).hexdigest(),
                },
                "built_at": started.isoformat(),
                "commit": commit,
                "buildings": table.area.value_counts().to_dict(),
                "left_out": left_out,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    print(f"wrote {path}: {table.area.value_counts().to_dict()}, left out {left_out}")


if __name__ == "__main__":
    main()
