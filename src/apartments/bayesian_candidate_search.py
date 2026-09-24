"""Preference frontiers over current observations of the selected PyMC fit.

Preferences determine ranking. Joint-posterior prices are separate in-sample
diagnostics, never utilities or independent bargain estimates.
"""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path

from threadpoolctl import threadpool_limits

from . import pricing, main_analysis
from .candidate_search import select_candidates
from .corrections import canonical
from .research_pipeline import digest, publish_bundle

VERSION = 'selected-pymc-current-preference-frontier-v1'
CONFLICT_FIELDS = {'bedroom_count_conflict': ('bedrooms',),
                   'known_bathroom_conflict_and_private_terrace': ('bathrooms',)}


def rank_current(analysis, preferences, *, as_of, max_age_days=7, budget=None,
                 unknown_policy='exclude', source_notes=None):
    if not isinstance(preferences, dict): raise ValueError('Preferences must map attributes to monthly dollars')
    source_notes = source_notes or {}
    rows = [r for r in analysis.rows if r.get('analysis_price_basis') == 'current_capture_gross_ask']
    source = {r['audit_id']: r for r in rows}
    if len(source) != len(rows): raise ValueError('Duplicate current fitted observation')
    selected, excluded, selection = select_candidates(rows, as_of=as_of, max_age_days=max_age_days, budget=budget)
    candidates = []
    for row in selected:
        value = deepcopy(row)
        active_ads = {(e.get('source'), str(e['source_listing_id']))
                      for e in row['active_advertisement_evidence']}
        other_conflicts = [r['audit_id'] for r in rows
            if r['unit_id'] == row['unit_id'] and r['audit_id'] != row['audit_id']
            and (r.get('source'), str(r['source_listing_id'])) in active_ads
            and source_notes.get(r['audit_id'], {}).get('interpretation_limited')]
        if other_conflicts:
            excluded.append({'record': row, 'reason': 'merged_advertisement_source_review_required',
                             'source_review_audit_ids': sorted(other_conflicts)})
            continue
        note = source_notes.get(row['audit_id'])
        fields = CONFLICT_FIELDS.get(note['kind'], ()) if note else ()
        if note and note.get('interpretation_limited') and not fields:
            excluded.append({'record': row, 'reason': 'unscoped_source_review_required'})
            continue
        # Preference-only withholding preserves the actual fitted source record.
        value['preference_attribute_withholding'] = {field: row.get(field) for field in fields}
        for field in fields: value[field] = None
        candidates.append(value)
    ranked = pricing.rank_apartments(candidates, preferences, unknown_policy=unknown_policy)
    for item in ranked:
        row = item['record']
        original = source[row['audit_id']]
        detail = analysis.detail(row['audit_id'])
        if (detail['source_record'] != original or detail['residual']['asking_rent'] != row['rent']
                or any(detail['residual'][k] != original[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'building'))):
            raise ValueError('Selected candidate does not match its fitted observation')
        note = source_notes.get(row['audit_id'])
        passed = detail['contribution_diagnostics']['acceptable']
        limited = bool(note and note['interpretation_limited'])
        status = 'source_review_required' if limited else 'estimated' if passed else 'diagnostic_only'
        item['market_comparison'] = {'status': status, 'model_family': 'pymc_bayesian',
            'same_observation_in_fit': True, 'independent_valuation': False,
            'latent_median_rent': detail['fitted_median_rent'] if passed and not limited else None,
            'residual_dollars': detail['residual']['residual_dollars'] if passed and not limited else None,
            'residual_log': detail['residual']['residual_log'] if passed and not limited else None,
            'draws': detail['draws'], 'derived_diagnostics': detail['contribution_diagnostics'],
            'source_review': note, 'warnings': detail['warnings'],
            'uncertainty': '95% posterior interval for latent conditional median asking rent; not a prediction interval.'}
        item['availability'] = {'status': 'source_reported_active_at_capture',
            'collected_at': row['collected_at'], 'age_days': row['capture_age_days'],
            'current_availability_verified': False}
        # Expose source measurements, retaining a separate audit of what ranking
        # withheld. The fitted observation itself is never modified.
        item['record'] = original
        item['preference_attribute_withholding'] = row['preference_attribute_withholding']
    report = {**selection, 'fitted_current_observations': len(rows), 'ranked_units': len(ranked),
        'exclusion_counts': dict(sorted(Counter(r['reason'] for r in excluded).items())),
        'eligible_preferences': sum(r['eligible'] for r in ranked),
        'frontier_units': sum(r['pareto_efficient'] for r in ranked),
        'source_review_withheld_units': sum(r['market_comparison']['status'] == 'source_review_required' for r in ranked),
        'diagnostic_only_units': sum(r['market_comparison']['status'] == 'diagnostic_only' for r in ranked),
        'unknown_policy': unknown_policy,
        'limitations': ['Monthly dollar preferences are supplied independently of fitted coefficients. Model prices, residuals and interval width never determine frontier membership or surplus.',
            'Only current capture observations already in the selected fit are considered; historical advertisements are not candidates.',
            'The as-of cutoff controls candidate capture/knowledge eligibility, not historical availability of this fitted model. This is retrospective analysis, not a backtest.',
            'Posterior prices use all retained joint draws and include the candidate observation in the fit. They are not independent valuations or automatic bargain labels.',
            'Unknown valued attributes exclude a candidate by default. Explicit zero policy may favor unknowns for negative preferences.',
            'Known source conflicts withhold the affected preference attributes and market interpretation. These are temporary analysis masks, not source corrections.',
            'Captured ACTIVE status is not a live availability guarantee. Unreported concessions, lease restrictions and attributes may remain.']}
    return ranked, excluded, report


def run(preferences, output, *, selection=main_analysis.DEFAULT_SELECTION, as_of,
        max_age_days=7, budget=None, unknown_policy='exclude'):
    from . import bayesian_analysis, bayesian_source_review, candidate_search
    preferences, selection = Path(preferences), Path(selection)
    modules = (pricing, bayesian_analysis, bayesian_source_review, main_analysis, candidate_search)
    paths = [Path(m.__file__) for m in modules]+[Path(__file__)]
    code = {p.name: p.read_text() for p in paths}
    selection_hash, preference_hash = digest(selection), digest(preferences)
    chosen, experiment, dataset = main_analysis.load_selection(selection)
    if main_analysis.is_summary(chosen):
        raise ValueError('Candidate search needs feature comparisons, which summary selections do not provide yet')
    weights = json.loads(preferences.read_text())
    with threadpool_limits(limits=1, user_api='blas'):
        analysis = bayesian_analysis.BayesianAnalysis.load(experiment, dataset)
        try:
            notes = {}
            if chosen.get('source_review'):
                notes = bayesian_source_review.load_source_review(experiment, dataset,
                    main_analysis.resolve_path(chosen['source_review']),
                    evidence=main_analysis.resolve_path(chosen['evidence']))
            ranked, excluded, report = rank_current(analysis, weights, as_of=as_of,
                max_age_days=max_age_days, budget=budget, unknown_policy=unknown_policy, source_notes=notes)
            # Refresh validation after the last candidate, before publishing.
            analysis.rows
        finally:
            analysis.close()
    if digest(selection) != selection_hash or digest(preferences) != preference_hash:
        raise ValueError('Selection or preferences changed while ranking')
    main_analysis.load_selection(selection)
    if any(p.read_text() != code[p.name] for p in paths): raise ValueError('Ranking implementation changed')
    files = dict(code)
    files.update({Path(__file__).name: Path(__file__).read_text(),
        'rankings.jsonl': ''.join(canonical(r)+'\n' for r in ranked),
        'excluded.jsonl': ''.join(canonical(r)+'\n' for r in excluded),
        'summary.json': canonical(report)+'\n', 'preferences.json': canonical(weights)+'\n',
        'selection.json': canonical(chosen)+'\n'})
    publish_bundle(output, files, {'version': VERSION, 'model_family': 'pymc_bayesian',
        'selection_sha256': selection_hash, 'preferences_sha256': preference_hash,
        'fit_manifest_sha256': chosen['fit_manifest_sha256'],
        'source_manifest_sha256': chosen['source_manifest_sha256'], 'source_review_manifest_sha256': chosen.get('source_review_manifest_sha256')})
    return report
