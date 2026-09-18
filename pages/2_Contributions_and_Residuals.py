"""Read-only analysis of the explicitly selected, verified joint Bayesian posterior."""
from pathlib import Path
import math
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from apartments.bayesian_analysis import BayesianAnalysis, bundle_signature
from apartments.bayesian_evidence import load_evidence
from apartments.main_analysis import load_selection

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = ROOT / 'config/main-analysis.json'
DEFAULT_EVIDENCE = ROOT / 'data/model/chelsea-analysis-descriptions-20260918'

st.set_page_config(page_title='Contributions and residuals', page_icon='🔎', layout='wide')
st.title('Chelsea — Bayesian contributions and residuals')
st.caption('Inspect the accepted saved posterior, investigate asking-price residuals, and compare apartment features jointly.')
st.info('These are conditional, in-sample asking-rent associations. A large residual suggests a listing or missing-feature review; it is not a bargain score. Saved current listings do not establish live availability.')


@st.cache_resource(show_spinner=False)
def load_analysis(experiment, dataset, signature):
    del signature  # Content is independently verified on load; file changes invalidate cache.
    return BayesianAnalysis.load(experiment, dataset)


@st.cache_resource(show_spinner=False)
def archived_evidence(dataset, evidence, signature):
    del signature
    return load_evidence(dataset, evidence)


def label(value):
    return str(value).replace('_', ' ').replace('.', ' · ')


def interval_text(interval, money=False):
    fmt = '${:,.0f}' if money else '{:+.4f}'
    return f"95% credible interval: {fmt.format(interval['lower_95'])} to {fmt.format(interval['upper_95'])}"


def source_links(record):
    for name, key in [('Advertisement on StreetEasy', 'advertisement_url'), ('Unit on StreetEasy', 'canonical_unit_url')]:
        url = record.get(key)
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed and parsed.scheme == 'https' and parsed.hostname in {'streeteasy.com', 'www.streeteasy.com'}:
            st.link_button(name, url)


with st.sidebar:
    st.header('Selected Bayesian analysis')
    selection_path = st.text_input('Analysis selection', str(DEFAULT_SELECTION))
    evidence_path = st.text_input('Archived description bundle', str(DEFAULT_EVIDENCE),
                                  help='Optional verified source archive; leave blank to disable.').strip()
    if st.button('Reload saved analysis'):
        load_analysis.clear()
        archived_evidence.clear()

try:
    selection, experiment, dataset = load_selection(selection_path)
    signature = bundle_signature(experiment / 'protocol', experiment / 'fit', dataset)
    with st.spinner('Verifying the saved Bayesian analysis…'):
        analysis = load_analysis(str(experiment), str(dataset), signature)
    rows, residual_records = analysis.rows, analysis.residuals
    evidence = (archived_evidence(str(dataset), evidence_path, bundle_signature(dataset, evidence_path))
                if evidence_path else {})
    source = {r['audit_id']: r for r in rows}
    records = []
    for residual in residual_records:
        r = source[residual['audit_id']]
        records.append({**residual, 'building': residual.get('building', r['building']),
            'canonical_unit_url': r.get('canonical_unit_url'),
            'current_capture': r.get('analysis_price_basis') == 'current_capture_gross_ask',
            'residual_percent': 100 * (residual['asking_rent'] / residual['fitted_rent'] - 1),
            'absolute_log_residual': abs(residual['residual_log'])})
    residuals = pd.DataFrame(records)
except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
    st.error(f'The selected Bayesian analysis could not be verified: {exc}')
    st.caption('A completed accepted fit, its exact dataset, and matching saved selection are required. This page does not fit or scrape.')
    st.stop()

if residuals.empty:
    st.info('No fitted observations are available.')
    st.stop()

columns = st.columns(4)
for col, name, value in zip(columns, ['Fitted observations', 'Units', 'Buildings', 'Saved current observations'],
                           [len(residuals), residuals.unit_id.nunique(), residuals.building.nunique(), residuals.current_capture.sum()]):
    col.metric(name, f'{value:,}')
with st.expander('Analysis identity and verification'):
    st.write('Experiment:', str(experiment))
    st.write('Dataset:', str(dataset))
    st.json(selection)
    st.json(analysis.summary)

st.subheader('Find a listing to examine')
f1, f2, f3 = st.columns(3)
scope = f1.selectbox('Observation scope', ['Saved current sample', 'All fitted observations'])
building = f2.selectbox('Building', [None, *sorted(residuals.building.unique())],
                        format_func=lambda value: 'All buildings' if value is None else label(value))
order = f3.selectbox('Review order', ['Largest absolute residual', 'Ask above fitted rent', 'Ask below fitted rent'])
one_per_unit = st.checkbox('Show one observation per unit', value=True)
search = st.text_input('Find advertisement ID or unit URL').strip()
view = residuals.copy()
if scope == 'Saved current sample':
    view = view[view.current_capture]
if building is not None:
    view = view[view.building == building]
if search:
    matches = pd.Series(False, index=view.index)
    for field in ['source_listing_id', 'canonical_unit_url', 'unit_id']:
        matches |= view[field].fillna('').astype(str).str.contains(search, case=False, regex=False)
    view = view[matches]
if order == 'Ask above fitted rent':
    view = view[view.residual_log > 0].sort_values(['residual_log', 'audit_id'], ascending=[False, True])
elif order == 'Ask below fitted rent':
    view = view[view.residual_log < 0].sort_values(['residual_log', 'audit_id'])
else:
    view = view.sort_values(['absolute_log_residual', 'audit_id'], ascending=[False, True])
if one_per_unit:
    view = view.drop_duplicates('unit_id')
if view.empty:
    st.info('No observations match these filters.')
    st.stop()
limit = st.selectbox('Maximum rows to review', [25, 100, 500], index=1)
review = view.head(limit)
st.caption(f'Showing {len(review):,} of {len(view):,} matching observations. Residual percentages use the fitted median as denominator.')
st.dataframe(review[['building', 'source_listing_id', 'period', 'asking_rent', 'fitted_rent',
    'latent_rent_lower_95', 'latent_rent_upper_95', 'residual_dollars', 'residual_percent']].rename(columns={
    'building': 'Building', 'source_listing_id': 'Advertisement', 'period': 'Month',
    'asking_rent': 'Ask ($)', 'fitted_rent': 'Fitted median ($)', 'latent_rent_lower_95': 'Lower 95% CrI ($)',
    'latent_rent_upper_95': 'Upper 95% CrI ($)', 'residual_dollars': 'Ask − median ($)',
    'residual_percent': 'Ask vs median (%)'}), hide_index=True, width='stretch')
labels = {r.audit_id: f'{label(r.building)} · ad {r.source_listing_id} · {r.period} · {r.residual_percent:+.1f}%'
          for r in review.itertuples()}
audit_id = st.selectbox('Observation to inspect', list(labels), format_func=labels.__getitem__)
try:
    detail = analysis.detail(audit_id)
except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
    st.error(f'The selected observation could not be verified: {exc}')
    st.stop()
record, residual = detail['source_record'], detail['residual']
interval = detail['fitted_median_rent']
st.subheader('Selected apartment')
a, b, c = st.columns(3)
a.metric('Advertised asking rent', f"${residual['asking_rent']:,.0f}")
b.metric('Posterior median fitted rent', f"${interval['median']:,.0f}")
b.caption(interval_text(interval, money=True))
c.metric('Ask − fitted median', f"${residual['residual_dollars']:+,.0f}")
st.caption(f"{detail['draws']:,} joint retained draws. The interval describes latent conditional-median asking rent, not a new listing's price range or arithmetic mean rent.")
source_links(record)
for warning in detail.get('warnings', []):
    st.warning(warning)

contributions_tab, contrast_tab, evidence_tab = st.tabs(['Contributions and history', 'Change apartment features', 'Source evidence'])
with contributions_tab:
    st.caption('Posterior MEAN log contributions sum to E[μ]. They are not additive dollar amounts, sums of posterior medians, or causal premiums. Category basis coefficients are not named amenity premiums; use a joint feature comparison below.')
    groups = detail['grouped_contributions']
    intervals = {item['group']: item['log_interval'] for item in detail['grouped_contribution_intervals']}
    contribution_ok = detail['contribution_diagnostics']['acceptable']
    table = []
    for group, mean in groups.items():
        item = {'Component': label(group), 'Posterior mean log contribution': mean}
        if contribution_ok and group in intervals:
            item.update({'Lower 95% CrI (log)': intervals[group]['lower_95'], 'Upper 95% CrI (log)': intervals[group]['upper_95']})
        table.append(item)
    st.dataframe(pd.DataFrame(table), hide_index=True, width='stretch')
    st.caption(f"Contribution mean sum: {math.fsum(groups.values()):.6f}; E[μ]: {detail['mean_log_rent']:.6f}. Exponentiating E[μ] need not equal the posterior median fitted rent.")
    if not contribution_ok:
        st.warning('Contribution diagnostics failed; contribution intervals are withheld.')
    with st.expander('Exact encoded contributions and diagnostics'):
        st.dataframe(pd.DataFrame(detail['contributions']), hide_index=True, width='stretch')
        st.json(detail['contribution_diagnostics'])
    st.subheader("This unit's fitted history")
    history = pd.DataFrame(detail['unit_history']).sort_values(['period', 'audit_id'])
    st.line_chart(history.set_index('period')[['asking_rent', 'fitted_rent']].rename(columns={'asking_rent': 'Advertised ask', 'fitted_rent': 'Fitted median'}))
    st.dataframe(history[['period', 'source_listing_id', 'asking_rent', 'fitted_rent', 'latent_rent_lower_95', 'latent_rent_upper_95']].rename(columns={
                     'period': 'Month', 'source_listing_id': 'Advertisement', 'asking_rent': 'Ask ($)',
                     'fitted_rent': 'Fitted median ($)', 'latent_rent_lower_95': 'Lower 95% CrI ($)',
                     'latent_rent_upper_95': 'Upper 95% CrI ($)'}),
                 hide_index=True, width='stretch')
    st.caption('Historical price dates may precede captures of listing attributes. This is retrospective evidence, not proof of when an attribute changed.')

with contrast_tab:
    st.caption('Change one or more physical source inputs jointly. Date, building and unit offsets remain fixed; bedroom/area and other interactions are recomputed. Unknown reporting and unsupported endpoints do not receive a physical-value estimate.')
    fields = analysis.fields
    chosen = st.multiselect('Features to change together', list(fields), format_func=label, key=f'fields:{audit_id}')
    if chosen:
        changes = {}
        with st.form(f'compare:{audit_id}'):
            for name in chosen:
                spec = fields[name]
                original = detail['source_values'].get(name)
                st.caption(f'Recorded {label(name)}: {"Unknown" if original is None else original}')
                key = f'change:{audit_id}:{name}'
                if spec['kind'] == 'category':
                    options = spec['options']
                    changes[name] = st.selectbox(label(name), options, index=options.index(original) if original in options else 0, key=key)
                elif spec['kind'] == 'boolean':
                    changes[name] = st.selectbox(label(name), [False, True], index=1 if original is True else 0,
                                                 format_func=lambda value: 'Yes' if value else 'No', key=key)
                else:
                    low, high, step = {'bedrooms': (0., 5., 1.), 'full_bathrooms': (1., 5., 1.),
                        'half_bathrooms': (0., 2., 1.), 'square_feet': (1., 100000., 10.)}.get(name, (-10., 200., 1.))
                    value = float(original) if original is not None else low
                    changes[name] = st.number_input(label(name), min_value=low, max_value=high,
                        value=min(high, max(low, value)), step=step, key=key)
            submitted = st.form_submit_button('Compare with recorded apartment')
        if submitted:
            try:
                result = analysis.counterfactual(audit_id, changes)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                st.error(f'This feature comparison could not be verified: {exc}')
            else:
                st.write('Comparison status:', result['status'])
                if result['status'] == 'accepted':
                    left, right = st.columns(2)
                    left.metric('Changed apartment: fitted median', f"${result['after_rent']['median']:,.0f}")
                    left.caption(interval_text(result['after_rent'], money=True))
                    right.metric('Joint rent change', f"${result['delta_dollars']['median']:+,.0f}",
                                 f"{result['delta_percent']['median']:+.2f}%", delta_color='off')
                    right.caption(interval_text(result['delta_dollars'], money=True))
                    st.caption('Percent-change '+interval_text(result['delta_percent'])+'%. Each interval is calculated jointly across posterior draws; medians need not subtract exactly.')
                else:
                    st.warning('Physical feature-value intervals withheld: '+result['status']+'.')
                for warning in result.get('warnings', []):
                    st.warning(warning)
                st.write('Endpoint support and knownness')
                st.json(result['support'])
                with st.expander('Joint comparison inputs and diagnostics'):
                    st.json(result['changes'])
                    st.json(result['diagnostics'])
                    st.write(result['held_fixed'])
                    st.caption(result['uncertainty'])
    else:
        st.info('Choose one or more features to compare jointly.')

with evidence_tab:
    st.caption('Archived descriptions are literal source text. Review them for missing amenities, ambiguous room labels or price-basis problems; this page does not modify evidence.')
    captures = evidence.get(audit_id, [])
    if captures:
        selected_capture = st.selectbox('Saved capture', list(range(len(captures))),
            format_func=lambda i: f"Capture {captures[i].get('capture_id')} · {captures[i].get('source_collected_at')}")
        capture = captures[selected_capture]
        if capture.get('description'):
            st.text(capture['description'])
        else:
            st.info('This capture has no archived description text.')
        st.json({key: value for key, value in capture.items() if key != 'description'})
    else:
        st.info('No archived description is available for this observation.' if evidence_path else 'Archived description review is disabled.')
    st.caption('Capture, interpretation and attribute-effective dates are different clocks. Source links can change after collection.')
    with st.expander('Complete source record'):
        st.json(record)
    with st.expander('Saved residual record'):
        st.json(residual)
