"""Quality diagnostics for the granular Modal parquet export.

The audit deliberately reports capture evidence and does not turn listing
observations into a historical lease or physical-unit table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


_TABLES = (
    "listing_observations",
    "listing_exclusions",
    "media_gallery_observations",
    "event_mentions",
    "snapshots",
    "fetch_observations",
    "building_observations",
    "inventory_rows",
    "inventory_observations",
    "source_changes",
    "frontier",
    "url_aliases",
    "inventory_row_links",
    "rental_units",
    "rental_unit_memberships",
    "rental_unit_observations",
)
_NUMERIC = {
    "listing_observations": (
        "bedrooms",
        "bathrooms",
        "square_feet",
        "room_count",
        "collected_at",
        "parsed_at",
    ),
    "event_mentions": ("price", "percent_change"),
    "snapshots": ("observed_at",),
    "fetch_observations": ("fetched_at", "status"),
    "building_observations": ("residential_units", "latitude", "longitude"),
}


def _files(root: Path, table: str) -> list[Path]:
    directory = root / table
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*.parquet") if p.is_file())


def _relation(db: duckdb.DuckDBPyConnection, files: list[Path], name: str) -> bool:
    if not files:
        return False
    # DDL cannot use prepared parameters for read_parquet paths. Quote each
    # filesystem path explicitly after escaping SQL string delimiters.
    paths = ", ".join("'" + str(p).replace("'", "''") + "'" for p in files)
    db.execute(
        f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet([{paths}])"
    )
    return True


def _fetchone(
    db: duckdb.DuckDBPyConnection, sql: str, args: list[Any] | None = None
) -> Any:
    return db.execute(sql, args or []).fetchone()[0]


def _columns(db: duckdb.DuckDBPyConnection, relation: str) -> set[str]:
    return {row[0] for row in db.execute(f"DESCRIBE {relation}").fetchall()}


def _json_state(field: str) -> str:
    return (
        f"CASE WHEN {field} IS NULL OR lower(trim(cast({field} AS VARCHAR))) IN ('', 'null') THEN 'missing' "
        f"WHEN trim(cast({field} AS VARCHAR)) IN ('{{}}', '[]') THEN 'empty' ELSE 'nonempty' END"
    )


def _numeric_stats(
    db: duckdb.DuckDBPyConnection, relation: str, field: str, invalid: str
) -> dict[str, Any]:
    row = db.execute(
        f"""SELECT count(*) AS total, count({field}) AS non_null,
                   count(*) FILTER (WHERE {field} IS NOT NULL AND ({invalid})) AS invalid
            FROM {relation}"""
    ).fetchone()
    return {"total": int(row[0]), "non_null": int(row[1]), "invalid": int(row[2])}


def audit_dataset(root: Path) -> dict[str, Any]:
    """Return a memory-bounded quality report for a granular parquet root.

    ``root`` contains one directory per output table, optionally with hive-style
    subdirectories. Only aggregate queries and bounded samples are materialized.
    """
    root = Path(root)
    db = duckdb.connect(config={"memory_limit": "1GB", "threads": "2"})
    relations: dict[str, bool] = {}
    try:
        for table in _TABLES:
            relations[table] = _relation(db, _files(root, table), table)

        counts = {
            table: int(_fetchone(db, f"SELECT count(*) FROM {table}")) if present else 0
            for table, present in relations.items()
            if table
            not in {
                "listing_exclusions",
                "media_gallery_observations",
                "inventory_observations",
                "source_changes",
                "frontier",
                "url_aliases",
                "inventory_row_links",
                "rental_units",
                "rental_unit_memberships",
                "rental_unit_observations",
            }
            or present
        }
        result: dict[str, Any] = {
            "root": str(root),
            "tables": {
                "counts": counts,
                "present": [t for t, ok in relations.items() if ok],
            },
            "numeric": {},
            "listing_observations": {},
            "event_mentions": {},
            "parse_failures": {},
            "suspicious_samples": {},
            "limitations": [
                "This audits capture observations and source event mentions; it is not a lease table.",
                "Attributes are capture-time observations and are not automatically historical.",
                "Canonical URL associations are source-declared unit identities, not independently verified physical homes.",
                "Duplicate event rows are retained as evidence; event_key is used for distinct semantics only.",
            ],
        }

        for table, fields in _NUMERIC.items():
            if not relations[table]:
                continue
            result["numeric"][table] = {}
            for field in fields:
                invalid = "NOT isfinite({0})".format(field)
                if field == "bedrooms":
                    invalid = f"NOT isfinite({field}) OR {field} < 0 OR {field} > 20"
                elif field in {"bathrooms", "room_count"}:
                    invalid = f"NOT isfinite({field}) OR {field} <= 0 OR {field} > 20"
                elif field == "square_feet":
                    invalid = (
                        f"NOT isfinite({field}) OR {field} <= 0 OR {field} > 50000"
                    )
                elif field == "price":
                    invalid = f"NOT isfinite({field}) OR {field} <= 0"
                if field in {"collected_at", "parsed_at", "observed_at", "fetched_at"}:
                    invalid = f"NOT isfinite({field}) OR {field} <= 0"
                result["numeric"][table][field] = _numeric_stats(
                    db, table, field, invalid
                )

        if relations["listing_observations"]:
            listing = result["listing_observations"]
            listing["by_listing_type"] = {
                str(row[0] or "unknown"): int(row[1])
                for row in db.execute(
                    "SELECT coalesce(listing_type, 'unknown'), count(*) FROM listing_observations GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
            listing["distinct_listing_identities"] = int(
                _fetchone(
                    db,
                    "SELECT count(DISTINCT (coalesce(listing_type, 'unknown'), listing_id)) FROM listing_observations WHERE nullif(trim(cast(listing_id AS VARCHAR)), '') IS NOT NULL",
                )
            )
            listing["missingness_by_listing_type"] = {}
            fields = (
                "url",
                "listing_id",
                "building_slug",
                "unit_label",
                "bedrooms",
                "bathrooms",
                "square_feet",
                "room_count",
                "features_json",
                "amenities_json",
                "pricing_json",
                "collected_at",
                "parsed_at",
            )
            for kind in ("rental", "sale", "unknown"):
                row: dict[str, int] = {}
                for field in fields:
                    row[field] = int(
                        _fetchone(
                            db,
                            f"SELECT count(*) FILTER (WHERE {field} IS NULL OR cast({field} AS VARCHAR) = '') FROM listing_observations WHERE coalesce(listing_type, 'unknown') = ?",
                            [kind],
                        )
                    )
                listing["missingness_by_listing_type"][kind] = row
            listing["json_completeness_by_listing_type"] = {}
            for kind in ("rental", "sale", "unknown"):
                listing["json_completeness_by_listing_type"][kind] = {}
                for field in ("features_json", "amenities_json", "pricing_json"):
                    listing["json_completeness_by_listing_type"][kind][field] = {
                        str(r[0]): int(r[1])
                        for r in db.execute(
                            f"SELECT {_json_state(field)}, count(*) FROM listing_observations WHERE coalesce(listing_type, 'unknown') = ? GROUP BY 1 ORDER BY 1",
                            [kind],
                        ).fetchall()
                    }
            listing["source_labels"] = {
                "building_slug_distinct": int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT nullif(trim(building_slug), '')) FROM listing_observations",
                    )
                ),
                "unit_label_distinct": int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT nullif(trim(unit_label), '')) FROM listing_observations",
                    )
                ),
                "interpretation": "Labels are source strings and do not prove physical-unit identity.",
            }
            listing["source_pairs"] = {
                kind: int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT (nullif(trim(building_slug), ''), nullif(trim(unit_label), ''))) FROM listing_observations WHERE coalesce(listing_type, 'unknown') = ? AND nullif(trim(building_slug), '') IS NOT NULL AND nullif(trim(unit_label), '') IS NOT NULL",
                        [kind],
                    )
                )
                for kind in ("rental", "sale", "unknown")
            }
            listing["attribute_disagreements"] = []
            rows = db.execute(
                """SELECT listing_type, listing_id, count(DISTINCT nullif(trim(building_slug), '')) AS buildings,
                          count(DISTINCT nullif(trim(unit_label), '')) AS units, count(*) AS observations
                   FROM listing_observations WHERE nullif(trim(listing_id), '') IS NOT NULL
                   GROUP BY listing_type, listing_id HAVING buildings > 1 OR units > 1 ORDER BY observations DESC, listing_id LIMIT 100"""
            ).fetchall()
            listing["attribute_disagreements"] = [
                {
                    "listing_type": r[0] or "unknown",
                    "listing_id": r[1],
                    "building_labels": int(r[2]),
                    "unit_labels": int(r[3]),
                    "observations": int(r[4]),
                }
                for r in rows
            ]
            listing["attribute_disagreement_count"] = int(
                _fetchone(
                    db,
                    """SELECT count(*) FROM (
                SELECT listing_type, listing_id FROM listing_observations
                WHERE nullif(trim(listing_id), '') IS NOT NULL
                GROUP BY listing_type, listing_id
                HAVING count(DISTINCT nullif(trim(building_slug), '')) > 1
                    OR count(DISTINCT nullif(trim(unit_label), '')) > 1)""",
                )
            )
            disagreements = db.execute(
                """SELECT listing_type, building_slug, unit_label, count(*) AS observations,
                          count(DISTINCT bedrooms) AS bedrooms, count(DISTINCT bathrooms) AS bathrooms,
                          count(DISTINCT square_feet) AS square_feet
                   FROM listing_observations
                   WHERE nullif(trim(building_slug), '') IS NOT NULL AND nullif(trim(unit_label), '') IS NOT NULL
                   GROUP BY listing_type, building_slug, unit_label
                   HAVING bedrooms > 1 OR bathrooms > 1 OR square_feet > 1
                   ORDER BY observations DESC LIMIT 100"""
            ).fetchall()
            listing["source_pair_attribute_disagreement_count"] = int(
                _fetchone(
                    db,
                    """SELECT count(*) FROM (
                SELECT listing_type, building_slug, unit_label FROM listing_observations
                WHERE nullif(trim(building_slug), '') IS NOT NULL AND nullif(trim(unit_label), '') IS NOT NULL
                GROUP BY listing_type, building_slug, unit_label
                HAVING count(DISTINCT bedrooms) > 1 OR count(DISTINCT bathrooms) > 1 OR count(DISTINCT square_feet) > 1)""",
                )
            )
            listing["source_pair_attribute_disagreements"] = [
                {
                    "listing_type": r[0] or "unknown",
                    "building_slug": r[1],
                    "unit_label": r[2],
                    "observations": int(r[3]),
                    "distinct_bedrooms": int(r[4]),
                    "distinct_bathrooms": int(r[5]),
                    "distinct_square_feet": int(r[6]),
                }
                for r in disagreements
            ]
            result["parse_failures"]["listing_observations"] = {
                "by_status": {
                    str(r[0] or "unknown"): int(r[1])
                    for r in db.execute(
                        "SELECT coalesce(parse_status, 'unknown'), count(*) FROM listing_observations GROUP BY 1 ORDER BY 1"
                    ).fetchall()
                },
                "error_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM listing_observations WHERE nullif(trim(error), '') IS NOT NULL",
                    )
                ),
                "by_error": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT error,count(*) FROM listing_observations WHERE error IS NOT NULL GROUP BY error ORDER BY count(*) DESC LIMIT 30"
                    ).fetchall()
                },
                "gallery_error_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM listing_observations WHERE url LIKE '%/media_gallery%' AND error IS NOT NULL",
                    )
                ),
            }
            sample_rows = (
                db.execute(
                    """SELECT listing_id, listing_type, bedrooms, bathrooms, square_feet, error
                   FROM listing_observations
                   WHERE bedrooms < 0 OR bedrooms > 20 OR bathrooms < 0 OR bathrooms > 20
                      OR square_feet <= 0 OR square_feet > 50000 OR nullif(trim(error), '') IS NOT NULL
                   LIMIT 100"""
                ).fetchall()
                if counts["listing_observations"]
                else []
            )
            result["suspicious_samples"]["listing_observations"] = [
                dict(
                    zip(
                        [
                            "listing_id",
                            "listing_type",
                            "bedrooms",
                            "bathrooms",
                            "square_feet",
                            "error",
                        ],
                        row,
                    )
                )
                for row in sample_rows
            ]

        if relations["event_mentions"]:
            event = result["event_mentions"]
            event["by_category"] = {
                str(r[0] or "unknown"): int(r[1])
                for r in db.execute(
                    "SELECT coalesce(event_category, 'unknown'), count(*) FROM event_mentions GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
            event["price"] = {
                "positive": int(
                    _fetchone(db, "SELECT count(*) FROM event_mentions WHERE price > 0")
                ),
                "non_positive": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM event_mentions WHERE price IS NOT NULL AND price <= 0",
                    )
                ),
            }
            event["dates"] = {
                "parseable": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM event_mentions WHERE try_cast(event_date AS DATE) IS NOT NULL",
                    )
                ),
                "unparseable": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM event_mentions WHERE event_date IS NOT NULL AND try_cast(event_date AS DATE) IS NULL",
                    )
                ),
            }
            event["by_year"] = {
                str(r[0]): int(r[1])
                for r in db.execute(
                    "SELECT year(try_cast(event_date AS DATE)), count(*) FROM event_mentions WHERE try_cast(event_date AS DATE) IS NOT NULL GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
            year_bounds = db.execute(
                "SELECT min(year(try_cast(event_date AS DATE))), max(year(try_cast(event_date AS DATE))) FROM event_mentions WHERE try_cast(event_date AS DATE) IS NOT NULL"
            ).fetchone()
            event["years"] = {
                "min": int(year_bounds[0]) if year_bounds[0] is not None else None,
                "max": int(year_bounds[1]) if year_bounds[1] is not None else None,
            }
            event["price_change"] = {
                "at_most_one_percent": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM event_mentions WHERE percent_change IS NOT NULL AND abs(percent_change) <= 1",
                    )
                ),
                "with_percent_change": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM event_mentions WHERE percent_change IS NOT NULL",
                    )
                ),
            }
            event["event_key"] = {
                "rows": counts["event_mentions"],
                "distinct": int(
                    _fetchone(
                        db, "SELECT count(DISTINCT event_key) FROM event_mentions"
                    )
                ),
                "duplicate_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) - count(DISTINCT event_key) FROM event_mentions",
                    )
                ),
            }
            density_sql = "(SELECT count(*) n FROM event_mentions GROUP BY snapshot_id)"
            event["density"] = {
                "listing_ids": int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT (event_category, listing_id)) FROM event_mentions WHERE listing_id IS NOT NULL",
                    )
                ),
                "captures": int(_fetchone(db, f"SELECT count(*) FROM {density_sql}")),
                "events_per_capture": {
                    "min": int(
                        _fetchone(db, f"SELECT coalesce(min(n), 0) FROM {density_sql}")
                    ),
                    "max": int(
                        _fetchone(db, f"SELECT coalesce(max(n), 0) FROM {density_sql}")
                    ),
                    "p50": float(
                        _fetchone(
                            db,
                            f"SELECT coalesce(quantile_cont(n, 0.5), 0) FROM {density_sql}",
                        )
                    ),
                    "p95": float(
                        _fetchone(
                            db,
                            f"SELECT coalesce(quantile_cont(n, 0.95), 0) FROM {density_sql}",
                        )
                    ),
                },
            }
            event["occurrence_uniqueness"] = {
                "rows": counts["event_mentions"],
                "distinct_occurrences": int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT (snapshot_id, episode_index, event_category, event_index)) FROM event_mentions",
                    )
                ),
            }
            result["suspicious_samples"]["event_mentions"] = [
                dict(
                    zip(
                        [
                            "listing_id",
                            "event_date",
                            "price",
                            "percent_change",
                            "event_key",
                        ],
                        r,
                    )
                )
                for r in db.execute(
                    "SELECT listing_id,event_date,price,percent_change,event_key FROM event_mentions WHERE (price IS NOT NULL AND price <= 0) OR (event_date IS NOT NULL AND try_cast(event_date AS DATE) IS NULL) LIMIT 100"
                ).fetchall()
            ]

        if relations["building_observations"]:
            result["parse_failures"]["building_observations"] = {
                "by_status": {
                    str(r[0] or "unknown"): int(r[1])
                    for r in db.execute(
                        "SELECT coalesce(parse_status, 'unknown'), count(*) FROM building_observations GROUP BY 1 ORDER BY 1"
                    ).fetchall()
                },
                "error_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM building_observations WHERE nullif(trim(error), '') IS NOT NULL",
                    )
                ),
            }
        if relations["inventory_observations"]:
            result["inventory_observations"] = {
                "parse_status": {
                    str(r[0] or "unknown"): int(r[1])
                    for r in db.execute(
                        "SELECT coalesce(parse_status, 'unknown'), count(*) FROM inventory_observations GROUP BY 1 ORDER BY 1"
                    ).fetchall()
                },
                "count_vs_row_count": {
                    "observations": int(
                        _fetchone(db, "SELECT count(*) FROM inventory_observations")
                    ),
                    "count_sum": int(
                        _fetchone(
                            db,
                            "SELECT coalesce(sum(count), 0) FROM inventory_observations",
                        )
                    ),
                    "row_count_sum": int(
                        _fetchone(
                            db,
                            "SELECT coalesce(sum(row_count), 0) FROM inventory_observations",
                        )
                    ),
                    "mismatch_rows": int(
                        _fetchone(
                            db,
                            "SELECT count(*) FROM inventory_observations WHERE count IS NOT NULL AND row_count IS NOT NULL AND count <> row_count",
                        )
                    ),
                },
            }

        for table in ("frontier", "url_aliases"):
            if relations[table]:
                label = "kind" if table == "frontier" else "reason"
                result[table] = {
                    "counts": {
                        str(r[0] or "unknown"): int(r[1])
                        for r in db.execute(
                            f"SELECT coalesce({label}, 'unknown'), count(*) FROM {table} GROUP BY 1 ORDER BY 1"
                        ).fetchall()
                    }
                }
        if relations["source_changes"]:
            cols = _columns(db, "source_changes")
            changes = result["source_changes"] = {"rows": counts["source_changes"]}
            if "source_path" in cols:
                changes["by_source_path"] = {
                    str(r[0] or "unknown"): int(r[1])
                    for r in db.execute(
                        "SELECT coalesce(source_path, 'unknown'), count(*) FROM source_changes GROUP BY 1 ORDER BY 1"
                    ).fetchall()
                }
            if "source_timestamp" in cols:
                changes["dates"] = {
                    "parseable": int(
                        _fetchone(
                            db,
                            "SELECT count(*) FROM source_changes WHERE try_cast(source_timestamp AS DATE) IS NOT NULL",
                        )
                    ),
                    "unparseable": int(
                        _fetchone(
                            db,
                            "SELECT count(*) FROM source_changes WHERE source_timestamp IS NOT NULL AND try_cast(source_timestamp AS DATE) IS NULL",
                        )
                    ),
                }
            if "snapshot_id" in cols:
                changes["by_snapshot"] = int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT snapshot_id) FROM source_changes WHERE snapshot_id IS NOT NULL",
                    )
                )

        if relations["media_gallery_observations"]:
            result["media_gallery_observations"] = {
                "rows": counts["media_gallery_observations"],
                "by_listing_type": {
                    str(r[0] or "unknown"): int(r[1])
                    for r in db.execute(
                        "SELECT listing_type,count(*) FROM media_gallery_observations GROUP BY listing_type"
                    ).fetchall()
                },
                "by_status": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT parse_status,count(*) FROM media_gallery_observations GROUP BY parse_status"
                    ).fetchall()
                },
                "error_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM media_gallery_observations WHERE nullif(trim(error),'') IS NOT NULL",
                    )
                ),
                "by_error": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT error,count(*) FROM media_gallery_observations WHERE error IS NOT NULL GROUP BY error"
                    ).fetchall()
                },
            }
        if relations["listing_exclusions"]:
            result["listing_exclusions"] = {
                "rows": counts["listing_exclusions"],
                "by_reason": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT reason,count(*) FROM listing_exclusions GROUP BY reason"
                    ).fetchall()
                },
                "by_canonical_error": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT canonical_unit_error,count(*) FROM listing_exclusions GROUP BY canonical_unit_error"
                    ).fetchall()
                },
            }
        if relations["snapshots"]:
            coverage = result["coverage"] = {}
            snapshot_type = (
                "coalesce(s.page_type,s.kind)"
                if "page_type" in _columns(db, "snapshots")
                else "s.kind"
            )
            for kind, table in (
                ("listing", "listing_observations"),
                ("media_gallery", "media_gallery_observations"),
                ("building", "building_observations"),
                ("inventory", "inventory_observations"),
            ):
                if not relations[table]:
                    continue
                excluded = (
                    " AND NOT EXISTS (SELECT 1 FROM listing_exclusions x WHERE x.snapshot_id=s.snapshot_id)"
                    if kind == "listing" and relations["listing_exclusions"]
                    else ""
                )
                coverage[kind] = {
                    "expected_snapshots": int(
                        _fetchone(
                            db,
                            f"SELECT count(DISTINCT s.snapshot_id) FROM snapshots s WHERE {snapshot_type} = ?",
                            [kind],
                        )
                    ),
                    "observed_snapshots": int(
                        _fetchone(
                            db, f"SELECT count(DISTINCT snapshot_id) FROM {table}"
                        )
                    ),
                    "expected_unobserved": int(
                        _fetchone(
                            db,
                            f"SELECT count(DISTINCT s.snapshot_id) FROM snapshots s WHERE {snapshot_type} = ? AND NOT EXISTS (SELECT 1 FROM {table} t WHERE t.snapshot_id = s.snapshot_id){excluded}",
                            [kind],
                        )
                    ),
                }
                if excluded:
                    coverage[kind]["intentionally_excluded"] = int(
                        _fetchone(
                            db,
                            f"SELECT count(DISTINCT x.snapshot_id) FROM listing_exclusions x JOIN snapshots s USING(snapshot_id) WHERE {snapshot_type}='listing'",
                        )
                    )
        if relations["fetch_observations"]:
            fetch = result["fetch_observations"] = {
                "status_counts": {
                    str(r[0] if r[0] is not None else "null"): int(r[1])
                    for r in db.execute(
                        "SELECT status, count(*) FROM fetch_observations GROUP BY 1 ORDER BY 1"
                    ).fetchall()
                }
            }
            clocks = db.execute(
                "SELECT min(fetched_at), max(fetched_at) FROM fetch_observations WHERE fetched_at IS NOT NULL"
            ).fetchone()
            fetch["fetched_at_range"] = {"min": clocks[0], "max": clocks[1]}
            fetch["fetched_years"] = {
                str(r[0]): int(r[1])
                for r in db.execute(
                    "SELECT year(to_timestamp(fetched_at)), count(*) FROM fetch_observations WHERE fetched_at IS NOT NULL AND isfinite(fetched_at) GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
        if relations["listing_observations"]:
            years = db.execute(
                "SELECT coalesce(listing_type, 'unknown'), year(to_timestamp(collected_at)), count(*) FROM listing_observations WHERE collected_at IS NOT NULL AND isfinite(collected_at) GROUP BY 1, 2 ORDER BY 1, 2"
            ).fetchall()
            result["listing_observations"]["collected_years_by_type"] = {}
            for type_name, year_value, count_value in years:
                result["listing_observations"]["collected_years_by_type"].setdefault(
                    str(type_name), {}
                )[str(year_value)] = int(count_value)
        if relations["inventory_rows"] and relations["inventory_observations"]:
            result["inventory_observations"]["row_count_by_snapshot_mismatch"] = int(
                _fetchone(
                    db,
                    """SELECT count(*) FROM inventory_observations i WHERE i.row_count IS NOT NULL AND i.row_count <> (SELECT count(*) FROM inventory_rows r WHERE r.snapshot_id = i.snapshot_id)""",
                )
            )

        if relations["inventory_row_links"]:
            result["inventory_row_links"] = {
                "by_kind": {
                    str(r[0]): int(r[1])
                    for r in db.execute(
                        "SELECT row_kind,count(*) FROM inventory_row_links GROUP BY row_kind"
                    ).fetchall()
                },
                "rows": counts["inventory_row_links"],
                "distinct_occurrences": int(
                    _fetchone(
                        db,
                        "SELECT count(DISTINCT (snapshot_id,row_index)) FROM inventory_row_links",
                    )
                ),
                "missing_source_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM inventory_row_links l WHERE NOT EXISTS (SELECT 1 FROM inventory_rows r WHERE r.snapshot_id=l.snapshot_id AND r.row_index=l.row_index)",
                    )
                ),
                "unlinked_source_rows": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM inventory_rows r WHERE NOT EXISTS (SELECT 1 FROM inventory_row_links l WHERE r.snapshot_id=l.snapshot_id AND r.row_index=l.row_index)",
                    )
                ),
                "recovered_legacy_links": int(
                    _fetchone(
                        db,
                        "SELECT count(*) FROM inventory_row_links WHERE record_url IS NULL AND listing_url IS NOT NULL",
                    )
                ),
            }
        result["referential_checks"] = {}
        if relations["snapshots"]:
            for table in (
                "listing_observations",
                "listing_exclusions",
                "media_gallery_observations",
                "building_observations",
                "inventory_rows",
                "inventory_observations",
                "event_mentions",
                "source_changes",
            ):
                if relations[table] and "snapshot_id" in {
                    r[0] for r in db.execute(f"DESCRIBE {table}").fetchall()
                }:
                    result["referential_checks"][f"{table}_missing_snapshot"] = int(
                        _fetchone(
                            db,
                            f"SELECT count(*) FROM {table} t WHERE t.snapshot_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM snapshots s WHERE s.snapshot_id = t.snapshot_id)",
                        )
                    )
        if relations["listing_exclusions"]:
            checks = result["referential_checks"]
            checks["listing_exclusions_duplicate_snapshots"] = int(
                _fetchone(
                    db,
                    "SELECT count(*) - count(DISTINCT snapshot_id) FROM listing_exclusions",
                )
            )
            checks["listing_exclusions_invalid"] = int(
                _fetchone(
                    db,
                    "SELECT count(*) FROM listing_exclusions WHERE snapshot_id IS NULL OR coalesce(listing_type,'')<>'rental' OR coalesce(reason,'')<>'rental_missing_canonical_unit_page' OR nullif(canonical_unit_error,'') IS NULL",
                )
            )
            for table in ("listing_observations", "event_mentions", "source_changes"):
                if relations[table]:
                    checks[f"{table}_from_excluded_snapshot"] = int(
                        _fetchone(
                            db,
                            f"SELECT count(*) FROM {table} t WHERE EXISTS (SELECT 1 FROM listing_exclusions x WHERE x.snapshot_id=t.snapshot_id)",
                        )
                    )
        if relations["media_gallery_observations"]:
            checks = result["referential_checks"]
            checks["media_gallery_duplicate_snapshots"] = int(
                _fetchone(
                    db,
                    "SELECT count(*) - count(DISTINCT snapshot_id) FROM media_gallery_observations",
                )
            )
            checks["media_gallery_invalid_page_type"] = int(
                _fetchone(
                    db,
                    "SELECT count(*) FROM media_gallery_observations WHERE snapshot_id IS NULL OR coalesce(page_type,'')<>'media_gallery'",
                )
            )
            for table in (
                "listing_observations",
                "listing_exclusions",
                "event_mentions",
                "source_changes",
            ):
                if relations[table]:
                    checks[f"{table}_from_gallery_snapshot"] = int(
                        _fetchone(
                            db,
                            f"SELECT count(*) FROM {table} t WHERE EXISTS (SELECT 1 FROM media_gallery_observations g WHERE g.snapshot_id=t.snapshot_id)",
                        )
                    )
        return result
    finally:
        db.close()
