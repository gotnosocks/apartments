import numpy as np
import pytest
from scipy import stats

from rentfrontier import drift_quantiles, drift_score, drift_today


def posterior(seed=0, draws=120, rows=40):
    """A small synthetic posterior with every kind of row: units with a record (a small
    unit sd), new units and new buildings (a large one, and locations that vary more over
    the draws), noise from a fifth of the unit sd to five times it, two-peaked rows, and
    degrees of freedom from 1.2 to 40."""
    rng = np.random.default_rng(seed)
    spread = rng.choice([0.01, 0.05, 0.3], rows)
    loc = (
        8
        + 0.4 * rng.standard_normal(rows)
        + spread * rng.standard_normal((draws, rows))
    )
    # Two-peaked rows: half the draws sit 0.6 higher.
    loc[: draws // 2, ::7] += 0.6
    usd = rng.choice([0.006, 0.03, 0.12, 0.35], rows) * rng.uniform(
        0.8, 1.2, (draws, rows)
    )
    sigma = rng.choice([0.02, 0.06, 0.15], rows) * rng.uniform(0.8, 1.2, (draws, rows))
    nu = rng.choice([1.2, 1.7, 2.0, 4.0, 40.0], draws)
    return loc, usd, sigma, nu


def test_the_exact_quantiles_sit_at_their_levels_of_the_cdf():
    block = posterior()
    q = drift_quantiles.exact(*block)
    assert q.shape == (40, len(drift_quantiles.LEVELS))
    share = drift_quantiles.cdf(q, *block)
    np.testing.assert_allclose(
        share, np.tile(drift_quantiles.LEVELS, (40, 1)), atol=1e-6, rtol=0
    )
    # In log rent too: a much tighter tolerance moves no quantile by 1e-6.
    tight = drift_quantiles.exact(*block, tol=1e-12)
    assert np.abs(q - tight).max() < 1e-6
    assert (
        np.abs(drift_quantiles.cdf(tight, *block) - drift_quantiles.LEVELS).max()
        < 1e-12
    )
    # Levels in any order and far in the tails.
    p = (0.999, 0.5, 1e-4)
    far = drift_quantiles.exact(*block, p=p)
    np.testing.assert_allclose(
        drift_quantiles.cdf(far, *block), np.tile(p, (40, 1)), atol=1e-7, rtol=0
    )
    assert (np.diff(q[:, :-1], axis=1) > 0).all()


def test_the_cdf_is_the_scores_cdf():
    loc, usd, sigma, nu = posterior(1)
    y = loc.mean(axis=0) + 0.1
    out = drift_score.score_rows(loc, usd, sigma, nu, y, samples=1)
    np.testing.assert_allclose(
        drift_quantiles.cdf(y, loc, usd, sigma, nu), out["cdf"], atol=1e-14, rtol=0
    )


def test_the_quantiles_of_one_normal_and_of_one_student_t():
    rows = 3
    one = np.ones((1, rows))
    # No noise to speak of: a Normal with the unit sd.
    q = drift_quantiles.exact(
        8 * one, 0.1 * one, 1e-9 * one, [5.0], p=(0.025, 0.5, 0.9)
    )
    np.testing.assert_allclose(
        q[0], 8 + 0.1 * stats.norm.ppf([0.025, 0.5, 0.9]), atol=1e-7
    )
    # No unit spread to speak of: a Student-t with the noise scale, up to the grid's error.
    for nu in (1.5, 3.0, 30.0):
        q = drift_quantiles.exact(
            8 * one, 1e-9 * one, 0.05 * one, [nu], p=(0.025, 0.5, 0.9)
        )
        want = 8 + 0.05 * stats.t.ppf([0.025, 0.5, 0.9], nu)
        np.testing.assert_allclose(q[0], want, atol=1e-6)


def test_the_blocks_and_the_threads_do_not_change_the_quantiles(monkeypatch):
    block = posterior(2, draws=30, rows=23)
    whole = drift_quantiles.exact(*block)
    monkeypatch.setattr(drift_quantiles, "BLOCK_ELEMENTS", 30 * drift_score.NODES * 4)
    # A block's sums run in another order, which moves the last digits and no more.
    small = drift_quantiles.exact(*block)
    np.testing.assert_allclose(small, whole, atol=1e-12, rtol=0)
    np.testing.assert_array_equal(drift_quantiles.exact(*block, workers=3), small)
    q, med = drift_quantiles.quantiles(*block)
    np.testing.assert_array_equal(np.c_[q, med], small)
    assert drift_quantiles.exact(*(v[:, :0] for v in block[:3]), block[3]).shape == (
        0,
        9,
    )


def test_a_far_start_and_a_bad_level_are_handled():
    # Components so far apart that the Normal start lands where the cdf is flat: the
    # bracket's bisection steps take over and the root is still found.
    loc = np.array([[0.0], [0.0], [0.0], [50.0]])
    usd = np.full((4, 1), 0.01)
    sigma = np.full((4, 1), 0.01)
    nu = np.full(4, 30.0)
    p = (0.025, 0.5, 0.74, 0.76, 0.975)
    q = drift_quantiles.exact(loc, usd, sigma, nu, p=p)
    np.testing.assert_allclose(
        drift_quantiles.cdf(q, loc, usd, sigma, nu)[0], p, atol=1e-6, rtol=0
    )
    assert q[0, 2] < 1 and q[0, 3] > 49
    with pytest.raises(ValueError):
        drift_quantiles.exact(loc, usd, sigma, nu, p=(0.0, 0.5))


def hard(rng, rows=40):
    """A block of rows on which Newton's step, unguarded, cycles: few components, some in
    two groups up to 3 apart, locations with an sd up to 1 over the components, unit sds
    from 0.001 to 0.5, noise scales from 0.005 to 0.3 and degrees of freedom from 1.2
    to 40."""
    d = rng.integers(2, 60)
    loc = 8 + rng.choice([0.005, 0.05, 0.3, 1.0]) * rng.standard_normal((d, rows))
    loc[: d // 2, ::5] += rng.choice([0.3, 1, 3])
    usd = 10 ** rng.uniform(-3, -0.3, (d, rows))
    sigma = 10 ** rng.uniform(-2.3, -0.5, (d, rows))
    return loc, usd, sigma, rng.choice([1.2, 1.7, 2, 4, 40], d)


def test_newton_does_not_cycle_between_the_ends_of_a_bracket():
    # Row 18 of the third block: at the 5% level Newton's step from either end of the
    # bracket lands on the other end, so with no safeguard but the bracket the solver
    # ran out of evaluations.
    rng = np.random.default_rng(1)
    for _ in range(3):
        loc, usd, sigma, nu = hard(rng)
    row = [v[:, 18:19] for v in (loc, usd, sigma)]
    q = drift_quantiles.exact(*row, nu, p=(0.05,), max_iter=20)
    assert abs(drift_quantiles.cdf(q, *row, nu)[0, 0] - 0.05) <= 1e-6


def test_the_solver_converges_on_hard_rows():
    rng = np.random.default_rng(1)
    levels = np.array(drift_quantiles.LEVELS)
    for _ in range(10):
        block = hard(rng)
        # Well inside `MAX_ITER`: the hardest of these rows takes under 30 evaluations.
        q = drift_quantiles.exact(*block, max_iter=40)
        assert np.abs(drift_quantiles.cdf(q, *block) - levels).max() <= 1e-6


def test_many_replicates_bring_the_sampled_quantiles_to_the_exact_ones():
    loc, usd, sigma, nu = posterior(3, draws=60, rows=12)
    nu = np.full(60, 4.0)
    exact_q, exact_med = drift_quantiles.quantiles(loc, usd, sigma, nu)
    gap = {}
    for samples in (8, 8_000):
        q, med = drift_today.quantiles(loc, usd, sigma, nu, seed=1, samples=samples)
        gap[samples] = max(np.abs(q - exact_q).max(), np.abs(med - exact_med).max())
    # 480,000 replicates a row: the 2.5% point's standard error is about 0.002 here.
    assert gap[8_000] < 0.01 and gap[8_000] < 0.2 * gap[8]
    # The score's own sampled quantiles, the same way.
    y = loc.mean(axis=0)
    out = drift_score.score_rows(loc, usd, sigma, nu, y, seed=2, samples=8_000)
    assert np.abs(out["q"] - exact_q).max() < 0.01
    assert np.abs(out["pred"] - exact_med).max() < 0.003


def test_exact_scores_put_an_ask_under_a_bound_exactly_when_its_share_is():
    # The Deals table's lo95, lo80 and lo50 are the 2.5%, 10% and 25% points and its hi
    # bounds the 75%, 90% and 97.5% points. With exact quantiles an ask is under a bound
    # exactly when the share of the distribution under the ask is under the bound's level.
    loc, usd, sigma, nu = posterior(4, draws=80, rows=400)
    rng = np.random.default_rng(5)
    y = loc.mean(axis=0) + 0.25 * rng.standard_t(3, 400)
    out = drift_score.score_rows(loc, usd, sigma, nu, y, exact=True)
    assert out["q"].dtype == np.float64
    sides = 0
    for j, level in enumerate(drift_score.Q):
        under = y < out["q"][:, j]
        np.testing.assert_array_equal(under, out["cdf"] < level)
        sides += under.sum()
    np.testing.assert_array_equal(y < out["pred"], out["cdf"] < 0.5)
    assert 0 < sides < 400 * len(drift_score.Q)
    # Asks set right at a bound are within the tolerance of its level.
    at = drift_score.score_rows(loc, usd, sigma, nu, out["q"][:, 1], exact=True)
    np.testing.assert_allclose(at["cdf"], 0.05, atol=1e-6, rtol=0)
    # The exact path reads no seed and leaves the other scores alone.
    again = drift_score.score_rows(
        loc, usd, sigma, nu, y, seed=9, samples=1, exact=True
    )
    sampled = drift_score.score_rows(loc, usd, sigma, nu, y, seed=9)
    for k in ("q", "pred"):
        np.testing.assert_array_equal(again[k], out[k])
    for k in ("elpd", "cdf", "unit_sd"):
        np.testing.assert_array_equal(sampled[k], out[k])
    assert sampled["q"].dtype == np.float32
    # The sampled bounds leave some asks on the other side from their share.
    wrong = sum(
        ((y < sampled["q"][:, j]) != (out["cdf"] < level)).sum()
        for j, level in enumerate(drift_score.Q)
    )
    assert wrong > 0
