import jax.numpy as jnp
import numpy as np
from test_gibbs import DESIGNS, synthetic

from rentfrontier import gibbs, model


def test_walkmin1_differs_from_slopemin3_only_in_the_walk_minimum():
    s = model.MODELS[
        "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope"
        "-slopemin3"
    ]
    m = model.MODELS[s.name + "-walkmin1"]
    assert m.walk_min_rows_per_knot == 1.0
    assert {k for k, v in vars(m).items() if getattr(s, k) != v} == {
        "name",
        "walk_min_rows_per_knot",
    }


def test_masked_buildings_touch_no_knot_and_output_no_walk():
    prep = synthetic(seed=2, units_per_building=3, months=72)
    config = DESIGNS["walkmin-long"]
    on = model.walk_mask(prep, config)
    assert 0 < on.sum() < len(on)
    d = gibbs.build_design(prep, config)
    plain = gibbs.build_design(prep, DESIGNS["walk"])
    # The walk's rank counts the touched knots of buildings with a walk only.
    k = model.n_knots(d.n_months, config.walk_knot_months)
    touched = np.zeros(d.n_buildings)
    for bk in plain.buckets:
        touched[np.asarray(bk.buildings)] = (np.asarray(bk.knot) < k).sum(1)
    assert d.walk_rank == int((touched * on).sum())
    rng = np.random.default_rng(0)
    state = {
        "theta": jnp.zeros(d.a.shape[1]),
        "local": jnp.asarray(rng.normal(0, 0.1, (d.n_buildings, d.n_local))),
        "unit": jnp.zeros(d.n_units),
        "nu": 5.0,
        **{name: 0.05 for name in d.scale_names},
    }
    steps = np.asarray(gibbs.site_values(d, state)["walk_step"])
    assert (steps[on == 0] == 0).all()
    assert (steps[on == 1] != 0).all()
