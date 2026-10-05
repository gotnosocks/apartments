"""A new analysis month of current captures on the combined neighbourhood cohort.

`refresh_analysis_cohort` replaces current captures within one month of Chelsea's
reviewed cohort. This module moves the combined cohort
(`rentfrontier.cohort combine`, `combined-neighbourhood-cohort-v1`) to a later
analysis month:

- Every historical row of a month before the new one is kept exactly.
- The parent's current-capture rows (an earlier month's ACTIVE asks) are
  dropped; the new captures replace them.
- New rows come from verified bounded-refresh collections, the same way as
  `refresh_analysis_cohort`:
  - failed refreshes block older successes;
  - selection uses `fit_robust_analysis.current_rows`: ACTIVE captures in the
    analysis month, 0-5 bedrooms, 1-5 baths, $750-50,000;
  - bathrooms come from `bathroom_projection`.
- Each new row's neighbourhood is its discovery seed in the collection's review
  queue (`/for-rent/west-village` is West Village; `/for-rent/chelsea` and
  `/for-rent/west-chelsea` are Chelsea; any other seed, or seeds of both, is
  ambiguous and excluded). It must agree with the neighbourhood of the
  building's earlier rows.
- The floor is the ad's own floor, else its unit label read as
  `rentfrontier.cohort.floor_of` reads it, against the smallest floor count the
  granular crawls' building pages report (`cohort.floor_counts`). A building whose
  historical rows the floor review excluded from label numbering
  (`reviewed_building_numbering_excluded`) gets no label floor.
- A dropped current row's review (`research_review_history`) is carried to the new
  row of the same advertisement when the new capture repeats the reviewed claim;
  if the claim changed, the build stops for a new review.
- A row is excluded when its building is not in the registry the feature sets
  read, since there is no location or lot for it.

    python -m models.current_capture_cohort --parent <combined dataset> \
        --collection <collection root> --review-queue <detail-review-queue.jsonl> \
        --registry <buildings.parquet> --granular <crawl> [--granular <crawl>] \
        --output <dir> --as-of <cutoff>
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from apartments.corrections import canonical, instant
from apartments.research_pipeline import digest, publish_bundle
from . import (
    bathroom_projection,
    fit_robust_analysis,
    refresh_analysis_cohort as refresh,
)

try:
    from rentfrontier import cohort
except ImportError:  # the frontier package is not installed in the project venv
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frontier" / "src"))
    from rentfrontier import cohort

VERSION = "combined-current-capture-cohort-v1"
PARENT_VERSION = "combined-neighbourhood-cohort-v1"
SEEDS = {
    "/for-rent/west-village": "West Village",
    "/for-rent/chelsea": "Chelsea",
    "/for-rent/west-chelsea": "Chelsea",
}
NUMBERING_EXCLUDED = "reviewed_building_numbering_excluded"
HISTORICAL = "historical_initial_own_advertisement_ask"
CURRENT = "current_capture_gross_ask"


def seed_neighbourhoods(queue_rows):
    """source_listing_id -> neighbourhood from each queued ad's discovery seeds
    (None when they name both, or a seed outside SEEDS)."""
    names = defaultdict(set)
    for row in queue_rows:
        for o in row.get("observations") or []:
            if o.get("seed"):
                names[str(row["source_listing_id"])].add(
                    SEEDS.get(urlsplit(o["seed"]).path.rstrip("/"))
                )
    return {k: (v.pop() if len(v) == 1 else None) for k, v in names.items()}


def carry_review(projected, old):
    """The dropped row's bathroom-composition review applied to the new row of the
    same advertisement, when the new capture repeats the reviewed counts."""
    keys = ("bathrooms", "reported_full_bathrooms", "reported_half_bathrooms")
    history = old.get("research_review_history") or []
    if any(h.get("action") != "mask_bathroom_composition" for h in history) or any(
        projected.get(k) != old.get(k) for k in keys
    ):
        raise ValueError(f"Review of {old['audit_id']} needs explicit reapplication")
    evidence = {
        **projected["bathroom_count_evidence"],
        "composition_status": old["bathroom_count_evidence"]["composition_status"],
        "flags": sorted(
            {
                *projected["bathroom_count_evidence"]["flags"],
                *old["bathroom_count_evidence"]["flags"],
            }
        ),
    }
    carried = [{**h, "carried_from_audit_id": old["audit_id"]} for h in history]
    return {
        **projected,
        "bathroom_count_evidence": evidence,
        "research_review_history": carried,
    }


def unit_label(url):
    parts = urlsplit(url).path.strip("/").split("/")
    return parts[2] if len(parts) == 3 and parts[0] == "building" else None


def assemble(
    parent_rows,
    candidates,
    failures,
    sources,
    neighbourhoods,
    registry,
    counts,
    *,
    as_of,
    max_age_days,
    evidence_of=refresh.capture_evidence,
):
    cutoff = instant(as_of)
    month = cutoff.strftime("%Y-%m-01")
    if any(instant(r["known_at"]) > cutoff for r in parent_rows):
        raise ValueError("Parent evidence is later than cutoff")
    history, dropped, reviewed = [], [], {}
    for row in parent_rows:
        if row["analysis_price_basis"] == HISTORICAL and row["period"] < month:
            history.append(row)
        elif row["analysis_price_basis"] == CURRENT and row["period"] < month:
            dropped.append(row["audit_id"])
            if row.get("research_review_history"):
                reviewed[str(row["source_listing_id"])] = row
        else:
            raise ValueError("Parent has rows in or after the new analysis month")
    known = defaultdict(set)
    for row in history:
        known[row["building"]].add(row["neighbourhood"])
    units = {row["unit_id"] for row in history}
    unnumbered = {
        row["building"]
        for row in history
        if (row.get("floor_label_provenance") or {}).get("status") == NUMBERING_EXCLUDED
    }
    available, excluded = refresh.combine_records(candidates, failures, as_of=as_of)
    fresh, selection_exclusions, selection = fit_robust_analysis.current_rows(
        available, as_of=as_of, max_age_days=max_age_days
    )
    excluded.extend(selection_exclusions)
    evidence, current = [], []
    for row in fresh:
        name = neighbourhoods.get(str(row["source_listing_id"]))
        reason = (
            "no_or_ambiguous_discovery_seed"
            if name is None
            else "seed_disagrees_with_building_neighbourhood"
            if known[row["building"]] - {name}
            else "building_not_in_registry"
            if row["building"] not in registry
            else None
        )
        if reason:
            excluded.append({"record": row, "reason": reason})
            continue
        source = evidence_of(row, sources[row["capture_id"]])
        projected = bathroom_projection.project({**row, "period": month}, [source])
        floor, why = cohort.floor_of(
            {"advertised_floor": row.get("advertised_floor")},
            [unit_label(row["canonical_unit_url"])],
            counts.get(row["building"]),
        )
        if why == "label_proxy" and row["building"] in unnumbered:
            floor, why = None, NUMBERING_EXCLUDED
        projected.update(
            neighbourhood=name,
            listed_floor=floor,
            label_derived_floor=floor if why == "label_proxy" else None,
            floor_label_provenance={
                "status": why,
                "building_floor_count": counts.get(row["building"]),
            },
        )
        if str(row["source_listing_id"]) in reviewed:
            projected = carry_review(projected, reviewed[str(row["source_listing_id"])])
        source["audit_id"] = projected["audit_id"]
        evidence.append(source)
        current.append(projected)
    if not current:
        raise ValueError("No eligible current rows")
    rows = sorted(history + current, key=lambda r: (r["period"], r["unit_id"]))
    if len({r["audit_id"] for r in rows}) != len(rows) or len(
        {(r["unit_id"], r["period"]) for r in rows}
    ) != len(rows):
        raise ValueError("Duplicate analytical identity or unit-month")
    buildings = defaultdict(set)
    for row in rows:
        buildings[row["unit_id"]].add(row["building"])
    if any(len(b) != 1 for b in buildings.values()):
        raise ValueError("Conflicting unit/building identity")
    summary = {
        "rows": len(rows),
        "historical_rows": len(history),
        "current_rows": len(current),
        "analysis_month": month,
        "dropped_previous_current_rows": len(dropped),
        "current_by_neighbourhood": dict(Counter(r["neighbourhood"] for r in current)),
        "current_new_units": sum(r["unit_id"] not in units for r in current),
        "units": len(buildings),
        "buildings": len({r["building"] for r in rows}),
        "historical_rows_preserved_exactly": True,
        "selection": selection,
        "exclusions": dict(Counter(e["reason"] for e in excluded)),
        "carried_reviews": sorted(
            r["audit_id"] for r in current if r.get("research_review_history")
        ),
        "current_floor_status": dict(
            Counter(r["floor_label_provenance"]["status"] for r in current)
        ),
        "current_bathroom_flags": dict(
            Counter(f for r in current for f in r["bathroom_count_evidence"]["flags"])
        ),
    }
    return rows, evidence, excluded, summary, dropped


def run(
    parent,
    collections,
    review_queues,
    registry,
    granular,
    output,
    *,
    as_of,
    max_age_days=1,
):
    import pyarrow.parquet as pq

    if instant(as_of) > datetime.now(UTC):
        raise ValueError("Analysis cutoff is in the future")
    parent = Path(parent)
    manifest = json.loads((parent / "complete.json").read_text())
    observations = (parent / "observations.jsonl").read_bytes()
    if (
        manifest.get("version") != PARENT_VERSION
        or manifest["files"]["observations.jsonl"]
        != hashlib.sha256(observations).hexdigest()
    ):
        raise ValueError("A verified combined neighbourhood cohort is required")
    candidates, failures, sources, bindings = [], [], {}, []
    for root in collections:
        c, f, s, b = refresh.load_collection(root)
        if sources.keys() & s.keys():
            raise ValueError("Collections have overlapping capture identities")
        candidates.extend(c)
        failures.extend(f)
        sources.update(s)
        bindings.append(b)
    neighbourhoods = seed_neighbourhoods(
        [r for path in review_queues for r in refresh.records(Path(path).read_bytes())]
    )
    names = set(
        pq.read_table(registry, columns=["building"]).column("building").to_pylist()
    )
    counts = {}
    for crawl in granular:
        for building, n in cohort.floor_counts(Path(crawl)).items():
            counts[building] = min(n, counts.get(building, n))
    rows, evidence, excluded, summary, dropped = assemble(
        refresh.records(observations),
        candidates,
        failures,
        sources,
        neighbourhoods,
        names,
        counts,
        as_of=as_of,
        max_age_days=max_age_days,
    )
    modules = (bathroom_projection, fit_robust_analysis, refresh, cohort)
    paths = [Path(__file__), *(Path(m.__file__) for m in modules)]
    files = {
        "observations.jsonl": "".join(canonical(r) + "\n" for r in rows),
        "current-source-evidence.jsonl": "".join(canonical(r) + "\n" for r in evidence),
        "current-excluded.jsonl": "".join(canonical(r) + "\n" for r in excluded),
        "refresh-failures.jsonl": "".join(canonical(r) + "\n" for r in failures),
        "summary.json": canonical(summary) + "\n",
        **{p.name: p.read_text() for p in paths},
    }
    return publish_bundle(
        output,
        files,
        {
            "version": VERSION,
            "as_of": instant(as_of).isoformat(),
            "parent": str(parent),
            "parent_manifest_sha256": digest(parent / "complete.json"),
            "collections": bindings,
            "review_queues": {str(p): digest(Path(p)) for p in review_queues},
            "registry": {"path": str(registry), "sha256": digest(Path(registry))},
            "granular": {str(g): digest(Path(g) / "complete.json") for g in granular},
            "max_age_days": float(max_age_days),
            "summary": summary,
            "dropped_current_audit_ids": dropped,
            "implementation_sha256": {p.name: digest(p) for p in paths},
            "policy": "Historical rows unchanged; earlier current captures replaced by the new month's "
            "ACTIVE captures. No backward filling, identity merges, model fit or promotion.",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument(
        "--collection", dest="collections", type=Path, action="append", required=True
    )
    parser.add_argument(
        "--review-queue",
        dest="review_queues",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--granular", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--max-age-days", type=float, default=1)
    print(canonical(run(**vars(parser.parse_args()))["summary"]))
