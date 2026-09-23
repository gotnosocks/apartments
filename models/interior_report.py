"""Report matched interior experiments without promoting exploratory claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import interior_model, minimal_rent_model as baseline


def run(experiment, dataset, parent_residuals, output):
    root = Path(experiment)
    sm, sf = _verified_bundle(root / "summary", retain={"results.json"})
    pm, pf = _verified_bundle(root / "protocol", retain={"protocol.json"})
    protocol = json.loads(pf["protocol.json"])
    if sm["protocol_sha256"] != pm["protocol_sha256"]:
        raise ValueError("Summary/protocol mismatch")
    summaries = json.loads(sf["results.json"])
    dm, df = _verified_bundle(dataset, retain={"observations.jsonl"})
    if dm != protocol["dataset_manifest"]:
        raise ValueError("Projected dataset differs from experiment")
    inputs = {
        r["audit_id"]: r
        for r in (
            json.loads(s) for s in df["observations.jsonl"].decode().split("\n") if s
        )
    }
    rm, rf = _verified_bundle(parent_residuals, retain={"residuals.jsonl"})
    if (
        rm["dataset_manifest"]
        != protocol["dataset_manifest"]["parent_dataset_manifest"]
    ):
        raise ValueError("Parent residuals do not bind the matched cohort")
    parent = {
        r["audit_id"]: r
        for r in (
            json.loads(s) for s in rf["residuals.jsonl"].decode().split("\n") if s
        )
    }
    cm, cf = _verified_bundle(
        root / "standard/comparison", retain={"fitted-values.jsonl"}
    )
    fm, ff = _verified_bundle(root / "standard/values", retain={"model.json"})
    if any(m["protocol_sha256"] != sm["protocol_sha256"] for m in (cm, fm)):
        raise ValueError("Fit/comparison protocol mismatch")
    rows = [json.loads(s) for s in cf["fitted-values.jsonl"].decode().split("\n") if s]
    if set(parent) != {r["audit_id"] for r in rows} or len(rows) != len(parent):
        raise ValueError("Comparison membership mismatch")
    parity = max(
        abs(r["baseline_fitted_rent"] - parent[r["audit_id"]]["fitted_rent"])
        for r in rows
    )
    # Different sparse assembly orders can cause tiny solver stopping differences.
    if parity > 0.02:
        raise ValueError("Experimental baseline materially differs from parent")
    enriched = []
    for r in rows:
        enriched.append(
            {
                **r,
                "values_minus_reporting_dollars": r["values_fitted_rent"]
                - r["reporting_fitted_rent"],
                "baseline_residual_dollars": r["asking_rent"]
                - r["baseline_fitted_rent"],
                "reporting_residual_dollars": r["asking_rent"]
                - r["reporting_fitted_rent"],
                "values_residual_dollars": r["asking_rent"] - r["values_fitted_rent"],
            }
        )
    changed = []
    seen = set()
    for r in sorted(
        enriched,
        key=lambda r: (-abs(r["values_minus_reporting_dollars"]), r["audit_id"]),
    ):
        if r["unit_id"] in seen:
            continue
        seen.add(r["unit_id"])
        changed.append(r)
        if len(changed) == 20:
            break
    current = [
        r for r in enriched if r["analysis_price_basis"] == "current_capture_gross_ask"
    ]
    # Attach exact interior log terms for the selected diagnostics using the
    # original source rows retained in the parent residual records.
    fitted = interior_model.load_saved(json.loads(ff["model.json"]))
    selected = {r["audit_id"]: r for r in changed + current}
    source_rows = []
    for r in selected.values():
        source = inputs[r["audit_id"]]
        source_rows.append({**source, **{k: r[k] for k in interior_model.FIELDS}})
    frame = pd.DataFrame(source_rows)
    frame["period"] = pd.to_datetime(frame.period)
    enc = fitted["encoder"]
    matrix = enc.matrix(frame)
    a, b = enc.offsets["interior"]
    terms = matrix[:, a:b].toarray() * fitted["beta"][a:b]
    for r, values in zip(selected.values(), terms):
        r["interior_log_contributions"] = dict(
            zip(enc.interior_features, values.tolist())
        )
        r["interpretation"] = (
            "Diagnostic in-sample residual; reported claims and group effects enter the fit. Direct terms are not the whole refit change."
        )
    stability = {
        field: [] for field in ("advertised_ceiling_feet", "advertised_levels")
    }
    for summary in summaries:
        for contrast in summary["results"]["values"]["contrasts"]:
            stability[contrast["field"]].append(
                {
                    "settings": summary["settings"],
                    "rent_percent_change": contrast["rent_percent_change"],
                }
            )
    support = protocol["dataset_manifest"]["support"]
    lines = [
        "# Advertised interior features: matched descriptive experiment",
        "",
        f"All variants fit the same {len(rows):,} observations, including {len(current)} current captures.",
        "The baseline, reporting-only and value models share the same existing amenities, price targets and building/unit identities.",
        "",
        "| Group shrinkage | Baseline log RMSE | Reporting log RMSE | Values log RMSE | Ceiling foot contrast | Triplex/duplex contrast |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        results = summary["results"]
        contrasts = results["values"]["contrasts"]
        lines.append(
            f"| {summary['settings']} | "
            + " | ".join(
                f"{results[v]['metrics']['log_rmse']:.6f}"
                for v in ("baseline", "reporting", "values")
            )
            + " | "
            + " | ".join(f"{c['rent_percent_change']:+.3f}%" for c in contrasts)
            + " |"
        )
    standard = next(s for s in summaries if s["settings"] == "standard")
    comparison = standard["comparisons"]["values_minus_reporting"]
    lines += [
        "",
        f"Adding known values beyond reporting changes fitted rent by a median absolute ${comparison['median_absolute_fitted_change_dollars']:.2f}; the largest change is ${comparison['maximum_absolute_fitted_change_dollars']:,.2f}.",
        "These are joint ceiling/level effects after refitting, not isolated feature ablations. In-sample fit improvements alone do not establish reliable premiums.",
        "",
        "## Evidence and interpretation",
        "",
        "| Advertised claim | Known rows | Units | Buildings | Buildings with known-value variation |",
        "|---|---:|---:|---:|---:|",
    ]
    for field, v in support.items():
        lines.append(
            f"| {field} | {v['known_rows']} | {v['known_units']} | {v['known_buildings']} | {v['buildings_with_known_value_variation']} |"
        )
    lines += [
        "",
        "Ceiling height means an unambiguous advertised height somewhere in the home; it can be room-specific. It is not an independently measured or uniform height.",
        "Levels have one single-level, 822 duplex and 51 triplex rows. Only eight buildings and one unit have known level variation. The estimated slope primarily describes triplex versus duplex advertising; it does not support a general single-level-to-duplex premium.",
        "Floor-through and skylight are positive-or-unknown only. Their magnitude columns are zero; reporting terms cannot separate physical presence from marketing and extraction patterns.",
        "Strict scope/renovation guards produce nonrandom unknowns. Current advertisement 5153890, the motivating duplex, remains unknown in this projection because its description says renovation is in progress. This experiment does not resolve that apartment’s omitted-feature question.",
        "The source review still found price-basis caveats in ads 3089130 and 2288458. Cohort cleanup and independent source validation remain incomplete. Historical feature descriptions were often collected later than price events.",
        "",
        "## Current captured listings",
        "",
        "| Advertisement | Ask | Baseline fit | Reporting fit | Values fit | Ask minus values fit |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in current:
        lines.append(
            f"| {r['source_listing_id']} | ${r['asking_rent']:,.0f} | ${r['baseline_fitted_rent']:,.0f} | ${r['reporting_fitted_rent']:,.0f} | ${r['values_fitted_rent']:,.0f} | ${r['values_residual_dollars']:+,.0f} |"
        )
    lines += [
        "",
        f"The recomputed baseline matches the prior scientific fit within ${parity:.6f} across all {len(rows):,} rows. All saved fits enforce convergence and exact coefficient-reload parity.",
        "This experiment is retained as research, without replacing the current analysis model or publishing these contrasts as established amenity values.",
    ]
    return publish_bundle(
        output,
        {
            "report.md": "\n".join(lines) + "\n",
            "contrast-stability.json": canonical(stability) + "\n",
            "changed-queue.jsonl": "".join(canonical(r) + "\n" for r in changed),
            "current-comparison.jsonl": "".join(canonical(r) + "\n" for r in current),
            "baseline-parity.json": canonical(
                {"rows": len(rows), "maximum_absolute_dollars": parity}
            )
            + "\n",
            "report.py": Path(__file__).read_text(),
        },
        {
            "version": "advertised-interior-experiment-report-v1",
            "summary_manifest": sm,
            "parent_residual_manifest": rm,
            "protocol_sha256": pm["protocol_sha256"],
            "implementation_sha256": digest(__file__),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("experiment", "dataset", "parent-residuals", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    run(args.experiment, args.dataset, args.parent_residuals, args.output)
