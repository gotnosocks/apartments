"""Entry points for the selected Bayesian apartment analysis and research."""
import streamlit as st

st.set_page_config(page_title='Bayesian asking-rent analysis', page_icon='📈', layout='wide')
st.title('Bayesian asking-rent analysis')
st.write('Review feature contributions, uncertainty, asking-price residuals and joint feature changes for the explicitly selected accepted posterior.')
st.page_link('pages/2_Contributions_and_Residuals.py', label='Open contributions and residuals', icon='🔎')
st.page_link('pages/3_Bayesian_Research.py', label='Open Bayesian research comparisons', icon='🧪')
st.caption('The analysis pages verify saved data and model bindings. They do not scrape, fit, or promote a research experiment.')
