from copy import deepcopy
import hashlib
import json

import pytest

from apartments.corrections import canonical
from docs.analysis.scripts import check_spline_main_page as m


def example():
    row = {'audit_id':'a','unit_id':'unit:a','source_listing_id':'123',
           'analysis_price_basis':'historical_initial_own_advertisement_ask','furnished':None}
    message = 'A furnished rental; it does not establish furnished-only terms.'
    case = {k:row[k] for k in ('audit_id','unit_id','source_listing_id')}
    case.update(source_row_sha256=hashlib.sha256(canonical(row).encode()).hexdigest(),
                kinds=['furnished_offer_unmodeled'],messages=[message])
    notes = {'a':{'interpretation_limited':True,'message':message,
                  'issues':[{'kind':case['kinds'][0],'message':message}]}}
    return row,case,notes


def test_legacy_defaults_are_preserved_without_expanded_annotations():
    spec = m.load_expectations()
    assert spec['counts']=={'rows':52653,'current_rows':172,'known_floor_rows':29907,'source_review_cases':8}
    assert spec['historical_issues']==[]


def test_explicit_expanded_expectations_bind_four_issues_three_historical_ads():
    spec=m.load_expectations(m.ROOT/'docs/analysis/expanded-spline-main-page-expectations-20260919.json')
    assert spec['counts']['known_floor_rows']==35992
    assert spec['known_current_floor_rows']==134
    assert len(spec['historical_issues'])==3
    assert sum(len(r['kinds']) for r in spec['historical_issues'])==4
    by_ad={r['source_listing_id']:r for r in spec['historical_issues']}
    assert 'furnished_only_offer_unmodeled' in by_ad['4141846']['kinds']
    assert by_ad['4141846']['floor_scenario']=={'before':6.,'after':7.}
    assert by_ad['2021775']['kinds']==['furnished_offer_unmodeled']
    assert 'does not establish furnished-only' in by_ad['2021775']['messages'][0]


@pytest.mark.parametrize('fault',['bool_count','negative_count','missing_count','duplicate_audit',
                                 'missing_hash','missing_message','bad_current_count','unchanged_scenario'])
def test_invalid_explicit_expectations_fail(tmp_path,fault):
    spec=m.load_expectations(m.ROOT/'docs/analysis/expanded-spline-main-page-expectations-20260919.json')
    if fault=='bool_count':spec['counts']['rows']=True
    if fault=='negative_count':spec['counts']['rows']=-1
    if fault=='missing_count':del spec['counts']['source_review_cases']
    if fault=='duplicate_audit':spec['historical_issues'].append(deepcopy(spec['historical_issues'][0]))
    if fault=='missing_hash':del spec['source_issues_manifest_sha256']
    if fault=='missing_message':spec['historical_issues'][0]['messages']=[]
    if fault=='bad_current_count':spec['known_current_floor_rows']=173
    if fault=='unchanged_scenario':spec['historical_issues'][1]['floor_scenario']={'before':6.,'after':6.}
    path=tmp_path/'expectations.json';path.write_text(json.dumps(spec))
    with pytest.raises(ValueError):m.load_expectations(path)


def test_exact_historical_warning_and_source_are_preserved():
    row,case,notes=example()
    before=deepcopy((row,case,notes))
    result=m.verify_historical_notes([row],notes,[case])
    assert result[0]['source_record']==row and result[0]['note']==notes['a']
    assert (row,case,notes)==before


@pytest.mark.parametrize('fault',['wrong_unit','wrong_ad','changed_source','current','missing_annotation',
                                 'extra_annotation','strengthened_furnishing','changed_message',
                                 'dropped_merged_message','not_limited'])
def test_changed_identity_or_furnishing_strength_fails(fault):
    row,case,notes=example()
    if fault=='wrong_unit':row['unit_id']='unit:other'
    if fault=='wrong_ad':row['source_listing_id']='456'
    if fault=='changed_source':row['furnished']=True
    if fault=='current':row['analysis_price_basis']='current_capture_gross_ask'
    if fault=='missing_annotation':notes.clear()
    if fault=='extra_annotation':notes['other']=deepcopy(notes['a'])
    if fault=='strengthened_furnishing':notes['a']['issues'][0]['kind']='furnished_only_offer_unmodeled'
    if fault=='changed_message':notes['a']['issues'][0]['message']='Furnished only.'
    if fault=='dropped_merged_message':notes['a']['message']='Dropped reviewed statement.'
    if fault=='not_limited':notes['a']['interpretation_limited']=False
    with pytest.raises(ValueError):m.verify_historical_notes([row],notes,[case])
