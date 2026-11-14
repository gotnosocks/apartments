import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import test_drift as td
import test_drift_building_phase_line as tln

from rentfrontier import drift, drift_building_phase, drift_building_phase_duplex
from rentfrontier import drift_building_phase_segment as seg_model
from rentfrontier import drift_today as dt

SC = dict(ss=0.06, sd=0.08, tau_u=2.5, s2=0.03**2, rho=0.8, nu=5.0)
# The line variance of the tests with lines.
L2 = 0.07**2


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


def toy_lines(seed=0, sites=5, units=20, k=2):
    """`toy`'s rows, with each building's units dealt into `k` lines by their number."""
    site, unit, t, c, r = toy(seed, sites, units)
    line = np.unique(site * k + unit % k, return_inverse=True)[1]
    return site, unit, t, c, r, line


def lined(site, unit, t, line, path=True, sites=5):
    """`dt.layout` of the rows, with their lines."""
    lay = dt.layout(site, unit, t, 4 if path else None, sites)
    return dt.with_lines(lay, site, line, int(line.max()) + 1)


def dense(site, unit, t, c, sc, path=True, line=None, l2=0.0):
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
    out = S + K + np.diag(1 / c)
    if line is not None:
        out = out + np.where(line[:, None] == line[None, :], l2, 0.0)
    return out


def dense_target(
    site, unit, t, c, r, sc, tu, ts, tt, path=True, line=None, l2=0.0, tl=-1
):
    """The dense conditional mean and variance of a row's path and unit term, and with
    `line` its line level, for a row of unit `tu`, building `ts`, time `tt` and line `tl`."""
    Sig = dense(site, unit, t, c, sc, path, line, l2)
    q, qt = np.floor(t * 4), np.floor(tt * 4)
    s2 = sc["s2"] if path else 0.0
    g = np.where(site == ts, s2 * sc["rho"] ** np.abs(qt - q), 0.0) + np.where(
        unit == tu,
        sc["ss"] ** 2 + sc["sd"] ** 2 * np.exp(-np.abs(tt - t) / sc["tau_u"]),
        0.0,
    )
    prior = s2 + sc["ss"] ** 2 + sc["sd"] ** 2
    if line is not None:
        g = g + np.where(line == tl, l2, 0.0)
        prior += l2
    mean = g @ np.linalg.solve(Sig, r)
    var = prior - g @ np.linalg.solve(Sig, g)
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


@pytest.mark.parametrize("path", [True, False])
def test_sigma_inverse_with_lines_matches_dense_algebra(path):
    site, unit, t, c, r, line = toy_lines()
    lay = lined(site, unit, t, line, path)
    Ws = dt.line_W(lay, dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"]), L2)
    Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])[1] if path else None
    got = dt.sigma_inv(lay, Ws, Qi, r)
    want = np.linalg.solve(dense(site, unit, t, c, SC, path, line, L2), r)
    np.testing.assert_allclose(got, want, rtol=1e-8, atol=1e-8)


@pytest.mark.parametrize("path", [True, False])
def test_targets_with_lines_match_dense_conditionals(path):
    """Rows of `drift_line`'s three cases: units with rows, at later days and inside their
    history; new units of a line with rows; and new lines, in a building with rows and in
    one with none."""
    site, unit, t, c, r, line = toy_lines(1)
    lay = lined(site, unit, t, line, path)
    Ws = dt.line_W(lay, dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"]), L2)
    H = Qi = None
    if path:
        H, Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])
    first = {u: np.flatnonzero(unit == u)[0] for u in np.unique(unit)}
    # Units 5 and 7 share a line in a building whose other line has rows too.
    assert line[first[5]] == line[first[7]] and site[first[5]] == site[first[6]]
    rows = [
        (0, site[first[0]], line[first[0]], 9.6),
        (3, site[first[3]], line[first[3]], 4.0),
        (3, site[first[3]], line[first[3]], 11.0),
        (19, site[first[19]], line[first[19]], 30.0),
        (-1, site[first[5]], line[first[5]], 9.6),
        (-1, site[first[6]], line[first[6]], 2.0),
        (-1, site[first[5]], -1, 9.6),
        (-1, 4, -1, 9.6),
    ]
    tu, ts, tl, tt = (np.array(v) for v in zip(*rows))
    q = np.floor(tt * 4).astype(int)
    keys, pair = dt.pairs(ts, q)
    tg = dict(unit=tu, site=ts, t=tt, q=q, pair_keys=keys, pair=pair, line=tl)
    sc = SC | {"l2": L2} | ({} if path else {"s2": 0.0})
    mean, var = dt.targets(lay, Ws, Qi, H, r, tg, sc)
    for k in range(len(tu)):
        m, v = dense_target(
            site, unit, t, c, r, SC, tu[k], ts[k], tt[k], path, line, L2, tl[k]
        )
        assert mean[k] == pytest.approx(m, abs=1e-9)
        assert var[k] == pytest.approx(v, abs=1e-9)


def test_prior_draw_with_lines_has_the_prior_covariance():
    site, unit, t, _, _, line = toy_lines(2, sites=3, units=6)
    lay = lined(site, unit, t, line, sites=3)
    sc = SC | {"l2": L2}
    rng, line_rng = np.random.default_rng(3), np.random.default_rng(5)
    draws = np.stack([dt.prior_draw(rng, lay, sc, line_rng) for _ in range(40_000)])
    want = dense(site, unit, t, np.full(len(t), np.inf), SC, line=line, l2=L2)
    np.testing.assert_allclose(np.cov(draws.T), want, atol=4e-4)


def test_targets_on_a_lined_design_match_the_dense_conditional():
    """A small LN1 design built as `test_drift_building_phase_line` builds its own, with
    its held-out rows predicted at their own dates in the three cases of `drift_line`'s
    prediction step."""
    full = td._design(per_unit=9)
    train, _, _ = tln._split(full, tln._lines(full))
    pred = train.pred
    pu, pl, ps, pt = pred["unit"], pred["line"], pred["site"], pred["years"]
    seen, known = pu >= 0, pl >= 0
    assert seen.any() and (~seen & known).any() and (~known).any()
    years = drift.years(train)
    order = np.lexsort((years, train.unit, train.site))
    site, unit, t = train.site[order], train.unit[order], years[order]
    line = train.line[order]
    sites = int(max(site.max(), ps.max())) + 1
    lay = dt.layout(site, unit, t, 4, sites)
    lay = dt.with_lines(lay, site, line, train.lines)
    rng = np.random.default_rng(6)
    c = rng.uniform(20, 400, len(site))
    r = 0.1 * rng.standard_normal(len(site))
    sc = SC | {"l2": tln.LINE_SD**2}
    Ws = dt.line_W(lay, dt.unit_W(lay, c, sc["ss"], sc["sd"], sc["tau_u"]), sc["l2"])
    H, Qi = dt.building_system(lay, Ws, sc["s2"], sc["rho"])
    q = np.floor(pt * 4).astype(np.int64)
    keys, pair = dt.pairs(ps, q)
    tg = dict(unit=pu, site=ps, t=pt, q=q, pair_keys=keys, pair=pair, line=pl)
    mean, var = dt.targets(lay, Ws, Qi, H, r, tg, sc)
    Sig = dense(site, unit, t, c, sc, True, line, sc["l2"])
    g = (
        np.where(
            site[None, :] == ps[:, None],
            sc["s2"] * sc["rho"] ** np.abs(q[:, None] - np.floor(t * 4)[None, :]),
            0.0,
        )
        + np.where(
            unit[None, :] == pu[:, None],
            sc["ss"] ** 2
            + sc["sd"] ** 2 * np.exp(-np.abs(pt[:, None] - t[None, :]) / sc["tau_u"]),
            0.0,
        )
        + np.where(line[None, :] == pl[:, None], sc["l2"], 0.0)
    )
    prior = sc["s2"] + sc["ss"] ** 2 + sc["sd"] ** 2 + sc["l2"]
    want_var = prior - np.einsum("pi,ip->p", g, np.linalg.solve(Sig, g.T))
    np.testing.assert_allclose(mean, g @ np.linalg.solve(Sig, r), rtol=0, atol=1e-9)
    np.testing.assert_allclose(var, want_var, rtol=0, atol=1e-9)


def fake_fit(lines, line_sd=0.0, draws=3, seed=0):
    """What `predict` reads of a fit, on `toy_lines`' rows, and rows to predict past the
    grid: every unit, a new unit of a known line and new lines. With `lines` the layout
    holds the rows' lines and the kept draws hold `line_sd`."""
    site, unit, t, _, r, line = toy_lines(seed)
    u = t * drift.YEAR_WEEKS
    week = np.floor(u)
    frac = u - week
    t = (week + frac) / drift.YEAR_WEEKS
    rng = np.random.default_rng(seed)
    weeks = int(week.max()) + 2
    kept = dict(
        L=np.cumsum(0.01 * rng.standard_normal((draws, weeks + 1)), axis=1),
        g=np.full(draws, 0.001),
        tau=np.full(draws, 0.01),
        unit_sd=np.full(draws, SC["ss"]),
        drift_sd=np.full(draws, SC["sd"]),
        drift_tau=np.full(draws, SC["tau_u"]),
        nu=np.full(draws, SC["nu"]),
        sigma=rng.uniform(0.05, 0.15, (draws, 4)),
        building_ar_sd=np.full(draws, np.sqrt(SC["s2"])),
        building_ar_rho=np.full(draws, SC["rho"]),
        bld=0.1 * rng.standard_normal((draws, 5)),
        gp_w=np.zeros((draws, 1)),
    )
    lay = dt.layout(site, unit, t, 4, 5)
    if lines:
        lay = dt.with_lines(lay, site, line, int(line.max()) + 1)
        kept["line_sd"] = np.full(draws, line_sd)
    fit = SimpleNamespace(
        kept=kept,
        pick=np.arange(draws),
        lay=lay,
        y=r + 0.2,
        xb=0.01 * rng.standard_normal((draws, len(site))).astype(np.float32),
        week=week,
        frac=frac,
        site=site,
        group=rng.integers(0, 4, len(site)),
        phase=None,
        Bc=np.zeros((5, 1)),
    )
    first = np.r_[0, np.flatnonzero(np.diff(unit)) + 1]
    tu = np.r_[unit[first], -1, -1, -1]
    ts = np.r_[site[first], site[0], site[0], 4]
    tl = np.r_[line[first], line[0], -1, -1]
    n = len(tu)
    rw = dt.Rows(
        unit=tu,
        site=ts,
        week=np.full(n, weeks + 3.0),
        frac=np.full(n, 0.5),
        xb=np.zeros((draws, n), np.float32),
        group=np.zeros(n, np.int64),
        phase=None,
        line=tl if lines else None,
    )
    return fit, rw


@pytest.mark.parametrize("line_sd", [0.0, 1e-6])
def test_with_no_line_spread_todays_prices_are_l1s(line_sd):
    l1, rw1 = fake_fit(lines=False)
    ln1, rw2 = fake_fit(lines=True, line_sd=line_sd)
    a = dt.predict(l1, [rw1], log=lambda s: None)[0]
    b = dt.predict(ln1, [rw2], log=lambda s: None)[0]
    for k in ("loc", "usd"):
        if line_sd == 0:
            np.testing.assert_array_equal(a[k], b[k])
        else:
            np.testing.assert_allclose(a[k], b[k], rtol=0, atol=1e-5)
    # A real line spread moves the prices.
    ln1.kept["line_sd"][:] = 0.1
    moved = dt.predict(ln1, [rw2], log=lambda s: None)[0]
    assert np.abs(moved["usd"] - a["usd"]).max() > 1e-3


def test_an_l1_fit_never_runs_the_line_code(monkeypatch):
    fit, rw = fake_fit(lines=False)
    want = dt.predict(fit, [rw], log=lambda s: None)[0]

    def refuse(*args, **kw):
        raise AssertionError("an L1 fit ran the line code")

    for name in ("with_lines", "line_W", "line_pairs"):
        monkeypatch.setattr(dt, name, refuse)
    monkeypatch.setattr(dt.drift_line, "line_layout", refuse)
    assert "line" not in fit.lay and "line" not in dt.target_index([rw])
    got = dt.predict(fit, [rw], log=lambda s: None)[0]
    for k in ("loc", "usd"):
        np.testing.assert_array_equal(got[k], want[k])


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


def test_unit_labels_come_from_the_ads_pages(tmp_path):
    ads = tmp_path / "ads.parquet"
    pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "page": [
                "https://streeteasy.com/building/10-bank-street-new_york/4flr",
                "https://streeteasy.com/building/44-berry/6c?featured=1",
                None,
            ],
        }
    ).to_parquet(ads)
    got = dt.unit_labels(ads, ["2", "3", "1", "9"])
    assert list(got) == ["6C", "", "4FLR", ""]


def test_the_phased_models_are_served():
    for name in (
        "drift-building-phase-level",
        "drift-building-phase-segment",
        "drift-building-phase-duplex",
        "drift-building-phase-line",
    ):
        assert name in dt.MODELS


def phase_fit(phases, phase, price_at, unit_id, held):
    fit = SimpleNamespace()
    fit.frame = pd.DataFrame({"price_at": price_at, "unit_id": unit_id})
    fit.held = np.asarray(held)
    fit.full = SimpleNamespace(phase=np.asarray(phase), phases=tuple(phases))
    return fit


def test_phase_today_bins_the_months_and_keeps_a_cells_mark():
    day = pd.Timestamp("2026-11-13")
    price_at = ["2026-10-01", "2025-12-01", "2024-01-01", "2026-01-01", "2026-11-01"]
    unit_id = ["1", "2", "3", None, "5"]
    held = [False, False, False, False, True]
    P = drift_building_phase.PHASES
    fit = phase_fit(P, [2, 2, 2, 2, 3], price_at, unit_id, held)
    got = dt.phase_today(fit, np.arange(5), day)
    # 1.4, 11.4 and 34.4 months; no unit; a held-out ad keeps its own phase.
    assert [P[i] for i in got] == ["0-2", "10-13", "26+", "none", "3-9"]
    cells = drift_building_phase_duplex.cells()
    own = [cells.index(c) for c in ("0-2|duplex", "3-9|other", "0-2|duplex")]
    fit = phase_fit(cells, own + [0, 1], price_at, unit_id, held)
    got = dt.phase_today(fit, np.arange(5), day)
    assert [cells[i] for i in got] == [
        "0-2|duplex",
        "10-13|other",
        "26+|duplex",
        "none|other",
        "10-13|duplex",
    ]
    fit = phase_fit(P[:2], [0, 0, 0, 0, 0], price_at, unit_id, held)
    with pytest.raises(SystemExit):
        dt.phase_today(fit, np.arange(5), day)


def test_phase_level_shift_moves_the_columns_to_todays_phase():
    P = drift_building_phase.PHASES
    names = ["alpha", "phase:none", "phase:0-2", "phase:3-9", "phase:26+"]
    rng = np.random.default_rng(0)
    beta = rng.standard_normal((3, len(names)))
    own = np.array([0, 1, 2, 3, 6, 4])
    fit = SimpleNamespace(
        names=names,
        kept={"beta": beta},
        full=SimpleNamespace(phase=own, phases=P),
    )
    today = np.array([2, 1, 6, 0, 6, 3])

    def x(phase):
        return np.stack(
            [np.ones(len(phase))]
            + [phase == P.index(n.split(":")[1]) for n in names[1:]],
            axis=1,
        )

    want = (x(today) - x(own)) @ beta.T
    rows = np.arange(len(own))
    np.testing.assert_allclose(dt.phase_level_shift(fit, rows, today), want.T)


def test_today_rows_moves_l2s_levels_and_the_paths_to_the_day(monkeypatch):
    P = drift_building_phase.PHASES
    rng = np.random.default_rng(2)
    base = rng.standard_normal((3, 4))
    own, today = np.array([0, 1, 2, 1]), np.array([2, 2, 1, 0])
    names = ["alpha", "phase:none", "phase:0-2"]
    fit = SimpleNamespace(
        names=names,
        kept={"beta": rng.standard_normal((3, len(names)))},
        season_cols=[],
        start=pd.Timestamp("2025-01-06"),
        full=SimpleNamespace(
            phase=own, phases=P, site=np.arange(4), group=np.zeros(4, int)
        ),
        seg=SimpleNamespace(),
    )
    seen = []

    def shift(f, rows, t_new):
        seen.append(t_new)
        return np.zeros((3, len(rows)))

    monkeypatch.setattr(dt, "base_xb", lambda f, rows: base.copy())
    monkeypatch.setattr(dt, "phase_today", lambda f, rows, day: today)
    monkeypatch.setattr(dt, "segment_shift", shift)
    apts = pd.DataFrame({"row": np.arange(4), "unit": np.arange(4)})
    day = pd.Timestamp("2026-11-13")
    rw = dt.today_rows(fit, apts, day)
    # The paths' time is `day`'s, in the years of the segment model's knots.
    years = (day - fit.start).days / seg_model.YEAR_DAYS
    assert seen == [pytest.approx(years)]
    level = dt.phase_level_shift(fit, np.arange(4), today)
    assert np.abs(level).min() > 0
    np.testing.assert_allclose(rw.xb, base + level)
    # L1's design has no level columns and no paths.
    fit.names, fit.kept["beta"], fit.seg = ["alpha"], fit.kept["beta"][:, :1], None
    np.testing.assert_allclose(dt.today_rows(fit, apts, day).xb, base)
    assert len(seen) == 1
    # A fit with lines gives each apartment its newest ad's line.
    assert dt.today_rows(fit, apts, day).line is None
    fit.full.line = np.array([5, -1, 2, 0])
    np.testing.assert_array_equal(dt.today_rows(fit, apts, day).line, [5, -1, 2, 0])


@dataclasses.dataclass
class SegDesign:
    x: np.ndarray
    names: list
    count: dict
    week: np.ndarray
    frac: np.ndarray
    start: pd.Timestamp
    site: np.ndarray
    group: np.ndarray
    surfaces: list


def test_segment_shift_matches_the_design_at_the_new_time():
    rng = np.random.default_rng(1)
    n = 400
    week = np.sort(rng.integers(0, 80, n))
    # The first quarter's rows are all of one segment, so its other columns are left out.
    site = np.where(week < 14, 0, rng.integers(0, 3, n))
    group = np.where(week < 14, 0, rng.integers(0, 4, n))
    base = SegDesign(
        x=np.ones((n, 1)),
        names=["alpha"],
        count={},
        week=week,
        frac=rng.uniform(0, 1, n),
        start=pd.Timestamp("2025-01-06"),
        site=site,
        group=group,
        surfaces=[{"name": "m", "sites": 2}, {"name": "o", "sites": 1}],
    )
    d = seg_model.segment_paths(base)
    sg = dt.segment_terms(d, d.names)
    assert len(sg.cols) < len(seg_model.segment_names(d)) * len(sg.knots)
    beta = rng.standard_normal((2, len(d.names)))
    fit = SimpleNamespace(
        seg=sg,
        pick=np.arange(2),
        kept={"beta": beta},
        full=SimpleNamespace(t=drift.years(d)),
    )
    rows = rng.choice(n, 50, replace=False)

    def x_at(t):
        h = seg_model.hat_weights(np.full(len(rows), t), sg.knots)[:, sg.j]
        return h * ((sg.row[rows][:, None] == sg.k) - sg.share[sg.j, sg.k])

    old = d.x[rows][:, sg.cols]
    for t_new in (0.7, sg.knots[-1]):
        want = (x_at(t_new) - old) @ beta[:, sg.cols].T
        np.testing.assert_allclose(dt.segment_shift(fit, rows, t_new), want.T)
    # Past the last quarter start the paths hold their value there.
    np.testing.assert_allclose(
        dt.segment_shift(fit, rows, sg.knots[-1] + 0.4),
        dt.segment_shift(fit, rows, sg.knots[-1]),
    )
    d.x[5, sg.cols[0]] += 0.1
    with pytest.raises(SystemExit):
        dt.segment_terms(d, d.names)
