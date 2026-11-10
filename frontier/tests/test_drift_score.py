import numpy as np
import pytest
from scipy import integrate, stats

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
    np.testing.assert_allclose(out["elpd"], want, atol=1e-7)
    np.testing.assert_allclose(
        out["cdf"], stats.t.cdf((y - loc) / sigma, 4.0).mean(0), atol=1e-8
    )


@pytest.mark.parametrize("nu", [2.2, 4.0, 30.0])
def test_scores_match_the_integral_at_every_ratio_of_the_scales(nu):
    """A narrow Student-t inside a wide Normal, the two alike, and the reverse, at the
    centre and far out: a 21-node rule over the Normal lost up to 0.67 nats a row at
    sigma / unit sd = 1 / 6."""
    cases = [
        (sigma, usd, off)
        for sigma, usd in ((0.02, 0.12), (0.03, 0.1), (0.05, 0.05), (0.08, 0.01))
        for off in (0.0, 0.4, 1.7, 6.0, 25.0)
    ]
    sigma, usd, off = (np.array(v)[None, :] for v in zip(*cases))
    y = 8 + off[0] * np.hypot(sigma[0], usd[0])
    loc = np.full_like(sigma, 8.0)
    out = drift_score.score_rows(loc, usd, sigma, np.array([nu]), y, at=y - 0.03)
    for i, (s, u, _) in enumerate(cases):
        dens = lambda e, s=s, u=u, v=y[i]: (
            stats.t.pdf(e / s, nu)
            / s
            * stats.norm.pdf(  # noqa: E731
                v - 8 - e, 0, u
            )
        )
        mass = lambda e, s=s, u=u, v=y[i]: (
            stats.t.pdf(e / s, nu)
            / s
            * stats.norm.cdf(  # noqa: E731
                v - 8 - e, 0, u
            )
        )
        pts = [0.0, y[i] - 8]
        want = sum(
            integrate.quad(dens, a, b, limit=400, epsabs=0, epsrel=1e-10)[0]
            for a, b in zip([-np.inf, *sorted(pts)], [*sorted(pts), np.inf])
        )
        cdf = sum(
            integrate.quad(mass, a, b, limit=400, epsabs=1e-13, epsrel=1e-10)[0]
            for a, b in zip([-np.inf, *sorted(pts)], [*sorted(pts), np.inf])
        )
        assert abs(out["elpd"][i] - np.log(want)) < 2e-5, (cases[i], out["elpd"][i])
        assert abs(out["cdf"][i] - cdf) < 2e-6, (cases[i], out["cdf"][i], cdf)
    assert (out["cdf_at"] <= out["cdf"]).all() and (out["cdf_at"] < out["cdf"]).any()


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
