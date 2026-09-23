import argparse
import json

import numpy as np
import pymc as pm

from models import jax_sampling_trial as trial


def test_summarize_writes_steps_and_repository_diagnostics(tmp_path):
    import nutpie

    with pm.Model() as model:
        scale = pm.HalfNormal("sigma", 1.0)
        pm.Normal("y", 0.0, scale, observed=np.random.default_rng(1).normal(size=50))
    inference = nutpie.sample(
        nutpie.compile_pymc_model(model),
        draws=60,
        tune=60,
        chains=2,
        seed=1,
        progress_bar=False,
    )
    inference.attrs["sampling_time"] = 2.0
    record = {"sampling_seconds": 2.0}
    args = argparse.Namespace(draws=60, tune=60)
    trial.summarize(record, inference, args, tmp_path)
    saved = json.loads((tmp_path / "trial.json").read_text())
    assert (
        saved["leapfrog_steps"]["mean"] > 0
        and saved["lockstep_steps_per_iteration"] >= saved["leapfrog_steps"]["mean"]
    )
    assert (
        saved["diagnostics"]["divergences"] >= 0
        and "min_ess_bulk" in saved["diagnostics"]
    )
    assert (
        saved["min_ess_bulk_per_sampling_second"]
        == saved["diagnostics"]["min_ess_bulk"] / 2.0
    )
