"""Export a verified monthly fit after testing portable prediction parity."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import robust_pricing, pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_rent_model as amenities
from . import minimal_rent_model as baseline
from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrasts


def export(dataset, experiment, output, *, prediction_month):
    root=Path(experiment);at=robust_pricing.month(prediction_month)
    name=at.strftime('%Y-%m')
    pm,pf=_verified_bundle(root/'protocol',retain={'protocol.json'})
    protocol=json.loads(pf['protocol.json'])
    protocol_hash=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    if protocol.get('version')!='chelsea-sequential-monthly-v1' or pm.get('protocol_sha256')!=protocol_hash:
        raise ValueError('Verified sequential monthly protocol required')
    summary,_=_verified_bundle(root/'summary')
    if summary.get('protocol_sha256')!=protocol_hash:
        raise ValueError('Completed experiment protocol mismatch')
    for module in (amenities,baseline,ablation,contrasts,pricing):
        if digest(module.__file__)!=protocol['implementation_sha256'][Path(module.__file__).name]:
            raise ValueError('Executed model implementation differs from experiment')
    if any(importlib.metadata.version(k)!=v for k,v in protocol['versions'].items()):
        raise ValueError('Model runtime version differs from experiment')
    split=next((s for s in protocol['splits'] if s['month']==at.strftime('%Y-%m-%d')),None)
    if split is None:
        raise ValueError('Month absent from completed experiment')
    fm,ff=_verified_bundle(root/name/'fit',retain={'models.json','diagnostics.json'})
    if fm.get('protocol_sha256')!=protocol_hash or any(fm.get(k)!=v for k,v in split.items()):
        raise ValueError('Fit identity does not match requested month')
    diagnostic=json.loads(ff['diagnostics.json'])
    if not 0<=diagnostic['objective_relative_change']<=1e-5:
        raise ValueError('Unconverged fit')
    data,source,_=amenities.load_analytical(dataset)
    if source!=protocol['source_manifest']:
        raise ValueError('Analytical source differs from fitted source')
    naive=pd.Timestamp(at.date());train=data[data.period<naive];test=data[data.period.eq(naive)]
    if (contrasts.membership(train)!=split['train_sha256']
            or contrasts.membership(test)!=split['test_sha256']):
        raise ValueError('Fit train/test membership differs from source')
    if train.groupby('unit_id').building.nunique().gt(1).any():
        raise ValueError('Canonical training unit maps to multiple buildings')
    saved=json.loads(ff['models.json'])['amenities']
    artifact={'version':robust_pricing.VERSION,'encoder':saved['encoder'],
              'coefficients':saved['beta'],'center':saved['center'],
              'training':{'start_month':str(train.period.min().date()),'end_month':str(train.period.max().date()),
                          'rows':len(train),'units':int(train.unit_id.nunique()),'buildings':int(train.building.nunique()),
                          'knowledge_cutoff':source.get('as_of'),
                          'latest_evidence_known_at':str(train.known_at.max()) if 'known_at' in train else None,
                          'unit_buildings':dict(train[['unit_id','building']].drop_duplicates().itertuples(index=False,name=None)),
                          'source_listing_ids':sorted(set(train.source_listing_id.astype(str))),
                          'source_manifest':source,'membership_sha256':split['train_sha256']},
              'validation':{'experiment_protocol_sha256':protocol_hash,'fit_manifest':fm,
                            'prediction_month':name,'mode':'retrospective development; later-collected attributes',
                            'max_serving_horizon_months':1},
              'limitations':['Market associations and renter willingness to pay are separate.',
                             'This exported historical fit is not a current-market model.',
                             'No uncertainty band is promoted; pooled bands failed for unfamiliar buildings.']}
    portable=robust_pricing.RobustPricingModel(artifact)
    encoder=amenities.AmenityEncoder.__new__(amenities.AmenityEncoder)
    for key,value in saved['encoder'].items():
        setattr(encoder,key,value)
    encoder.periods=pd.DatetimeIndex(pd.to_datetime(encoder.periods))
    fitted={'encoder':encoder,'beta':np.asarray(saved['beta']),'center':saved['center']}
    expected=np.exp(baseline.predict(fitted,test))
    actual=np.array([portable.predict(row,name+'-01')['predicted_rent'] for row in test.to_dict('records')])
    relative=float(np.max(abs(actual/expected-1)))
    if not np.allclose(actual,expected,rtol=1e-11,atol=1e-8):
        raise ValueError('Portable encoder predictions differ from scientific implementation')
    parity={'rows':len(test),'maximum_absolute_dollar_difference':float(np.max(abs(actual-expected))),
            'maximum_relative_difference':relative,'test_membership_sha256':split['test_sha256']}
    return publish_bundle(output,{'model.json':canonical(artifact)+'\n','parity.json':canonical(parity)+'\n',
                                  'producer.py':Path(__file__).read_text(),
                                  'runtime.py':Path(robust_pricing.__file__).read_text()},
                          {'model_version':robust_pricing.VERSION,'protocol_sha256':protocol_hash,
                           'fit_manifest_sha256':hashlib.sha256(canonical(fm).encode()).hexdigest(),
                           'runtime_sha256':digest(robust_pricing.__file__),
                           'pricing_features_sha256':digest(pricing.__file__)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prediction-month',required=True)
    args=parser.parse_args()
    print(canonical(export(args.dataset,args.experiment,args.output,prediction_month=args.prediction_month)))
