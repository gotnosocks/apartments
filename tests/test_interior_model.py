"""Interior values must not reuse presence-only mentions as physical premiums."""
import json

import numpy as np
import pandas as pd
import pytest

from models import amenity_ablation as ablation
from models import amenity_rent_model as amenities
from models import interior_model as interior
from models import minimal_rent_model as baseline


def sample():
    rows = []
    for month in range(1, 5):
        for unit in range(24):
            height = (9., 11., None)[unit % 3]
            rent = 3000*np.exp(.04*(height-10) if height is not None else -.03)
            rows.append(dict(unit_id=f'u{unit}', building=f'b{unit//4}',
                period=pd.Timestamp(2024, month, 1), bedrooms=1., bathrooms=1.,
                square_feet=650., asking_rent=rent, log_rent=np.log(rent),
                advertised_ceiling_feet=height, advertised_levels=2. if unit % 2 else None,
                floor_through_mention=1. if unit % 3 else None, skylight_mention=None,
                laundry_type=('none', 'in_unit', None)[unit % 3]))
    return pd.DataFrame(rows)


def test_known_only_centering_and_constant_mentions():
    data = sample()
    encoder = interior.encoder_class('values')(data)
    start, stop = encoder.offsets['interior']
    matrix = encoder.matrix(data).toarray()[:, start:stop]
    columns = dict(zip(encoder.interior_features, matrix.T))
    assert np.allclose(columns['advertised_ceiling_feet'][data.advertised_ceiling_feet.notna()].mean(), 0)
    assert (columns['advertised_ceiling_feet'][data.advertised_ceiling_feet.isna()] == 0).all()
    for field in ('advertised_levels', 'floor_through_mention', 'skylight_mention'):
        assert (columns[field] == 0).all()
        assert np.array_equal(columns[field+'.unknown'], data[field].isna())
    probe = data.iloc[:2].copy()
    probe['advertised_ceiling_feet'] = [12., None]
    probe['advertised_levels'] = [3., None]
    encoded = encoder.matrix(probe).toarray()[:, start:stop]
    assert encoded[0, 0] == 2.  # Frozen mean 10, standard deviation 1.
    assert encoded[1, 0] == 0
    assert encoded[0, 2] == 0  # New level cannot create support absent in training.


def test_reporting_ignores_known_magnitudes_and_baseline_matches_existing():
    data = sample()
    reporting = interior.encoder_class('reporting')(data)
    probe = pd.concat([data.iloc[:1]]*3, ignore_index=True)
    probe['advertised_ceiling_feet'] = [9., 12., None]
    matrix = reporting.matrix(probe).toarray()
    assert np.array_equal(matrix[0], matrix[1])
    assert not np.array_equal(matrix[0], matrix[2])
    original = ablation.encoder_class('full')(data)
    experimental = interior.encoder_class('baseline')(data)
    assert np.array_equal(original.matrix(data).toarray(), experimental.matrix(data).toarray())
    assert np.array_equal(original.penalty(amenities.SETTINGS).toarray(), experimental.penalty(amenities.SETTINGS).toarray())


@pytest.mark.parametrize('variant', interior.VARIANTS)
def test_real_fit_roundtrip_penalties_convergence_and_contrasts(variant):
    data = sample()
    settings = {**amenities.SETTINGS, 'interior_penalty': 3.}
    fitted = baseline.fit(data, settings, iterations=20, encoder_class=interior.encoder_class(variant))
    assert fitted['robust_objective_relative_change'] < 1e-7
    encoder = fitted['encoder']
    penalty = encoder.penalty(settings)
    assert penalty.shape[1] == encoder.matrix(data).shape[1] == encoder.n_parameters
    start, stop = encoder.offsets['interior']
    if stop > start:
        assert np.allclose(np.asarray(penalty.power(2).sum(axis=0)).ravel()[start:stop], 3.)
    saved = json.loads(json.dumps({'encoder': encoder.metadata(), 'beta': fitted['beta'].tolist(), 'center': fitted['center']}))
    loaded = interior.load_saved(saved)
    probe = data.iloc[:3].copy()
    probe['advertised_ceiling_feet'] = [12., None, 8.]
    assert np.array_equal(baseline.predict(loaded, probe), baseline.predict(fitted, probe))
    contrasts = interior.contribution_contrasts(loaded)
    assert contrasts[0]['supported'] == (variant == 'values')
    assert not contrasts[1]['supported']
    if variant == 'values':
        changed = probe.iloc[:1].copy()
        changed.advertised_ceiling_feet += 1
        actual = baseline.predict(loaded, changed)[0]-baseline.predict(loaded, probe.iloc[:1])[0]
        assert contrasts[0]['log_rent_change'] == pytest.approx(actual)
        assert actual > 0


def test_malformed_evidence_and_saved_fit_rejected():
    data = sample()
    for field, value in [('advertised_ceiling_feet', np.inf), ('advertised_levels', 1.5), ('skylight_mention', 2.)]:
        bad = data.copy()
        bad.loc[0, field] = value
        with pytest.raises(ValueError, match='interior evidence'):
            interior.encoder_class('values')(bad)
    fitted = baseline.fit(data, amenities.SETTINGS, encoder_class=interior.encoder_class('values'))
    with pytest.raises(ValueError, match='coefficients'):
        interior.load_saved({'encoder': fitted['encoder'].metadata(), 'beta': [], 'center': fitted['center']})
    with pytest.raises(ValueError, match='version'):
        interior.load_saved({'encoder': {'model_version': 'other'}})
