"""Source-linked fitted-residual review for iterative model and data diagnosis."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from apartments import robust_pricing, pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = "fitted-residual-review-v1"


def family(term):
    if term.startswith("building:"):
        return "building"
    if term.startswith("unit:"):
        return "unit"
    if term in ("center", "intercept"):
        return "reference"
    if term.startswith("trend:"):
        return "trend"
    if term.startswith("season:"):
        return "season"
    if (
        term == "size_missing"
        or term.endswith(".unknown")
        or term.endswith("=__unknown__")
    ):
        return "missingness"
    if term == "log_size_within_bedrooms":
        return "size"
    if term.startswith("amenity:"):
        return term.split(":", 1)[1].split("=", 1)[0].split(".", 1)[0]
    return "layout"


def residual(model, row):
    predicted = model.predict(row, row["period"])
    fitted = predicted["predicted_rent"]
    asking = float(row["asking_rent"])
    groups = defaultdict(list)
    for term, value in predicted["log_components"].items():
        groups[family(term)].append(value)
    grouped = {key: math.fsum(values) for key, values in sorted(groups.items())}
    log_error = math.log(asking / fitted)
    current = row.get("analysis_price_basis") == "current_capture_gross_ask"
    return {
        "audit_id": row["audit_id"],
        "unit_id": row["unit_id"],
        "building_id": row["building_id"],
        "source_listing_id": row["source_listing_id"],
        "period": row["period"],
        "canonical_unit_url": row.get("canonical_unit_url"),
        "advertisement_url": "https://streeteasy.com/rental/"
        + str(row["source_listing_id"]),
        "capture_ids": row.get("capture_ids") or [row.get("capture_id")],
        "analysis_price_basis": row.get("analysis_price_basis"),
        "current_capture": current,
        "asking_rent": asking,
        "fitted_rent": fitted,
        "asking_minus_fitted": asking - fitted,
        "asking_vs_fitted_percent": 100 * math.expm1(log_error),
        "log_residual": log_error,
        "absolute_log_residual": abs(log_error),
        "log_contributions_by_family": grouped,
        "group_adjustment_percent": 100
        * math.expm1(grouped.get("building", 0) + grouped.get("unit", 0)),
        "residual_type": "in_sample_fitted_diagnostic",
        "current_capture_in_fit": str(row.get("capture_id"))
        in model.artifact["training"].get("current_capture_ids", []),
        "warnings": predicted["warnings"],
    }


def review_queue(residuals, *, top_units=20):
    if not isinstance(top_units, int) or not 1 <= top_units <= 200:
        raise ValueError("Choose 1–200 distinct units per residual tail")
    chosen = {}
    reasons = defaultdict(list)
    # Distinct units per tail prevent one recurring apartment from filling the
    # queue with many dates of essentially the same anomaly.
    for label, reverse in [("positive_residual", True), ("negative_residual", False)]:
        units = set()
        for row in sorted(
            residuals, key=lambda r: (r["log_residual"], r["audit_id"]), reverse=reverse
        ):
            if (label == "positive_residual" and row["log_residual"] <= 0) or (
                label == "negative_residual" and row["log_residual"] >= 0
            ):
                continue
            if row["unit_id"] in units:
                continue
            units.add(row["unit_id"])
            chosen[row["audit_id"]] = row
            reasons[row["audit_id"]].append(label)
            if len(units) >= top_units:
                break
    for row in residuals:
        if row["current_capture"]:
            chosen[row["audit_id"]] = row
            reasons[row["audit_id"]].append("current_capture")
    return [
        {
            **row,
            "selection_reasons": reasons[key],
            "review_status": "unreviewed",
            "review_question": "Check source price terms, layout/area, amenities, identity and timing before attributing the residual to a missing feature or data error.",
        }
        for key, row in sorted(
            chosen.items(),
            key=lambda item: (-item[1]["absolute_log_residual"], item[0]),
        )
    ]


def summarize(rows):
    if not rows:
        return {"rows": 0}
    return {
        "rows": len(rows),
        "units": len({r["unit_id"] for r in rows}),
        "buildings": len({r["building_id"] for r in rows}),
        "median_absolute_log_residual": statistics.median(
            r["absolute_log_residual"] for r in rows
        ),
        "median_asking_vs_fitted_percent": statistics.median(
            r["asking_vs_fitted_percent"] for r in rows
        ),
        "median_absolute_dollar_residual": statistics.median(
            abs(r["asking_minus_fitted"]) for r in rows
        ),
    }


def markdown(queue, summary):
    lines = [
        "# Fitted-residual review",
        "",
        "These are in-sample diagnostics after fitting current observations. Large residuals are review signals, not automatic corrections or bargain scores.",
        "",
        f"Fit observations: {summary['all']['rows']:,}; current captures: {summary['current']['rows']}.",
        "",
    ]
    for title, predicate in [
        ("Current captures", lambda r: r["current_capture"]),
        (
            "Large positive residuals",
            lambda r: "positive_residual" in r["selection_reasons"],
        ),
        (
            "Large negative residuals",
            lambda r: "negative_residual" in r["selection_reasons"],
        ),
    ]:
        lines.extend(
            [
                "## " + title,
                "",
                "| Advertisement | Month | Ask | Fitted | Ask − fitted | Difference |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in sorted(
            filter(predicate, queue), key=lambda r: -r["absolute_log_residual"]
        ):
            lines.append(
                f"| [{row['source_listing_id']}]({row['advertisement_url']}) | {row['period'][:7]} | ${row['asking_rent']:,.0f} | ${row['fitted_rent']:,.0f} | ${row['asking_minus_fitted']:+,.0f} | {row['asking_vs_fitted_percent']:+.1f}% |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "Grouped log contributions sum to log fitted rent. They describe the chosen parameterization; they are not standalone causal premiums. Building/unit offsets can absorb omitted amenities, so inspect their size as well as residuals. The current sample is a bounded refresh, not complete Chelsea coverage. Historical rows use initial advertisement asks; current rows use capture-time asks.",
            "",
            "Inspect the immutable source and matched dates, record the finding, then apply a supported correction or test a recurring omitted feature. Preserve unresolved cases; never change raw data merely to shrink a residual.",
            "",
        ]
    )
    return "\n".join(lines)


def run(model_bundle, dataset, output, *, top_units=20):
    model = robust_pricing.RobustPricingModel.load(model_bundle)
    manifest, files = _verified_bundle(dataset, retain={"observations.jsonl"})
    if (
        manifest.get("dataset_version") != "historical-plus-current-capture-analysis-v1"
        or manifest != model.artifact["training"]["source_manifest"]
    ):
        raise ValueError(
            "Residuals require the exact verified dataset used for this analysis fit"
        )
    source = [
        json.loads(s)
        for s in files["observations.jsonl"].decode().splitlines()
        if s.strip()
    ]
    results = [residual(model, row) for row in source]
    queue = review_queue(results, top_units=top_units)
    by_id = {row["audit_id"]: row for row in source}
    for row in queue:
        original = by_id[row["audit_id"]]
        row["source_record"] = original
        row["log_components"] = model.predict(original, original["period"])[
            "log_components"
        ]
    summary = {
        "version": VERSION,
        "all": summarize(results),
        "current": summarize([r for r in results if r["current_capture"]]),
        "review_rows": len(queue),
        "selection_counts": dict(
            Counter(reason for r in queue for reason in r["selection_reasons"])
        ),
        "top_units_per_tail": top_units,
        "review_state": "Unreviewed queue; no diagnoses or corrections inferred from residual magnitude.",
        "limitations": model.artifact["limitations"],
    }
    encoder = model.encoder
    support = {
        "core_layout": model.artifact["training"].get("layout_support", {}),
        "amenity_numeric": encoder["amenity_numeric"],
        "amenity_category_counts": encoder["amenity_category_counts"],
        "interpretation": "Training support and missingness, not evidence that every feature effect is separately identified.",
    }
    return publish_bundle(
        output,
        {
            "residuals.jsonl": "".join(canonical(r) + "\n" for r in results),
            "review-queue.jsonl": "".join(canonical(r) + "\n" for r in queue),
            "summary.json": canonical(summary) + "\n",
            "factor-support.json": canonical(support) + "\n",
            "report.md": markdown(queue, summary),
        },
        {
            "version": VERSION,
            "model_manifest": model.manifest,
            "dataset_manifest": manifest,
            "top_units_per_tail": top_units,
            "implementation_sha256": digest(__file__),
            "runtime_sha256": digest(robust_pricing.__file__),
            "pricing_features_sha256": digest(pricing.__file__),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-units", type=int, default=20)
    args = parser.parse_args()
    print(
        canonical(run(args.model, args.dataset, args.output, top_units=args.top_units))
    )
