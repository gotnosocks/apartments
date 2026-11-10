"""Pooling the chains of several runs of one fit (`rentfrontier.drift_pool`)."""

import json

import numpy as np
import pytest

from rentfrontier import drift, drift_pool
from rentfrontier.run import split_rhat


def _part(tmp_path, name, seed, draws, kept, shift=0.0, **over):
    rng = np.random.default_rng(seed)
    arrays = {
        "trace/nu": rng.normal(size=(2, draws)) + shift,
        "trace/beta": rng.normal(size=(2, draws, 3)),
        "kept/nu": rng.normal(size=(2, kept)),
        "kept/pred_loc": rng.normal(size=(2, kept, 5)),
        "kept/pred_y": np.arange(5.0),
        "kept/pred_group": np.array([0, 1, 2, 3, 0]),
        "names": np.array(["alpha", "a", "b"]),
        "heldout": np.array([True, False, True]),
    }
    record = {
        "name": name,
        "commit": "abc",
        "dirty": False,
        "started_at": f"2026-11-10T0{seed}:00:00+0000",
        "dataset_observations_sha256": "d",
        "split": "latest",
        "split_seed": 1,
        "feature_set": "drift-building",
        "model": {"name": "drift-building", "priors": {"a": 1}},
        "sampler": "drift-building",
        "tier": "full",
        "sizes": {"train": 10, "heldout": 5},
        "sampler_settings": {"chains": 2, "warmup": 10, "draws": 99, "seed": seed},
        "seconds": {"prepare": 1.0, "sampling": 10.0},
        "cost_usd": None,
        "diagnostics": {"passes": False, "max_rhat": 1.2, "min_ess": 30.0},
        "gibbs": {"sweeps": 10 + draws, "seconds_per_sweep": 1.5},
        "log": ["first", "second"],
    } | over
    d = tmp_path / name
    d.mkdir()
    np.savez_compressed(d / "posterior.npz", **arrays)
    (d / "result.json").write_text(json.dumps(record))
    return arrays, record


@pytest.fixture
def table(monkeypatch):
    def diagnostics(trace, names):
        r = split_rhat(np.asarray(trace["nu"]))
        return {
            "max_rhat": r,
            "max_rhat_name": "nu",
            "min_ess": 500.0,
            "min_ess_name": "nu",
            "passes": r <= 1.01,
            "chains": trace["nu"].shape[0],
            "names": list(names),
        }

    monkeypatch.setattr(drift, "diagnostics", diagnostics)


def test_pooled_run_has_every_parts_chains_cut_to_the_shortest_part(tmp_path, table):
    a, _ = _part(tmp_path, "a", 1, draws=400, kept=20)
    b, _ = _part(tmp_path, "b", 2, draws=300, kept=15)
    c, _ = _part(tmp_path, "c", 3, draws=360, kept=18)
    drift_pool.main(["all", "a", "b", str(tmp_path / "c"), "--runs", str(tmp_path)])
    z = np.load(tmp_path / "all" / "posterior.npz")
    assert z["trace/nu"].shape == (6, 300)
    assert z["trace/beta"].shape == (6, 300, 3)
    assert z["kept/pred_loc"].shape == (6, 15, 5)
    np.testing.assert_array_equal(z["trace/nu"][:2], a["trace/nu"][:, :300])
    np.testing.assert_array_equal(z["trace/nu"][2:4], b["trace/nu"])
    np.testing.assert_array_equal(z["kept/pred_loc"][4:], c["kept/pred_loc"][:, :15])
    # The predicted rows' data and the run's own arrays have no chain axis.
    np.testing.assert_array_equal(z["kept/pred_y"], a["kept/pred_y"])
    np.testing.assert_array_equal(z["kept/pred_group"], a["kept/pred_group"])
    np.testing.assert_array_equal(z["names"], a["names"])
    np.testing.assert_array_equal(z["heldout"], a["heldout"])
    r = json.loads((tmp_path / "all" / "result.json").read_text())
    assert r["name"] == "all"
    assert r["sampler_settings"]["chains"] == 6
    assert r["pooled_draws"] == {"traced": 300, "kept": 15}
    assert [p["seed"] for p in r["pooled_from"]] == [1, 2, 3]
    assert [p["sweeps"] for p in r["pooled_from"]] == [410, 310, 370]
    assert r["seconds"] == {"prepare": 3.0, "sampling": 30.0}
    assert r["started_at"] == "2026-11-10T01:00:00+0000"
    # The table is the pooled chains', not a part's.
    assert r["diagnostics"]["chains"] == 6
    assert r["diagnostics"]["names"] == ["alpha", "a", "b"]
    assert r["diagnostics"]["passes"]
    assert r["log"][0] == "a: first" and r["log"][-1] == "c: second"


def test_parts_that_disagree_fail_the_pooled_gate_though_each_passes_alone(
    tmp_path, table
):
    _part(tmp_path, "a", 1, draws=400, kept=20)
    _part(tmp_path, "b", 2, draws=400, kept=20, shift=1.0)
    drift_pool.main(["all", "a", "b", "--runs", str(tmp_path)])
    r = json.loads((tmp_path / "all" / "result.json").read_text())
    assert not r["diagnostics"]["passes"]
    assert r["diagnostics"]["max_rhat"] > 1.1


def test_pooling_refuses_parts_that_are_not_one_fit_on_different_seeds(tmp_path, table):
    _part(tmp_path, "a", 1, draws=40, kept=4)
    _part(tmp_path, "same-seed", 1, draws=40, kept=4)
    _part(tmp_path, "other-commit", 2, draws=40, kept=4, commit="def")
    _part(tmp_path, "other-data", 3, draws=40, kept=4, dataset_observations_sha256="e")
    _part(
        tmp_path,
        "other-settings",
        4,
        draws=40,
        kept=4,
        sampler_settings={"chains": 2, "warmup": 20, "draws": 99, "seed": 4},
    )
    _part(tmp_path, "dirty", 5, draws=40, kept=4, dirty=True)
    for other, why in (
        ("same-seed", "share a seed"),
        ("other-commit", "differ in commit"),
        ("other-data", "differ in dataset_observations_sha256"),
        ("other-settings", "differ in their settings"),
        ("dirty", "differ in dirty"),
    ):
        with pytest.raises(SystemExit, match=why):
            drift_pool.main(["all", "a", other, "--runs", str(tmp_path)])
    # The predicted rows may differ in a logarithm's last bit, and by no more.
    for name, off, ok in (("last-bit", 2e-15, True), ("other-rows", 1e-6, False)):
        arrays, _ = _part(tmp_path, name, 6, draws=40, kept=4)
        arrays["kept/pred_y"] = arrays["kept/pred_y"] + off
        np.savez_compressed(tmp_path / name / "posterior.npz", **arrays)
        if ok:
            drift_pool.main(["bit", "a", name, "--runs", str(tmp_path)])
        else:
            with pytest.raises(SystemExit, match="differ in kept/pred_y"):
                drift_pool.main(["all", "a", name, "--runs", str(tmp_path)])
    with pytest.raises(SystemExit, match="at least two"):
        drift_pool.main(["all", "a", "--runs", str(tmp_path)])
    assert not (tmp_path / "all").exists()
    _part(tmp_path, "b", 2, draws=40, kept=4)
    drift_pool.main(["all", "a", "b", "--runs", str(tmp_path)])
    with pytest.raises(SystemExit, match="already has a result"):
        drift_pool.main(["all", "a", "b", "--runs", str(tmp_path)])
