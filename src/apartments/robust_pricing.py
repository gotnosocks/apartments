"""Portable replay of the validated robust encoder; no fitting or optional runtime.

The scientific producer must export a verified bundle after prediction parity
checks. Log components describe the saved parameterization, not causal premiums.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from . import pricing
from .research_pipeline import _verified_bundle, digest

VERSION = 'portable-robust-rent-v1'
CORE_FEATURES = ['intercept', *[f'bedrooms_gt_{n}' for n in range(5)],
                 'bathrooms_above_one', 'log_size_within_bedrooms', 'size_missing']


def month(value):
    if isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}',value):
        value += '-01'
    return pricing._timestamp(value).replace(day=1,hour=0,minute=0,second=0,microsecond=0)


def month_distance(start, end):
    return (end.year-start.year)*12+end.month-start.month


def _normalize(record):
    # DataFrame exports may contain floating NaN in otherwise categorical columns.
    # Match the scientific producer's feature_record missing-value normalization.
    return pricing._normalize({key:None if isinstance(value,float) and math.isnan(value) else value
                               for key,value in record.items()})


class RobustPricingModel:
    def __init__(self, artifact):
        if artifact.get('version') != VERSION:
            raise ValueError('Unsupported robust pricing artifact')
        self.artifact = artifact
        self.encoder = artifact['encoder']
        self.beta = artifact['coefficients']
        self.center = artifact['center']
        enc = self.encoder
        if (enc.get('model_version') != 'chelsea-matched-amenities-v1'
                or enc.get('ablation_variant') != 'full'
                or enc.get('bedroom_encoding') != 'incremental'
                or enc.get('features') != CORE_FEATURES):
            raise ValueError('Only the full centered incremental robust encoder is supported')
        if not all(math.isfinite(x) for x in [self.center,*self.beta]):
            raise ValueError('Nonfinite model coefficient')
        self.periods = [month(p) for p in enc['periods']]
        if not self.periods or any(month_distance(a,b)!=1 for a,b in zip(self.periods,self.periods[1:])):
            raise ValueError('Model months must be contiguous')
        groups = [('features',len(CORE_FEATURES)),('trend',len(self.periods)),('season',12),
                  ('building',len(enc['buildings'])),('unit',len(enc['units'])),
                  ('amenities',len(enc['amenity_features']))]
        offset = 0
        for name,size in groups:
            if list(enc['offsets'][name]) != [offset,offset+size]:
                raise ValueError('Invalid encoder offsets')
            offset += size
        if len(self.beta) != offset or enc['n_parameters'] != offset:
            raise ValueError('Coefficient dimension mismatch')
        expected = [v for name in enc['amenity_numeric'] for v in (name,name+'.unknown')]
        # JSON canonicalization sorts mapping keys; saved feature order is authoritative.
        if set(expected) | {f'{name}={value}' for name,levels in enc['amenity_categories'].items() for value in levels} != set(enc['amenity_features']):
            raise ValueError('Amenity feature metadata mismatch')
        if len(enc['amenity_active_columns']) != len(enc['amenity_features']):
            raise ValueError('Amenity mask dimension mismatch')
        for support in enc['amenity_numeric'].values():
            if not math.isfinite(support['scale']) or support['scale'] <= 0:
                raise ValueError('Invalid amenity scale')
        self.lookups = {name:{value:i for i,value in enumerate(enc[name+'s'])} for name in ('building','unit')}

    @classmethod
    def load(cls, path):
        import json
        manifest,files = _verified_bundle(Path(path),retain={'model.json'})
        if manifest.get('model_version') != VERSION:
            raise ValueError('Not a portable robust pricing bundle')
        if (manifest.get('runtime_sha256')!=digest(__file__)
                or manifest.get('pricing_features_sha256')!=digest(pricing.__file__)):
            raise ValueError('Portable runtime or feature implementation differs from exported bundle')
        model = cls(json.loads(files['model.json']))
        model.manifest = manifest
        return model

    def _encode(self, record, prediction_month):
        row = _normalize(record)
        bedrooms = pricing._number(row.get('bedrooms'))
        bathrooms = pricing._number(row.get('bathrooms'))
        if (bedrooms is None or not 0 <= bedrooms <= 5 or bedrooms%1
                or bathrooms is None or not 1 <= bathrooms <= 5 or (bathrooms*2)%1):
            raise ValueError('Layout outside validated support: bedrooms 0–5, bathrooms 1–5 in half steps')
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('unit_id','building_id')):
            raise ValueError('Canonical unit_id and building_id are required')
        known_building=self.artifact['training'].get('unit_buildings',{}).get(row['unit_id'])
        if known_building is not None and known_building!=row['building_id']:
            raise ValueError('Known canonical unit is paired with a different building')
        row.update(bedrooms=bedrooms,bathrooms=bathrooms)
        at = month(prediction_month); enc = self.encoder
        row['observed_at'] = at.isoformat()
        size = pricing._number(row.get('square_feet'))
        if size is not None and not 150 <= size <= 6000:
            size = None
        median = enc['size_medians'].get(str(int(bedrooms)),enc['size_default'])
        values = [1.,*[float(bedrooms>n) for n in range(5)],bathrooms-1,
                  math.log(size/median) if size is not None else 0.,float(size is None)]
        encoded = {i:value for i,value in enumerate(values) if value}
        labels = {i:name for i,name in enumerate(CORE_FEATURES)}
        trend = min(max(month_distance(self.periods[0],at),0),len(self.periods)-1)
        i = enc['offsets']['trend'][0]+trend; encoded[i]=1.; labels[i]='trend:'+self.periods[trend].strftime('%Y-%m')
        i = enc['offsets']['season'][0]+at.month-1;encoded[i]=1.;labels[i]='season:'+str(at.month)
        for group,field in [('building','building_id'),('unit','unit_id')]:
            key = row[field]
            if key in self.lookups[group]:
                i=enc['offsets'][group][0]+self.lookups[group][key]
                encoded[i]=1.;labels[i]=group+':'+str(key)
        raw = pricing._raw_features(row,'2000-01-01')
        warnings = []
        if size is None:
            warnings.append('Square footage is unknown or outside 150–6000; the training missing-size encoding is used.')
        for index,name in enumerate(enc['amenity_features']):
            if '=' in name:
                field,level=name.split('=',1)
                category=pricing._category(row.get(field))
                centers=enc['amenity_category_centers'][field]
                value = (float(category=='__unknown__') if level=='__unknown__' else
                         float(category==level)-centers[level] if category in centers else 0.)
            else:
                unknown=name.endswith('.unknown');field=name.removesuffix('.unknown')
                support=enc['amenity_numeric'][field]; observed=raw[field]
                value = float(observed is None) if unknown else (
                    (observed-support['center'])/support['scale']
                    if observed is not None and support['unique_values']>1 else 0.)
                if not unknown and observed is not None and support['unique_values']<2:
                    warnings.append(field+': no identified magnitude contrast in training data.')
            value *= float(enc['amenity_active_columns'][index])
            i=enc['offsets']['amenities'][0]+index
            if value:
                encoded[i]=value;labels[i]='amenity:'+name
        for field,levels in enc['amenity_categories'].items():
            category=pricing._category(row.get(field))
            if category not in levels and category!='__unknown__':
                warnings.append(field+': unseen category; no category contrast is identified.')
        return encoded,labels,warnings,row,at

    def predict(self, record, prediction_month):
        encoded,labels,warnings,row,at=self._encode(record,prediction_month)
        contributions={'center':self.center,**{labels[i]:self.beta[i]*value for i,value in encoded.items()}}
        log_prediction=math.fsum(contributions.values())
        rent=math.exp(log_prediction)
        if not math.isfinite(rent):
            raise ValueError('Nonfinite prediction')
        familiar = ('seen_unit' if row['unit_id'] in self.lookups['unit'] else
                    'new_unit_seen_building' if row['building_id'] in self.lookups['building'] else 'new_building')
        if familiar=='new_building':
            warnings.append('No fitted building effect; unseen-building errors are materially larger.')
        return {'predicted_rent':rent,'prediction_month':at.strftime('%Y-%m'),
                'forecast_horizon_months':month_distance(self.periods[-1],at),
                'training_end_month':self.periods[-1].strftime('%Y-%m'),'familiarity':familiar,
                'log_components':contributions,
                'uncertainty':{'status':'unsupported_new_building' if familiar=='new_building' else 'not_calibrated_for_serving',
                               'interval':None,
                               'reason':'Pooled new-building bands failed validation.' if familiar=='new_building' else
                                        'Research residual bands have not been promoted as a serving calibration artifact.'},
                'warnings':sorted(set(warnings)),
                'interpretation':'Conditional advertised asking rent; log components sum to log rent but are not standalone amenity premiums.'}

    def marginal_contributions(self, record, changes, prediction_month):
        allowed={*pricing.NUMERIC,*pricing.CATEGORICAL,*pricing.EXPOSURES,'elevator'}-{'building_id'}
        normalized={next((k for k,aliases in pricing.ALIASES.items() if key in aliases),key):value
                    for key,value in changes.items()}
        if not normalized or set(normalized)-allowed or len(normalized)!=len(changes):
            raise ValueError('Supply distinct supported attribute changes; identity/date changes are not amenity contrasts')
        before_record=_normalize(record);after_record={**before_record,**normalized}
        before=self.predict(before_record,prediction_month);after=self.predict(after_record,prediction_month)
        warnings=before['warnings']+after['warnings']
        unknown=False
        for field in normalized:
            if field in self.encoder['amenity_categories']:
                unknown |= any(pricing._category(r.get(field))=='__unknown__' for r in (before_record,after_record))
            elif field in pricing.EXPOSURES:
                unknown |= any(r.get(field) is None for r in (before_record,after_record))
            else:
                unknown |= any(r.get(field) is None for r in (before_record,after_record))
        if unknown:
            warnings.append('A changed attribute has an unknown reference or destination; this includes reporting-pattern changes, not an identified physical amenity contrast.')
        return {'baseline_rent':before['predicted_rent'],'changed_rent':after['predicted_rent'],
                'dollar_change':after['predicted_rent']-before['predicted_rent'],
                'percent_change':(after['predicted_rent']/before['predicted_rent']-1)*100,
                'changes':normalized,'status':'unknown_attribute_contrast' if unknown else 'computed',
                'warnings':sorted(set(warnings)),
                'interpretation':'Conditional model contrast with interactions recomputed; not causal or personal willingness to pay.'}
