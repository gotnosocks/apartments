"""Recover listing links from preserved inventory-row HTML without rewriting source rows."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from streeteasy_archive.extract import _selector, canonical_url, kind_for


SCHEMA = pa.schema(
    [
        ("snapshot_id", pa.int64()),
        ("row_index", pa.int64()),
        ("listing_url", pa.string()),
        ("row_kind", pa.string()),
        ("record_url", pa.string()),
        ("link_basis", pa.string()),
        ("parsed_at", pa.float64()),
        ("candidate_urls_json", pa.string()),
    ]
)
IMPLEMENTATION = "inventory-links-v2"


def _text(value):
    return value if isinstance(value, str) else None


def _record_url(row):
    value = _text(row.get("listing_url"))
    if value:
        return value
    raw = row.get("record_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict):
        for key in ("url", "listing_url", "listingUrl"):
            if data.get(key):
                return _text(data[key])
    return None


def _candidates(row):
    html = _text(row.get("row_html")) or ""
    values = []
    if html.strip():
        try:
            sel = _selector(html.encode("utf-8"))
            values = sel.css("a::attr(href), [href]::attr(href)").getall()
        except Exception:
            values = []
    valid = []
    for value in values:
        url = canonical_url(value)
        if (
            url
            and kind_for(url) in {"listing", None}
            and (kind_for(url) == "listing" or "/closing/" in url)
        ):
            if url not in valid:
                valid.append(url)
    return valid


def _is_placeholder(row):
    html = _text(row.get("row_html")) or ""
    if not html.strip():
        return False
    try:
        text = (
            _selector(html.encode())
            .xpath("normalize-space(.)")
            .get()
            .lower()
            .rstrip(".")
        )
    except Exception:
        return False
    return text in {
        "no info for unavailable units",
        "no units available",
        "no listings available",
        "no records",
        "no units",
        "no listings",
    }


def build_inventory_links(root: Path) -> dict:
    """Build ``inventory_row_links/derived.parquet`` from inventory row parts.

    The source table is read in Arrow batches and never overwritten. Rebuilding
    replaces only the derived output after its temporary file is complete.
    """
    root = Path(root)
    source_dir = root / "inventory_rows"
    files = (
        sorted(p for p in source_dir.rglob("*.parquet") if p.is_file())
        if source_dir.exists()
        else []
    )
    output_dir = root / "inventory_row_links"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "derived.parquet"
    partial = output_dir / "derived.parquet.partial"
    if partial.exists():
        partial.unlink()
    writer = pq.ParquetWriter(partial, SCHEMA, compression="zstd")
    counts = {
        "listing": 0,
        "closing": 0,
        "placeholder": 0,
        "unclassified": 0,
        "ambiguous": 0,
    }
    stats = {
        "rows": 0,
        "recovered_legacy_links": 0,
        "mismatched_nonnull_record_url": 0,
        "unresolved": 0,
        "ambiguous": 0,
    }
    basis_counts = {}
    input_hash = hashlib.sha256()
    parsed_at = time.time()
    try:
        for path in files:
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=256):
                output_rows = []
                for row in batch.to_pylist():
                    stats["rows"] += 1
                    record_url = _record_url(row)
                    input_hash.update(
                        json.dumps(
                            [
                                row.get("snapshot_id"),
                                row.get("row_index"),
                                row.get("row_html"),
                                record_url,
                            ],
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        ).encode("utf-8")
                    )
                    input_hash.update(b"\n")
                    record_canonical = canonical_url(record_url) if record_url else None
                    candidates = _candidates(row)
                    basis = "html"
                    chosen = None
                    if len(candidates) == 1:
                        chosen = candidates[0]
                    elif len(candidates) > 1:
                        basis = "ambiguous_html"
                        stats["ambiguous"] += 1
                        if record_canonical in candidates:
                            chosen = record_canonical
                            basis = "record_disambiguation"
                    elif record_canonical and (
                        kind_for(record_canonical) == "listing"
                        or "/closing/" in record_canonical
                    ):
                        chosen = record_canonical
                        basis = "record_fallback"
                    elif _is_placeholder(row):
                        basis = "placeholder"
                    else:
                        basis = "unresolved"
                    if len(candidates) > 1 and not chosen:
                        kind = "ambiguous"
                    elif chosen and "/closing/" in chosen:
                        kind = "closing"
                    elif chosen:
                        kind = "listing"
                    elif basis == "placeholder":
                        kind = "placeholder"
                    else:
                        kind = "unclassified"
                    if kind == "unclassified":
                        stats["unresolved"] += 1
                    if (
                        row.get("listing_url") is None
                        and chosen
                        and basis in {"html", "record_fallback"}
                    ):
                        stats["recovered_legacy_links"] += 1
                    if record_canonical and chosen and record_canonical != chosen:
                        stats["mismatched_nonnull_record_url"] += 1
                    counts[kind] += 1
                    basis_counts[basis] = basis_counts.get(basis, 0) + 1
                    output_rows.append(
                        {
                            "snapshot_id": row.get("snapshot_id"),
                            "row_index": row.get("row_index"),
                            "listing_url": chosen,
                            "row_kind": kind,
                            "record_url": record_url,
                            "link_basis": basis,
                            "parsed_at": parsed_at,
                            "candidate_urls_json": json.dumps(
                                candidates, separators=(",", ":")
                            ),
                        }
                    )
                if output_rows:
                    writer.write_table(pa.Table.from_pylist(output_rows, schema=SCHEMA))
        writer.close()
        partial.replace(output)
    except Exception:
        writer.close()
        raise
    return {
        "parsed_at": parsed_at,
        "rows": stats["rows"],
        "rows_by_kind": counts,
        "basis_counts": basis_counts,
        "recovered_legacy_links": stats["recovered_legacy_links"],
        "mismatched_nonnull_record_url": stats["mismatched_nonnull_record_url"],
        "unresolved": stats["unresolved"],
        "ambiguous": stats["ambiguous"],
        "implementation": IMPLEMENTATION,
        "implementation_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "input_identity_row_html_record_url_sha256": input_hash.hexdigest(),
        "output": str(output),
    }
