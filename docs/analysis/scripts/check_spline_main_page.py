"""Validate an accepted spline candidate and its floor scenario through real UI.

This script does not fit, select, edit observations, or replace expected prices
with constants. Run only after the candidate posterior and source review finish.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from threadpoolctl import threadpool_limits

from apartments import bayesian_analysis, bayesian_source_review, main_analysis
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_floor_spline_contract as contract

ROOT = Path(__file__).resolve().parents[3]
VERSION = 'spline-main-page-validation-v1'
ADVERTISEMENT = '5155021'
EXPECTED_COUNTS = {'rows':52653,'current_rows':172,'known_floor_rows':29907,'source_review_cases':8}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def widget(page, kind, label):
    matches = [value for value in getattr(page,kind) if value.label == label]
    require(len(matches)==1, f'Expected one {kind} widget labeled {label!r}')
    return matches[0]


def healthy(page):
    require(not page.exception and not page.error,
            'Streamlit failed: '+str([v.value for v in [*page.exception,*page.error]]))


def currency(value):
    return f'${value:,.0f}'


def json_values(page):
    return [json.loads(item.value) if isinstance(item.value,str) else item.value for item in page.json]


def backend_expectations(selection_path):
    selection,experiment,dataset = main_analysis.load_selection(selection_path)
    require(bool(selection.get('evidence')) and bool(selection.get('source_review')),
            'Candidate requires its matching description archive and completed eight-case review')
    evidence = main_analysis.resolve_path(selection['evidence'])
    review = main_analysis.resolve_path(selection['source_review'])
    notes = bayesian_source_review.load_source_review(experiment,dataset,review,evidence=evidence)
    analysis = bayesian_analysis.BayesianAnalysis.load(experiment,dataset)
    try:
        require(analysis.protocol.get('version')==contract.EXPERIMENT,'Candidate is not the spline experiment')
        rows = analysis.rows
        counts = {'rows':len(rows),
            'current_rows':sum(r.get('analysis_price_basis')=='current_capture_gross_ask' for r in rows),
            'known_floor_rows':analysis.design.floor_support['known_rows'],'source_review_cases':len(notes)}
        require(counts==EXPECTED_COUNTS,'Candidate source coverage or review counts differ: '+str(counts))
        candidates = [r for r in rows if str(r['source_listing_id'])==ADVERTISEMENT
                      and r.get('analysis_price_basis')=='current_capture_gross_ask']
        require(len(candidates)==1,'Expected one captured-current observation for advertisement '+ADVERTISEMENT)
        row = candidates[0];identity = row['audit_id']
        require(row.get('floor_label_provenance',{}).get('status')=='label_proxy',
                'Selected unit does not retain label-proxy floor provenance')
        detail = analysis.detail(identity)
        require(detail['source_values'].get('listed_floor')==2.,'Recorded floor is not 2')
        require(analysis.fields.get('listed_floor',{}).get('kind')=='numeric',
                'Spline design does not expose the listed-floor numeric scenario')
        require(notes.get(identity,{}).get('interpretation_limited') is True,
                'Expected source-conflict review note is absent')
        require(notes[identity]['kind']=='bedroom_count_conflict' and 'bedroomCount=0' in notes[identity]['message'],
                'Expected literal bedroom source conflict is absent')
        scenario = analysis.counterfactual(identity,{'listed_floor':3.})
        require(scenario['status']=='accepted','Floor 2→3 backend scenario failed: '+scenario['status'])
        require(scenario['changes']=={'listed_floor':3.},'Counterfactual changed additional inputs')
        require({k:v for k,v in scenario['before'].items() if k!='listed_floor'}
                == {k:v for k,v in scenario['after'].items() if k!='listed_floor'},
                'An unspecified source input changed in the floor scenario')
        require(bool(scenario['changed_encoded_features'])
                and all(n.startswith('listed_floor_spline_') for n in scenario['changed_encoded_features']),
                'Floor scenario changed nonfloor or missingness coefficients')
        require(currency(detail['fitted_median_rent']['median'])==currency(scenario['before_rent']['median']),
                'Detail and counterfactual baseline fitted rents differ')
        result = {'counts':counts,'audit_id':identity,'source_listing_id':ADVERTISEMENT,
            'recorded_floor':2.,'changed_floor':3.,'floor_label_provenance':row['floor_label_provenance'],
            'source_review':notes[identity], 'source_record':row,
            'before_rent':scenario['before_rent'],'after_rent':scenario['after_rent'],
            'before_median_display':currency(scenario['before_rent']['median']),
            'after_median_display':currency(scenario['after_rent']['median']),
            'backend_scenario':scenario,'protocol_sha256':analysis.summary['protocol_sha256'],
            'source_observations_sha256':analysis.summary['source_observations_sha256'],
            'experiment_version':analysis.protocol['version']}
        # Any model/source change while deriving expectations invalidates them.
        analysis.rows
        return selection,result
    finally:
        analysis.close()


def run(selection,output,timeout=300):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    selection,output = Path(selection).resolve(),Path(output)
    selection_hash = digest(selection)
    default_path = ROOT/'config/main-analysis.json'
    default_hash = digest(default_path) if default_path.is_file() else None
    page_path = ROOT/'pages/2_Contributions_and_Residuals.py'
    code_paths = [Path(__file__),page_path,Path(bayesian_analysis.__file__),
                  Path(bayesian_source_review.__file__),Path(main_analysis.__file__)]
    code_hashes = {p.name:digest(p) for p in code_paths}
    chosen,expected = backend_expectations(selection)
    st.cache_resource.clear()
    try:
        # Open the actual page, then use its real selection control. No page,
        # posterior, expected-rent, evidence, or widget behavior is mocked.
        page = AppTest.from_file(str(page_path)).run(timeout=timeout)
        widget(page,'text_input','Analysis selection').set_value(str(selection)).run(timeout=timeout)
        healthy(page)
        displayed = json_values(page)
        require(chosen in displayed,'Rendered page is not using the supplied candidate selection')
        require(any(isinstance(v,dict) and v.get('experiment_version')==contract.EXPERIMENT
                    and v.get('protocol_sha256')==expected['protocol_sha256'] for v in displayed),
                'Rendered analysis identity does not match the spline posterior')
        require(widget(page,'metric','Fitted observations').value==f"{EXPECTED_COUNTS['rows']:,}",
                'Rendered fitted observation count differs')
        require(widget(page,'metric','Saved current observations').value==str(EXPECTED_COUNTS['current_rows']),
                'Rendered captured-current count differs')
        widget(page,'selectbox','Maximum rows to review').set_value(500).run(timeout=timeout)
        healthy(page)
        table = page.dataframe[0].value
        require(len(table)==EXPECTED_COUNTS['current_rows'],'Current review table dropped observations')
        require(int(table['Source review'].ne('').sum())==EXPECTED_COUNTS['source_review_cases'],
                'Rendered source-review count differs')
        widget(page,'text_input','Find advertisement ID or unit URL').set_value(ADVERTISEMENT).run(timeout=timeout)
        healthy(page)
        require(len(page.dataframe[0].value)==1,'Advertisement search did not select exactly one row')
        require(str(page.dataframe[0].value.iloc[0]['Advertisement'])==ADVERTISEMENT,'Wrong advertisement rendered')
        require(widget(page,'selectbox','Observation to inspect').value==expected['audit_id'],'Wrong observation selected')
        require(widget(page,'metric','Posterior median fitted rent').value==expected['before_median_display'],
                'Rendered baseline fitted rent differs from exact backend posterior')
        require(any('bedroomCount=0' in w.value for w in page.warning),'Source bedroom conflict warning missing')
        require(expected['source_record'] in json_values(page),'Complete source record is not rendered intact')
        widget(page,'multiselect','Features to change together').set_value(['listed_floor']).run(timeout=timeout)
        healthy(page)
        control = widget(page,'number_input','listed floor')
        require(control.value==2.,'Listed-floor numeric control does not initialize to recorded floor 2')
        require(widget(page,'multiselect','Features to change together').value==['listed_floor'],
                'Floor scenario selected another feature')
        control.set_value(3.)
        widget(page,'button','Compare with recorded apartment').click().run(timeout=timeout)
        healthy(page)
        require(widget(page,'metric','Posterior median fitted rent').value==expected['before_median_display'],
                'Scenario mutated the displayed recorded apartment price')
        require(widget(page,'metric','Changed apartment: fitted median').value==expected['after_median_display'],
                'Rendered floor-3 fitted rent differs from exact backend posterior')
        require(any('Comparison status:' in item.value and 'accepted' in item.value for item in page.markdown),
                'Rendered counterfactual status is not accepted')
        require(any('bedroomCount=0' in w.value for w in page.warning),'Source conflict disappeared after scenario')
        require(any('does not resolve the source conflict' in w.value for w in page.warning),
                'Source uncertainty warning disappeared after floor scenario')
        require(expected['source_record'] in json_values(page),'Scenario changed the rendered source record')
        require({'listed_floor':3.} in json_values(page),'Rendered comparison inputs differ from floor-only change')
        require(digest(selection)==selection_hash,'Candidate selection changed during page validation')
        main_analysis.load_selection(selection)
        require((digest(default_path) if default_path.is_file() else None)==default_hash,
                'Main selection changed during candidate validation')
        require(all(digest(p)==code_hashes[p.name] for p in code_paths),'Page/backend implementation changed during validation')
        result = {'version':VERSION,**expected,'selection':str(selection),'selection_sha256':selection_hash,
            'candidate_selection':chosen,'main_selection_changed':False,
            'source_conflict_warning_preserved':True,'source_record_unchanged':True,
            'floor_numeric_control_verified':True,'floor_only_scenario_rendered_status':'accepted',
            'streamlit_exceptions':0,'streamlit_errors':0,'implementation_sha256':code_hashes,
            'verification':'Actual saved PyMC posterior, source archive, review notes and Streamlit page. Expected prices derive from the accepted backend joint posterior; no model, evidence, page or price mocks.'}
        publish_bundle(output,{'validation.json':canonical(result)+'\n',**{p.name:p.read_text() for p in code_paths}},
            {'version':VERSION,'selection_sha256':selection_hash,'implementation_sha256':code_hashes})
        print(canonical({k:result[k] for k in ('version','counts','before_median_display','after_median_display',
            'source_conflict_warning_preserved','main_selection_changed')}),flush=True)
        return result
    finally:
        st.cache_resource.clear()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=300,help='Maximum seconds for each actual Streamlit rerun')
    args=parser.parse_args()
    require(args.timeout>0,'Timeout must be positive')
    with threadpool_limits(limits=1,user_api='blas'):
        run(**vars(args))
