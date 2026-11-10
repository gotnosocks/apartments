import numpy as np
from scipy import stats

from rentfrontier import drift_score


def test_scores_match_a_plain_student_t_without_a_unit_sd():
    rng = np.random.default_rng(0)
    draws, rows = 50, 30
    loc = 8 + 0.01 * rng.standard_normal((draws, rows))
    sigma = np.full((draws, rows), 0.1)
    nu = np.full(draws, 4.0)
    y = 8 + 0.1 * rng.standard_normal(rows)
    out = drift_score.score_rows(loc, np.zeros((draws, rows)), sigma, nu, y)
    want = np.log(stats.t.pdf((y - loc) / sigma, 4.0).mean(0) / 0.1)
    np.testing.assert_allclose(out["elpd"], want, rtol=1e-10)
    np.testing.assert_allclose(
        out["cdf"], stats.t.cdf((y - loc) / sigma, 4.0).mean(0), rtol=1e-10
    )


def test_unit_sd_widens_the_predictive_distribution():
    rng = np.random.default_rng(1)
    draws, rows = 400, 200
    loc = np.full((draws, rows), 8.0)
    sigma = np.full((draws, rows), 0.05)
    usd = np.full((draws, rows), 0.1)
    nu = np.full(draws, 2000.0)
    # y drawn from the model: the intervals cover at their nominal rates and the cdf is flat.
    y = 8 + 0.1 * rng.standard_normal(rows) + 0.05 * rng.standard_normal(rows)
    out = drift_score.score_rows(loc, usd, sigma, nu, y, samples=8)
    width = out["q"][:, 6] - out["q"][:, 1]
    sd = np.hypot(0.1, 0.05)
    np.testing.assert_allclose(width.mean(), 2 * 1.645 * sd, rtol=0.05)
    assert 0.35 < out["cdf"].mean() < 0.65
    # The density is close to a Normal's with the joined variance.
    want = stats.norm.logpdf(y, 8.0, sd)
    assert np.abs(out["elpd"] - want).max() < 0.01
    res = out | dict(y=y)
    s = drift_score.summary(res)
    assert s["rows"] == rows and 0.8 < s["coverage"]["90"] <= 1.0
