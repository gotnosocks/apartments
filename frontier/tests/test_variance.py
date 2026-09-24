import numpy as np
from rentfrontier import variance


def synthetic(rng, draws=50, rows=20000):
    market = rng.normal(0, 0.1, (1, rows)).repeat(draws, 0)
    feats = rng.normal(0, 0.3, (1, rows)).repeat(draws, 0)
    building = rng.normal(0, 0.2, (1, rows)).repeat(draws, 0)
    unit = rng.normal(0, 0.1, (1, rows)).repeat(draws, 0)
    noise = rng.normal(0, 0.05, rows)
    terms = {"market": market, "bedrooms": feats, "building": building, "unit": unit}
    y = (market + feats + building + unit)[0] + noise
    return y, terms


def test_shares_sum_to_one_and_recover_independent_fractions():
    rng = np.random.default_rng(0)
    y, terms = synthetic(rng)
    sh = variance.decompose(y, terms)
    total = sum(sh[g] for g in (*variance.GROUPS, "residual"))
    np.testing.assert_allclose(total, 1.0, atol=1e-12)
    true = np.array([0.01, 0.09, 0.04, 0.01, 0.0025])
    true = true / true.sum()
    got = [
        sh[g].mean()
        for g in ("market and time", "features", "building", "unit", "residual")
    ]
    np.testing.assert_allclose(got, true, atol=0.01)
    assert np.allclose(sh["building over time"], 0)


def test_streaming_chunks_match_one_shot():
    rng = np.random.default_rng(1)
    y, terms = synthetic(rng, rows=9000)
    one = variance.decompose(y, terms)
    m = variance.Moments(50)
    for idx in np.array_split(np.arange(9000), 7):
        m.add(
            variance.grouped({k: v[:, idx] for k, v in terms.items()}, 50, len(idx)),
            y[idx],
        )
    many = m.shares()
    for g in (*variance.GROUPS, "residual"):
        np.testing.assert_allclose(many[g], one[g], atol=1e-10)
