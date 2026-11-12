"""Shared helpers for the review queues: where the data is, how to read it, and how to write a
queue.

Each producer reads the newest clean pipeline build (the records, ads and rows files its catalog
line lists), the site's diagnostics, and the ledger in this checkout. It turns them into cards
in the format of `docs/review-app.md` and writes `<out>/<queue>/cards.jsonl` and `meta.json`,
each under a temporary name first and then renamed, so the site never reads half a file.

Everything here reads with DuckDB under a memory cap, since the records file runs to a few
gigabytes and thelio runs fits beside these jobs.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[3]
DATASETS = Path(
    os.environ.get("PIPELINE_DATASETS", "/data1/apartments/pipeline/datasets")
)
SITE = Path("/data1/apartments/site")
STATE = Path("/data1/apartments/pipeline/state/pipeline.duckdb")
SPRINT = Path("/data1/apartments/tmp/outlier-sprint/s2")

# StreetEasy's photo host serves each key at these sizes (checked with curl on 2026-11-12;
# se_small_200_100 gives 404). Cards show photos at the large size and floor plans at the
# extra large one, where room labels stay legible on a phone.
PHOTO_SIZE = "se_large_800_400"
PLAN_SIZE = "se_extra_large_1500_800"
TEXT_CHARS = 1200


@dataclass
class Sources:
    """Paths a producer reads. The defaults are thelio's; tests point them at fixtures."""

    datasets: Path = DATASETS
    diagnostics: Path = SITE / "diagnostics"
    ledger: Path = REPO / "pipeline" / "ledger"
    reviews: Path = REPO / "config" / "reviews"
    state: Path = STATE
    sprint: Path = SPRINT
    memory: str = "2GB"
    files: dict = field(default_factory=dict)

    def pipeline(self) -> dict:
        """The records, ads and rows files of the newest clean build in the catalog."""
        if not self.files:
            self.files = pipeline_files(self.datasets)
        return self.files


def pipeline_files(datasets: Path) -> dict:
    """The files of the newest catalog line from a clean checkout, as paths, with the build's
    time. A last line without its line break is still being written, so it is left out."""
    lines = (datasets / "catalog.ndjson").read_text().split("\n")[:-1]
    clean = [
        entry
        for entry in map(json.loads, filter(str.strip, lines))
        if entry.get("code", {}).get("clean") is True
    ]
    if not clean:
        raise ValueError(f"{datasets / 'catalog.ndjson'} lists no clean build")
    entry = clean[-1]
    out = {"built": entry.get("built"), "commit": entry["code"].get("commit")}
    for key, name in (("records", "records"), ("ads_file", "ads"), ("rows", "rows")):
        out[name] = str(datasets / entry[key]["path"])
    return out


def connect(sources: Sources) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with views `ads`, `rows` and `records` on the build's files."""
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{sources.memory}'; SET threads=2")
    files = sources.pipeline()
    for view in ("ads", "rows", "records"):
        con.execute(
            f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{files[view]}')"
        )
    return con


def head_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# The ledger


def entry_id(line: str) -> str:
    """The ledger's ID of a line: the first 16 hex digits of its SHA-256."""
    return hashlib.sha256(line.encode()).hexdigest()[:16]


def ledger_lines(folder: Path) -> list[dict]:
    """Every line of the NDJSON files directly in `folder`, parsed, with its `_id`."""
    out = []
    for path in sorted(folder.glob("*.ndjson")):
        for text in path.read_text().splitlines():
            if text.strip():
                line = json.loads(text)
                line["_id"] = entry_id(text)
                out.append(line)
    return out


def live_entries(folder: Path) -> dict[str, list[dict]]:
    """The corrections ledger's entries in force, by listing ID: each exclude, set or drop_lot
    no retract undoes."""
    lines = ledger_lines(folder)
    retracted = {x["entry"] for x in lines if x.get("change") == "retract"}
    out: dict[str, list[dict]] = {}
    for line in lines:
        if line.get("change") != "retract" and line["_id"] not in retracted:
            out.setdefault(str(line["listing_id"]), []).append(line)
    return out


def live_unit_pages(folder: Path) -> set[str]:
    """The unit pages of joins in force in the unit ledger, as `building/unit` slugs."""
    if not folder.is_dir():
        return set()
    lines = ledger_lines(folder)
    retracted = {x["entry"] for x in lines if x.get("change") == "retract"}
    return {
        f"{line['building']}/{unit}"
        for line in lines
        if line.get("change") == "join_units" and line["_id"] not in retracted
        for unit in line["units"]
    }


# Reading ads


def label(page: str | None) -> str | None:
    """The unit label at the end of a unit page, in upper case."""
    if not page or "/" not in page:
        return None
    return page.rstrip("/").rsplit("/", 1)[-1].upper()


def whole(value):
    """A number as an int when it is whole, so cards say 2 rather than 2.0."""
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:
            return None
        if value.is_integer():
            return int(value)
    return value


def day(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()[:10]
    return str(value)[:10]


def wanted_table(con: duckdb.DuckDBPyConnection, name: str, ids: Iterable) -> None:
    ids = sorted({str(i) for i in ids})
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} (listing_id VARCHAR)")
    if ids:
        con.executemany(f"INSERT INTO {name} VALUES (?)", [[i] for i in ids])


AD_COLUMNS = (
    "listing_id, unit_id, building, page, neighbourhood, status, on_day, off_day, first_ask, "
    "latest_ask, bedrooms, full_baths, half_baths, square_feet, advertised_floor, label_floor, "
    "floor_plans, exclusion_reasons, ledger_entries, fate, in_rows"
)


def ads_where(con: duckdb.DuckDBPyConnection, where: str, params=()) -> list[dict]:
    """Rows of the ads file matching `where`, as dicts, with the row's `record` (from the rows
    file) under `row`."""
    sql = f"""
        SELECT {", ".join("a." + c.strip() for c in AD_COLUMNS.split(","))},
               r.period AS row_period, r.bedrooms AS row_bedrooms,
               r.full_baths AS row_full_baths, r.half_baths AS row_half_baths,
               r.square_feet AS row_square_feet, r.latest_ask AS row_latest_ask
        FROM ads a LEFT JOIN rows r USING (listing_id)
        WHERE {where}
    """
    cur = con.execute(sql, list(params))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def ads_by_ids(con: duckdb.DuckDBPyConnection, ids: Iterable) -> dict[str, dict]:
    wanted_table(con, "wanted_ads", ids)
    rows = ads_where(con, "a.listing_id IN (SELECT listing_id FROM wanted_ads)")
    return {r["listing_id"]: r for r in rows}


def ads_in_buildings(con: duckdb.DuckDBPyConnection, buildings: Iterable) -> list[dict]:
    """Every ad of the buildings with these slugs, ordered by building and first day."""
    con.execute("CREATE OR REPLACE TEMP TABLE wanted_buildings (building VARCHAR)")
    con.executemany(
        "INSERT INTO wanted_buildings VALUES (?)", [[b] for b in sorted(set(buildings))]
    )
    return ads_where(
        con,
        "a.building IN (SELECT building FROM wanted_buildings) "
        "ORDER BY a.building, a.on_day, a.listing_id",
    )


def raw_records(con: duckdb.DuckDBPyConnection, ids: Iterable) -> dict[str, dict]:
    """The latest captured record of each listing in `ids`, parsed."""
    ids = sorted({int(i) for i in ids})
    con.execute("CREATE OR REPLACE TEMP TABLE wanted_raw (listing_id BIGINT)")
    con.executemany("INSERT INTO wanted_raw VALUES (?)", [[i] for i in ids])
    rows = con.execute(
        """
        SELECT r.listing_id::VARCHAR, arg_max(r.raw_listing_json, r.last_collected_at)
        FROM records r SEMI JOIN wanted_raw w ON r.listing_id = w.listing_id
        GROUP BY 1
        """
    ).fetchall()
    out = {}
    for lid, text in rows:
        try:
            out[lid] = json.loads(text) if text else {}
        except json.JSONDecodeError:
            out[lid] = {}
    return out


def media_url(key: str, size: str) -> str:
    return f"https://photos.zillowstatic.com/fp/{key}-{size}.webp"


def record_of(ad: dict) -> dict | None:
    """The row's recorded values as the corrections ledger's `when` gives them, or None for an
    ad the rows file lacks."""
    if ad.get("row_period") is None:
        return None
    return {
        "period": day(ad["row_period"])[:7],
        "bedrooms": whole(ad["row_bedrooms"]),
        "full_baths": whole(ad["row_full_baths"]),
        "half_baths": whole(ad["row_half_baths"]),
        "square_feet": whole(ad["row_square_feet"]),
        "latest_ask": whole(ad["row_latest_ask"]),
    }


def card_ad(
    ad: dict,
    raw: dict | None,
    photos: int = 8,
    plans: int = 4,
    text: bool = True,
    mark: str | None = None,
) -> dict:
    """An ad of a card's `ads` block: the ad's coded facts, its lister, photos, floor plans and
    text from its latest record, and its `record` when the rows file holds it."""
    raw = raw or {}
    media = raw.get("media") or {}
    photo_keys = [p["key"] for p in media.get("photos") or [] if p.get("key")]
    plan_keys = [p["key"] for p in media.get("floorPlans") or [] if p.get("key")]
    plan_keys = plan_keys or list(ad.get("floor_plans") or [])
    floor = ad.get("label_floor")
    if floor is None:
        floor = ad.get("advertised_floor")
    out = {
        "listing_id": str(ad["listing_id"]),
        "unit": label(ad.get("page")),
        "opened": day(ad.get("on_day")),
        "closed": day(ad.get("off_day")),
        "status": (ad.get("status") or "").lower() or None,
        "first_ask": whole(ad.get("first_ask")),
        "last_ask": whole(ad.get("latest_ask")),
        "bedrooms": whole(ad.get("bedrooms")),
        "full_baths": whole(ad.get("full_baths")),
        "half_baths": whole(ad.get("half_baths")),
        "square_feet": whole(ad.get("square_feet")),
        "floor": whole(floor),
        "lister": (raw.get("legacy") or {}).get("sourceGroupLabel"),
        "photos": [media_url(k, PHOTO_SIZE) for k in photo_keys[:photos]],
        "floor_plans": [media_url(k, PLAN_SIZE) for k in plan_keys[:plans]],
        "url": f"https://streeteasy.com/rental/{ad['listing_id']}",
    }
    if text:
        out["text"] = cut(raw.get("description") or "")
    if mark:
        out["mark"] = mark
    record = record_of(ad)
    if record:
        out["record"] = record
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def plain(text: str) -> str:
    """An ad's description without its HTML tags and entities, in one paragraph."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def cut(text: str, limit: int = TEXT_CHARS) -> str:
    text = plain(text)
    if len(text) <= limit:
        return text
    return text[: text.rfind(" ", 0, limit)].rstrip(",;:") + " …"


def money(value) -> str:
    return "" if value is None else f"${value:,.0f}"


def beds_text(value) -> str:
    value = whole(value)
    if value is None:
        return "beds unknown"
    if value == 0:
        return "studio"
    return f"{value} bed"


def address(slug: str | None) -> str:
    """A readable address from a building slug, as `16 Monitor Street, Brooklyn`."""
    if not slug:
        return ""
    words = slug.replace("_", " ").split("-")
    borough = {
        "new york": "Manhattan",
        "brooklyn": "Brooklyn",
        "queens": "Queens",
        "bronx": "Bronx",
        "staten island": "Staten Island",
    }
    tail = words[-1] if words else ""
    if tail in borough:
        return f"{' '.join(words[:-1]).title()}, {borough[tail]}"
    return " ".join(words).title()


# Writing a queue


def write_queue(out: Path, meta: dict, cards: list[dict]) -> Path:
    """Write `<out>/<queue>/cards.jsonl` then `meta.json`, each under a temporary name and then
    renamed into place."""
    folder = out / meta["queue"]
    folder.mkdir(parents=True, exist_ok=True)
    ids = [c["id"] for c in cards]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{meta['queue']}: card ids repeat")
    meta = {**meta, "count": len(cards)}
    tmp = folder / f".cards.jsonl.{os.getpid()}"
    with tmp.open("w") as fh:
        for card in cards:
            fh.write(json.dumps(card, ensure_ascii=False, sort_keys=False) + "\n")
    tmp.replace(folder / "cards.jsonl")
    tmp = folder / f".meta.json.{os.getpid()}"
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(folder / "meta.json")
    return folder


def meta(queue: str, module: str, **fields) -> dict:
    return {
        "queue": queue,
        **fields,
        "built": now(),
        "source": f"src/apartments/review_cards/{module}.py on {head_commit()}",
    }
