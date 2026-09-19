from pathlib import Path
import json,re
from collections import Counter
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
root=Path('/home/ben/code/apartments/data/model'); dataset=root/'chelsea-reviewed-current-analysis-20260918'
dm,df=_verified_bundle(dataset,retain={'observations.jsonl','current-source-evidence.jsonl'})
rows={r['audit_id']:r for line in df['observations.jsonl'].decode().splitlines() if (r:=json.loads(line))['analysis_price_basis']=='current_capture_gross_ask'}
word={'one':1,'two':2,'three':3,'four':4,'five':5}
pattern=re.compile(r'(?<![\w.])(\d+(?:\.\d+)?|one|two|three|four|five)[\s-]+bed(?:room)?s?\b',re.I)
assert pattern.search('Beautiful 1.5 Bedroom').group(1)=='1.5'
classes={}
for ads,kind in [
 ('5128130 5105519 5142129 5162288 5155093 5129824 5145603 5123323 5099751 5129573 5163476 5160167 5157053','building_inventory'),
 ('5154473 5156197','fractional_marketing_layout_and_building_inventory'),
 ('5112310 5161269','negated_conversion'),('5162581','alternative_layout'),
 ('5137952','flex_alcove'),('5155021','unresolved_count_conflict')]:
 for ad in ads.split(): classes[ad]=kind
reasons={
 'building_inventory':'Counts refer to the range of apartments offered by the building, not the listed apartment.',
 'fractional_marketing_layout_and_building_inventory':'The own headline markets 1.5 bedrooms; retain this fractional wording as extra-layout evidence, not five bedrooms or a repaired integer count. Other counts describe building inventory.',
 'negated_conversion':'The mismatching count occurs in an explicit denial of flexing/converting to that number of bedrooms.',
 'alternative_layout':'The description presents a one-bedroom-plus-home-office alternative to the listed two-bedroom layout.',
 'flex_alcove':'The studio is marketed as a flex one-bedroom with a sleeping alcove; this is layout/convertibility evidence, not proof of a separate bedroom.',
 'unresolved_count_conflict':'Own headline says one bedroom while structured bedroomCount=0 and roomCount=1. Captured same-line images cannot resolve it. No count is selected by model residual.'}
findings=[]
for line in df['current-source-evidence.jsonl'].decode().splitlines():
 e=json.loads(line);row=rows[e['audit_id']];text=e['description'] or ''
 assert e['unit_id']==row['unit_id'] and e['source_listing_id']==row['source_listing_id']
 claims=[]
 for m in pattern.finditer(text):
  token=m.group(1).lower();value=word[token] if token in word else float(token)
  if value==row['bedrooms']:continue
  start,end=max(0,m.start()-100),min(len(text),m.end()+170)
  claims.append({'value_as_written':value,'start':m.start(),'end':m.end(),'literal':m.group(),
                 'context_start':start,'context_end':end,'context':text[start:end]})
 if claims:
  ad=row['source_listing_id'];kind=classes[ad]
  findings.append({'audit_id':row['audit_id'],'source_listing_id':ad,'source_bedrooms':row['bedrooms'],
   'family':kind,'manual_review_reason':reasons[kind],'claims':claims,'source_evidence':e,
   'source_row_sha256':__import__('hashlib').sha256(canonical(row).encode()).hexdigest()})
assert {r['source_listing_id'] for r in findings}==set(classes)
summary={'version':'current-bedroom-claim-development-audit-v1','current_rows_scanned':len(rows),
 'candidate_rows':len(findings),'review_families':dict(Counter(r['family'] for r in findings)),
 'policy':'Development review of an explicit-number bedroom phrase screen across current captures, not an exhaustive accuracy estimate. Decimal marketing counts are preserved literally. No automatic bedroom correction or floor/room legality inference. Only one reviewed candidate is an unresolved own-apartment integer-count contradiction.'}
publish_bundle(root/'chelsea-current-bedroom-claim-review-20260918',{
 'findings.jsonl':''.join(canonical(r)+'\n' for r in findings),'summary.json':canonical(summary)+'\n',
 'audit_current_bedroom_claims.py':Path(__file__).read_text()},
 {'version':summary['version'],'source_manifest_sha256':digest(dataset/'complete.json'),'summary':summary})
print(canonical(summary))
