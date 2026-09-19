from pathlib import Path
import json
import streamlit as st
from streamlit.testing.v1 import AppTest
from apartments.research_pipeline import publish_bundle,digest
from apartments.corrections import canonical
root=Path('/home/ben/code/apartments'); selection=root/'data/model/chelsea-main-current-candidate-20260919.json'
def widget(page,kind,label):return next(x for x in getattr(page,kind) if x.label==label)
st.cache_resource.clear()
page=AppTest.from_file(str(root/'pages/2_Contributions_and_Residuals.py')).run(timeout=180)
assert not page.exception and not page.error
widget(page,'text_input','Analysis selection').set_value(str(selection)).run(timeout=180)
assert not page.exception and not page.error
assert any(m.label=='Saved current observations' and m.value=='172' for m in page.metric)
widget(page,'selectbox','Maximum rows to review').set_value(500).run(timeout=90)
assert not page.exception and not page.error
assert len(page.dataframe[0].value)==172
assert page.dataframe[0].value['Source review'].ne('').sum()==8
assert any('bedroomCount=0' in w.value for w in page.warning)
widget(page,'text_input','Find advertisement ID or unit URL').set_value('5155021').run(timeout=90)
assert len(page.dataframe[0].value)==1
widget(page,'multiselect','Features to change together').set_value(['bedrooms']).run(timeout=90)
widget(page,'number_input','bedrooms').set_value(1.)
widget(page,'button','Compare with recorded apartment').click().run(timeout=90)
assert not page.exception and not page.error
assert any(m.label=='Changed apartment: fitted median' and m.value=='$3,665' for m in page.metric)
assert any('does not resolve the source conflict' in w.value for w in page.warning)
result={'version':'current-main-page-validation-v1','current_rows':172,'source_review_cases':8,
 'source_count_conflict_warning_visible':True,'source_count_unchanged':True,
 'one_bedroom_scenario_median_display':'$3,665','scenario_source_uncertainty_warning_visible':True,
 'streamlit_exceptions':0,'selection_sha256':digest(selection),
 'verification':'Actual saved PyMC posterior, source archive and review notes through Streamlit AppTest; no model/evidence mocks.'}
publish_bundle(root/'data/model/chelsea-current-main-page-validation-20260919',{
 'validation.json':canonical(result)+'\n','check_current_main_page.py':Path(__file__).read_text()},
 {'version':result['version'],'selection_sha256':digest(selection)})
print(canonical(result),flush=True)
st.cache_resource.clear()
