"""Publish manually read source findings for the fixed 26-unit development panel."""
import argparse
from pathlib import Path
import json
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle

# Explicit human-readable adjudications after reading every distinct full capture description.
REVIEWS={
'3393536':('label_only','Building description says elevator but gives no unit floor.', ['every apartment in this prewar elevator building'],[]),
'1411908':('label_only','Amenities and apartment description give no unit floor.', [],[]),
'665337':('stairs_compatible_not_physical_mapping','One flight is compatible with label2 under ordinary numbering; no physical-floor correction follows.', ['1 flight walk-up.'],[]),
'3259307':('count_and_access_ambiguity','Label1 and archived building count1 coexist with a short walk-up. Building count is only a compatibility screen; physical level remains unresolved.', ['Short Walk Up in intercom building.'],['building_count_and_numbering_review']),
'1856232':('label_only','No unit floor or elevator statement in the captured description.', [],[]),
'3642673':('label_only','Short advertisement gives no independent floor statement; video link not opened.', [],[]),
'4094446':('literal_floor_agrees','Unit-specific fourth-floor prose agrees with label4; original advertised_floor is null, so explicit-description extraction missed this corroboration.', ['perfectly positioned on the 4th floor on the south side of the Tower.'],['explicit_floor_extractor_coverage']),
'2789377':('label_only_with_price_basis_lead','No unit floor assertion. Description explicitly calls advertised rent net effective; historical target4530 needs original-price-path review before a correction.', ['-Rent advertised is net effective for 1 month free on an 12 month lease term.'],['own_price_basis_review']),
'3024360':('stairs_label_offset_ambiguity','Unit4A says four flights up. Label4 must not be treated as a verified count of floors above ground; source contains a potential numbering offset.', ['Apartment 4A features beautiful exposed brick', 'Four (4) flights up in a walk-up building.'],['numbering_and_physical_floor_review']),
'3759993':('building_count_agrees_only','Five-story building prose agrees with captured count5; it does not independently establish the unit floor3.', ['452 W. 23rd is an intimate five-story prewar walk-up building with only 9 units.'],[]),
'1235296':('label_only','Room description and address give no independent floor or elevator assertion.', [],[]),
'4431461':('label_only','Balcony, high ceilings and light are not an independent floor measurement.', [],[]),
'2700478':('label_only_with_price_basis_lead','No unit floor assertion. Target3208 coexists with explicit advertised-net text and gross3850; verify own historical price path before changing price basis.', ['ADVERTISED AMOUNT IS THE NET EFFECTIVE RENT BASED ON 2 MONTHS FREE FOR LEASES STARTING BY 4/15, GROSS RENT IS $3,850'],['own_price_basis_review']),
'3100003':('label_only','Floor-to-ceiling doors and heated floors refer to finishes, not floor level.', [],[]),
'3921499':('literal_floor_agrees','Explicit sixth-floor walk-up agrees with label6; original advertised_floor is null.', ['**Note this is a sixth floor walk up.'],['explicit_floor_extractor_coverage']),
'4114823':('literal_floor_agrees','Explicit sixth-floor unit agrees with label6; original advertised_floor is null.', ['Located in a well maintained and professionally managed walk up building, 6th floor unit.'],['explicit_floor_extractor_coverage']),
'3010982':('label_only_missing_building_count','Single-digit label7 admitted without building count under the declared policy. Prose names London Terrace Gardens but does not establish unit floor or elevator.', ['London Terrace Gardens Pre-War charm in an excellent location.'],['building_entity_and_elevator_evidence']),
'3798517':('label_only_missing_building_count','Single-digit label9 admitted without building count. Doorman and concierge language does not independently establish elevator presence.', ['London Terrace Gardens, located in the heart of fashionable West Chelsea, is a part of the history of New York.'],['building_entity_and_elevator_evidence']),
'3941179':('building_count_agrees_only','32-story building prose agrees with captured count32; label14 remains a proxy.', ['The 32-story luxury apartment building is breathtaking both inside and out'],[]),
'2019944':('qualitative_high_floor_only','High-floor description is qualitatively compatible with label15 but does not verify its literal level.', ['This newly renovated high-floor sun-blasted 1BR/1BTH condo'],[]),
'1778297':('label_only','Corner, prewar and high ceilings do not independently identify floor10.', [],['building_elevator_evidence']),
'3676084':('label_only','High Line views and floor-to-ceiling windows do not independently identify floor11 or elevator.', [],['building_elevator_evidence']),
'5058235':('qualitative_high_floor_only','High-floor description is compatible with label29; full-floor amenities describe shared space, not a unit floor measurement.', ['HIGH FLOOR 1 BEDROOM - Sunny South Exposure'],[]),
'4228899':('building_starting_floor_not_unit_floor','Apartments starting on26 is a building-wide range, not an explicit assertion that unit48I is on26. Label48 passes captured count53.', ['offering exquisite apartments starting on the 26th floor.'],[]),
'3721679':('building_starting_floor_not_unit_floor','Building-wide start26 is not the floor of unit33C. Elevator unknown remains unknown until source-specific review; another panel ad in this building has elevatorTrue.', ['offering exquisite apartments starting on the 26th floor.'],['building_elevator_evidence']),
'2032521':('building_starting_floor_not_unit_floor','Building-wide start26 is not the floor of unit52H. Elevator unknown remains unknown until source-specific review.', ['offering exquisite apartments starting on the 26th floor.'],['building_elevator_evidence']),
}


def run(panel,output,as_of):
    panel=Path(panel); manifest,files=_verified_bundle(panel,retain={'cases.jsonl','selection.json'})
    cases=[json.loads(l) for l in files['cases.jsonl'].decode().split('\n') if l]
    if {c['observation']['source_listing_id'] for c in cases} != set(REVIEWS):raise ValueError('Manual review identity set differs from fixed panel')
    decisions=[]
    for case in cases:
        row=case['observation'];status,note,quotes,followups=REVIEWS[row['source_listing_id']]
        spans=[]
        for quote in quotes:
            matched=False
            for capture in case['descriptions']:
                text=capture['description'] or '';start=text.find(quote)
                if start<0:continue
                matched=True
                spans.append({k:capture[k] for k in ('capture_id','raw_listing_sha256','body_sha256','description_sha256')}|
                    {'start':start,'end':start+len(quote),'literal':quote})
            if not matched:raise ValueError('Manual quote not present in own captured description')
        decisions.append({k:row[k] for k in ('audit_id','unit_id','source_listing_id','building')}|
            {'cell':case['panel_cell'],'status':status,'note':note,'reviewed_at':as_of,
             'reviewer':'Codex manual reading of every distinct full captured description',
             'quotes':spans,'followups':followups,'applied_correction':False})
    return publish_bundle(output,{'decisions.jsonl':''.join(canonical(d)+'\n' for d in decisions),
        Path(__file__).name:Path(__file__).read_text()}, {'version':'floor-source-development-panel-review-v1',
        'panel_manifest_sha256':digest(panel/'complete.json'),'reviewed_units':len(decisions),'reviewed_at':as_of,
        'policy':'Manual source interpretation only. This panel is not independent ground truth, a population accuracy study, or a holdout. No dataset or model correction applied.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('panel','output','as-of'):p.add_argument('--'+name,required=True)
    print(canonical(run(**vars(p.parse_args()))))
