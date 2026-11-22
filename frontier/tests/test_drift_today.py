import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import test_drift as td
import test_drift_building_phase_line as tln

from rentfrontier import (
    building_attrs,
    drift,
    drift_building_phase,
    drift_building_phase_duplex,
    drift_building_phase_year,
    drift_score,
)
from rentfrontier import drift_building_phase_segment as seg_model
from rentfrontier import drift_building_phase_unitkn_ablate as ablate
from rentfrontier import drift_building_phase_unitkn_unified as unified
from rentfrontier import drift_building_phase_unitkn_unified_seg as unified_seg
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


def test_the_table_draws_as_many_replicates_as_the_score_in_no_more_memory():
    # The Today table's bounds are sampled like the score's, and a block holds no more
    # replicates of a component than it did at 4 replicates and 20,000 rows.
    assert dt.SAMPLES == dt.drift_score.SAMPLES >= 32
    assert dt.SAMPLES * dt.CHUNK <= 4 * 20_000
    rng = np.random.default_rng(3)
    loc = 8 + 0.03 * rng.standard_normal((192, 40))
    usd, sig = np.full(loc.shape, 0.065), np.full(loc.shape, 0.06)
    nu = np.full(192, 4.0)
    spread = {}
    for samples in (4, dt.SAMPLES):
        q = [
            dt.quantiles(loc, usd, sig, nu, seed=k, samples=samples)[0]
            for k in range(6)
        ]
        spread[samples] = np.std(np.stack(q)[:, :, [0, 7]], axis=0, ddof=1).mean()
    assert spread[dt.SAMPLES] < 0.5 * spread[4]
    assert spread[dt.SAMPLES] < 0.006


def table_inputs(n, seed=0):
    """What `table` reads for `n` apartments whose prices are far apart and tightly known:
    apartment j's median is close to 1,000 (j + 1) dollars. The apartments are not in
    name order, and each one's frame row is not its place among them."""
    rng = np.random.default_rng(seed)
    row = rng.permutation(n)
    name = rng.permutation(n)
    frame = pd.DataFrame(
        {
            "listing_id": np.arange(n) + 500,
            "building": [f"b{k % 3}" for k in range(n)],
            "unit_id": [str(k) for k in range(n)],
            "neighbourhood": "Chelsea",
            "bedrooms": 1.0,
            "full_baths": 1.0,
            "half_baths": 0.0,
            "latest_day": "2026-11-01",
            "latest_ask": 3000.0,
        }
    )
    apts = pd.DataFrame(
        {
            "apartment": [f"a{k:03d}" for k in name],
            "row": row,
            "held": np.arange(n) % 2 == 0,
            "unit_ads": np.arange(n),
        }
    )
    price = 1000.0 * (np.arange(n) + 1)
    comp = dict(
        loc=np.tile(np.log(price), (3, 1)).astype(np.float32),
        usd=np.full((3, n), 1e-3, np.float32),
        nu=np.full(3, 5.0),
        sigma=np.full((3, 2), 1e-3),
        phase=None,
    )
    rw = SimpleNamespace(group=np.arange(n) % 2, phase=None)
    return SimpleNamespace(frame=frame), apts, comp, rw, price


@pytest.mark.parametrize("n", [1, 3, 4, 5, 7, 8, 9])
def test_the_table_gives_every_apartment_its_own_row_at_the_block_edges(monkeypatch, n):
    # One fewer than, exactly and one more than one and two blocks of 4.
    monkeypatch.setattr(dt, "CHUNK", 4)
    fit, apts, comp, rw, price = table_inputs(n)
    out = dt.table(fit, apts, comp, rw, None)
    assert list(out.columns) == list(dt.COLUMNS)
    assert sorted(apts.apartment) == list(out.apartment)
    got = out.set_index("apartment").loc[apts.apartment]
    # Each apartment keeps its own frame row, counts and prices: none is dropped, repeated
    # or moved to a neighbour's place where one block ends and the next begins.
    np.testing.assert_array_equal(
        got.listing_id.to_numpy(), (apts.row.to_numpy() + 500).astype(str)
    )
    np.testing.assert_array_equal(got.unit_ads.to_numpy(), apts.unit_ads.to_numpy())
    np.testing.assert_array_equal(got.on_market.to_numpy(), apts.held.to_numpy())
    bounds = got[["median", *dt.BOUNDS]].to_numpy(float)
    assert np.isfinite(bounds).all() and np.isfinite(got.unit_sd.to_numpy()).all()
    np.testing.assert_allclose(bounds, price[:, None] * np.ones(7), rtol=0.02)
    assert (np.diff(got[list(dt.BOUNDS)].to_numpy(float), axis=1) >= 0).all()


def test_the_tables_draws_are_keyed_by_block():
    # Sampled, as the table is unless asked for the exact bounds, a block's replicates come
    # from a stream seeded with the block's first place, so the sampled bounds depend on
    # CHUNK by design: the table is each block's `quantiles`.
    n = 9
    fit, apts, comp, rw, _ = table_inputs(n)
    tables = {}
    for chunk in (4, n + 1):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(dt, "CHUNK", chunk)
            out = dt.table(fit, apts, comp, rw, None, exact=False)
        got = out.set_index("apartment").loc[apts.apartment]
        tables[chunk] = got[["median", *dt.BOUNDS]].to_numpy(float)
        for a in range(0, n, chunk):
            sl = slice(a, a + chunk)
            q, med = dt.quantiles(
                comp["loc"][:, sl].astype(float),
                comp["usd"][:, sl].astype(float),
                dt.mixture_sd(comp, rw, sl),
                comp["nu"],
                seed=a,
            )
            want = np.exp(np.c_[med, q[:, list(dt.BOUNDS.values())]]).round(0)
            np.testing.assert_array_equal(tables[chunk][sl], want)
    # The first block of 4 starts the same stream as the one block of 10, but lays its
    # draws out over fewer rows, so the two tables differ.
    assert not np.array_equal(tables[4], tables[n + 1])
    np.testing.assert_allclose(tables[4], tables[n + 1], rtol=0.02)


def test_the_exact_table_does_not_depend_on_the_blocks_or_the_threads():
    # With `exact` the bounds are the roots of each apartment's cdf: the same table whatever
    # CHUNK and the threads, with every bound at its level of the cdf.
    n = 9
    fit, apts, comp, rw, _ = table_inputs(n)
    tables = []
    for chunk, workers in ((4, 1), (n + 1, 1), (4, 3)):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(dt, "CHUNK", chunk)
            out = dt.table(fit, apts, comp, rw, None, exact=True, workers=workers)
        got = out.set_index("apartment").loc[apts.apartment]
        tables.append(got[["median", *dt.BOUNDS]].to_numpy(float))
    np.testing.assert_array_equal(tables[0], tables[1])
    np.testing.assert_array_equal(tables[0], tables[2])
    block = (
        comp["loc"].astype(float),
        comp["usd"].astype(float),
        dt.mixture_sd(comp, rw),
        comp["nu"],
    )
    q, med = dt.drift_quantiles.quantiles(*block)
    want = np.exp(np.c_[med, q[:, list(dt.BOUNDS.values())]]).round(0)
    np.testing.assert_array_equal(tables[0], want)
    levels = [dt.drift_score.Q[i] for i in dt.BOUNDS.values()]
    share = dt.drift_quantiles.cdf(q[:, list(dt.BOUNDS.values())], *block)
    np.testing.assert_allclose(share, np.tile(levels, (n, 1)), atol=1e-6, rtol=0)


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
        "drift-building-phase-plutoasof",
    ):
        assert name in dt.MODELS


def phase_fit(phases, phase, price_at, unit_id, held):
    fit = SimpleNamespace()
    fit.frame = pd.DataFrame({"price_at": price_at, "unit_id": unit_id})
    fit.held = np.asarray(held)
    fit.full = SimpleNamespace(
        phase=np.asarray(phase), phases=tuple(phases), cells=None
    )
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
    marked = "duplex or penthouse"
    own = [cells.index(c) for c in (f"0-2|{marked}", "3-9|other", f"0-2|{marked}")]
    fit = phase_fit(cells, own + [0, 1], price_at, unit_id, held)
    got = dt.phase_today(fit, np.arange(5), day)
    assert [cells[i] for i in got] == [
        f"0-2|{marked}",
        "10-13|other",
        f"26+|{marked}",
        "none|other",
        f"10-13|{marked}",
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
        full=SimpleNamespace(phase=own, phases=P, lease=own, leases=P),
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
            phase=own,
            phases=P,
            lease=own,
            leases=P,
            cells=None,
            site=np.arange(4),
            group=np.zeros(4, int),
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


def kapped(site, unit, t, c, sc, ukap, path=True):
    """`dense` with Student-t lasting levels: the lasting variance of unit k's rows is
    ss^2 / ukap[k]."""
    out = dense(site, unit, t, c, sc, path)
    same_unit = unit[:, None] == unit[None, :]
    return out + np.where(same_unit, sc["ss"] ** 2 * (1 / ukap[unit] - 1)[:, None], 0)


def test_sigma_inverse_and_targets_with_unit_kap_match_dense_algebra():
    site, unit, t, c, r = toy(1)
    lay = dt.layout(site, unit, t, 4, 5)
    ukap = np.random.default_rng(7).gamma(1.5, 1 / 1.5, lay["units"])
    Ws = dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"], ukap)
    H, Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])
    Sig = kapped(site, unit, t, c, SC, ukap)
    want = np.linalg.solve(Sig, r)
    np.testing.assert_allclose(dt.sigma_inv(lay, Ws, Qi, r), want, rtol=1e-8, atol=1e-8)
    tu = np.array([0, 3, 9, -1, -1])
    ts = np.array([site[unit == 0][0], site[unit == 3][0], site[unit == 9][0], 1, 4])
    tt = np.array([9.6, 4.0, 9.6, 9.6, 9.6])
    q = np.floor(tt * 4).astype(int)
    keys, pair = dt.pairs(ts, q)
    tg = dict(unit=tu, site=ts, t=tt, q=q, pair_keys=keys, pair=pair)
    new_kap = np.array([9.0, 9.0, 9.0, 0.4, 2.5])
    mean, var = dt.targets(lay, Ws, Qi, H, r, tg, SC, ukap, new_kap)
    qtr = np.floor(t * 4)
    for k in range(len(tu)):
        vl = SC["ss"] ** 2 / (ukap[tu[k]] if tu[k] >= 0 else new_kap[k])
        g = np.where(
            site == ts[k], SC["s2"] * SC["rho"] ** np.abs(q[k] - qtr), 0.0
        ) + np.where(
            unit == tu[k],
            vl + SC["sd"] ** 2 * np.exp(-np.abs(tt[k] - t) / SC["tau_u"]),
            0.0,
        )
        prior = SC["s2"] + vl + SC["sd"] ** 2
        assert mean[k] == pytest.approx(g @ want, abs=1e-9)
        assert var[k] == pytest.approx(prior - g @ np.linalg.solve(Sig, g), abs=1e-9)


def test_posterior_draw_gives_the_lasting_levels_conditional():
    """With one row, s given r is Normal with mean v r / V and variance v - v^2 / V, where
    v is the lasting variance and V the row's whole variance."""
    site, unit, t = np.array([0]), np.array([0]), np.array([1.0])
    c, r = np.array([100.0]), np.array([0.2])
    lay = dt.layout(site, unit, t, 4, 1)
    ukap = np.array([0.5])
    Ws = dt.unit_W(lay, c, SC["ss"], SC["sd"], SC["tau_u"], ukap)
    Qi = dt.building_system(lay, Ws, SC["s2"], SC["rho"])[1]
    rng = np.random.default_rng(5)
    s = np.concatenate(
        [
            dt.posterior_draw(rng, lay, Ws, Qi, r, c, SC, ukap=ukap)[1]
            for _ in range(20_000)
        ]
    )
    v = SC["ss"] ** 2 / ukap[0]
    V = SC["s2"] + v + SC["sd"] ** 2 + 1 / c[0]
    assert s.mean() == pytest.approx(v * r[0] / V, abs=2e-3)
    assert s.var() == pytest.approx(v - v * v / V, rel=0.03)


def test_a_new_units_predictive_is_the_student_t_prior():
    """A new unit in a building with no rows learns nothing from the training rows, so over
    the components its term is the path's and the drift's normals plus ss times a Student-t
    on nu_u degrees of freedom."""
    site, unit, t, c, r = toy(2)
    lay = dt.layout(site, unit, t, 4, 5)
    sc = SC | {"ss": 0.3, "unit_dof": 3.0}
    n = 4000
    tg = dict(
        unit=np.full(n, -1),
        site=np.full(n, 4),
        t=np.full(n, 9.6),
        q=np.full(n, 38),
    )
    tg["pair_keys"], tg["pair"] = dt.pairs(tg["site"], tg["q"])
    m, v = dt.components(lay, r, np.full(len(r), 0.1), tg, sc, seed=1, burn=2, keep=20)
    rng = np.random.default_rng(2)
    got = (m + np.sqrt(v) * rng.standard_normal(v.shape)).ravel()
    ref_n = got.size
    ref = sc["ss"] * rng.standard_t(3.0, ref_n) + np.sqrt(
        sc["s2"] + sc["sd"] ** 2
    ) * rng.standard_normal(ref_n)
    np.testing.assert_allclose(m, 0.0, atol=1e-12)
    p = [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]
    np.testing.assert_allclose(np.quantile(got, p), np.quantile(ref, p), atol=0.02)
    # A normal level of the same scale has thinner tails.
    assert np.quantile(np.abs(got), 0.98) > 1.2 * np.quantile(
        np.abs(
            np.sqrt(sc["s2"] + sc["sd"] ** 2 + sc["ss"] ** 2)
            * rng.standard_normal(ref_n)
        ),
        0.98,
    )


def test_a_huge_unit_dof_gives_the_normal_models_prices():
    fit, rw = fake_fit(lines=False)
    a = dt.predict(fit, [rw], log=lambda s: None)[0]
    fit.kept["unit_dof"] = np.full(len(fit.pick), 1e9)
    b = dt.predict(fit, [rw], log=lambda s: None)[0]
    for k in ("loc", "usd"):
        np.testing.assert_allclose(a[k], b[k], rtol=0, atol=1e-4)


def test_the_student_t_unit_models_are_served():
    for name in (
        "drift-building-unitt",
        "drift-building-phase-unitt",
        "drift-building-phase-unitk",
        "drift-building-phase-unitkn",
        "drift-building-phase-unitkn-level",
        "drift-building-phase-unitkn-segment",
    ):
        assert name in dt.MODELS


# ------------------------------------------------------------------ noise cells


def test_the_unified_and_ablation_models_are_served():
    for spec in (unified, unified_seg, ablate):
        assert dt.MODELS[spec.NAME] is spec


def test_the_ablation_design_takes_the_runs_variant():
    assert dt.design_kw(unified, {"ablate_variant": ["y1"]}) == {}
    got = dt.design_kw(ablate, {"ablate_variant": ["sbf", "y1", "marks", "covid_vol"]})
    assert got == {"variant": ("sbf", "y1", "marks", "covid_vol")}
    with pytest.raises(SystemExit, match="no ablate_variant"):
        dt.design_kw(ablate, {})
    for token in dt.DAY_MEAN_TOKENS:
        with pytest.raises(SystemExit, match=token):
            dt.design_kw(ablate, {"ablate_variant": ["y1", token]})


def cell_frame(seed=0, n=500):
    """Ads of 6 buildings over 2022 to mid 2026, a tenth with no unit."""
    rng = np.random.default_rng(seed)
    unit = pd.Series([f"u{i}" for i in rng.integers(0, 20, n)], dtype=object)
    unit[rng.uniform(size=n) < 0.1] = None
    at = pd.Timestamp("2022-01-03", tz="UTC") + pd.to_timedelta(
        rng.integers(0, 1640 * 86400, n), "s"
    )
    return pd.DataFrame(
        {
            "audit_id": np.arange(n).astype(str),
            "building": [f"B{i}" for i in rng.integers(0, 6, n)],
            "unit_id": unit,
            "price_at": at,
            "bedrooms": rng.integers(0, 4, n).astype(float),
        }
    )


def cell_design(frame, held, changed, covid):
    """The unified models' noise cells of `frame`, as their designs build them: lease
    phase, year, a coded mark, the thin first ad, the new-unit marks and the Covid regime."""
    P, Y = drift_building_phase.PHASES, drift_building_phase_year.YEARS
    lease = drift_building_phase.phase_index(frame)
    year = drift_building_phase_year.year_index(frame)
    none = lease == P.index("none")
    count = unified.prior_bld_bed_count(frame, ~held)
    bed = frame.bedrooms.to_numpy()
    cols = (
        {f"phase:{p}": lease == P.index(p) for p in P[1:]}
        | {f"yr:{y}": year == Y.index(y) for y in Y[1:]}
        | {
            "mark:changed_counts": changed,
            "mark:thin_first_ad": none & (count < unified.THIN_BLD_BED_MAX),
            "mark:covid_surge": covid == 2,
            "mark:covid_elevated": covid == 1,
            "mark:new_bed2": none & (bed == 2),
            "mark:new_bed3p": none & (bed >= 3),
        }
    )
    mat = np.column_stack(list(cols.values())).astype(float)
    phase, phases, pmap, free = unified.compact_phase_map(list(cols), mat, ~held)
    return SimpleNamespace(phase=phase, phases=phases, phase_map=pmap), free


def cell_fit(seed=0, draws=4, held_2026=False):
    frame = cell_frame(seed)
    rng = np.random.default_rng(seed + 1)
    n = len(frame)
    held = rng.uniform(size=n) < 0.2
    if held_2026:
        held |= frame.price_at.dt.year.to_numpy() == 2026
    changed = rng.uniform(size=n) < 0.2
    d, free = cell_design(frame, held, changed, rng.integers(0, 3, n))
    cells = dt.cell_terms(d, frame)
    logf = rng.normal(0, 0.3, (draws, cells.pmap.shape[1]))
    scale = np.exp(logf @ cells.pmap.T)
    cells.log_factor = dt.log_factors(cells.pmap, scale)
    full = SimpleNamespace(
        phase=d.phase,
        phases=d.phases,
        lease=cells.lease,
        leases=drift_building_phase.PHASES,
        cells=cells,
        site=np.zeros(n, int),
        group=np.arange(n) % 4,
    )
    fit = SimpleNamespace(
        frame=frame, held=held, kept={"phase_scale": scale}, full=full
    )
    return fit, d, free, logf, changed


def test_cell_terms_read_the_factors_from_the_cells_names():
    fit, d, free, logf, _ = cell_fit()
    cells = fit.full.cells
    assert cells.names == free
    np.testing.assert_array_equal(
        cells.lease, drift_building_phase.phase_index(fit.frame)
    )
    np.testing.assert_allclose(cells.log_factor, logf, atol=1e-10)
    # A row whose cell does not hold its own lease phase is not the design's.
    bad = d.phase.copy()
    bad[np.flatnonzero(cells.lease == drift_building_phase.PHASES.index("0-2"))[0]] = 0
    with pytest.raises(SystemExit, match="phase:0-2"):
        dt.cell_terms(SimpleNamespace(**(vars(d) | {"phase": bad})), fit.frame)
    # A factor drift_today cannot set for a day is refused.
    odd = vars(d) | {
        "phases": tuple(p.replace("mark:changed", "mark:odd") for p in d.phases)
    }
    with pytest.raises(SystemExit, match="mark:odd"):
        dt.cell_terms(SimpleNamespace(**odd), fit.frame)
    with pytest.raises(SystemExit, match="not the phase_map"):
        dt.log_factors(
            cells.pmap, fit.kept["phase_scale"] * 1.01 ** np.arange(len(d.phases))
        )
    assert (
        dt.cell_terms(SimpleNamespace(phase=d.phase, phases=d.phases), fit.frame)
        is None
    )


def test_cell_today_moves_the_lease_year_and_day_marks_and_keeps_the_rest(monkeypatch):
    fit, _, _, logf, changed = cell_fit()
    monkeypatch.setattr(dt, "covid_regime", lambda day: (0.0, 1.0))
    day = pd.Timestamp("2026-07-01")
    n = len(fit.frame)
    own = fit.full.phase.copy()
    before = fit.kept["phase_scale"].copy()
    got = dt.cell_today(fit, np.arange(n), day)
    cl, held = fit.full.cells, fit.held
    # An ad on the market keeps its own cell.
    np.testing.assert_array_equal(got[held], own[held])
    v = pd.DataFrame(cl.pmap[got], columns=cl.names)
    lease = dt.lease_names(fit, np.arange(n), day)
    free = ~held
    for p in drift_building_phase.PHASES[1:]:
        np.testing.assert_array_equal(v[f"phase:{p}"][free], (lease == p)[free])
    assert (v.filter(like="yr:")[free].sum(axis=1) == 1).all()
    assert v["yr:2026"][free].all()
    np.testing.assert_array_equal(v["mark:changed_counts"][free], changed[free])
    assert (v["mark:covid_elevated"][free] == 1).all()
    assert (v["mark:covid_surge"][free] == 0).all()
    f = fit.frame
    key = f.building + "|" + f.bedrooms.astype(int).astype(str)
    count = key.map(key[free].value_counts()).fillna(0).to_numpy()
    new = lease == "none"
    thin = new & (count < unified.THIN_BLD_BED_MAX)
    np.testing.assert_array_equal(v["mark:thin_first_ad"][free], thin[free])
    np.testing.assert_array_equal(
        v["mark:new_bed2"][free], (new & (f.bedrooms == 2).to_numpy())[free]
    )
    np.testing.assert_array_equal(
        v["mark:new_bed3p"][free], (new & (f.bedrooms >= 3).to_numpy())[free]
    )
    # Cells the fit never saw are added with their factors from the fit's, and the
    # cells it saw keep theirs.
    k = len(before[0])
    assert got.max() >= k
    np.testing.assert_array_equal(fit.kept["phase_scale"][:, :k], before)
    np.testing.assert_allclose(
        fit.kept["phase_scale"][:, got], np.exp(logf @ cl.pmap[got].T), rtol=1e-8
    )
    assert len(fit.full.phases) == len(cl.pmap) == fit.kept["phase_scale"].shape[1]
    for i in np.flatnonzero(free)[:20]:
        on = [m for m, x in zip(cl.names, cl.pmap[got[i]]) if x]
        assert fit.full.phases[got[i]] == ("|".join(on) or "ref")
    # Asked again, the cells are the ones already added.
    np.testing.assert_array_equal(dt.cell_today(fit, np.arange(n), day), got)
    assert fit.kept["phase_scale"].shape[1] == len(cl.pmap)


def test_a_year_or_cell_the_fit_cannot_price_is_refused(monkeypatch):
    monkeypatch.setattr(dt, "covid_regime", lambda day: (0.0, 0.0))
    fit = cell_fit(held_2026=True)[0]
    assert "yr:2026" not in fit.full.cells.names
    with pytest.raises(SystemExit, match="yr factor for 2026"):
        dt.cell_today(fit, np.arange(len(fit.frame)), pd.Timestamp("2026-07-01"))
    # Two factors that only ever come together leave each one's factor free.
    cl = SimpleNamespace(
        pmap=np.array([[0, 0, 0], [1, 1, 0], [0, 0, 1]], float),
        names=["phase:none", "mark:thin_first_ad", "mark:baths_2"],
        log_factor=np.log([[1.0, 2.0, 3.0]]),
    )
    fit = SimpleNamespace(
        full=SimpleNamespace(cells=cl, phases=("ref", "a", "b")),
        kept={"phase_scale": np.array([[1.0, 2.0, 3.0]])},
    )
    got = dt.cell_index(fit, np.array([[1, 1, 1], [0, 0, 1], [1, 1, 1]]))
    np.testing.assert_array_equal(got, [3, 2, 3])
    np.testing.assert_allclose(fit.kept["phase_scale"], [[1.0, 2.0, 3.0, 6.0]])
    assert fit.full.phases[3] == "phase:none|mark:thin_first_ad|mark:baths_2"
    with pytest.raises(SystemExit, match="leave free"):
        dt.cell_index(fit, np.array([[1, 0, 0]]))


def test_covid_regime_is_the_ablation_designs(tmp_path, monkeypatch):
    reg = tmp_path / "registry.parquet"
    pd.DataFrame({"building": ["B"], "bbl": [1000000001]}).to_parquet(reg, index=False)
    monkeypatch.setattr(building_attrs, "REGISTRY", reg)
    csv = tmp_path / "covid.csv"
    days = pd.date_range("2020-03-01", "2020-07-01", freq="D")
    hosp = np.r_[np.linspace(0, 400, 60), np.linspace(400, 10, len(days) - 60)]
    hosp[40] = np.nan
    table = {"date_of_interest": days.strftime("%m/%d/%Y"), "HOSP_COUNT_7DAY_AVG": hosp}
    for b in ("MN", "BX", "BK", "QN", "SI"):
        table[f"{b}_HOSPITALIZED_COUNT_7DAY_AVG"] = hosp / 5
        table[f"{b}_CASE_COUNT_7DAY_AVG"] = hosp * 3
    table["CASE_COUNT_7DAY_AVG"] = hosp * 15
    pd.DataFrame(table).to_csv(csv, index=False)
    at = pd.date_range("2019-12-01", "2020-09-30", freq="37h", tz="UTC")
    frame = pd.DataFrame(
        {"building": "B", "price_at": at.astype(str), "bedrooms": np.ones(len(at))}
    )

    class Design:
        names = ("alpha",)
        x = np.ones((len(at), 1))
        y = np.zeros(len(at))

    want = ablate.covid_features(frame, Design(), csv_path=csv)[2]
    got = np.array([dt.covid_regime(t, csv) for t in at])
    assert want[:, 0].any() and want[:, 1].any() and (want.sum(axis=1) == 0).any()
    np.testing.assert_array_equal(got, want)


def test_the_unified_segment_paths_leave_their_reference_columns_out():
    rng = np.random.default_rng(3)
    n = 600
    week = np.sort(rng.integers(0, 90, n))
    base = SegDesign(
        x=np.ones((n, 1)),
        names=["alpha"],
        count={},
        week=week,
        frac=rng.uniform(0, 1, n),
        start=pd.Timestamp("2023-10-02"),
        site=rng.integers(0, 3, n),
        group=rng.integers(0, 4, n),
        surfaces=[{"name": "manhattan", "sites": 2}, {"name": "outer", "sites": 1}],
    )
    d = unified_seg.identifiable_segment_paths(base)
    seg = [c for c in d.names if c.startswith("seg:")]
    assert seg and not any(
        c.startswith(f"seg:{unified_seg.REF_SEGMENT}:")
        or c.endswith(f":{unified_seg.REF_QUARTER}")
        for c in seg
    )
    sg = dt.segment_terms(d, d.names)
    full = seg_model.segment_paths(base)
    assert len(sg.cols) < len(dt.segment_terms(full, full.names).cols)
    beta = rng.standard_normal((2, len(d.names)))
    fit = SimpleNamespace(
        seg=sg,
        pick=np.arange(2),
        kept={"beta": beta},
        full=SimpleNamespace(t=drift.years(d)),
    )
    rows = rng.choice(n, 60, replace=False)

    def x_at(t):
        h = seg_model.hat_weights(np.full(len(rows), t), sg.knots)[:, sg.j]
        return h * ((sg.row[rows][:, None] == sg.k) - sg.share[sg.j, sg.k])

    old = d.x[rows][:, sg.cols]
    for t_new in (0.1, 0.9, sg.knots[-1]):
        want = (x_at(t_new) - old) @ beta[:, sg.cols].T
        np.testing.assert_allclose(
            dt.segment_shift(fit, rows, t_new), want.T, atol=1e-12
        )
    # On 2024-01-01 every path is 0, so an ad then moves only by its own time's path.
    ref = (unified_seg.REFERENCE - base.start).days / seg_model.YEAR_DAYS
    np.testing.assert_allclose(
        dt.segment_shift(fit, rows, ref), -(old @ beta[:, sg.cols].T).T, atol=1e-12
    )


def test_todays_held_out_ads_score_as_drift_score_scores_them(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "covid_regime", lambda day: (1.0, 0.0))
    fit = cell_fit(seed=4, draws=6)[0]
    held = np.flatnonzero(fit.held)
    m, draws = len(held), len(fit.kept["phase_scale"])
    rng = np.random.default_rng(5)
    y = rng.normal(8, 0.4, m)
    fit.frame["latest_ask"] = np.nan
    fit.frame.loc[held, "latest_ask"] = np.exp(y)
    loc = y + rng.normal(0, 0.1, (draws, m))
    usd = rng.uniform(0.05, 0.15, (draws, m))
    sigma = rng.uniform(0.05, 0.2, (draws, 4))
    nu = rng.uniform(3, 9, draws)
    group = fit.full.group[held]
    np.savez(
        tmp_path / "posterior.npz",
        **{
            "kept/pred_loc": loc[None],
            "kept/pred_unit_sd": usd[None],
            "kept/sigma": sigma[None],
            "kept/nu": nu[None],
            "kept/phase_scale": fit.kept["phase_scale"][None],
            "kept/pred_y": y,
            "kept/pred_group": group,
            "kept/pred_phase": fit.full.phase[held],
        },
        heldout=held,
    )
    theirs = drift_score.score_run(tmp_path)
    # The Today table's apartments come first and add the day's cells to the fit's.
    k = fit.kept["phase_scale"].shape[1]
    dt.phase_today(fit, np.arange(len(fit.frame)), pd.Timestamp("2026-07-01"))
    assert fit.kept["phase_scale"].shape[1] > k
    phase = dt.phase_today(fit, held, pd.Timestamp("2026-07-01"))
    np.testing.assert_array_equal(phase, fit.full.phase[held])
    comp = dict(loc=loc, usd=usd, sigma=sigma, nu=nu, phase=fit.kept["phase_scale"])
    got = dt.check(fit, comp, SimpleNamespace(group=group, phase=phase), theirs)
    assert got["elpd"]["today"] == got["elpd"]["fit"]
    assert got["median_gap"]["median_abs"] == 0 and got["median_gap"]["p95_abs"] == 0
    assert got["coverage"]["today"] == got["coverage"]["fit"]


def test_today_rows_moves_l2s_levels_by_the_lease_phase_not_the_cell(monkeypatch):
    monkeypatch.setattr(dt, "covid_regime", lambda day: (0.0, 0.0))
    fit = cell_fit(seed=6)[0]
    n = len(fit.frame)
    P = drift_building_phase.PHASES
    names = ["alpha", "phase:none", "phase:0-2", "phase:26+"]
    rng = np.random.default_rng(7)
    base = rng.standard_normal((4, n))
    fit.names, fit.season_cols, fit.seg = names, [], None
    fit.kept["beta"] = rng.standard_normal((4, len(names)))
    fit.start = pd.Timestamp("2022-01-03")
    monkeypatch.setattr(dt, "base_xb", lambda f, rows: base.copy())
    apts = pd.DataFrame({"row": np.arange(n), "unit": np.arange(n)})
    day = pd.Timestamp("2026-07-01")
    rw = dt.today_rows(fit, apts, day)
    lease = pd.Index(P).get_indexer(dt.lease_names(fit, np.arange(n), day))
    lease[fit.held] = fit.full.lease[fit.held]
    want = (
        fit.kept["beta"][:, 1:]
        @ (
            (lease[:, None] == [1, 2, 6]).astype(float)
            - (fit.full.lease[:, None] == [1, 2, 6])
        ).T
    )
    assert np.abs(want).max() > 0
    np.testing.assert_allclose(rw.xb, base + want)
    np.testing.assert_array_equal(rw.phase[fit.held], fit.full.phase[fit.held])
    assert rw.phase.max() < len(fit.full.phases)


def test_y1_pre2024_treats_2024_and_later_as_reference(monkeypatch):
    monkeypatch.setattr(dt, "covid_regime", lambda day: (0.0, 0.0))
    fit = cell_fit(seed=8)[0]
    cl = fit.full.cells
    keep = [
        j
        for j, name in enumerate(cl.names)
        if not (name.startswith("yr:") and int(name.split(":")[1]) >= 2024)
    ]
    cl.names = [cl.names[j] for j in keep]
    cl.pmap = cl.pmap[:, keep]
    cl.log_factor = cl.log_factor[:, keep]
    cl.ref_years = {2024, 2025, 2026}
    fit.full.phases = tuple(
        "|".join(n for n, on in zip(cl.names, r) if on) or "ref" for r in cl.pmap
    )
    fit.kept["phase_scale"] = np.exp(cl.log_factor @ cl.pmap.T)
    rows = np.flatnonzero(~fit.held)
    for day in ("2024-06-01", "2025-11-10", "2026-11-22"):
        phase = dt.cell_today(fit, rows, pd.Timestamp(day))
        # No yr:* factor is active for 2024+ under y1_pre2024.
        yr_cols = [j for j, n in enumerate(cl.names) if n.startswith("yr:")]
        assert not (cl.pmap[phase][:, yr_cols] > 0.5).any()
