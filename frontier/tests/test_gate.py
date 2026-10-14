import numpy as np

from rentfrontier import collect
from rentfrontier.run import building_diagnostics, diagnostics, split_rhat


def trace(rng, buildings, chains=2, draws=2000):
    def iid(*shape):
        return rng.normal(size=(chains, draws, *shape)).astype(np.float32)

    return {
        "scalars": iid(len(collect.SCALARS)),
        "beta": iid(2),
        "trend": iid(3),
        "fslope_scales": iid(1),
        "sigma_groups": iid(1),
        "building": buildings[..., :4],
        "unit": iid(4),
        "building_all": buildings,
    }


def test_split_rhat_vectorises_over_trailing_axes():
    x = np.random.default_rng(0).normal(size=(2, 500, 3))
    r = split_rhat(x)
    assert r.shape == (3,)
    for j in range(3):
        assert np.isclose(r[j], split_rhat(x[..., j]))


def test_iid_buildings_pass():
    rng = np.random.default_rng(1)
    b = rng.normal(size=(2, 2000, 300)).astype(np.float32)
    d = diagnostics(trace(rng, b), ["a", "b"], buildings=np.arange(300) + 1000)
    assert d["passes"]
    assert d["buildings"]["checked"] == 300
    assert d["buildings"]["over_rhat"] == 0
    assert d["_per_building"]["rhat"].shape == (300,)


def test_one_untraced_building_off_between_chains_fails_the_gate():
    rng = np.random.default_rng(2)
    b = rng.normal(size=(2, 2000, 300)).astype(np.float32)
    b[1, :, 250] += 0.5  # chain 2 sits elsewhere on building 250 only
    names = np.array([f"b{i}" for i in range(300)])
    d = diagnostics(trace(rng, b), ["a", "b"], buildings=names)
    assert not d["passes"]
    assert d["max_rhat_name"] == "building[b250]"
    assert d["buildings"]["over_rhat"] == 1


def test_slow_mixing_building_fails_on_ess():
    rng = np.random.default_rng(3)
    b = rng.normal(size=(2, 2000, 50))
    walk = np.zeros((2, 2000))
    for t in range(1, 2000):  # AR(1), rho 0.99: a few dozen effective draws
        walk[:, t] = 0.99 * walk[:, t - 1] + 0.14 * rng.normal(size=2)
    b[..., 7] = walk
    d = diagnostics(trace(rng, b.astype(np.float32)), ["a", "b"])
    assert not d["passes"]
    assert d["min_ess"] < 400
    assert d["min_ess_name"] == "building[7]"


def test_buildings_with_a_constant_effect_drop_out():
    rng = np.random.default_rng(4)
    b = rng.normal(size=(2, 1000, 20))
    b[..., 3] = 0.0
    out = building_diagnostics(b)
    assert np.isnan(out["rhat"][3]) and np.isnan(out["ess"][3])
    assert np.isfinite(np.delete(out["rhat"], 3)).all()


def test_building_diagnostics_chunks_agree_with_one_pass():
    b = np.random.default_rng(5).normal(size=(2, 400, 70))
    a = building_diagnostics(b, chunk=16)
    c = building_diagnostics(b, chunk=1000)
    assert np.allclose(a["rhat"], c["rhat"]) and np.allclose(a["ess"], c["ess"])


def test_traces_without_every_building_keep_the_traced_gate():
    rng = np.random.default_rng(6)
    t = trace(rng, rng.normal(size=(2, 2000, 8)).astype(np.float32))
    del t["building_all"]
    d = diagnostics(t, ["a", "b"])
    assert "buildings" not in d
    assert "32+32 traced" in d["gate"]


def test_a_stuck_building_fails_rather_than_dropping_out():
    rng = np.random.default_rng(7)
    b = rng.normal(size=(2, 1000, 20))
    b[0, :, 5], b[1, :, 5] = 0.0, 1.0
    out = building_diagnostics(b)
    assert np.isinf(out["rhat"][5])
    d = diagnostics(trace(rng, b[:, :, :].repeat(2, axis=1)[:, :2000]), ["a", "b"])
    assert not d["passes"]
