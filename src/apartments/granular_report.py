"""Human-readable Markdown rendering for a granular quality report."""
from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    if value is None:
        return "not reported"
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def _pct(value: int | float, denominator: int | float) -> str:
    if not denominator:
        return "not reported"
    return f"{100 * value / denominator:.1f}%"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_fmt(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def _json_states(value: dict[str, Any], total: int) -> str:
    return "; ".join(f"{state} {count} ({_pct(count, total)})" for state, count in sorted(value.items())) or "not reported"


def render_report(report: dict) -> str:
    """Render an audit dictionary without inferring unreported data quality."""
    tables = report.get("tables", {}).get("counts", {})
    listings = report.get("listing_observations", {})
    events = report.get("event_mentions", {})
    lines = ["# Granular data quality report", "", "This report describes captured source evidence. It does not establish a complete census, signed leases, or verified physical units.", ""]
    provenance = report.get("provenance", {})
    provenance_rows = [["Report root", report.get("root")], ["Source snapshot", provenance.get("snapshot")], ["Run version", provenance.get("version")]]
    if provenance_rows[0][1] is not None or any(row[1] is not None for row in provenance_rows[1:]):
        lines += ["## Provenance", "", _table(["Field", "Value"], provenance_rows), ""]
    ledger = provenance.get("corrections") or report.get("corrections")
    if isinstance(ledger, dict):
        records = ledger.get("record_count", ledger.get("records"))
        if isinstance(records, (list, tuple)):
            records = len(records)
        lines += [f"Correction ledger: active={_fmt(ledger.get('enabled'))}, visible records={_fmt(records)}.", ""]

    lines += ["## Captured tables", "", _table(["Table", "Rows"], [[name, count] for name, count in tables.items()]), ""]

    by_type = listings.get("by_listing_type", {})
    identity_count = listings.get("distinct_listing_identities")
    lines += ["## Listing observations", "", _table(["Listing type", "Observed captures", "Share of captures"], [[kind, count, _pct(count, sum(by_type.values()))] for kind, count in sorted(by_type.items())]), ""]
    lines += [f"Distinct typed listing identities: **{_fmt(identity_count)}** (listing type and listing ID are separate namespaces).", ""]
    pairs = listings.get("source_pairs", {})
    lines += [f"Distinct source `(building_slug, unit_label)` pairs: rental **{_fmt(pairs.get('rental'))}**, sale **{_fmt(pairs.get('sale'))}**, unknown **{_fmt(pairs.get('unknown'))}**. These are source labels, not verified physical units.", ""]

    missing = listings.get("missingness_by_listing_type", {})
    completeness = listings.get("json_completeness_by_listing_type", {})
    rows = []
    for kind in ("rental", "sale", "unknown"):
        total = by_type.get(kind, 0)
        for field in ("bedrooms", "bathrooms", "square_feet", "room_count"):
            count = missing.get(kind, {}).get(field)
            rows.append([kind, field, count, _pct(count, total) if count is not None else "not reported"])
        for field in ("features_json", "amenities_json", "pricing_json"):
            states = completeness.get(kind, {}).get(field)
            rows.append([kind, field, _json_states(states, total) if states is not None else "not reported", ""])
    lines += ["### Model-variable missingness and JSON state", "", _table(["Type", "Field", "Missing/count state", "% missing where available"], rows), ""]

    numeric = report.get("numeric", {}).get("listing_observations", {})
    if numeric:
        lines += ["### Numeric quality flags", "", "Invalid values are quality flags retained in the source observations; they are not deleted.", "", _table(["Field", "Non-null", "Invalid/range flags"], [[field, values.get("non_null"), values.get("invalid")] for field, values in numeric.items()]), ""]

    lines += ["## History events", ""]
    price = events.get("price", {})
    dates = events.get("dates", {})
    years = events.get("years", {})
    keys = events.get("event_key", {})
    lines += [_table(["Measure", "Value"], [
        ["Event rows", keys.get("rows", tables.get("event_mentions"))],
        ["Positive prices", price.get("positive")],
        ["Parseable dates", dates.get("parseable")],
        ["Date range", f"{_fmt(years.get('min'))}–{_fmt(years.get('max'))}"],
        ["Distinct semantic event keys", keys.get("distinct")],
        ["Duplicate evidence rows", keys.get("duplicate_rows")],
        ["Events with change ≤1%", events.get("price_change", {}).get("at_most_one_percent")],
    ]), "", "Repeated event rows are retained evidence; duplicate keys do not imply rows were discarded.", ""]
    if events.get("by_category") or events.get("density"):
        lines += ["### Event categories and density", "", _table(["Category/measure", "Value"], [[f"Category: {k}", v] for k, v in events.get("by_category", {}).items()] + [["Density", events.get("density", {}).get("events_per_capture")]]), ""]

    lines += ["## Disagreements and parse failures", "", _table(["Diagnostic", "Count"], [
        ["Listing identity attribute disagreement groups", listings.get("attribute_disagreement_count")],
        ["Source-pair attribute disagreement groups", listings.get("source_pair_attribute_disagreement_count")],
        ["Listing parse error rows", report.get("parse_failures", {}).get("listing_observations", {}).get("error_rows")],
        ["Building parse error rows", report.get("parse_failures", {}).get("building_observations", {}).get("error_rows")],
    ]), "", "Attribute disagreements are retained for review and are not automatically corrected or treated as proven temporal changes. Missing amenities do not mean absence, and nonempty JSON can still contain an empty item list.", ""]

    coverage = report.get("coverage", {})
    if coverage:
        lines += ["## Coverage and linkage checks", "", _table(["Kind", "Expected snapshots", "Observed snapshots", "Expected without observation"], [[kind, value.get("expected_snapshots"), value.get("observed_snapshots"), value.get("expected_unobserved")] for kind, value in coverage.items()]), ""]
    refs = report.get("referential_checks", {})
    if refs:
        lines += [_table(["Referential check", "Rows missing referenced snapshot"], [[name, count] for name, count in refs.items()]), ""]
    fetch = report.get("fetch_observations", {})
    if fetch:
        lines += ["Fetch status counts: " + ", ".join(f"{k}={v}" for k, v in fetch.get("status_counts", {}).items()) + ".", ""]
    inventory = report.get("inventory_observations", {})
    if inventory:
        mismatch = inventory.get("count_vs_row_count", {})
        lines += ["Inventory reconciliation: " + ", ".join(f"{k}={_fmt(v)}" for k, v in mismatch.items()) + ".", ""]
        if "row_count_by_snapshot_mismatch" in inventory:
            lines += [f"Inventory row-count mismatches by snapshot: **{inventory['row_count_by_snapshot_mismatch']}**.", ""]

    linked = report.get("inventory_row_links")
    if linked:
        lines += ["## Inventory link interpretation", "", _table(["Measure", "Count"], [[k,v] for k,v in linked.items() if k != "by_kind"]), "", _table(["Row kind", "Count"], [[k,v] for k,v in linked.get("by_kind",{}).items()]), "", "This companion table derives links from saved row HTML while preserving original extraction metadata. Placeholder messages do not represent extra units.", ""]

    changes = report.get("source_changes")
    if changes:
        lines += ["## Source changes", "", _table(["Measure", "Value"], [["Rows", changes.get("rows")], ["By source path", ", ".join(f"{k}={v}" for k, v in changes.get("by_source_path", {}).items())], ["Date parsing", ", ".join(f"{k}={v}" for k, v in changes.get("dates", {}).items())], ["Snapshots represented", changes.get("by_snapshot")]]), ""]

    lines += ["## Interpretation limits and next data-quality actions", "", "- Attributes describe the capture in which they were observed; do not back-join the latest attributes onto historical events.", "- Keep source-label disagreements visible and review them; do not auto-correct or silently merge labels into physical units.", "- Choose listing identity, event deduplication, and model time windows explicitly before training.", "- Quantify missingness by variable and listing type, investigate parse failures, and reconcile snapshot linkage before modeling.", "- Treat any future aggregation as a modeling decision; this report does not assert physical-unit completeness or signed-lease outcomes.", ""]
    return "\n".join(lines)
