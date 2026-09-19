"""Regenerate the eight reviewed current cases against a completed joint posterior.

Reuse the explicitly frozen development panel across fits. Residual ranks may
change; panel membership does not. New cases need a separate source review.
"""
from pathlib import Path
import argparse
import json
import gzip
import hashlib
from apartments.bayesian_analysis import BayesianAnalysis
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from apartments.granular_parse import parse_listing
root=Path('/home/ben/code/apartments')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--experiment',type=Path,default=root/'data/model/chelsea-bayesian-current-floor-disk-20260918')
parser.add_argument('--dataset',type=Path,default=root/'data/model/chelsea-reviewed-current-analysis-20260918')
parser.add_argument('--descriptions',type=Path,default=root/'data/model/chelsea-refreshed-bayesian-descriptions-20260918')
parser.add_argument('--output',type=Path,default=root/'data/model/chelsea-current-residual-source-review-20260918')
args=parser.parse_args()
experiment,dataset,descriptions=args.experiment,args.dataset,args.descriptions
panel_path=root/'config/reviews/chelsea-residual-development-panel-20260919.json'
panel=json.loads(panel_path.read_text())
review={
 '5155021':('bedroom_count_conflict','Structured bedroomCount=0 and roomCount=1 conflict with an explicit one-bedroom description. Same-line photos do not resolve the listed apartment layout. Do not choose the count by closeness to fitted rent; withhold bargain/premium interpretation until layout evidence resolves it.'),
 '5116119':('known_bathroom_conflict_and_private_terrace','Previously reviewed two-full/zero-half source counts conflict with two en suites plus a powder room. Composition is already masked. Private terrace and luxury finishes remain candidate omitted features; the description cannot identify their separate prices.'),
 '5155202':('unmodeled_explicit_floor_and_renovation','Own-apartment first-floor claim and newly updated kitchen/bath/windows are explicit. Floor is unknown in this analytical row; review-based enrichment can add the claim without deriving physical height. Renovation is a candidate feature, not a residual-based price repair.'),
 '5161975':('no_new_count_error_identified','Structured studio agrees with the description. Building services are present; apartment area is unknown. No new numeric source correction is established from this text.'),
 '5159492':('layout_and_renovation_candidate','One-bedroom count agrees. Description reports renovation, a windowed kitchen/bath and French doors. Area is unknown. These are candidate layout/condition features; a negative residual alone does not identify a missing feature.'),
 '5128483':('building_template_and_monthly_fees','Description mostly describes the building, including its 32 stories; do not treat that as the apartment floor. Recurring amenity and billing fees matter for user total cost, while this fit targets advertised base asking rent. No net/gross correction is established.'),
 '5115645':('private_elevator_loft_and_stale_description_price','Private elevator access to the third floor, high ceilings, long loft layout and south exposure are explicit candidate attributes. Optional furnishings cost extra. Earlier reviewed own price history supports the current $6,950 ask despite stale $7,750 description text.'),
 '5163034':('unmodeled_explicit_floor_and_renovation','Two-bedroom count agrees; first-floor apartment, new kitchen and in-unit laundry are explicit. Laundry is already represented. First-floor and renovation evidence are candidates for reviewed enrichment.'),
}
analysis=BayesianAnalysis.load(experiment,dataset)
try:
 evidence=load_evidence(dataset,descriptions)
 current=analysis.summary['current_residuals']
 ranked=sorted(current,key=lambda r:(-abs(r['residual_log']),r['audit_id']))
 panel_ids=panel['source_listing_ids']
 assert len(panel_ids)==len(set(panel_ids)) and set(panel_ids)==set(review)
 selected=[r for r in ranked if r['source_listing_id'] in panel_ids]
 assert len(selected)==len(panel_ids) and {r['source_listing_id'] for r in selected}==set(panel_ids)
 ranks={r['audit_id']:i+1 for i,r in enumerate(ranked)}
 cases=[]
 for row in selected:
  ad=row['source_listing_id']; kind,reason=review[ad]
  detail=analysis.detail(row['audit_id'])
  assert detail['contribution_diagnostics']['acceptable']
  cases.append({'rank_by_absolute_current_log_residual':ranks[row['audit_id']],
    'source_listing_id':ad,'review_kind':kind,'review_reason':reason,
    'residual':row,'joint_posterior_detail':detail,'source_captures':evidence[row['audit_id']]})
 rawpath=root/'data/probes/chelsea-discovery-details-20260918/archive/bodies/8c/8cfe74da1351f97f571a20ff8331d764b9becca30923ca79c85e35ea1d99d2ec.gz'
 body=gzip.decompress(rawpath.read_bytes()); assert hashlib.sha256(body).hexdigest()==rawpath.stem
 parsed,_=parse_listing(body,'https://streeteasy.com/rental/5155021');payload=json.loads(parsed['raw_listing_json'])
 target=next(c for c in cases if c['source_listing_id']=='5155021')
 assert str(payload['id'])=='5155021' and payload['propertyDetails']['bedroomCount']==0
 assert target['source_captures'][0]['description']==payload['description']
 scenario=analysis.counterfactual(target['residual']['audit_id'],{'bedrooms':1})
 target['raw_bedroom_fields']={k:payload['propertyDetails'].get(k) for k in ('bedroomCount','roomCount')}
 result={'version':'current-residual-source-case-review-v1','cases':len(cases),'current_rows':len(current),
  'all_case_contribution_diagnostics_pass':True,'bedroom_scenario_status':scenario['status'],
  'main_model_changed':False,'source_counts_or_prices_changed':False,
  'panel_id':panel['panel_id'],'selection_policy':panel['purpose'],
  'interpretation':'Residual-selected development review, not an independent feature validation or market accuracy estimate. Scenario changes reported bedrooms under the fitted joint posterior; it does not resolve source truth or refit building/unit offsets.'}
 publish_bundle(args.output,{
  'cases.jsonl':''.join(canonical(c)+'\n' for c in cases),
  'bedroom-source-scenario.json':canonical(scenario)+'\n','summary.json':canonical(result)+'\n',
  'review_current_residual_cases.py':Path(__file__).read_text(),
  'development-panel.json':panel_path.read_text()},
  {'version':result['version'],'fit_manifest_sha256':digest(experiment/'fit/complete.json'),
   'dataset_manifest_sha256':digest(dataset/'complete.json'),'descriptions_manifest_sha256':digest(descriptions/'complete.json'),
   'raw_body_sha256':rawpath.stem,'implementation_sha256':digest(Path(__file__))})
 print(canonical(result),flush=True)
 print(canonical({k:scenario.get(k) for k in ['status','delta_percent','before_rent','after_rent','diagnostics']}),flush=True)
finally:
 analysis.close()
