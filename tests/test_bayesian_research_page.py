"""Exercise the separate saved Bayesian research surface with accepted artifacts."""
from pathlib import Path
import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
from apartments.bayesian_review import NAMES

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'pages/3_Bayesian_Research.py'
AVAILABLE=all((ROOT/'data/model'/name/'complete.json').exists() for name in NAMES.values())


def select(page,label):return next(item for item in page.selectbox if item.label==label)


@pytest.mark.skipif(not AVAILABLE,reason='Local accepted Bayesian Chelsea artifacts unavailable')
def test_real_page_reports_support_switches_fits_and_handles_unverified_input():
    page=AppTest.from_file(str(PAGE)).run(timeout=30)
    assert not page.exception and not page.error
    assert len(page.dataframe)==8
    assert any(x.label=='Saved current observations' and x.value=='13' for x in page.metric)
    assert len(select(page,'Current observation to inspect').options)==13
    assert any('only 2 advertisements' in item.value for item in page.warning)
    rare=page.dataframe[5].value
    flagged=rare.loc[rare['Second-half evidence']!='']
    assert len(flagged)==2
    assert all('this endpoint 1 ad / 1 row' in text for text in flagged['Second-half evidence'])
    assert any(metric.label=='Largest current fitted-rent movement between priors' and metric.value=='$7.82' for metric in page.metric)
    assert 'Median shift (log units)' in page.dataframe[6].value.columns
    select(page,'Amenity').select('hvac_type').run(timeout=30)
    assert not page.exception
    assert 'Sparse endpoint (<30 rows)' in page.dataframe[3].value.columns
    assert page.dataframe[3].value['Sparse endpoint (<30 rows)'].any()
    assert any('42,655' in x.value for x in page.markdown)
    select(page,'Accepted fit').select('Half feature-prior scale').run(timeout=30)
    assert not page.exception and not page.error
    assert any(x.label=='Feature prior multiplier' and x.value=='0.5' for x in page.metric)
    select(page,'Bedroom count for bathroom comparisons').select(2).run(timeout=30)
    assert set(page.dataframe[0].value['Bedrooms'])=={2}
    page.text_input[0].set_value(str(ROOT/'missing-research-artifacts')).run(timeout=30)
    assert not page.exception and page.error
    assert 'could not be verified' in page.error[0].value
    assert len(page.dataframe)==0
