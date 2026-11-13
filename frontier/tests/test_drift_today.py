import numpy as np
import pandas as pd
import pytest

from rentfrontier import drift_today as dt

SC = dict(ss=0.06, sd=0.08, tau_u=2.5, s2=0.03**2, rho=0.8, nu=5.0)


def toy(seed=0, sites=5, units=14):
    """Training rows of a few buildings sorted by building, unit and time, with quarters
    far apart in some buildings so that the padded systems have gaps."""
    rng = np.random.default_rng(seed)
    site_of = np.sort(rng.integers(0, sites - 1, units))  # the last building has no row
    n_of = rng.integers(1, 6, units)
    site = np.repeat(site_of, n_of)
    unit = np.repeat(np.arange(units), n_of)
    t = np.concatenate([np.sort(rng.uniform(0, 9, k)) for k in n_of])
    c = rng.uniform(20, 400, len(site))
    r = 0.1 * rng.standard_normal(len(site))
    return site, unit, t, c, r


def dense(site, unit, t, c, sc, path=True):
    q = np.floor(t * 4)
    same_site = site[:, None] == site[None, :]
    same_unit = unit[:, None] == unit[None, :]
    S = np.where(same_site, sc["s2"] * sc["rho"] ** np.abs(q[:, None] - q[None, :]), 0)
    S = S if path else 0 * S
    K = np.where(
        same_unit,
        sc["ss"] ** 2
        + sc["sd"] ** 2 * np.exp(-np.abs(t[:, None] - t[None, :]) / sc["tau_u"]),
        0,
    )
    return S + K + np.diag(1 / c)


def dense_target(site, unit, t, c, r, sc, tu, ts, tt, path=True):
    Sig = dense(site, unit, t, c, sc, path)
    q, qt = np.floor(t * 4), np.floor(tt * 4)
    s2 = sc["s2"] if path else 0.0
    g = np.where(site == ts, s2 * sc["rho"] ** np.abs(qt - q), 0.0) + np.where(
        unit == tu,
        sc["ss"] ** 2 + sc["sd"] ** 2 * np.exp(-np.abs(tt - t) / sc["tau_u"]),
        0.0,
    )
    mean = g @ np.linalg.solve(Sig, r)
    var = s2 + sc["ss"] ** 2 + sc["sd"] ** 2 - g @ np.linalg.solve(Sig, g)
    return mean, var


@pytest.mark.parametrize("path", [True, False])
def test_sigma_inverse_matches_dense_algebra(path):
    site, unit, t, c, r = toy()
    lay = dt.layout(site, unit, t, 4 if path else None, 5)
    Ws = dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"])
    Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])[1] if path else None
    got = dt.sigma_inv(lay, Ws, Qi, r)
    want = np.linalg.solve(dense(site, unit, t, c, SC, path), r)
    np.testing.assert_allclose(got, want, rtol=1e-8, atol=1e-8)


@pytest.mark.parametrize("path", [True, False])
def test_targets_match_dense_conditionals(path):
    """Rows to predict in every case: a unit with rows, at a later day and inside its
    history, a new unit in a building with rows, and a new unit in a building with none."""
    site, unit, t, c, r = toy(1)
    lay = dt.layout(site, unit, t, 4 if path else None, 5)
    Ws = dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"])
    H = Qi = None
    if path:
        H, Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])
    tu = np.array([0, 3, 3, 9, -1, -1, 13, 13])
    ts = np.array(
        [
            site[unit == u][0] if u >= 0 else s
            for u, s in zip(tu, [0, 0, 0, 0, 1, 4, 0, 0])
        ]
    )
    tt = np.array([9.6, 4.0, 11.0, 9.6, 9.6, 9.6, 2.0, 30.0])
    q = np.floor(tt * 4).astype(int)
    keys, pair = dt.pairs(ts, q)
    tg = dict(unit=tu, site=ts, t=tt, q=q, pair_keys=keys, pair=pair)
    sc = SC | ({} if path else {"s2": 0.0})
    mean, var = dt.targets(lay, Ws, Qi, H, r, tg, sc)
    for k in range(len(tu)):
        m, v = dense_target(site, unit, t, c, r, SC, tu[k], ts[k], tt[k], path)
        assert mean[k] == pytest.approx(m, abs=1e-9)
        assert var[k] == pytest.approx(v, abs=1e-9)


def test_prior_draw_has_the_prior_covariance():
    site, unit, t, c, _ = toy(2, sites=3, units=5)
    lay = dt.layout(site, unit, t, 4, 3)
    rng = np.random.default_rng(3)
    draws = np.stack([dt.prior_draw(rng, lay, SC) for _ in range(40_000)])
    want = dense(site, unit, t, np.full(len(t), np.inf), SC)
    np.testing.assert_allclose(np.cov(draws.T), want, atol=4e-4)


def test_lam_step_draws_the_noise_conditional():
    """With one row the noise given r is Normal with a known mean and variance, so the
    mean of the Gamma's rate term checks the Matheron draw of the noise."""
    site, unit, t = np.array([0]), np.array([0]), np.array([1.0])
    c = np.array([100.0])
    r = np.array([0.2])
    lay = dt.layout(site, unit, t, 4, 1)
    sc = SC | {"nu": 1e6}
    Ws = dt.unit_W(lay, c, sc["ss"], sc["sd"], sc["tau_u"])
    Qi = dt.building_system(lay, Ws, sc["s2"], sc["rho"])[1]
    rng = np.random.default_rng(4)
    eps = []
    for _ in range(20_000):
        e0 = rng.standard_normal(1) / np.sqrt(c)
        delta = r - dt.prior_draw(rng, lay, sc) - e0
        eps.append(e0 + dt.sigma_inv(lay, Ws, Qi, delta) / c)
    eps = np.concatenate(eps)
    k = sc["s2"] + sc["ss"] ** 2 + sc["sd"] ** 2
    noise = 1 / c[0]
    assert eps.mean() == pytest.approx(r[0] * noise / (k + noise), abs=2e-4)
    assert eps.var() == pytest.approx(noise * k / (k + noise), rel=0.03)
    lam = dt.lam_step(rng, lay, Ws, Qi, r, c, np.array([0.1]), sc)
    assert lam[0] == pytest.approx(1.0, abs=0.01)


def test_quantiles_of_a_normal_mixture():
    loc = np.zeros((4, 1))
    usd = np.full((4, 1), 0.1)
    sig = np.full((4, 1), 1e-6)
    q, med = dt.quantiles(loc, usd, sig, np.full(4, 5.0), samples=50_000)
    assert med[0] == pytest.approx(0.0, abs=0.003)
    assert q[0, 5] == pytest.approx(0.1 * 1.2816, abs=0.004)


def test_season_matches_the_design():
    day = pd.Timestamp("2026-11-13")
    got = dt.season_at(day)
    doy = day.dayofyear - 1 + 0.5
    assert got["sin1"] == pytest.approx(np.sin(2 * np.pi * doy / 365.25))
    assert got["cos2"] == pytest.approx(np.cos(4 * np.pi * doy / 365.25))


class FakeFit:
    def __init__(self, L, g, tau):
        self.kept = dict(
            L=np.asarray([L]),
            g=np.asarray([g]),
            tau=np.asarray([tau]),
            unit_sd=np.ones(1),
            drift_sd=np.ones(1),
            drift_tau=np.ones(1),
            nu=np.ones(1),
            sigma=np.ones((1, 4)),
        )
        self.lay = {"path": False}


def test_walk_interpolates_inside_the_grid_and_drifts_past_it():
    fit = FakeFit([0.0, 0.1, 0.3], g=0.01, tau=0.02)
    week = np.array([0, 1, 2, 2, 5])
    mean, var = dt.walk(fit, 0, week, np.array([0.5, 0.25, 0.0, 0.5, 0.0]))
    np.testing.assert_allclose(mean, [0.05, 0.15, 0.3, 0.3 + 0.005, 0.3 + 0.03])
    np.testing.assert_allclose(var, [0, 0, 0, 0.5 * 0.02**2, 3 * 0.02**2])
    # A week given as floats, as today_rows builds it, gives the same walk.
    again, _ = dt.walk(fit, 0, week.astype(float), np.array([0.5, 0.25, 0.0, 0.5, 0.0]))
    np.testing.assert_allclose(again, mean)


def test_apartments_take_each_units_newest_ad():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "b", "b"],
            "unit_id": ["1", "1", "2", None, "7"],
            "latest_day": [
                "2026-01-01",
                "2026-05-01",
                "2025-01-01",
                "2026-02-01",
                "2026-11-01",
            ],
        }
    )
    held = np.array([False, False, False, False, True])
    fit = type("F", (), {})()
    fit.frame, fit.held = frame, held
    fit.full = type("U", (), {"unit": np.array([0, 0, 1, 2, -1])})()
    out = dt.apartments(fit).set_index("apartment")
    assert out.loc["a|1", "row"] == 1 and out.loc["a|1", "unit_ads"] == 2
    assert out.loc["a|2", "unit_ads"] == 1
    assert out.loc["b|", "unit"] == 2
    assert out.loc["b|7", "held"] and out.loc["b|7", "unit_ads"] == 0
