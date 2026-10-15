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
