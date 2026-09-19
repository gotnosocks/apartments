"""Read-only importance sensitivity of five spline priors; never refit or select.

Alternative intervals approximate a changed-prior posterior only when conservative
weight gates pass. They are not additional PyMC chains or a selected posterior.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import arviz as az
import arviz_stats  # Registers the public xarray azstats PSIS accessor.
import numpy as np
import pandas as pd
from scipy.special import logsumexp
from threadpoolctl import threadpool_limits
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report
from . import bayesian_source_sensitivity as source
from . import bayesian_feature_design_v2 as ordered
from . import bayesian_floor_spline_contract as contract
from . import bayesian_category_contrasts as contrasts

VERSION = 'spline-floor-importance-prior-sensitivity-v1'
ALTERNATIVE_SCALES = (.05, .20)
PSIS_IMPLEMENTATION = {'distribution':'arviz-stats','version':'1.2.0',
    'api':'DataArray.azstats.psislw', 'input':'negative normalized log prior ratios; installed API negates input internally'}
GATE = {'pareto_k_strict_upper': .5, 'minimum_weight_ess': 1000.,
        'minimum_weight_ess_fraction': .10, 'maximum_normalized_weight': .01,
        'minimum_chain_mass_multiple': .5, 'maximum_chain_mass_multiple': 1.5,
        'minimum_reff_times_weight_ess': 400.}
LIMITATIONS = [
    'Conditional importance-sampling sensitivity from one exact PyMC posterior, not a refit, new chain, surrogate model, or main-model selection.',
    'Only the five spline coefficient priors change. Likelihood, source data, floor missingness, all other priors, and every joint draw remain unchanged; nuisance-parameter dependence is retained through whole-draw weights.',
    'Raw self-normalized weights determine alternative summaries. PSIS diagnoses tail behavior and supplies smoothed-weight diagnostics; it does not replace the retained posterior or resample it.',
    'Weight ESS is 1/sum(w^2) and does not account for MCMC autocorrelation. Coefficient bulk ESS/N determines PSIS r_eff; r_eff times weight ESS is only a conservative heuristic safeguard, not a formally adjusted ESS or MCSE.',
    'Adequate weight diagnostics cannot prove that unsampled regions of an alternative posterior were covered. A full PyMC refit is required when gates fail or stronger sensitivity claims are needed.',
    'Intervals are weighted empirical pointwise 95% credible-interval approximations for floor contributions relative to observed floor 2, not simultaneous bands, physical-height effects, causal values, or predictive rent intervals.',
    'Median shifts compare summaries of two probability distributions on the same draws. They are not posterior intervals for differences between priors.',
]


def prior_log_ratios(beta, baseline_scale, alternative_scale):
    beta = np.asarray(beta, dtype=float)
    scales = (baseline_scale, alternative_scale)
    if (beta.ndim != 3 or beta.shape[2] != 5 or beta.shape[0] < 2 or beta.shape[1] < 4
            or not np.isfinite(beta).all()
            or any(isinstance(v,(bool,np.bool_)) or not np.isfinite(v) or v <= 0 for v in scales)):
        raise ValueError('Finite chain/draw/five-coefficient array and positive Normal scales required')
    values = (5*math.log(baseline_scale/alternative_scale)
              + .5*np.sum((beta/baseline_scale)**2-(beta/alternative_scale)**2,axis=2))
    if not np.isfinite(values).all(): raise ValueError('Nonfinite prior density ratios')
    return values


def weight_summary(weights):
    weights = np.asarray(weights,dtype=float)
    if weights.ndim != 2 or not np.isfinite(weights).all() or np.any(weights < 0) or not np.isclose(weights.sum(),1.,rtol=1e-12,atol=1e-14):
        raise ValueError('Normalized chain/draw importance weights required')
    ess = float(1/np.sum(weights**2))
    return {'ess':ess,'ess_fraction':ess/weights.size,'maximum_weight':float(weights.max()),
            'chain_mass':weights.sum(axis=1).tolist(), 'ess_accounts_for_autocorrelation':False}


def importance_weights(log_ratios, reff):
    log_ratios = np.asarray(log_ratios,dtype=float)
    if (log_ratios.ndim != 2 or log_ratios.shape[0] < 2 or log_ratios.shape[1] < 4
            or not np.isfinite(log_ratios).all() or not np.isfinite(reff) or not 0 < reff <= 1):
        raise ValueError('Finite chain/draw log ratios and relative ESS in (0,1] required')
    normalized = log_ratios-logsumexp(log_ratios)
    raw = np.exp(normalized)
    # This installed API consumes log-likelihood-style values and negates
    # internally. Old az.psislw had the opposite input convention. Fail closed
    # on a version change until its adapter and orientation tests are reviewed.
    if importlib.metadata.version('arviz-stats') != PSIS_IMPLEMENTATION['version']:
        raise ValueError('Unreviewed arviz-stats PSIS input convention/version')
    psis_error = None
    try:
        smooth_log,khat = xr.DataArray(-normalized.ravel(),dims='sample').azstats.psislw(dim='sample',r_eff=reff)
        smooth_log = np.asarray(smooth_log.values,dtype=float)
        smooth = np.exp(smooth_log-logsumexp(smooth_log)).reshape(log_ratios.shape)
        k = float(khat.item())
        smooth_summary = weight_summary(smooth)
    except (ValueError, ArithmeticError) as exc:
        k, smooth_summary, psis_error = float('nan'), None, str(exc)
    raw_summary = weight_summary(raw)
    reasons=[]
    if not np.isfinite(k) or k >= GATE['pareto_k_strict_upper']: reasons.append('pareto_k_not_below_0.5')
    if psis_error is not None: reasons.append('psis_computation_failed')
    for kind,value in [('raw',raw_summary),('psis',smooth_summary)]:
        if value is None: continue
        if value['ess'] < GATE['minimum_weight_ess']: reasons.append(kind+'_weight_ess_below_1000')
        if value['ess_fraction'] < GATE['minimum_weight_ess_fraction']: reasons.append(kind+'_weight_ess_fraction_below_0.10')
        if value['maximum_weight'] > GATE['maximum_normalized_weight']: reasons.append(kind+'_maximum_weight_above_0.01')
        if not all(GATE['minimum_chain_mass_multiple']/len(raw) <= v <= GATE['maximum_chain_mass_multiple']/len(raw) for v in value['chain_mass']):
            reasons.append(kind+'_chain_mass_imbalance')
        value['reff_times_weight_ess_heuristic'] = reff*value['ess']
        if value['reff_times_weight_ess_heuristic'] < GATE['minimum_reff_times_weight_ess']:
            reasons.append(kind+'_reff_times_weight_ess_below_400')
    diagnostic={'acceptable':not reasons,'withholding_reasons':reasons,'pareto_k':k if np.isfinite(k) else None,
        'pareto_k_finite':bool(np.isfinite(k)), 'psis_r_eff':reff, 'psis_error':psis_error, 'psis_implementation':dict(PSIS_IMPLEMENTATION),'raw':raw_summary,'psis':smooth_summary,
        'raw_log_ratio_min':float(log_ratios.min()),'raw_log_ratio_max':float(log_ratios.max()),
        'log_normalizer':float(logsumexp(log_ratios)), 'gate':dict(GATE)}
    return raw,diagnostic


def weighted_interval(values, weights):
    """Inverse weighted empirical CDF; all retained draws, no resampling."""
    values,weights=np.asarray(values,dtype=float).ravel(),np.asarray(weights,dtype=float).ravel()
    if (values.shape!=weights.shape or not len(values) or not np.isfinite(values).all()
            or not np.isfinite(weights).all() or np.any(weights<0) or not weights.sum()>0):
        raise ValueError('Finite equal-length values and nonnegative positive-total weights required')
    keep=weights>0;values,weights=values[keep],weights[keep]
    order=np.argsort(values,kind='stable');values,weights=values[order],weights[order]
    cdf=np.cumsum(weights/weights.sum());cdf[-1]=1.
    points=values[np.searchsorted(cdf,[.025,.5,.975],side='left')]
    return {**dict(zip(('lower_95','median','upper_95'),map(float,points))),
            'probability_positive':float(weights[values>0].sum()/weights.sum())}


def percent_interval(value):
    return {**value,**{k:100*math.expm1(value[k]) for k in ('lower_95','median','upper_95')}}


def calculate(design,beta,prior_multiplier=1.):
    if (design.version != contract.DESIGN or design.floor_prior_scale != .10
            or 2. not in design.floor_levels or not np.isfinite(prior_multiplier) or prior_multiplier <= 0):
        raise ValueError('Require baseline .10 spline prior and observed floor 2')
    names=[f'listed_floor_spline_{i}' for i in range(5)]
    if [n for n in design.features if n.startswith('listed_floor_spline_')] != names:
        raise ValueError('This sensitivity changes exactly five spline coefficients')
    beta=np.asarray(beta,dtype=float)
    if beta.ndim!=3 or beta.shape[2]!=len(design.features) or not np.isfinite(beta).all():
        raise ValueError('Posterior coefficient shape or values differ')
    index=[design.features.index(n) for n in names]
    if not np.array_equal(design.prior_scales[index],np.full(5,.10)):
        raise ValueError('Baseline spline prior vector differs')
    selected=beta[:,:,index]
    ds=xr.Dataset({'floor_beta':(('chain','draw','feature'),selected)},coords={'feature':names})
    table=az.summary(ds,kind='diagnostics',round_to='none')
    values=table[['r_hat','ess_bulk','ess_tail']].to_numpy()
    if not np.isfinite(values).all() or table.r_hat.max()>=1.01 or min(table.ess_bulk.min(),table.ess_tail.min())<400:
        raise ValueError('Baseline spline coefficient diagnostics fail')
    reff=min(1.,float(table.ess_bulk.min())/(beta.shape[0]*beta.shape[1]))
    definitions=[{'id':f'floor:2->{level:g}','floor':level,'reference_floor':2.,
        'design_vector':design.contrast_vector(2.,level).tolist()} for level in design.floor_levels if level!=2.]
    base_rows,_=contrasts.calculate(beta,definitions)
    uniform=np.full(beta.shape[:2],1/(beta.shape[0]*beta.shape[1]))
    joint={row['floor']:np.einsum('cdf,f->cd',beta,row['design_vector']) for row in base_rows}
    # Use one empirical-CDF definition for baseline and alternatives.
    for row in base_rows:
        if row['log_effect'] is not None:
            row['log_effect']=weighted_interval(joint[row['floor']],uniform)
            row['percent_effect']=percent_interval(row['log_effect'])
    zero={'lower_95':0.,'median':0.,'upper_95':0.,'probability_positive':0.}
    base_rows.append({'floor':2.,'reference_floor':2.,'log_effect':zero,'percent_effect':zero,
        'status':'deterministic_reference','diagnostics':{'deterministic':True}})
    base_rows.sort(key=lambda r:r['floor'])
    alternatives=[]
    for scale in ALTERNATIVE_SCALES:
        raw,diagnostic=importance_weights(prior_log_ratios(selected,.10*prior_multiplier,scale*prior_multiplier),reff)
        points=[]
        for row in base_rows:
            point={'floor':row['floor'],'reference_floor':2.,'log_effect':None,'percent_effect':None,
                'median_log_shift_from_base':None,'median_percentage_point_shift_from_base':None}
            if row['floor']==2.:
                point.update(log_effect=zero,percent_effect=zero,median_log_shift_from_base=0.,
                    median_percentage_point_shift_from_base=0.,status='deterministic_reference')
            elif not diagnostic['acceptable']:
                point['status']='withheld_importance_weight_diagnostics'
            elif row['log_effect'] is None:
                point['status']='withheld_baseline_contrast_diagnostics'
            else:
                effect=weighted_interval(joint[row['floor']],raw);percent=percent_interval(effect)
                point.update(status='conditional_importance_approximation',log_effect=effect,percent_effect=percent,
                    median_log_shift_from_base=effect['median']-row['log_effect']['median'],
                    median_percentage_point_shift_from_base=percent['median']-row['percent_effect']['median'])
            points.append(point)
        alternatives.append({'floor_prior_scale':scale,'effective_coefficient_prior_sd':scale*prior_multiplier,
            'diagnostics':diagnostic,'points':points,
            'status':'conditional_importance_approximation' if diagnostic['acceptable'] else 'withheld_requires_refit'})
    return {'version':VERSION,'baseline_floor_prior_scale':.10,'prior_multiplier':prior_multiplier,
        'changed_coefficients':names,'draws':beta.shape[0]*beta.shape[1],'chains':beta.shape[0],
        'minimum_coefficient_bulk_ess':float(table.ess_bulk.min()),'psis_r_eff':reff,
        'coefficient_diagnostics':table[['r_hat','ess_bulk','ess_tail']].to_dict('index'),
        'relative_efficiency_rule':'min(1, minimum five-coefficient bulk ESS / total retained draws)',
        'quantile_rule':'Inverse weighted empirical CDF at .025,.5,.975; positive probability uses strict >0.',
        'baseline_curve':base_rows,'alternatives':alternatives,'floor_support':design.floor_support,
        'main_selection_changed':False,'posterior_refitted':False,'limitations':LIMITATIONS}


def build(experiment,dataset):
    experiment,dataset=Path(experiment),Path(dataset)
    paths={'fit':experiment/'fit','protocol':experiment/'protocol','source':dataset}
    bindings={k:digest(p/'complete.json') for k,p in paths.items()}
    verified,manifests=report.build_report(experiment,dataset)
    protocol=json.loads(source.comparison.bound_bytes(experiment/'protocol','protocol.json',manifests['protocol_manifest']))
    if protocol.get('version')!=contract.EXPERIMENT: raise ValueError('Accepted spline experiment required')
    reconstruction=source.verify_design(experiment,dataset,protocol,manifests)
    _,files=_verified_bundle(dataset,retain={'observations.jsonl'})
    frame=pd.DataFrame(report.jsonl(files['observations.jsonl']));frame.period=pd.to_datetime(frame.period)
    frame.square_feet=pd.to_numeric(frame.square_feet,errors='coerce')
    design=ordered.load_design(experiment/'fit',frame,protocol)
    posterior_path=experiment/'fit/posterior.nc'
    with xr.open_dataset(posterior_path,group='posterior',engine='h5netcdf',cache=False) as posterior:
        if (posterior.beta.dims!=('chain','draw','feature') or posterior.feature.values.tolist()!=design.features
                or posterior.sizes['chain']!=protocol['chains'] or posterior.sizes['draw']!=protocol['draws']):
            raise ValueError('Posterior retained dimensions or feature order differ')
        beta=posterior.beta.load().values
    result=calculate(design,beta,protocol['prior_multiplier'])
    if (bindings!={k:digest(p/'complete.json') for k,p in paths.items()}
            or digest(posterior_path)!=manifests['fit_manifest']['files']['posterior.nc']):
        raise ValueError('Source or posterior binding changed during sensitivity analysis')
    result.update(bindings=bindings,posterior_sha256=manifests['fit_manifest']['files']['posterior.nc'],
        protocol_sha256=verified['protocol_sha256'],source_observations_sha256=verified['source_observations_sha256'],
        design_reconstruction=reconstruction,verified_report_sha256=hashlib.sha256((canonical(verified)+'\n').encode()).hexdigest(),
        experiment=str(experiment.resolve()),dataset=str(dataset.resolve()),
        versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','pandas','xarray','arviz','arviz-stats','h5netcdf')})
    return result,verified


def markdown(result):
    lines=['# Floor-prior importance sensitivity','',*LIMITATIONS,'',
        '| Alternative scale | Status | Pareto k | Raw weight ESS | Max raw weight |',
        '|---|---|---:|---:|---:|']
    for item in result['alternatives']:
        d=item['diagnostics'];lines.append(f"| {item['floor_prior_scale']} | {item['status']} | {d['pareto_k']} | {d['raw']['ess']:.1f} | {d['raw']['maximum_weight']:.6f} |")
    for item in result['alternatives']:
        d=item['diagnostics']
        if d['withholding_reasons']:
            lines.append('\nScale '+str(item['floor_prior_scale'])+' withheld: '+', '.join(d['withholding_reasons'])+'.\n')
    def formatted(point):
        value=point['percent_effect']
        return ('Withheld' if value is None else
                f"{value['median']:+.2f}% [{value['lower_95']:+.2f}, {value['upper_95']:+.2f}]")
    lines.extend(['','Pointwise floor-component intervals relative to floor 2; alternative columns are importance approximations.',
        '', '| Floor | Baseline .10 | Alternative .05 | Alternative .20 |', '|---:|---:|---:|---:|'])
    alternatives=[{p['floor']:p for p in item['points']} for item in result['alternatives']]
    for point in result['baseline_curve']:
        lines.append('| '+str(point['floor'])+' | '+formatted(point)+' | '
                     +' | '.join(formatted(other[point['floor']]) for other in alternatives)+' |')
    return '\n'.join(lines)+'\n'


def run(experiment,dataset,output):
    # Freeze the read-side verifier and reconstruction dependencies as well as inputs.
    from . import bayesian_floor_spline_design as design
    from . import bayesian_floor_increment_design as floor_source
    from . import bayesian_floor_execution as execution
    modules=(report,source,ordered,contract,contrasts,design,floor_source,execution,
             execution.storage_protocol,report.interaction_contract,report.reviewed_source_lineage,source.comparison)
    paths=[Path(__file__),*[Path(m.__file__) for m in modules]]
    hashes={p.name:digest(p) for p in paths}
    result,verified=build(experiment,dataset)
    if any(digest(p)!=hashes[p.name] for p in paths):raise ValueError('Sensitivity/verifier implementation changed')
    result['report_implementation_sha256']=hashes
    publish_bundle(output,{'sensitivity.json':canonical(result)+'\n','sensitivity.md':markdown(result),
        'verified-report.json':canonical(verified)+'\n',**{p.name:p.read_text() for p in paths}},
        {'version':VERSION,'bindings':result['bindings'],'implementation_sha256':hashes})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('experiment','dataset','output'):parser.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):run(**vars(parser.parse_args()))
