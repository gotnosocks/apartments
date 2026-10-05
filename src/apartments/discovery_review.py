"""Publish the detail-review queue for a bounded rental discovery report; no network calls.

Generalizes the frozen September 18 Chelsea review script
(data/model/chelsea-current-discovery-pass-review-20260918/publish_discovery_review.py)
to any discovery report and its seeds, with the same summary keys. The queue is the input of
``apartments.discovery_detail_refresh``: one row per in-scope advertisement, with
every source card occurrence. A reference dataset is optional and only flags
advertisements that already appear in it.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = "bounded-rental-discovery-review-v1"
CURRENT_BASIS = "current_capture_gross_ask"


def _lines(blob):
    return [json.loads(s) for s in blob.decode().split("\n") if s.strip()]


def review(discovery_report, *, reference=None):
    """Return (summary, queue rows, out-of-scope occurrences) for a discovery report."""
    _, blobs = _verified_bundle(
        discovery_report, retain={"run.json", "pages.jsonl", "coverage.json"}
    )
    run = json.loads(blobs["run.json"])
    coverage = json.loads(blobs["coverage.json"])
    pages = _lines(blobs["pages.jsonl"])
    fitted, current = set(), set()
    if reference is not None:
        _, data = _verified_bundle(reference, retain={"observations.jsonl"})
        rows = _lines(data["observations.jsonl"])
        fitted = {r["source_listing_id"] for r in rows}
        current = {
            r["source_listing_id"]
            for r in rows
            if r["analysis_price_basis"] == CURRENT_BASIS
        }
    queue, outside, clocks, keys = defaultdict(list), [], [], set()
    for page in pages:
        clocks.append(page["source_clock"]["capture_started_at"])
        for experiment in (
            page["search_source_reference"].get("experiments") or {}
        ).values():
            if experiment.get("randomization_key"):
                keys.add(experiment["randomization_key"])
        for card in page["cards"]:
            item = {
                "seed": page["seed_path"],
                "page": page["page"],
                "source_url": page["source_url"],
                "source_clock": page["source_clock"],
                "body_sha256": page["body_sha256"],
                "capture_reference": page["capture_reference"],
                "card": card,
            }
            # Reports from rental-search-v2 named this field in_chelsea_scope.
            if card["in_scope"] if "in_scope" in card else card["in_chelsea_scope"]:
                queue[card["source_listing_id"]].append(item)
            else:
                outside.append(item)
    items = []
    for identifier, observations in sorted(queue.items()):
        urls = {o["card"]["canonical_url"] for o in observations}
        if len(urls) != 1:
            raise ValueError(
                "Conflicting advertisement identity requires review: " + identifier
            )
        items.append(
            {
                "source_listing_id": identifier,
                "canonical_unit_url": next(iter(urls)),
                "observed_detail_urls": sorted(
                    {o["card"]["href"] for o in observations}
                ),
                "appears_in_selected_fit": identifier in fitted,
                "appears_in_selected_current_rows": identifier in current,
                "observations": observations,
                "status": "discovered_search_evidence; detail_refresh_and_identity_review_required",
            }
        )
    seeds = {
        key: {
            name: value
            for name, value in part.items()
            if name
            in (
                "pages",
                "displayed_totals",
                "placement_counts",
                "regular_occurrences",
                "regular_unique_ids",
                "pagination_chain_closed",
                "market_census_established",
            )
        }
        | {"repeated_regular_ids": len(part["regular_duplicates"])}
        for key, part in coverage["seeds"].items()
    }
    summary = {
        "version": VERSION,
        "accepted_new_requests": sum(
            a["outcome"]["status"] == "accepted" for a in run["attempts"]
        ),
        "new_request_intents": run["new_request_intents"],
        "reused_provider_submissions": run["reused_provider_submissions"],
        "reserved_requests": run["global_reserved_requests"],
        "ceiling": run["max_requests"],
        "stop_reason": run["stop_reason"],
        "pending_observed_urls": run["pending_observed_urls"],
        "source_clock_range": [min(clocks), max(clocks)] if clocks else None,
        "seeds": seeds,
        "unique_regular_advertisements": len(coverage["regular_union_ids"]),
        "cross_seed_regular_overlap": len(coverage["cross_seed_regular_overlap_ids"]),
        "in_scope_advertisements_all_placements": len(items),
        "in_scope_distinct_canonical_units": len(
            {r["canonical_unit_url"] for r in items}
        ),
        "out_of_scope_occurrences": len(outside),
        "out_of_scope_placements": dict(
            Counter(o["card"]["placement"] for o in outside)
        ),
        "out_of_scope_areas": dict(
            Counter(o["card"]["source_fields"]["areaName"] for o in outside)
        ),
        "advertisements_already_in_selected_fit": len(set(queue) & fitted),
        "selected_current_advertisements_rediscovered": sorted(set(queue) & current),
        "selected_current_advertisements_not_seen": sorted(current - set(queue)),
        "unique_page_experiment_randomization_keys": len(keys),
        "identity_conflicts": len(coverage["listing_identity_conflicts"]),
        "complete_inventory": False,
        "interpretation": "Visited search evidence only. Closed pagination, displayed counts and "
        "request success do not establish unique inventory coverage. Different page "
        "experiment identifiers are observed; their causal role in duplicate organic "
        "ordering has not been tested. Search cards are not detail-verified current "
        "analytical observations.",
    }
    return summary, items, outside


def publish(discovery_report, output, *, reference=None):
    summary, items, outside = review(discovery_report, reference=reference)
    metadata = {
        "version": VERSION,
        "discovery_report_manifest_sha256": digest(
            Path(discovery_report) / "complete.json"
        ),
    }
    if reference is not None:
        metadata["reference_source_manifest_sha256"] = digest(
            Path(reference) / "complete.json"
        )
    publish_bundle(
        output,
        {
            "review.json": canonical(summary) + "\n",
            "detail-review-queue.jsonl": "".join(canonical(i) + "\n" for i in items),
            "out-of-scope.jsonl": "".join(canonical(o) + "\n" for o in outside),
        },
        metadata,
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--discovery-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--reference", type=Path, help="verified dataset bundle with observations.jsonl"
    )
    args = parser.parse_args(argv)
    print(
        canonical(publish(args.discovery_report, args.output, reference=args.reference))
    )


if __name__ == "__main__":
    main()
