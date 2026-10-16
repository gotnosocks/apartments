import dataclasses

import numpy as np
from rentfrontier import gibbs, model

from test_gibbs import DESIGNS, synthetic


def test_unitnu4_differs_from_slopemin3_only_in_the_unit_degrees_of_freedom():
    base = model.MODELS[
        "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3"
    ]
    m = model.MODELS[base.name + "-unitnu4"]
    assert m.unit_nu_fixed == 4.0
    assert {k for k, v in vars(m).items() if getattr(base, k) != v} == {
        "name",
        "unit_nu_fixed",
    }


def test_gibbs_holds_the_fixed_unit_degrees_of_freedom():
    config = dataclasses.replace(DESIGNS["tunits"], unit_nu_fixed=4.0)
    out = gibbs.run(
        synthetic(),
        config,
        gibbs.Settings(chains=2, warmup=20, draws=20, keep_every=4),
        log=lambda *_: None,
    )
    np.testing.assert_allclose(np.asarray(out["mean"]["unit_nu"]), 4.0)
    assert float(np.asarray(out["mean"]["unit_scale"])) > 0


def test_the_ar1_twin_differs_from_unitnu4_only_in_the_walk():
    base = model.MODELS[
        "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4"
    ]
    m = model.MODELS[base.name + "-arwalk-fixedrho"]
    assert (m.walk_ar, m.walk_ar_rho) == (True, 0.89)
    assert {k for k, v in vars(m).items() if getattr(base, k) != v} == {
        "name",
        "walk_ar",
        "walk_ar_rho",
    }


def test_gibbs_runs_the_fixed_rho_walk_with_slopemin3_and_fixed_unit_tails():
    config = dataclasses.replace(
        DESIGNS["tunits"],
        unit_nu_fixed=4.0,
        building_walk=True,
        walk_ar=True,
        walk_ar_rho=0.89,
        bedroom_slope=True,
        bedroom_slope_min_rows=3,
    )
    out = gibbs.run(
        synthetic(),
        config,
        gibbs.Settings(chains=2, warmup=20, draws=20, keep_every=4),
        log=lambda *_: None,
    )
    np.testing.assert_allclose(np.asarray(out["mean"]["unit_nu"]), 4.0)
    rho = np.asarray(out["trace"]["scalars"])[
        ..., gibbs.collect_module.SCALARS.index("walk_rho")
    ]
    np.testing.assert_allclose(rho, 0.89)
