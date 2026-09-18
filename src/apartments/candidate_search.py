"""Freshness-aware snapshots, preference frontiers, and separate market scoring."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from . import pricing, robust_pricing
from .corrections import canonical
from .research_pipeline import digest, publish_bundle


def select_candidates(records, *, as_of, max_age_days=7, budget=None):
    cutoff=pricing._timestamp(as_of)
    max_age_days=float(max_age_days)
    budget=float(budget) if budget is not None else None
    if not math.isfinite(max_age_days) or max_age_days<0:
        raise ValueError('Maximum capture age must be finite and nonnegative')
    if budget is not None and (not math.isfinite(budget) or budget<=0):
        raise ValueError('Budget must be finite and positive')
    grouped=defaultdict(list);excluded=[];count=0
    def reject(row,reason):
        excluded.append({'record':row,'reason':reason})
    for raw in records:
        count+=1
        if not isinstance(raw,dict):
            raise ValueError('Candidate JSONL records must be objects')
        row=pricing._normalize(raw)
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('unit_id','building_id')):
            reject(raw,'missing_canonical_identity');continue
        listing=row.get('source_listing_id')
        if not isinstance(listing,(str,int)) or isinstance(listing,bool) or not str(listing).strip():
            reject(raw,'missing_advertisement_identity');continue
        try:
            collected=pricing._timestamp(row['collected_at'])
            known=pricing._timestamp(row.get('known_at',row.get('known_as_of',row['collected_at'])))
        except (KeyError,ValueError,TypeError,OverflowError,OSError):
            reject(raw,'missing_or_invalid_collection_knowledge_clock');continue
        if known<collected:
            reject(raw,'knowledge_precedes_collection');continue
        if collected>cutoff or known>cutoff:
            reject(raw,'not_known_at_cutoff');continue
        grouped[(str(row['unit_id']),str(row.get('source','unspecified')),str(listing))].append((collected,row,raw))
    selected=[];superseded=0;duplicates=0;active=defaultdict(list)
    for (unit,source,listing),versions in sorted(grouped.items()):
        latest=max(v[0] for v in versions)
        current=[v for v in versions if v[0]==latest]
        superseded+=len(versions)-len(current)
        distinct={canonical(v[1]) for v in current}
        if len(distinct)!=1:
            for _,_,raw in current:
                reject(raw,'conflicting_latest_capture')
            continue
        duplicates+=len(current)-1
        collected,row,raw=current[0]
        if str(row.get('listing_status','')).upper()!='ACTIVE':
            reject(raw,'latest_capture_not_confirmed_active');continue
        if (cutoff-collected).total_seconds()>max_age_days*86400:
            reject(raw,'stale_capture');continue
        if row.get('price_basis')!='gross_advertised_rent':
            reject(raw,'unsupported_price_basis');continue
        if not (row.get('capture_id') or row.get('capture_ids')):
            reject(raw,'missing_capture_reference');continue
        rent=pricing._number(row.get('rent'))
        if rent is None or rent<=0:
            reject(raw,'invalid_asking_rent');continue
        row.update(rent=rent,unit_id=unit,collected_at=collected.isoformat(),
                   capture_age_days=(cutoff-collected).total_seconds()/86400)
        active[unit].append((row,raw))
    # Different advertisements do not supersede one another merely because an
    # archive crawler fetched their pages in a different order.
    comparison_fields=('rent',*pricing.NUMERIC,*pricing.CATEGORICAL,*pricing.EXPOSURES,'elevator',
                       'furnished','short_term','concession')
    merged=0
    for unit,advertisements in sorted(active.items()):
        variants={canonical({k:row.get(k) for k in comparison_fields}) for row,_ in advertisements}
        if len(variants)>1:
            for _,raw in advertisements:
                reject(raw,'conflicting_active_advertisements')
            continue
        row,raw=max(advertisements,key=lambda pair:(pair[0]['collected_at'],canonical(pair[0])))
        if budget is not None and row['rent']>budget:
            reject(raw,'over_budget');continue
        flag=next((f for f in ('furnished','short_term','concession') if pricing._boolean(row.get(f))==1),None)
        if flag:
            reject(raw,'excluded_'+flag);continue
        row=dict(row)
        row['active_advertisement_evidence']=[{'source':r.get('source'),'source_listing_id':r['source_listing_id'],
              'collected_at':r['collected_at'],'capture_id':r.get('capture_id'),'capture_ids':r.get('capture_ids')}
             for r,_ in sorted(advertisements,key=lambda pair:canonical(pair[0]))]
        merged+=len(advertisements)-1
        selected.append(row)
    return selected,excluded,{'input_records':count,'selected_units':len(selected),
        'superseded_observations':superseded,'identical_latest_duplicates':duplicates,
        'compatible_active_advertisements_merged':merged,
        'exclusion_counts':dict(sorted(Counter(r['reason'] for r in excluded).items())),
        'as_of':cutoff.isoformat(),'max_capture_age_days':max_age_days,'budget':budget}


def market_comparison(model, row, *, as_of):
    at=pricing._timestamp(as_of);prediction_month=robust_pricing.month(at)
    horizon=robust_pricing.month_distance(model.periods[-1],prediction_month)
    knowledge=model.artifact['training'].get('knowledge_cutoff')
    published=model.artifact.get('published_at')
    if knowledge is None or pricing._timestamp(knowledge)>at or (published and pricing._timestamp(published)>at):
        return {'status':'model_not_known_at_cutoff','predicted_rent':None}
    maximum=model.artifact['validation']['max_serving_horizon_months']
    if not 1<=horizon<=maximum:
        return {'status':'model_outside_serving_horizon','predicted_rent':None,
                'forecast_horizon_months':horizon,'maximum_horizon_months':maximum}
    try:
        prediction=model.predict(row,prediction_month)
    except ValueError as exc:
        return {'status':'unsupported_candidate_attributes','predicted_rent':None,'reason':str(exc)}
    listing_ids=model.artifact['training'].get('source_listing_ids')
    same_ad=None if listing_ids is None else str(row.get('source_listing_id')) in listing_ids
    return {'status':'estimated',**prediction,
            'same_advertisement_in_training':same_ad,
            'independent_valuation':False,
            'training_overlap_note':('This advertisement contributed to training; its residual is partly fitted to its own asking history.'
                                    if same_ad else 'This is a conditional research-model comparison, not an independently validated valuation.'),
            'prediction_basis':'historical_own_advertisement_initial_gross_ask',
            'asking_minus_predicted':row['rent']-prediction['predicted_rent']}


def score_candidates(candidates, preferences, output, *, model_bundle, as_of,
                     max_age_days=7, budget=None, unknown_policy='exclude'):
    candidate_bytes=Path(candidates).read_bytes();preference_bytes=Path(preferences).read_bytes()
    rows=[json.loads(line) for line in candidate_bytes.decode().split('\n') if line.strip()]
    weights=json.loads(preference_bytes)
    if not isinstance(weights,dict):
        raise ValueError('Preferences must map supported attributes to monthly dollar values')
    model=robust_pricing.RobustPricingModel.load(model_bundle)
    selected,excluded,selection=select_candidates(rows,as_of=as_of,max_age_days=max_age_days,budget=budget)
    ranked=pricing.rank_apartments(selected,weights,unknown_policy=unknown_policy)
    for row in ranked:
        row['market_comparison']=market_comparison(model,row['record'],as_of=as_of)
        row['availability']={'status':'source_reported_active_at_capture',
                             'collected_at':row['record']['collected_at'],
                             'age_days':row['record']['capture_age_days'],
                             'current_availability_verified':False}
    report={**selection,'eligible_preferences':sum(r['eligible'] for r in ranked),
            'frontier_units':sum(r['pareto_efficient'] for r in ranked),
            'market_status_counts':dict(sorted(Counter(r['market_comparison']['status'] for r in ranked).items())),
            'unknown_policy':unknown_policy,
            'limitations':['Availability is source-reported at the selected capture; no live availability guarantee.',
                           'Preference values are user-supplied dollars; market predictions never determine the frontier.',
                           'Within an advertisement, latest inactive or conflicting observations cannot be replaced with older active captures.',
                           'Inactive historical advertisements do not supersede separate active advertisements; conflicting active advertisements are excluded.',
                           'Model horizon and evidence knowledge cutoff are checked separately from capture age.',
                           'Unknown furnished/concession/short-term flags are retained; source omissions remain possible.',
                           'No calibrated uncertainty interval is served; unfamiliar-building pooled bands failed validation.']}
    return publish_bundle(output,{'rankings.jsonl':''.join(canonical(r)+'\n' for r in ranked),
                                  'candidates.jsonl':candidate_bytes.decode(),
                                  'excluded.jsonl':''.join(canonical(r)+'\n' for r in excluded),
                                  'selection.json':canonical(report)+'\n','preferences.json':canonical(weights)+'\n'},
                          {'ranking_version':'fresh-robust-frontier-v1',
                           'candidates_sha256':hashlib.sha256(candidate_bytes).hexdigest(),
                           'preferences_sha256':hashlib.sha256(preference_bytes).hexdigest(),
                           'model_manifest':model.manifest,'selection':report,
                           'implementation_sha256':digest(__file__),'runtime_sha256':digest(robust_pricing.__file__),
                           'preferences_implementation_sha256':digest(pricing.__file__)})
