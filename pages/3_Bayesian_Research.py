"""Review completed Bayesian research without fitting or loading posterior arrays."""
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from apartments.bayesian_review import BayesianWorkspace, workspace_signature

ROOT=Path(__file__).resolve().parents[1]
st.set_page_config(page_title='Bayesian rental research',page_icon='🔬',layout='wide')
st.title('Chelsea — Bayesian research')
st.caption('Saved, accepted research fits: conditional feature comparisons and asking-rent residuals.')
st.info('These are conditional associations, not causal amenity values or personal willingness to pay. Current observations contribute to the fit. The main reviewed model remains unchanged.')


@st.cache_resource(show_spinner=False)
def load_workspace(root,signature):
    del signature
    return BayesianWorkspace.load(root)


def count(value):return ' / '.join(f"{value[k]:,}" for k in ('rows','units','buildings'))
def label(value):return value.replace('_',' ')
def uncertainty(value):return {'Median (%)':value['median'],'Lower 95% (%)':value['lower_95'],'Upper 95% (%)':value['upper_95']}


with st.sidebar:
    st.header('Saved research')
    root=st.text_input('Research artifact directory',str(ROOT/'data/model'))
    chosen=st.selectbox('Accepted fit',['Baseline feature priors','Half feature-prior scale'])
    if st.button('Reload verified reports'):load_workspace.clear()
try:
    with st.spinner('Verifying completed reports and their saved-fit bindings…'):
        workspace=load_workspace(root,workspace_signature(root))
except (OSError,ValueError,KeyError,TypeError) as exc:
    st.error(f'The Bayesian research could not be verified: {exc}')
    st.caption('Only completed, accepted and mutually bound reports can be displayed. This page does not scrape, fit or open posterior arrays.')
    st.stop()

research=workspace.baseline if chosen=='Baseline feature priors' else workspace.half
categories=workspace.categories if chosen=='Baseline feature priors' else workspace.half_categories
identity=workspace.identity['baseline' if chosen=='Baseline feature priors' else 'half_prior']
a,b,c,d=st.columns(4)
a.metric('Fitted observations',f"{research['cohort']['rows']:,}")
b.metric('Buildings',f"{research['cohort']['buildings']:,}")
c.metric('Saved current observations',research['cohort']['current_rows'])
d.metric('Feature prior multiplier',research['method']['prior_multiplier'])
with st.expander('Experiment, dataset and numerical checks'):
    st.json({'selected_fit':chosen,**identity,'cohort':research['cohort'],'method':research['method'],'diagnostics':research['diagnostics']})
    st.caption('The saved current sample does not establish live availability. Historical attribute captures can postdate price observations. Credible intervals are conditional on the measured data, priors and likelihood.')

bath_tab,category_tab,prior_tab,residual_tab=st.tabs(['Bathrooms','Named amenities','Prior sensitivity','Current residuals'])
with bath_tab:
    st.subheader('Full and half bathroom increments')
    st.caption('Same building, unit, date, square footage and other recorded features. Unknown or flagged bathroom counts are not interpreted as zero bathrooms.')
    st.write(f"Composition known: {research['cohort']['bathroom_composition_known']:,}; unknown or flagged: {research['cohort']['bathroom_composition_unknown']:,}.")
    rows=[]
    for kind,key in [('Full bath','full_bath_increments'),('Half bath','half_bath_increments')]:
        for item in research['bathrooms'][key]:
            if kind=='Full bath':change=f"{item['before_full_half'][0]} → {item['after_full_half'][0]} full, {item['before_full_half'][1]} half"
            else:change=f"{item['before_half']} → {item['after_half']} half, {item['full_bathrooms']} full"
            rows.append({'Bedrooms':item['bedrooms'],'Change':change,**uncertainty(item['percent_effect']),
                'Before rows / units / buildings':count(item['support_before']),'After rows / units / buildings':count(item['support_after']),
                'Sparse endpoint (<30 rows)':min(item['support_before']['rows'],item['support_after']['rows'])<30})
    bedrooms=st.selectbox('Bedroom count for bathroom comparisons',['All',*sorted({r['Bedrooms'] for r in rows})])
    st.dataframe(pd.DataFrame([r for r in rows if bedrooms=='All' or r['Bedrooms']==bedrooms]),hide_index=True,width='stretch')
    st.caption('Sparse support is shown for review; these intervals can depend strongly on priors. No unobserved endpoint is displayed.')
    st.subheader('Eliminating a full-bath shortage versus adding a surplus')
    st.caption('Joint log-increment difference: net full baths − bedrooms moving −1 → 0, minus 0 → +1. This is not a difference in percentage points; half baths do not remove a full-bath shortage.')
    balance=[]
    for item in research['bathrooms']['net_balance']:
        v=item['difference'];balance.append({'Bedrooms':item['bedrooms'],'Median log difference':v['median'],'Lower 95%':v['lower_95'],
            'Upper 95%':v['upper_95'],'P(first increment larger)':item['probability_first_increment_larger'],
            'Net −1 support':count(item['support'][0]),'Net 0 support':count(item['support'][1]),'Net +1 support':count(item['support'][2])})
    st.dataframe(pd.DataFrame(balance),hide_index=True,width='stretch')

with category_tab:
    st.subheader('Recorded amenity category comparisons')
    st.caption('Joint category contrasts preserve coefficient covariance. Unknown reporting is separate from explicitly recorded absence. Basis coefficients are not shown as premiums.')
    fields=[item['field'] for item in categories['categories']]
    field=st.selectbox('Amenity',fields,format_func=label)
    known=next(item for item in categories['categories'] if item['field']==field)
    st.write(f"Known: {known['known']['rows']:,} observations; unknown: {known['unknown']['rows']:,} observations.")
    st.dataframe(pd.DataFrame(known['levels']).rename(columns={'category':'Recorded category','rows':'Observations','units':'Units','buildings':'Buildings'}),hide_index=True,width='stretch')
    rows=[]
    for item in categories['contrasts']:
        if item['field']!=field:continue
        rows.append({'Change':label(item['before'])+' → '+label(item['after']),**uncertainty(item['percent_effect']),
            'Before rows / units / buildings':count(item['support_before']),'After rows / units / buildings':count(item['support_after']),
            'Shared buildings':item['overlap']['buildings'],'Shared units':item['overlap']['units'],
            'Sparse endpoint (<30 rows)':min(item['support_before']['rows'],item['support_after']['rows'])<30})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    st.caption('Shared units/buildings can reflect reporting differences or changes over time. Overlap is not a matched intervention. Sparse categories and little overlap deserve source review.')

with prior_tab:
    st.subheader('Sensitivity to halving feature-coefficient prior scales')
    st.caption('Same source cohort and exact contrast vectors; independently sampled fits. Building/unit priors and observation noise are unchanged. Differences below compare posterior medians descriptively; draws are not paired.')
    prior=workspace.sensitivity
    st.json(prior['changed_protocol_settings'])
    rows=[]
    for item in prior['contrasts']:
        before=item['before']['percent_effect'];after=item['after']['percent_effect']
        rows.append({'Comparison':item['id'],'Baseline median (%)':before['median'],'Baseline lower 95%':before['lower_95'],'Baseline upper 95%':before['upper_95'],
            'Half-prior median (%)':after['median'],'Half-prior lower 95%':after['lower_95'],'Half-prior upper 95%':after['upper_95'],
            'Median shift (percentage points)':item['median_shift_percentage_points']})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    st.write(f"Largest absolute category median shift: {prior['maximum_absolute_median_shift_percentage_points']:.3f} percentage points.")
    st.caption('Stability under this single change is not general prior robustness or causal identification.')
    st.subheader('Bathroom prior sensitivity — direct comparison')
    bathrooms=workspace.bathroom_sensitivity
    rare=bathrooms['second_half_support']
    st.warning(f"The second-half-bath coefficient is informed by only {rare['advertisements']} advertisements across all fitted layouts ({rare['rows']} observations). The table separately labels each selected endpoint's own support; these totals must not be mistaken for support at every endpoint.")
    st.caption('Both intervals are separate fits, holding the same building, unit, date, area and other encoded features fixed. Median shifts are descriptive percentage-point differences, not posterior intervals for changes between models.')
    def effect_text(value):return f"{value['median']:+.2f} [{value['lower_95']:+.2f}, {value['upper_95']:+.2f}]"
    comparisons=[]
    for key in ('full_bath_increments','half_bath_increments'):
        for item in bathrooms['tables'][key]:
            if key=='full_bath_increments':
                change=f"{item['before_full_half'][0]} → {item['after_full_half'][0]} full; {item['before_full_half'][1]} half"
                rarity=''
            else:
                change=f"{item['before_half']} → {item['after_half']} half; {item['full_bathrooms']} full"
                endpoint_ads=len({str(r['source_listing_id']) for r in rare['records']
                    if r['bedrooms']==item['bedrooms'] and r['reported_full_bathrooms']==item['full_bathrooms']
                    and r['reported_half_bathrooms']==item['after_half']})
                rarity=(f"{rare['advertisements']} total ads; this endpoint {endpoint_ads} ad / {item['support_after']['rows']} row" if item['before_half']==1 and item['after_half']==2 else '')
            change_values=item['changes']['percent_effect']
            comparisons.append({'Bedrooms':item['bedrooms'],'Change':change,
                'Baseline % [95% CrI]':effect_text(change_values['reference']),
                'Half-prior % [95% CrI]':effect_text(change_values['candidate']),
                'Median shift (percentage points)':change_values['median_change'],
                'Before rows / units / buildings':count(item['support_before']),
                'After rows / units / buildings':count(item['support_after']),
                'Second-half evidence':rarity})
    st.dataframe(pd.DataFrame(comparisons),hide_index=True,width='stretch')
    st.subheader('Net bathroom balance — log scale')
    st.caption('Compare the log-price increment for removing a full-bath shortage (−1 → 0) with adding a surplus (0 → +1). Values below are differences of log increments, not percentages or percentage points.')
    balances=[]
    for item in bathrooms['tables']['net_balance']:
        values=item['changes']['difference']
        balances.append({'Bedrooms':item['bedrooms'],'Baseline log difference [95% CrI]':effect_text(values['reference']),
            'Half-prior log difference [95% CrI]':effect_text(values['candidate']),
            'Median shift (log units)':values['median_change'],'Net −1 support':count(item['support'][0]),
            'Net 0 support':count(item['support'][1]),'Net +1 support':count(item['support'][2])})
    st.dataframe(pd.DataFrame(balances),hide_index=True,width='stretch')
    st.metric('Largest current fitted-rent movement between priors',f"${bathrooms['maximum_current_fitted_rent_movement']:.2f}")
    st.caption(f"Maximum absolute movement across the same {bathrooms['current_rows']} saved current observations; this is a comparison of fitted medians, not a predictive bound.")

with residual_tab:
    st.subheader('Saved current apartments')
    st.caption('Positive residual means asking rent exceeds the fitted conditional median. Fitted-rent intervals measure uncertainty in that latent median, not future rents or transaction prices. Residuals are review signals, not bargain scores.')
    rows=[{'Advertisement':r['source_listing_id'],'Building':r['building'],'Month':r['period'],'Ask ($)':r['asking_rent'],'Fitted median ($)':r['fitted_rent'],
           'Latent lower 95% ($)':r['latent_rent_lower_95'],'Latent upper 95% ($)':r['latent_rent_upper_95'],'Ask − fit ($)':r['residual_dollars'],
           'Ask vs fit (%)':100*(r['asking_rent']/r['fitted_rent']-1)} for r in research['current_residuals']]
    st.dataframe(pd.DataFrame(rows).sort_values('Ask vs fit (%)'),hide_index=True,width='stretch')
    options={r['audit_id']:r for r in research['current_residuals']}
    audit_id=st.selectbox('Current observation to inspect',list(options),format_func=lambda key:f"{options[key]['building']} · ad {options[key]['source_listing_id']}")
    item=options[audit_id]
    url=item.get('advertisement_url','');parsed=urlparse(url)
    if parsed.scheme=='https' and parsed.hostname in {'streeteasy.com','www.streeteasy.com'}:st.link_button('Open advertisement on StreetEasy',url)
    st.json({'audit_id':audit_id,'unit_id':item['unit_id'],'source_listing_id':item['source_listing_id'],
             'period':item['period'],'asking_rent':item['asking_rent'],'fitted_rent':item['fitted_rent'],
             'residual_dollars':item['residual_dollars'],'source_record':item['source_record']})
