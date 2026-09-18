"""Compare verified v2 feature-prior fits using saved summaries, without sampling.

Only sampling lengths, seed and the positive feature-prior multiplier may vary.
Intervals belong to individual fits; differences of medians are descriptive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_feature_report as verified

VERSION = 'verified-bayesian-feature-prior-sensitivity-v1'
ALLOWED = frozenset({'draws', 'tune', 'chains', 'seed', 'prior_multiplier'})
DESIGNS = ('feature-design.json', 'time-design.json', 'time-design.npz')
INTERVAL_KEYS = ('median', 'lower_95', 'upper_95', 'probability_positive')
LIMITATION = ('Each interval is a separate fit\'s 95% posterior interval. Median and endpoint '
              'changes and interval overlap are descriptive sensitivity summaries, not credible '
              'intervals or posterior probabilities for between-fit differences. Draws from '
              'different fits are never paired. Sampling variation can contribute to changes.')


def bound_bytes(root, name, manifest):
    """Reread a small saved product against its already verified bundle hash."""
    path = Path(root)/name
    if path.is_symlink():
        raise ValueError(f'Invalid artifact path: {name}')
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != manifest['files'].get(name):
        raise ValueError(f'Artifact changed after verification: {name}')
    return blob


def ranks(values):
    """Ascending average ranks, with exact ties; rank 1 is the smallest value."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for index in order[start:end]:
            result[index] = (start + 1 + end)/2
        start = end
    return result


def rank_correlation(left, right):
    a, b = ranks(left), ranks(right)
    if len(a) < 2 or min(a) == max(a) or min(b) == max(b):
        return {'spearman_rho': None, 'reason': 'Fewer than two rows or constant ranks'}
    am, bm = statistics.mean(a), statistics.mean(b)
    numerator = sum((x-am)*(y-bm) for x,y in zip(a,b,strict=True))
    denominator = math.sqrt(sum((x-am)**2 for x in a)*sum((y-bm)**2 for y in b))
    return {'spearman_rho': max(-1., min(1., numerator/denominator)), 'reason': None}


def interval_change(before, after):
    return {'reference': {k: before[k] for k in INTERVAL_KEYS},
            'candidate': {k: after[k] for k in INTERVAL_KEYS},
            'median_change': after['median']-before['median'],
            'lower_endpoint_change': after['lower_95']-before['lower_95'],
            'upper_endpoint_change': after['upper_95']-before['upper_95'],
            'intervals_overlap_descriptively': max(before['lower_95'],after['lower_95']) <= min(before['upper_95'],after['upper_95'])}


def compare_tables(before, after, interval_fields):
    """Identity includes all support and semantics, not the estimated effects."""
    def indexed(items):
        out = {}
        for item in items:
            fixed = {k:v for k,v in item.items() if k not in interval_fields and k != 'probability_first_increment_larger'}
            key = canonical(fixed)
            if key in out:
                raise ValueError('Duplicate comparison identity')
            out[key] = (fixed,item)
        return out
    a,b = indexed(before),indexed(after)
    if a.keys() != b.keys():
        raise ValueError('Contrast/coefficient identity, support or semantics differ')
    return [{**a[key][0], 'changes': {field: interval_change(a[key][1][field],b[key][1][field])
             for field in interval_fields}} for key in sorted(a)]


def coefficient_changes(before, after):
    def wrapped(items):
        return [{**{k:v for k,v in item.items() if k not in INTERVAL_KEYS},
                 'log_coefficient': {k:item[k] for k in INTERVAL_KEYS}} for item in items]
    return compare_tables(wrapped(before),wrapped(after),('log_coefficient',))


def residual_changes(reference, candidate, reference_report, candidate_report):
    a = {r['audit_id']:r for r in reference}
    b = {r['audit_id']:r for r in candidate}
    if a.keys() != b.keys():
        raise ValueError('Residual observation membership differs')
    ids = sorted(a)
    signed_a = [a[k]['residual_log'] for k in ids]
    signed_b = [b[k]['residual_log'] for k in ids]
    absolute_a,absolute_b = [abs(v) for v in signed_a],[abs(v) for v in signed_b]
    ranking = {label:dict(zip(ids,ranks(values),strict=True)) for label,values in
               [('signed_reference',signed_a),('signed_candidate',signed_b),
                ('absolute_reference',absolute_a),('absolute_candidate',absolute_b)]}
    ca = {r['audit_id']:r for r in reference_report['current_residuals']}
    cb = {r['audit_id']:r for r in candidate_report['current_residuals']}
    if ca.keys() != cb.keys():
        raise ValueError('Current capture membership differs')
    fields = ('fitted_rent','latent_rent_lower_95','latent_rent_upper_95','residual_dollars','residual_log')
    current = []
    for key in sorted(ca):
        item = {k:ca[key][k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent','advertisement_url','source_record')}
        item.update(reference={k:ca[key][k] for k in fields}, candidate={k:cb[key][k] for k in fields},
                    changes={k:cb[key][k]-ca[key][k] for k in ('fitted_rent','residual_dollars','residual_log')},
                    all_row_ranks={k:v[key] for k,v in ranking.items()})
        current.append(item)
    return {'rows':len(ids), 'signed_log_residual':rank_correlation(signed_a,signed_b),
            'absolute_log_residual':rank_correlation(absolute_a,absolute_b),
            'rank_convention':'Ascending average ranks; highest absolute rank means largest residual magnitude. Exact ties share rank.',
            'current_rows':current}


def build_comparison(experiments, dataset):
    if len(experiments) < 2:
        raise ValueError('At least two completed experiments are required')
    fits = []
    for experiment in experiments:
        root = Path(experiment)
        report, provenance = verified.build_report(root,dataset,top=1)
        protocol = json.loads(bound_bytes(root/'protocol','protocol.json',provenance['protocol_manifest']))
        if not {'adaptation','target_accept','seed','versions'} <= protocol.keys():
            raise ValueError('Protocol missing sampler or environment identity')
        multiplier = protocol['prior_multiplier']
        if not verified.finite(multiplier) or multiplier <= 0:
            raise ValueError('Prior multipliers must be finite and positive')
        if any(type(protocol[k]) is not int or protocol[k] < minimum for k,minimum in
               [('draws',1),('tune',1),('chains',2),('seed',0)]):
            raise ValueError('Invalid sampling length or seed')
        residuals = verified.jsonl(bound_bytes(root/'fit','residuals.jsonl',provenance['fit_manifest']))
        provenance['manifest_sha256'] = {'protocol':digest(root/'protocol'/'complete.json'),
                                         'fit':digest(root/'fit'/'complete.json'),
                                         'source':digest(Path(dataset)/'complete.json')}
        fits.append({'report':report,'protocol':protocol,'provenance':provenance,'residuals':residuals})
    fits.sort(key=lambda f:f['protocol']['prior_multiplier'])
    multipliers = [f['protocol']['prior_multiplier'] for f in fits]
    if len(set(multipliers)) != len(fits):
        raise ValueError('Each experiment must have a distinct prior multiplier')
    reference = next((f for f in fits if f['protocol']['prior_multiplier'] == 1),fits[0])
    fixed = {k:v for k,v in reference['protocol'].items() if k not in ALLOWED}
    design_hashes = {name:reference['provenance']['fit_manifest']['files'][name] for name in DESIGNS}
    for fit in fits:
        if {k:v for k,v in fit['protocol'].items() if k not in ALLOWED} != fixed:
            raise ValueError('Fixed protocol identity differs: only sampling lengths, seed and prior multiplier may change')
        if {name:fit['provenance']['fit_manifest']['files'][name] for name in DESIGNS} != design_hashes:
            raise ValueError('Exact feature/time design hashes differ')
    comparisons = []
    for fit in fits:
        if fit is reference:
            continue
        a,b = reference['report'],fit['report']
        comparisons.append({'candidate_prior_multiplier':fit['protocol']['prior_multiplier'],
            'bathrooms':{name:compare_tables(a['bathrooms'][name],b['bathrooms'][name],fields) for name,fields in
                [('full_bath_increments',('log_effect','percent_effect')),
                 ('half_bath_increments',('log_effect','percent_effect')),('net_balance',('difference',))]},
            'coefficients':{name:coefficient_changes(a['coefficients'][name],b['coefficients'][name])
                for name in ('encoded_value_coefficients','reporting_coefficients')},
            'residuals':residual_changes(reference['residuals'],fit['residuals'],a,b)})
    report = {'version':VERSION,'reference_prior_multiplier':reference['protocol']['prior_multiplier'],
        'reference_rule':'Multiplier 1 when included; otherwise the smallest multiplier.',
        'allowed_protocol_changes':sorted(ALLOWED),'fixed_protocol':fixed,'design_sha256':design_hashes,
        'cohort':reference['report']['cohort'],
        'fits':[{'experiment':f['report']['experiment'],'protocol_sha256':f['report']['protocol_sha256'],
                 'sampling_and_prior':{k:f['protocol'][k] for k in sorted(ALLOWED)},
                 'diagnostics':f['report']['diagnostics'],
                 'median_absolute_log_residual':f['report']['median_absolute_log_residual']} for f in fits],
        'bathroom_interpretation':{k:reference['report']['bathrooms'][k] for k in
                                   ('held_fixed','balance_scale','omitted_unsupported_or_unencoded')},
        'coefficient_interpretation':reference['report']['coefficients']['interpretation'],
        'omitted_category_basis_coefficients':reference['report']['coefficients']['omitted_category_basis_coefficients'],
        'comparisons':comparisons,'limitations':[LIMITATION,*reference['report']['limitations']]}
    provenance = [{'experiment':f['report']['experiment'],**f['provenance']} for f in fits]
    return report,provenance


def markdown_report(report):
    def cell(value):
        return str(value).replace('|','\\|').replace('\n',' ')
    def interval(value):
        return f"{value['median']:+.4g} [{value['lower_95']:+.4g}, {value['upper_95']:+.4g}]"
    def table(headers, rows):
        return '\n| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+''.join('| '+' | '.join(cell(v) for v in row)+' |\n' for row in rows)
    lines = ['# Feature-prior sensitivity', '',
             f"Reference multiplier: {report['reference_prior_multiplier']}. {report['cohort']['rows']:,} identical observations; {report['cohort']['current_rows']} current captures.",
             '',LIMITATION,'',report['coefficient_interpretation'],
             '', 'Both parameter and derived diagnostics passed for every fit. Exact fixed protocols and design hashes match.']
    for comparison in report['comparisons']:
        lines += ['',f"## Multiplier {comparison['candidate_prior_multiplier']} versus reference",'']
        for category,items in comparison['bathrooms'].items():
            lines += [f'### {category}',table(['Contrast and support','Scale','Reference median [95%]','Candidate median [95%]','Median change','Overlap (descriptive)'],
                [[canonical({k:v for k,v in item.items() if k != 'changes'}),scale,interval(change['reference']),interval(change['candidate']),f"{change['median_change']:+.4g}",change['intervals_overlap_descriptively']]
                 for item in items for scale,change in item['changes'].items()])]
        for category,items in comparison['coefficients'].items():
            lines += [f'### {category}',table(['Feature','Encoded interpretation','Reference [95%]','Candidate [95%]','Median change'],
                [[item['feature'],item['encoded_unit'],interval(item['changes']['log_coefficient']['reference']),interval(item['changes']['log_coefficient']['candidate']),f"{item['changes']['log_coefficient']['median_change']:+.4g}"] for item in items])]
        residuals = comparison['residuals']
        lines += ['### Residual movement',f"All-row signed log-residual Spearman: {residuals['signed_log_residual']}; absolute log-residual Spearman: {residuals['absolute_log_residual']}.",
                  residuals['rank_convention'],table(['Current source / audit ID','Ask','Reference fitted','Candidate fitted','Residual dollar change','Absolute rank reference → candidate'],
            [[f"[{r['source_listing_id']}]({r['advertisement_url']}) / {r['audit_id']}",r['asking_rent'],r['reference']['fitted_rent'],r['candidate']['fitted_rent'],r['changes']['residual_dollars'],
              f"{r['all_row_ranks']['absolute_reference']} → {r['all_row_ranks']['absolute_candidate']}"] for r in residuals['current_rows']])]
    lines += ['', '## Source binding', '', f"Observations SHA-256: `{report['fixed_protocol']['source_observations_sha256']}`.",
              'Full protocols, design hashes, fit manifests, source records, separate intervals and diagnostics are preserved in comparison.json and complete.json.',
              '', '## Interpretation limits', '',*['- '+item for item in report['limitations']]]
    return '\n\n'.join(lines)+'\n'


def run(experiments, dataset, output):
    report,provenance = build_comparison(experiments,dataset)
    sources = [Path(__file__),Path(verified.__file__)]
    return publish_bundle(output,{'comparison.json':canonical(report)+'\n','comparison.md':markdown_report(report),
                                 **{p.name:p.read_text() for p in sources}},
                          {'version':VERSION,'experiments':provenance,
                           'implementation_sha256':{p.name:digest(p) for p in sources}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,action='append',required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(canonical(run(args.experiment,args.dataset,args.output)))
