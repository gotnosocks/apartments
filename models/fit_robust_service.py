"""Fit the fixed validated specification for one explicit pricing month.

This refit creates a point-prediction artifact, not a new validation result. It
requires a verified historical projection whose knowledge cutoff has passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, UTC
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import pricing, robust_pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_ablation as ablation
from . import amenity_rent_model as amenities
from . import minimal_rent_model as baseline
from . import amenity_ablation_contrasts as contrasts


def run(dataset, validation, output, *, prediction_month):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        vp,vf=_verified_bundle(Path(validation)/'protocol',retain={'protocol.json'})
        vs,_=_verified_bundle(Path(validation)/'summary')
        validation_protocol=json.loads(vf['protocol.json'])
        vh=hashlib.sha256(canonical(validation_protocol).encode()).hexdigest()
        if (validation_protocol.get('version')!='chelsea-sequential-monthly-v1'
                or vp.get('protocol_sha256')!=vh or vs.get('protocol_sha256')!=vh):
            raise ValueError('Verified completed monthly validation required')
        paths=[Path(m.__file__) for m in (baseline,amenities,ablation,contrasts,pricing)]
        for path in paths:
            if digest(path)!=validation_protocol['implementation_sha256'][path.name]:
                raise ValueError('Scientific implementation differs from validated specification')
        versions={k:importlib.metadata.version(k) for k in validation_protocol['versions']}
        if versions!=validation_protocol['versions'] or amenities.SETTINGS!=validation_protocol['settings']:
            raise ValueError('Runtime or settings differ from validated specification')
        data,source,coverage=amenities.load_analytical(dataset)
        cutoff=pricing._timestamp(source['as_of'])
        if cutoff>datetime.now(UTC):
            raise ValueError('Analytical knowledge cutoff is still in the future; rebuild at a passed cutoff')
        origin=robust_pricing.month(prediction_month)
        train=data[data.period<pd.Timestamp(origin.date())].copy()
        if len(train)<100 or train.period.nunique()<24:
            raise ValueError('At least 100 rows and 24 historical months required')
        if pd.to_datetime(train.known_at,utc=True).max()>cutoff:
            raise ValueError('Training evidence is later than analytical knowledge cutoff')
        if train.groupby('unit_id').building.nunique().gt(1).any():
            raise ValueError('Canonical training unit maps to multiple buildings')
        if robust_pricing.month_distance(robust_pricing.month(str(train.period.max().date())),origin)!=1:
            raise ValueError('Source must cover the month immediately before the pricing month')
        if origin<robust_pricing.month(cutoff):
            raise ValueError('Serving pricing month cannot precede evidence knowledge month')
        paths += [Path(__file__),Path(robust_pricing.__file__)]
        protocol={'version':'fixed-robust-serving-fit-v1','source_manifest':source,
                  'validation_protocol_sha256':vh,'validation_summary_manifest':vs,
                  'settings':amenities.SETTINGS,'unit_effect':True,'iterations':20,
                  'pricing_month':origin.strftime('%Y-%m'),'train_rows':len(train),
                  'train_sha256':contrasts.membership(train),'versions':versions,
                  'implementation_sha256':{p.name:digest(p) for p in paths}}
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',
                                      **{p.name:p.read_text() for p in paths}},
                       {'protocol_sha256':ph,'version':protocol['version']})
        if (root/'model'/'complete.json').exists():
            manifest,_=_verified_bundle(root/'model')
            if manifest.get('serving_protocol_sha256')!=ph:
                raise ValueError('Existing serving model has different protocol')
            robust_pricing.RobustPricingModel.load(root/'model')
            return manifest
        fitted=baseline.fit(train,amenities.SETTINGS,iterations=20,encoder_class=ablation.encoder_class('full'))
        change=fitted['robust_objective_relative_change']
        if change is None or not np.isfinite(change) or change>1e-5:
            raise ValueError('Serving refit did not converge')
        artifact={'version':robust_pricing.VERSION,'encoder':fitted['encoder'].metadata(),
                  'coefficients':fitted['beta'].tolist(),'center':fitted['center'],
                  'training':{'start_month':str(train.period.min().date()),'end_month':str(train.period.max().date()),
                              'rows':len(train),'units':int(train.unit_id.nunique()),'buildings':int(train.building.nunique()),
                              'knowledge_cutoff':cutoff.isoformat(),'source_manifest':source,
                              'latest_evidence_known_at':str(train.known_at.max()),
                              'unit_buildings':dict(train[['unit_id','building']].drop_duplicates().itertuples(index=False,name=None)),
                              'source_listing_ids':sorted(set(train.source_listing_id.astype(str))),
                              'membership_sha256':protocol['train_sha256']},
                  'validation':{'experiment_protocol_sha256':vh,'summary_manifest':vs,
                                'max_serving_horizon_months':1,'pricing_month':origin.strftime('%Y-%m'),
                                'mode':'fixed specification refit; preceding retrospective validation is not a fresh test'},
                  'limitations':['Conditional gross asking rent, not signed lease rent or current availability.',
                                 'No calibrated interval is served; unfamiliar-building pooled bands failed validation.',
                                 'Later-collected historical attributes and archive selection limit market interpretation.',
                                 'The refit uses previously analyzed 2025–2026 data and has no new prospective performance result.']}
        portable=robust_pricing.RobustPricingModel(artifact)
        # Check every training identity/attribute combination at the serving month.
        probe=train.copy();probe['period']=pd.Timestamp(origin.date())
        expected=np.exp(baseline.predict(fitted,probe))
        actual=np.array([portable.predict(row,origin)['predicted_rent'] for row in probe.to_dict('records')])
        if not np.allclose(actual,expected,rtol=1e-11,atol=1e-8):
            raise ValueError('Portable serving predictions disagree with scientific encoder')
        parity={'rows':len(probe),'pricing_month':origin.strftime('%Y-%m'),
                'maximum_absolute_dollar_difference':float(np.max(abs(actual-expected))),
                'maximum_relative_difference':float(np.max(abs(actual/expected-1)))}
        # Publication time is recorded once and retained by verified no-refit replay.
        artifact['published_at']=datetime.now(UTC).isoformat()
        if any(digest(p)!=protocol['implementation_sha256'][p.name] for p in paths):
            raise ValueError('Implementation changed during serving fit')
        return publish_bundle(root/'model',{'model.json':canonical(artifact)+'\n',
                                          'parity.json':canonical(parity)+'\n',
                                          'diagnostics.json':canonical({'objective_relative_change':change,'solves':fitted['solves'],
                                                                         'source_coverage':coverage})+'\n'},
                              {'model_version':robust_pricing.VERSION,'serving_protocol_sha256':ph,
                               'runtime_sha256':digest(robust_pricing.__file__),
                               'pricing_features_sha256':digest(pricing.__file__)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--validation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prediction-month',required=True)
    args=parser.parse_args()
    print(canonical(run(args.dataset,args.validation,args.output,prediction_month=args.prediction_month)))
