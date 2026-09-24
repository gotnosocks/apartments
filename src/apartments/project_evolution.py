"""Metric ledger for the project-evolution dashboard.

The dashboard reports source scale, transformation quality, and model health
side-by-side.  A metric observation is never just a number: it carries its
cohort/version, comparability key, status, caveat, and evidence path.  This is
important because a smaller analytical cohort can be the result of a successful
source review, not a regression.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable


COLLECTION = "Data collection"
TRANSFORMATION = "Data transformation"
MODELING = "Modeling"
CATEGORIES = (COLLECTION, TRANSFORMATION, MODELING)
STATUSES = ("complete", "selected", "research", "active", "warning", "interrupted")


# Definitions are intentionally explicit.  The UI uses these to explain units,
# direction and limitations instead of coloring every increase green.
METRIC_DEFINITIONS: dict[str, dict[str, str]] = {
    # Collection: scale, request accounting, and missing coverage.
    "collection.building_roots": {"stage": COLLECTION, "label": "Distinct building roots", "unit": "buildings", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Source roots, not a census of physical buildings."},
    "collection.detail_url_successes": {"stage": COLLECTION, "label": "Successful detail URL captures", "unit": "URLs", "format": "integer", "direction": "context", "importance": "primary", "caveat": "URLs and listing episodes are not physical-unit counts."},
    "collection.detail_url_404": {"stage": COLLECTION, "label": "Historical detail URL 404 outcomes", "unit": "responses", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Explicit source gaps; not blindly retried."},
    "collection.inventory_rows": {"stage": COLLECTION, "label": "Saved inventory rows", "unit": "rows", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Includes rental/sale inventory records and source placeholders."},
    "collection.new_requests": {"stage": COLLECTION, "label": "New provider submissions", "unit": "requests", "format": "integer", "direction": "context", "importance": "primary", "caveat": "A request budget, not a coverage guarantee."},
    "collection.reused_captures": {"stage": COLLECTION, "label": "Reused archived captures", "unit": "captures", "format": "integer", "direction": "higher", "importance": "primary", "caveat": "Offline reuse avoids paid requests but does not add fresh evidence."},
    "collection.discovery_ads": {"stage": COLLECTION, "label": "Distinct discovery advertisements", "unit": "advertisements", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Search candidates, not distinct physical units or complete inventory."},
    "collection.eligible_candidates": {"stage": COLLECTION, "label": "Candidates passing existing eligibility", "unit": "advertisements", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Eligibility is a policy result; it is not proof of current availability."},
    "collection.discovery_retries": {"stage": COLLECTION, "label": "Discovery retries", "unit": "requests", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Zero retries is good for bounded accounting, but can leave failures unresolved."},
    "collection.unresolved_identity_candidates": {"stage": COLLECTION, "label": "Unresolved unit identities after detail collection", "unit": "candidates", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Unresolved identities remain separate rather than being auto-merged."},
    "collection.west_village_captures": {"stage": COLLECTION, "label": "West Village archive captures", "unit": "captures", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Two same-day audit snapshots of the active canonical-only run."},
    "collection.west_village_pending": {"stage": COLLECTION, "label": "West Village pending scoped URLs", "unit": "URLs", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Pending queue size is meaningful only with its run generation and scope."},
    "collection.west_village_excluded": {"stage": COLLECTION, "label": "West Village excluded scoped URLs", "unit": "URLs", "format": "integer", "direction": "context", "importance": "risk", "caveat": "Historical exclusions are reinterpretable evidence, not permanent rejections."},
    "collection.west_village_reused_ads": {"stage": COLLECTION, "label": "Verified exact-advertisement reuses", "unit": "reuses", "format": "integer", "direction": "higher", "importance": "primary", "caveat": "Read-only reuse of an exact matching saved capture."},
    # Transformation: source reconciliation, completeness, and review accounting.
    "transform.listing_observations": {"stage": TRANSFORMATION, "label": "Retained listing observations", "unit": "observations", "format": "integer", "direction": "context", "importance": "primary", "caveat": "A source projection count; later revisions can intentionally retain fewer rows."},
    "transform.history_mentions": {"stage": TRANSFORMATION, "label": "Parsed history mentions", "unit": "mentions", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Repeated source evidence is retained, not deduplicated into rents."},
    "transform.snapshots": {"stage": TRANSFORMATION, "label": "Source snapshots", "unit": "snapshots", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Capture records, including repeated and failed outcomes where applicable."},
    "transform.rental_label_pairs": {"stage": TRANSFORMATION, "label": "Rental building/unit-label pairs", "unit": "pairs", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Source labels, not resolved physical apartments."},
    "transform.sqft_missing_pct": {"stage": TRANSFORMATION, "label": "Square-footage missingness", "unit": "% of rental observations", "format": "percent", "direction": "lower", "importance": "risk", "caveat": "Missing is preserved as unknown; it is not imputed as zero."},
    "transform.feature_metadata_missing_pct": {"stage": TRANSFORMATION, "label": "Feature metadata missingness", "unit": "% of rental observations", "format": "percent", "direction": "lower", "importance": "risk", "caveat": "Feature metadata absence does not establish feature absence."},
    "transform.amenity_metadata_missing_pct": {"stage": TRANSFORMATION, "label": "Amenity metadata missingness", "unit": "% of rental observations", "format": "percent", "direction": "lower", "importance": "risk", "caveat": "Structured source coverage, not accuracy."},
    "transform.conflicting_attribute_groups": {"stage": TRANSFORMATION, "label": "Conflicting building/unit attribute groups", "unit": "groups", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Conflicts can be source errors, identity ambiguity, or real change; none is silently resolved."},
    "transform.nonpositive_price_mentions": {"stage": TRANSFORMATION, "label": "Nonpositive price mentions retained for treatment", "unit": "mentions", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Retained for explicit model-stage handling rather than dropped invisibly."},
    "transform.descriptions_recovered": {"stage": TRANSFORMATION, "label": "Descriptions recovered from archived bodies", "unit": "captures", "format": "integer", "direction": "higher", "importance": "primary", "caveat": "Offline reinterpretation, not new collection or proof of historical effective date."},
    "transform.description_recovery_quarantine": {"stage": TRANSFORMATION, "label": "Description recovery quarantines", "unit": "captures", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "A zero means this completed run found no failed recovery candidates."},
    "transform.recovered_advertisements": {"stage": TRANSFORMATION, "label": "Advertisements covered by recovered descriptions", "unit": "advertisements", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Coverage of recovered text, not a correctness estimate."},
    "transform.recovered_cohort_ads": {"stage": TRANSFORMATION, "label": "Recovered historical cohort advertisements", "unit": "advertisements", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Own-advertisement reconstruction with retrospective attribute timing limits."},
    "transform.recovered_cohort_units": {"stage": TRANSFORMATION, "label": "Recovered historical cohort units", "unit": "units", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Source-declared/canonical units, not independently surveyed apartments."},
    "transform.recovered_cohort_buildings": {"stage": TRANSFORMATION, "label": "Recovered historical cohort buildings", "unit": "buildings", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Building identities in the selected source cohort."},
    "transform.refresh_current_rows": {"stage": TRANSFORMATION, "label": "Current rows in refreshed analytical cohort", "unit": "rows", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Capture-time current observations, not guaranteed live availability."},
    "transform.reviewed_floor_masks": {"stage": TRANSFORMATION, "label": "Reviewed ambiguous floor claims masked", "unit": "claims", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Masking unsupported claims improves source meaning but reduces known support."},
    "transform.location_scope_exclusions": {"stage": TRANSFORMATION, "label": "Exact advertisements retained in location quarantine", "unit": "advertisements", "format": "integer", "direction": "context", "importance": "risk", "caveat": "Explicit scope decisions; no replacement address or price is inferred."},
    "transform.floor_coverage_pct": {"stage": TRANSFORMATION, "label": "Known listed-floor coverage", "unit": "% of fitted rows", "format": "percent", "direction": "higher", "importance": "primary", "caveat": "Listed floors are source proxies, not verified physical elevation."},
    "transform.known_floor_observations": {"stage": TRANSFORMATION, "label": "Known listed-floor observations", "unit": "observations", "format": "integer", "direction": "higher", "importance": "primary", "caveat": "Remaining unknown, conflicting and unsupported labels stay explicit."},
    "transform.direct_floor_additions": {"stage": TRANSFORMATION, "label": "New manually reviewed direct-floor additions", "unit": "observations", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Research-only additions awaiting matched source/model comparison."},
    "transform.direct_floor_known_observations": {"stage": TRANSFORMATION, "label": "Known floors after direct-floor revision", "unit": "observations", "format": "integer", "direction": "higher", "importance": "primary", "caveat": "The projection is reversible and not selected for the main fit yet."},
    # Modeling: cohort, inference health, residuals, validation, uncertainty, and cost.
    "model.baseline_active_observations": {"stage": MODELING, "label": "Baseline active observations", "unit": "observations", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Early descriptive pilot; no holdout accuracy claim."},
    "model.baseline_units": {"stage": MODELING, "label": "Baseline modeled units", "unit": "units", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Early source-page identities, before canonical-unit expansion."},
    "model.baseline_buildings": {"stage": MODELING, "label": "Baseline building labels", "unit": "buildings", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Early descriptive pilot coverage."},
    "model.accepted_rows": {"stage": MODELING, "label": "Accepted Bayesian fit rows", "unit": "rows", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Earlier accepted cohort; not automatically comparable to later source revisions."},
    "model.selected_rows": {"stage": MODELING, "label": "Selected Bayesian fit rows", "unit": "rows", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Current main selection, bound by config/main-analysis.json."},
    "model.selected_units": {"stage": MODELING, "label": "Selected fit units", "unit": "units", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Selected analytical cohort."},
    "model.selected_buildings": {"stage": MODELING, "label": "Selected fit buildings", "unit": "buildings", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Selected analytical cohort."},
    "model.selected_current_rows": {"stage": MODELING, "label": "Selected current observations", "unit": "rows", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Capture-time current status does not guarantee present availability."},
    "model.amenity_ablation_fits": {"stage": MODELING, "label": "Completed amenity ablation fits", "unit": "fits", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Development comparisons, not causal validation."},
    "model.unseen_building_baseline_mape": {"stage": MODELING, "label": "Unseen-building error, baseline", "unit": "% median absolute error", "format": "percent", "direction": "lower", "importance": "context", "caveat": "Historical development evaluation, secondary to factor/residual analysis."},
    "model.unseen_building_amenity_mape": {"stage": MODELING, "label": "Unseen-building error, amenities", "unit": "% median absolute error", "format": "percent", "direction": "lower", "importance": "context", "caveat": "Matched development comparison, not a causal amenity premium."},
    "model.monthly_validation_rows": {"stage": MODELING, "label": "Monthly validation rows", "unit": "held-out rows", "format": "integer", "direction": "context", "importance": "context", "caveat": "Retrospective asking-rent evaluation with reused development data."},
    "model.monthly_validation_fits": {"stage": MODELING, "label": "Converged monthly validation fits", "unit": "fits", "format": "integer", "direction": "context", "importance": "context", "caveat": "All fits in the reported rolling experiment."},
    "model.annual_validation_mape": {"stage": MODELING, "label": "Frozen annual-model error", "unit": "% median absolute error", "format": "percent", "direction": "lower", "importance": "context", "caveat": "Comparison baseline for monthly freshness."},
    "model.monthly_validation_mape": {"stage": MODELING, "label": "Monthly-refit error", "unit": "% median absolute error", "format": "percent", "direction": "lower", "importance": "context", "caveat": "Retrospective validation, not the primary factor-analysis objective."},
    "model.new_building_interval_coverage": {"stage": MODELING, "label": "New-building measured 95% interval coverage", "unit": "% of banded rows", "format": "percent", "direction": "higher", "importance": "risk", "caveat": "Failed calibration target; pooled fallback bands are not promoted."},
    "model.chains": {"stage": MODELING, "label": "Posterior chains", "unit": "chains", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Sampling protocol setting."},
    "model.warmup_draws": {"stage": MODELING, "label": "Warmup iterations", "unit": "draws", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Per-chain production protocol setting."},
    "model.retained_draws": {"stage": MODELING, "label": "Retained posterior draws", "unit": "draws", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Draw count matters alongside convergence and source checks."},
    "model.parameters": {"stage": MODELING, "label": "Unconstrained parameters", "unit": "parameters", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Includes building/unit/group structure; larger is not automatically better."},
    "model.max_rhat": {"stage": MODELING, "label": "Maximum parameter R-hat", "unit": "R-hat", "format": "decimal", "direction": "lower", "importance": "primary", "caveat": "Convergence diagnostic; target is near 1, not zero."},
    "model.min_bulk_ess": {"stage": MODELING, "label": "Minimum bulk ESS", "unit": "effective draws", "format": "decimal", "direction": "higher", "importance": "primary", "caveat": "Worst named parameter, not the median ESS."},
    "model.min_tail_ess": {"stage": MODELING, "label": "Minimum tail ESS", "unit": "effective draws", "format": "decimal", "direction": "higher", "importance": "primary", "caveat": "Important for interval endpoints."},
    "model.min_bfmi": {"stage": MODELING, "label": "Minimum BFMI", "unit": "diagnostic", "format": "decimal", "direction": "higher", "importance": "primary", "caveat": "Worst chain energy diagnostic."},
    "model.divergences": {"stage": MODELING, "label": "Divergences", "unit": "transitions", "format": "integer", "direction": "lower", "importance": "risk", "caveat": "Zero is desirable, but does not prove source or identification quality."},
    "model.residual_median_abs_log": {"stage": MODELING, "label": "Median absolute log residual", "unit": "log rent", "format": "decimal", "direction": "lower", "importance": "context", "caveat": "In-sample review signal, not independent prediction error."},
    "model.current_fit_median_move_dollars": {"stage": MODELING, "label": "Median current fitted-rent movement between revisions", "unit": "$ per month", "format": "currency", "direction": "context", "importance": "context", "caveat": "Matched source/model revision movement, not model accuracy."},
    "model.current_fit_max_move_dollars": {"stage": MODELING, "label": "Maximum current fitted-rent movement between revisions", "unit": "$ per month", "format": "currency", "direction": "context", "importance": "risk", "caveat": "Largest movement among the same current observations."},
    "model.current_residual_review_cases": {"stage": MODELING, "label": "Current residual cases with source review", "unit": "observations", "format": "integer", "direction": "context", "importance": "primary", "caveat": "Review queue size, not number of confirmed errors."},
    "model.cpu_retained_seconds_low": {"stage": MODELING, "label": "CPU retained sampling time, lower bound", "unit": "seconds", "format": "decimal", "direction": "lower", "importance": "context", "caveat": "One production-length benchmark; excludes some compilation/reporting costs."},
    "model.cpu_retained_seconds_high": {"stage": MODELING, "label": "CPU retained sampling time, upper bound", "unit": "seconds", "format": "decimal", "direction": "lower", "importance": "context", "caveat": "One production-length benchmark; timing range, not a confidence interval."},
    "model.gpu_compute_transfer_seconds": {"stage": MODELING, "label": "GPU retained compute plus transfer time", "unit": "seconds", "format": "decimal", "direction": "lower", "importance": "context", "caveat": "Includes first-loop JIT in the reported comparison."},
    "model.direct_floor_trace_gb": {"stage": MODELING, "label": "Interrupted direct-floor raw trace", "unit": "GB", "format": "decimal", "direction": "context", "importance": "risk", "caveat": "Sampling trace exists; finalization stalled and was stopped for separate recovery."},
}


@dataclass(frozen=True)
class MetricObservation:
    metric_id: str
    day: date
    value: float
    version: str
    comparability_key: str
    status: str
    source: tuple[str, ...]
    note: str = ""
    sequence: int = 0
    numerator: float | None = None
    denominator: float | None = None
    lower: float | None = None
    upper: float | None = None

    def as_record(self) -> dict[str, Any]:
        result = asdict(self)
        result["day"] = self.day.isoformat()
        result["source"] = list(self.source)
        return result


def _observation(
    metric_id: str,
    day: tuple[int, int, int],
    value: float,
    version: str,
    comparability_key: str,
    status: str,
    source: str | tuple[str, ...],
    *,
    note: str = "",
    sequence: int = 0,
    numerator: float | None = None,
    denominator: float | None = None,
    lower: float | None = None,
    upper: float | None = None,
) -> MetricObservation:
    if metric_id not in METRIC_DEFINITIONS:
        raise KeyError(metric_id)
    if status not in STATUSES:
        raise ValueError(status)
    sources = (source,) if isinstance(source, str) else source
    return MetricObservation(
        metric_id=metric_id,
        day=date(*day),
        value=float(value),
        version=version,
        comparability_key=comparability_key,
        status=status,
        source=tuple(sources),
        note=note,
        sequence=sequence,
        numerator=numerator,
        denominator=denominator,
        lower=lower,
        upper=upper,
    )


COMPLETION = "docs/data/chelsea-completion-2026-09-12.md"
GRANULAR = "docs/data/chelsea-granular-quality-2026-09-16.md"
DISCOVERY = "docs/analysis/chelsea-rental-discovery-2026-09-18.md"
ORCHESTRATOR = "docs/data/rental-discovery-orchestrator.md"
RECOVERY = "docs/analysis/chelsea-recovery-ablation-2026-09-18.md"
DESCRIPTION = "docs/data/description-recovery.md"
REFRESH = "docs/data/current-cohort-refresh.md"
CURRENT_ANALYSIS = "docs/model/current-analysis.md"
BAYESIAN = "docs/analysis/chelsea-bayesian-bathrooms-2026-09-18.md"
AMENITY = "docs/analysis/chelsea-amenities-2026-09-18.md"
FLOOR = "docs/analysis/chelsea-expanded-spline-floor-results-2026-09-19.md"
SAMPLER = "docs/analysis/chelsea-sampler-reassessment-2026-09-18.md"
CORRECTED = "docs/analysis/chelsea-corrected-main-fit-2026-09-19.md"
MONTHLY = "docs/analysis/chelsea-monthly-validation-2026-09-18.md"
TRANSFER = "docs/model/building-transfer-validation.md"
WEST = "docs/data/west-village-collection.md"
DIRECT_FLOOR = "docs/analysis/chelsea-direct-floor-offers-2026-09-20.md"
MODAL = "docs/analysis/modal-transfer-footprint-2026-09-19.md"


OBSERVATIONS: tuple[MetricObservation, ...] = (
    # Collection scale and gaps.
    _observation("collection.building_roots", (2026, 9, 12), 1311, "chelsea-backfill-20260912", "chelsea-archive", "complete", COMPLETION),
    _observation("collection.building_roots", (2026, 9, 16), 1311, "chelsea-granular-20260916", "chelsea-archive", "complete", GRANULAR),
    _observation("collection.detail_url_successes", (2026, 9, 12), 121109, "chelsea-backfill-20260912", "chelsea-archive", "complete", COMPLETION, note="35 additional redirect aliases are reported separately."),
    _observation("collection.detail_url_404", (2026, 9, 12), 966, "chelsea-backfill-20260912", "chelsea-archive", "warning", COMPLETION),
    _observation("collection.inventory_rows", (2026, 9, 16), 35071, "chelsea-granular-20260916", "chelsea-archive", "complete", GRANULAR),
    _observation("collection.new_requests", (2026, 9, 18), 28, "chelsea-rental-discovery-20260918", "chelsea-discovery-pass", "complete", DISCOVERY),
    _observation("collection.reused_captures", (2026, 9, 18), 4, "chelsea-rental-discovery-20260918", "chelsea-discovery-pass", "complete", DISCOVERY),
    _observation("collection.discovery_ads", (2026, 9, 18), 213, "chelsea-rental-discovery-20260918", "chelsea-discovery-pass", "complete", DISCOVERY),
    _observation("collection.eligible_candidates", (2026, 9, 18), 168, "chelsea-discovery-details-20260918", "chelsea-discovery-detail-pass", "complete", (DISCOVERY, "docs/data/discovery-detail-refresh.md")),
    _observation("collection.discovery_retries", (2026, 9, 18), 0, "chelsea-rental-discovery-20260918", "chelsea-discovery-pass", "complete", DISCOVERY),
    _observation("collection.unresolved_identity_candidates", (2026, 9, 18), 9, "chelsea-discovery-details-20260918", "chelsea-discovery-detail-pass", "warning", (DISCOVERY, "docs/data/discovery-detail-refresh.md")),
    _observation("collection.west_village_captures", (2026, 9, 20), 136, "west-village-audit-0008", "west-village-run", "active", WEST, sequence=1),
    _observation("collection.west_village_captures", (2026, 9, 20), 258, "west-village-audit-0109", "west-village-run", "active", WEST, sequence=2),
    _observation("collection.west_village_pending", (2026, 9, 20), 128, "west-village-audit-0008", "west-village-run", "active", WEST, sequence=1),
    _observation("collection.west_village_pending", (2026, 9, 20), 72, "west-village-audit-0109", "west-village-run", "active", WEST, sequence=2),
    _observation("collection.west_village_excluded", (2026, 9, 20), 21, "west-village-audit-0008", "west-village-run", "active", WEST, sequence=1),
    _observation("collection.west_village_excluded", (2026, 9, 20), 21, "west-village-audit-0109", "west-village-run", "active", WEST, sequence=2),
    _observation("collection.west_village_reused_ads", (2026, 9, 20), 20, "west-village-audit-0109", "west-village-run", "active", WEST, sequence=2),
    # Transformation scale and quality.
    _observation("transform.listing_observations", (2026, 9, 16), 121118, "chelsea-granular-20260916", "chelsea-granular", "complete", GRANULAR),
    _observation("transform.history_mentions", (2026, 9, 16), 2938566, "chelsea-granular-20260916", "chelsea-granular", "complete", GRANULAR),
    _observation("transform.snapshots", (2026, 9, 16), 124966, "chelsea-granular-20260916", "chelsea-granular", "complete", GRANULAR),
    _observation("transform.rental_label_pairs", (2026, 9, 16), 25570, "chelsea-granular-20260916", "chelsea-granular", "complete", GRANULAR),
    _observation("transform.sqft_missing_pct", (2026, 9, 16), 66.3, "chelsea-granular-20260916", "chelsea-granular", "warning", GRANULAR),
    _observation("transform.feature_metadata_missing_pct", (2026, 9, 16), 26.9, "chelsea-granular-20260916", "chelsea-granular", "warning", GRANULAR),
    _observation("transform.amenity_metadata_missing_pct", (2026, 9, 16), 6.3, "chelsea-granular-20260916", "chelsea-granular", "warning", GRANULAR),
    _observation("transform.conflicting_attribute_groups", (2026, 9, 16), 5464, "chelsea-granular-20260916", "chelsea-granular", "warning", GRANULAR),
    _observation("transform.nonpositive_price_mentions", (2026, 9, 16), 1274, "chelsea-granular-20260916", "chelsea-granular", "warning", GRANULAR),
    _observation("transform.descriptions_recovered", (2026, 9, 18), 27240, "chelsea-description-recovery-20260918", "description-recovery", "complete", DESCRIPTION, note="Recovered from archived bodies; no new requests."),
    _observation("transform.description_recovery_quarantine", (2026, 9, 18), 0, "chelsea-description-recovery-20260918", "description-recovery", "complete", DESCRIPTION),
    _observation("transform.recovered_advertisements", (2026, 9, 18), 19440, "chelsea-description-recovery-20260918", "description-recovery", "complete", DESCRIPTION),
    _observation("transform.recovered_cohort_ads", (2026, 9, 18), 54105, "chelsea-historical-20260918-v4", "historical-cohort-v4", "complete", RECOVERY),
    _observation("transform.recovered_cohort_units", (2026, 9, 18), 22253, "chelsea-historical-20260918-v4", "historical-cohort-v4", "complete", RECOVERY),
    _observation("transform.recovered_cohort_buildings", (2026, 9, 18), 1140, "chelsea-historical-20260918-v4", "historical-cohort-v4", "complete", RECOVERY),
    _observation("transform.refresh_current_rows", (2026, 9, 18), 172, "chelsea-refreshed-analysis-cohort-20260918", "refreshed-current-cohort", "complete", REFRESH),
    _observation("transform.reviewed_floor_masks", (2026, 9, 19), 17, "chelsea-reviewed-floor-masked-analysis-20260918", "floor-source-revision", "warning", CORRECTED),
    _observation("transform.location_scope_exclusions", (2026, 9, 20), 10, "chelsea-location-scope-analysis-20260920", "location-scope-revision", "research", "docs/analysis/chelsea-location-scope-followup-2026-09-20.md"),
    _observation("transform.floor_coverage_pct", (2026, 9, 19), 56.80, "chelsea-label-floor-analysis-20260919", "floor-source-comparison", "complete", FLOOR, note="Before expanded label-derived floor evidence."),
    _observation("transform.floor_coverage_pct", (2026, 9, 19), 68.36, "chelsea-expanded-label-floor-analysis-20260919", "floor-source-comparison", "selected", FLOOR, note="After expanded label-derived floor evidence.", sequence=1),
    _observation("transform.known_floor_observations", (2026, 9, 19), 35992, "chelsea-expanded-label-floor-analysis-20260919", "floor-source-comparison", "selected", FLOOR),
    _observation("transform.direct_floor_additions", (2026, 9, 20), 24, "chelsea-direct-floor-analysis-20260920", "direct-floor-research", "research", DIRECT_FLOOR),
    _observation("transform.direct_floor_known_observations", (2026, 9, 20), 35989, "chelsea-direct-floor-analysis-20260920", "direct-floor-research", "research", DIRECT_FLOOR, note="Before 24 bounded additions."),
    _observation("transform.direct_floor_known_observations", (2026, 9, 20), 36013, "chelsea-direct-floor-analysis-20260920", "direct-floor-research", "research", DIRECT_FLOOR, note="After 24 bounded additions.", sequence=1),
    # Modeling cohort, validation, and numerical health.
    _observation("model.baseline_active_observations", (2026, 9, 18), 444, "research-baseline-20260918", "legacy-descriptive-baseline", "complete", "docs/analysis/research-baseline-2026-09-18.md"),
    _observation("model.baseline_units", (2026, 9, 18), 223, "research-baseline-20260918", "legacy-descriptive-baseline", "complete", "docs/analysis/research-baseline-2026-09-18.md"),
    _observation("model.baseline_buildings", (2026, 9, 18), 115, "research-baseline-20260918", "legacy-descriptive-baseline", "complete", "docs/analysis/research-baseline-2026-09-18.md"),
    _observation("model.accepted_rows", (2026, 9, 18), 52711, "chelsea-bayesian-bathrooms-long-20260918", "bathroom-main-cohort", "complete", BAYESIAN),
    _observation("model.selected_rows", (2026, 9, 19), 52653, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", CURRENT_ANALYSIS),
    _observation("model.selected_units", (2026, 9, 19), 22155, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", CURRENT_ANALYSIS),
    _observation("model.selected_buildings", (2026, 9, 19), 1129, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", CURRENT_ANALYSIS),
    _observation("model.selected_current_rows", (2026, 9, 19), 172, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", CURRENT_ANALYSIS),
    _observation("model.amenity_ablation_fits", (2026, 9, 18), 42, "chelsea-recovered-amenity-validation-20260918", "amenity-development", "complete", RECOVERY),
    _observation("model.unseen_building_baseline_mape", (2026, 9, 18), 18.26, "chelsea-recovered-amenity-validation-20260918", "amenity-development", "complete", RECOVERY),
    _observation("model.unseen_building_amenity_mape", (2026, 9, 18), 14.04, "chelsea-recovered-amenity-validation-20260918", "amenity-development", "complete", RECOVERY),
    _observation("model.monthly_validation_rows", (2026, 9, 18), 23487, "chelsea-monthly-validation-20260918", "monthly-validation", "complete", MONTHLY),
    _observation("model.monthly_validation_fits", (2026, 9, 18), 72, "chelsea-monthly-validation-20260918", "monthly-validation", "complete", MONTHLY),
    _observation("model.annual_validation_mape", (2026, 9, 18), 9.82, "chelsea-monthly-validation-20260918", "monthly-validation", "complete", MONTHLY),
    _observation("model.monthly_validation_mape", (2026, 9, 18), 7.97, "chelsea-monthly-validation-20260918", "monthly-validation", "complete", MONTHLY),
    _observation("model.new_building_interval_coverage", (2026, 9, 18), 68.39, "chelsea-monthly-validation-20260918", "monthly-validation", "warning", MONTHLY),
    _observation("model.chains", (2026, 9, 19), 4, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.warmup_draws", (2026, 9, 19), 16000, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", SAMPLER),
    _observation("model.retained_draws", (2026, 9, 19), 24000, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.parameters", (2026, 9, 19), 23414, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.max_rhat", (2026, 9, 19), 1.0039819127, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.min_bulk_ess", (2026, 9, 19), 820.6987, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.min_tail_ess", (2026, 9, 19), 1513.2430, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.min_bfmi", (2026, 9, 19), 0.4357401, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.divergences", (2026, 9, 19), 0, "chelsea-bayesian-expanded-spline-floor-disk-20260919", "selected-main", "selected", FLOOR),
    _observation("model.residual_median_abs_log", (2026, 9, 19), 0.0350891, "chelsea-corrected-main-fit-20260919", "corrected-main-comparison", "complete", CORRECTED),
    _observation("model.current_fit_median_move_dollars", (2026, 9, 19), 1.29, "chelsea-corrected-main-fit-20260919", "corrected-main-comparison", "complete", CORRECTED),
    _observation("model.current_fit_max_move_dollars", (2026, 9, 19), 13.21, "chelsea-corrected-main-fit-20260919", "corrected-main-comparison", "warning", CORRECTED),
    _observation("model.current_residual_review_cases", (2026, 9, 19), 8, "chelsea-corrected-main-fit-20260919", "corrected-main-comparison", "complete", CORRECTED),
    _observation("model.cpu_retained_seconds_low", (2026, 9, 19), 600.08, "chelsea-cpu-gpu-sampler-comparison-20260919", "sampler-benchmark", "complete", SAMPLER),
    _observation("model.cpu_retained_seconds_high", (2026, 9, 19), 705.71, "chelsea-cpu-gpu-sampler-comparison-20260919", "sampler-benchmark", "complete", SAMPLER),
    _observation("model.gpu_compute_transfer_seconds", (2026, 9, 19), 1927.94, "chelsea-cpu-gpu-sampler-comparison-20260919", "sampler-benchmark", "complete", SAMPLER),
    _observation("model.direct_floor_trace_gb", (2026, 9, 20), 7.1, "chelsea-bayesian-direct-floor-spline-disk-20260920", "direct-floor-research", "interrupted", (DIRECT_FLOOR, "docs/model/modal.md"), note="Trace finished writing; synchronous finalization stalled and the run was stopped for recovery."),
)


def definitions(stage: str | None = None, importance: str | None = None) -> dict[str, dict[str, str]]:
    """Return metric definitions filtered by stage and/or importance."""

    return {
        key: value
        for key, value in METRIC_DEFINITIONS.items()
        if (stage is None or value["stage"] == stage)
        and (importance is None or value["importance"] == importance)
    }


def observations(
    *,
    stage: str | None = None,
    metric_id: str | None = None,
    include_statuses: Iterable[str] = STATUSES,
) -> list[MetricObservation]:
    """Return observations in stable chronological order."""

    allowed = set(include_statuses)
    selected = [
        item
        for item in OBSERVATIONS
        if item.status in allowed
        and (metric_id is None or item.metric_id == metric_id)
        and (stage is None or METRIC_DEFINITIONS[item.metric_id]["stage"] == stage)
    ]
    return sorted(selected, key=lambda item: (item.day, item.sequence, item.metric_id, item.version))


def latest_observation(metric_id: str, *, include_statuses: Iterable[str] = STATUSES) -> MetricObservation | None:
    values = observations(metric_id=metric_id, include_statuses=include_statuses)
    return values[-1] if values else None


def comparable_change(
    metric_id: str,
    *,
    include_statuses: Iterable[str] = STATUSES,
) -> dict[str, Any]:
    """Compare the latest observation to the prior observation only if keys match."""

    values = observations(metric_id=metric_id, include_statuses=include_statuses)
    if len(values) < 2:
        return {"comparable": False, "reason": "Only one dated observation is recorded."}
    latest = values[-1]
    previous = values[-2]
    if latest.comparability_key != previous.comparability_key:
        return {
            "comparable": False,
            "reason": "The latest and prior values use different source/cohort definitions.",
            "latest": latest,
            "previous": previous,
        }
    delta = latest.value - previous.value
    percent = (delta / previous.value * 100) if previous.value else None
    return {"comparable": True, "latest": latest, "previous": previous, "delta": delta, "percent": percent}


def metric_points(metric_id: str, category: str | None = None) -> list[dict[str, Any]]:
    """Compatibility/helper representation for plotting."""

    return [
        {
            "day": item.day,
            "value": item.value,
            "title": item.version,
            "status": item.status,
            "note": item.note,
            "source": item.source,
            "comparability_key": item.comparability_key,
            "lower": item.lower,
            "upper": item.upper,
        }
        for item in observations(stage=category, metric_id=metric_id)
    ]


def format_value(metric_id: str, value: float | None) -> str:
    if value is None:
        return "—"
    kind = METRIC_DEFINITIONS[metric_id]["format"]
    if kind == "integer":
        return f"{value:,.0f}"
    if kind == "percent":
        return f"{value:,.2f}%"
    if kind == "currency":
        return f"${value:,.2f}"
    if kind == "decimal":
        return f"{value:,.4f}"
    return f"{value:,.2f}"


def current_selection(root: Path) -> dict[str, Any]:
    """Read the selected-model pointer without loading a posterior."""

    path = root / "config" / "main-analysis.json"
    try:
        selection = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"available": False, "path": str(path)}
    cohort = selection.get("cohort", {})
    return {
        "available": True,
        "path": str(path),
        "dataset": selection.get("dataset", "unknown"),
        "experiment": selection.get("experiment", "unknown"),
        "rows": cohort.get("rows"),
        "units": cohort.get("units"),
        "buildings": cohort.get("buildings"),
        "current_rows": cohort.get("current_rows"),
        "model_family": selection.get("model_family", "unknown"),
        "selection_reason": selection.get("selection_reason", ""),
    }


def current_fit(root: Path) -> dict[str, Any]:
    """Read lightweight diagnostics for the selected fit, without opening draws."""

    selection = current_selection(root)
    if not selection.get("available"):
        return {"available": False}
    experiment = root / str(selection["experiment"])
    diagnostics_path = experiment / "fit" / "diagnostics.json"
    storage_path = experiment / "fit" / "storage.json"
    try:
        diagnostics = json.loads(diagnostics_path.read_text())
        storage = json.loads(storage_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"available": False, "experiment": str(experiment)}
    chains = storage.get("chains")
    draws = storage.get("draws")
    retained_draws = chains * draws if isinstance(chains, int) and isinstance(draws, int) else None
    return {
        "available": True,
        "experiment": str(experiment),
        "retained_draws": retained_draws,
        "max_rhat": diagnostics.get("max_rhat"),
        "divergences": diagnostics.get("divergences"),
        "acceptable": diagnostics.get("acceptable"),
    }


def evidence_paths(root: Path, paths: Iterable[str]) -> list[Path]:
    """Resolve repo-relative evidence paths that exist."""

    return [root / path for path in paths if (root / path).exists()]
