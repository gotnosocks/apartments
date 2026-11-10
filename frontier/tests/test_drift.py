import dataclasses

import numpy as np
import pandas as pd
import pytest
import test_building_zones_attrs as tba

from rentfrontier import b0, building_zones, drift
from rentfrontier import building_zones_attrs as bza


def _design(n=1500, weeks=30, seed=9, per_unit=3):
    """A simulated building-zones design with units of about `per_unit` rows inside each
    building, as a training design with every eighth row moved to the rows to predict."""
    reg = tba.registry_with_bins()
    footprints, attrs = tba.tables_of(reg)
    frame = tba._nyc_frame(n, weeks, seed)
    d = bza.design(
        frame, registry=reg, nj_registry=tba.NO_NJ, attrs=attrs, footprints=footprints
    )
    d = bza.subset(d, np.ones(len(d.y), bool))
    d = tba._simulated(d)
    rng = np.random.default_rng(seed)
    order = np.argsort(d.site, kind="stable")
    rank = np.empty(len(order), int)
    rank[order] = np.arange(len(order))
    first = np.r_[0, np.flatnonzero(np.diff(d.site[order])) + 1]
    start = np.repeat(first, np.diff(np.r_[first, len(order)]))
    # Unit sizes vary from 1 to 2 * per_unit - 1 rows.
    cut = rng.integers(1, 2 * per_unit, len(order))
    within = np.arange(len(order)) - start
    unit_sorted = d.site[order] * 1000 + within // cut[start]
    _, unit = np.unique(unit_sorted[rank], return_inverse=True)
    return drift.Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=int(unit.max() + 1),
    )


def _split(d, every=8):
    """`d`'s training design, with every `every`-th row held out to predict. The held-out
    rows of units left with no training row carry -1."""
    held = np.arange(len(d.y)) % every == 0
    seen = np.unique(d.unit[~held])
    unit = np.searchsorted(seen, d.unit)
    unit = np.where(np.isin(d.unit, seen), unit, -1)
    d = dataclasses.replace(d, unit=unit, units=len(seen))
    return drift.subset(d, ~held), drift.subset(d, held), held


def _sampler(train, block=7, joint=False):
    settings = drift.Settings(
        chains=2, warmup=10, draws=10, site_block=block, joint_amp=joint
    )
    return drift.make_sampler(train, building_zones.Priors(), settings)


def _state(init, parts, seed=0, hyp=(0.08, 0.1, 0.2)):
    """One chain's state with random lam and the unit scales at `hyp`."""
    jax, jnp = b0._jax()
    st = jax.tree.map(
        lambda v: v[0], init(jax.random.split(jax.random.PRNGKey(seed), 1))
    )
    rng = np.random.default_rng(seed)
    n = st["lam"].shape[0]
    return st | {
        "lam": jnp.asarray(rng.gamma(2.0, 0.5, n)),
        "hyp": jnp.log(jnp.asarray(hyp)),
    }


def _dense_cov(train, parts, st):
    """In the sampler's row order: the rows' covariance from the noise and u, the units'
    kernel alone, and the rows' weights."""
    order = parts["order"]
    ss, sd, tau = np.exp(np.asarray(st["hyp"]))
    t = drift.years(train)[order]
    unit = train.unit[order]
    c = np.asarray(st["lam"]) / np.asarray(st["sigma"])[train.group[order]] ** 2
    same = unit[:, None] == unit[None, :]
    K = np.where(
        same, ss**2 + sd**2 * np.exp(-np.abs(t[:, None] - t[None, :]) / tau), 0.0
    )
    return np.diag(1 / c) + K, K, c


def test_unit_index_keeps_whole_keys_when_a_unit_id_is_missing(tmp_path):
    """A missing unit_id read back from parquet is NaN: the keys must not be cut to its
    width, and the row is a unit of its own."""
    frame = pd.DataFrame(
        {
            "building": [101, 101, 102, 102, 250, 250, 250],
            "unit_id": ["u1", "u1", "u1", None, "u2", "u2", None],
        }
    )
    frame.to_parquet(tmp_path / "rows.parquet")
    frame = pd.read_parquet(tmp_path / "rows.parquet")
    held = np.array([False, False, False, False, False, True, True])
    unit, units = drift.unit_index(frame, held)
    # Sorted keys: 101|u1, 102|#row3, 102|u1, 250|u2. The held-out row with no unit_id has
    # no training row.
    assert units == 4
    np.testing.assert_array_equal(unit, [0, 0, 2, 1, 3, 3, -1])
    whole = pd.DataFrame({"building": ["a", "a", "b"], "unit_id": ["x", "x", "x"]})
    np.testing.assert_array_equal(
        drift.unit_index(whole, np.zeros(3, bool))[0], [0, 0, 1]
    )


def test_unit_layout_places_every_row_and_pair():
    unit = np.array([0, 0, 0, 1, 2, 2, 3, 3, 3, 3, 3, 4])
    t = np.arange(len(unit), dtype=float)
    lay = drift.unit_layout(unit, t, pads=(2, 3, 4))
    np.testing.assert_array_equal(lay["single"], np.isin(unit, [1, 4]))
    sizes = [b["idx"].shape for b in lay["buckets"]]
    assert sizes == [(1, 2), (1, 3), (1, 5)]
    # Every ordered pair of distinct rows of one unit appears once.
    want = {
        (i, j) for i in range(12) for j in range(12) if i != j and unit[i] == unit[j]
    }
    assert set(zip(lay["pi"].tolist(), lay["pj"].tolist())) == want
    assert len(lay["pi"]) == len(want)
    assert (np.diff(lay["pi"]) >= 0).all()
    # The places index a raveled stack of the buckets' matrices.
    mats = [np.zeros((*b["idx"].shape, b["idx"].shape[1])) for b in lay["buckets"]]
    flat = np.concatenate([m.ravel() for m in mats])
    flat[lay["take_off"]] += 1
    multi = ~lay["single"]
    flat[lay["take_d"][multi]] += 1
    assert flat.sum() == len(want) + multi.sum() and flat.max() == 1
    # Units 1 and 4 are single rows; the others sit in buckets.
    np.testing.assert_array_equal(lay["slot"][:, 0], [1, -1, 0, 2, -1])
    np.testing.assert_array_equal(lay["slot"][[1, 4], 1], [3, 11])


@pytest.mark.parametrize("block", [7, 4096])
def test_global_system_matches_the_dense_marginal(block):
    """theta's precision and linear term with the levels and u integrated out equal
    J' V^-1 J and J' V^-1 y for the rows' dense marginal covariance V. Units of up to 17 rows
    reach the padded buckets."""
    full = _design(per_unit=9)
    train, _, _ = _split(full)
    _, init, _, parts = _sampler(train, block=block)
    jax, jnp = b0._jax()
    st = _state(init, parts)
    D = parts["data"]

    def system(state):
        c = parts["weights"](D, state)
        w1, Wb = parts["unit_W"](D, state["hyp"], c)
        A, h, _ = parts["global_system"](D, state, c, w1, Wb)
        return np.asarray(A), np.asarray(h)

    A, h = system(st)
    # With every weight 0 the system holds the priors alone.
    A0, h0 = system(st | {"lam": jnp.zeros_like(st["lam"])})
    order = parts["order"]
    V, _, _ = _dense_cov(train, parts, st)
    zone = drift.site_zone(train)
    site = train.site[order]
    b2 = np.asarray(st["bld_sd"])[zone] ** 2
    V = V + np.where(site[:, None] == site[None, :], b2[site][:, None], 0.0)
    sl_b, sl_M, i_g, sl_w = parts["slices"]
    alpha = train.names.index("alpha")
    others = [j for j in range(len(train.names)) if j != alpha]
    n = len(train.y)
    J = np.zeros((n, parts["G"]))
    J[:, sl_b] = train.x[order][:, others]
    wk, fr = train.week[order], train.frac[order]
    J[np.arange(n), sl_M.start + wk] += 1 - fr
    J[np.arange(n), sl_M.start + wk + 1] += fr
    Bc, _ = drift.wave_matrix(train)
    J[:, sl_w] = Bc[site]
    Vi = np.linalg.inv(V)
    want_A, want_h = J.T @ Vi @ J, J.T @ Vi @ train.y[order]
    scale = np.sqrt(np.outer(np.diag(A), np.diag(A)))
    np.testing.assert_allclose((A - A0) / scale, want_A / scale, atol=1e-8)
    np.testing.assert_allclose(
        (h - h0) / np.sqrt(np.diag(A)), want_h / np.sqrt(np.diag(A)), atol=1e-6
    )


def test_unit_loglik_matches_the_dense_density():
    full = _design(per_unit=9)
    train, _, _ = _split(full)
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(1)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))

    def both(hyp):
        st = _state(init, parts, hyp=hyp)
        c = parts["weights"](D, st)
        ll = float(parts["unit_loglik"](D, st["hyp"], c, e))
        V, _, _ = _dense_cov(train, parts, st)
        _, logdet = np.linalg.slogdet(V)
        ev = np.asarray(e)
        return ll, -0.5 * logdet - 0.5 * ev @ np.linalg.solve(V, ev)

    a, b = both((0.08, 0.1, 0.2)), both((0.03, 0.2, 1.5))
    np.testing.assert_allclose(a[0] - b[0], a[1] - b[1], rtol=1e-9)


def test_scale_logp_matches_the_dense_density_as_sigma_and_the_unit_scales_move():
    full = _design(per_unit=9)
    train, _, _ = _split(full)
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(5)
    e = 0.2 * rng.standard_normal(len(train.y))
    st = _state(init, parts)
    prior = building_zones.Priors()
    group = np.asarray(D["group"])

    def both(hyp, sigma):
        sigma = np.asarray(sigma)
        x = jnp.asarray(np.concatenate([np.log(hyp), np.log(sigma)]))
        got = float(parts["scale_logp"](D, x, st["lam"], jnp.asarray(e)))
        at = st | {"hyp": jnp.log(jnp.asarray(hyp)), "sigma": jnp.asarray(sigma)}
        V, _, _ = _dense_cov(train, parts, at)
        _, logdet = np.linalg.slogdet(V)
        ss, sd, tau = hyp
        want = (
            -0.5 * logdet
            - 0.5 * e @ np.linalg.solve(V, e)
            # The priors, with the Jacobians of the logs.
            - ss**2 / (2 * drift.UNIT_SD_PRIOR**2)
            - sd**2 / (2 * drift.DRIFT_SD_PRIOR**2)
            - (np.log(tau) - drift.TAU_LOG_PRIOR[0]) ** 2
            / (2 * drift.TAU_LOG_PRIOR[1] ** 2)
            + np.log(ss)
            + np.log(sd)
            - np.sum(sigma**2) / (2 * prior.sigma**2)
            + np.sum(np.log(sigma))
        )
        return got, want

    assert len(np.unique(group)) > 1
    a = both((0.08, 0.1, 0.2), (0.05, 0.06, 0.07, 0.08))
    b = both((0.03, 0.2, 1.5), (0.09, 0.04, 0.11, 0.05))
    c = both((0.08, 0.1, 0.2), (0.09, 0.04, 0.11, 0.05))
    np.testing.assert_allclose(a[0] - b[0], a[1] - b[1], rtol=1e-9)
    np.testing.assert_allclose(a[0] - c[0], a[1] - c[1], rtol=1e-9)


def test_draw_u_has_the_conditional_mean_and_covariance():
    full = _design(n=400, per_unit=9)
    train, _, _ = _split(full)
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = _state(init, parts)
    rng = np.random.default_rng(2)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    c = parts["weights"](D, st)
    w1, Wb = parts["unit_W"](D, st["hyp"], c)
    draw = jax.jit(jax.vmap(lambda k: parts["draw_u"](D, k, st["hyp"], c, w1, Wb, e)))
    u = np.asarray(draw(jax.random.split(jax.random.PRNGKey(3), 4000)))
    V, K, _ = _dense_cov(train, parts, st)
    mean = K @ np.linalg.solve(V, np.asarray(e))
    cov = K - K @ np.linalg.solve(V, K)
    sd = np.sqrt(np.diag(cov))
    assert np.abs((u.mean(0) - mean) / sd).max() < 5 / np.sqrt(4000) * 1.2
    emp = np.cov(u.T)
    assert np.abs(emp - cov).max() < 0.15 * sd.max() ** 2


def test_predict_matches_the_dense_conditional():
    full = _design(per_unit=9)
    train, test, held = _split(full)
    assert (train.pred["unit"] == test.unit).all() and (test.unit < 0).any()
    assert test.pred is None
    _, init, predict, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = _state(init, parts)
    rng = np.random.default_rng(4)
    st = st | {
        "theta": jnp.asarray(0.01 * rng.standard_normal(parts["G"])),
        "lev": jnp.asarray(0.1 * rng.standard_normal(st["lev"].shape[0])),
    }
    loc, sd, mean = (np.asarray(v) for v in parts["predict"](D, st))
    order = parts["order"]
    e = np.asarray(D["y"] - parts["all_means"](D, st["theta"]) - st["lev"][D["site"]])
    V, _, _ = _dense_cov(train, parts, st)
    ss, s_d, tau = np.exp(np.asarray(st["hyp"]))
    t, unit = drift.years(train)[order], train.unit[order]
    same = train.pred["unit"][:, None] == unit[None, :]
    k = np.where(
        same,
        ss**2
        + s_d**2 * np.exp(-np.abs(train.pred["years"][:, None] - t[None, :]) / tau),
        0.0,
    )
    want_mean = k @ np.linalg.solve(V, e)
    want_var = ss**2 + s_d**2 - np.einsum("pi,ip->p", k, np.linalg.solve(V, k.T))
    np.testing.assert_allclose(mean, want_mean, atol=1e-6)
    np.testing.assert_allclose(sd, np.sqrt(want_var), atol=1e-6)
    unseen = train.pred["unit"] < 0
    assert unseen.any() and (mean[unseen] == 0).all()
    np.testing.assert_allclose(sd[unseen], np.hypot(ss, s_d), rtol=1e-6)
    # The location adds the rows' own columns, walk and building level.
    sl_b, sl_M, _, _ = parts["slices"]
    theta, lev = np.asarray(st["theta"]), np.asarray(st["lev"])
    alpha = train.names.index("alpha")
    others = [j for j in range(len(train.names)) if j != alpha]
    M = theta[sl_M]
    fixed = (
        test.x[:, others] @ theta[sl_b]
        + (1 - test.frac) * M[test.week]
        + test.frac * M[test.week + 1]
        + lev[test.site]
    )
    np.testing.assert_allclose(loc, fixed + mean, atol=1e-5)


@pytest.mark.parametrize("joint", [False, True])
def test_recovers_planted_unit_scales(joint):
    truth = dict(ss=0.08, sd=0.12, tau=0.15)
    full = _design(n=6000, per_unit=4)
    rng = np.random.default_rng(5)
    t, unit = drift.years(full), full.unit
    u = np.zeros(len(full.y))
    for k in range(full.units):
        rows = np.flatnonzero(unit == k)
        dt = np.abs(t[rows][:, None] - t[rows][None, :])
        K = truth["ss"] ** 2 + truth["sd"] ** 2 * np.exp(-dt / truth["tau"])
        u[rows] = rng.multivariate_normal(np.zeros(len(rows)), K)
    full = dataclasses.replace(full, y=full.y + u)
    train, test, held = _split(full)
    out = drift.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=300, keep_every=5, joint_amp=joint),
        log=lambda m: None,
        gp=None,
    )
    for name, key in (("unit_sd", "ss"), ("drift_sd", "sd"), ("drift_tau", "tau")):
        x = out["trace"][name]
        assert x.shape == (2, 300) and np.ptp(x) > 0
        lo, hi = np.quantile(x, [0.001, 0.999])
        assert lo < truth[key] < hi, (name, lo, hi)
    # The predicted unit levels follow the planted ones on the held-out rows.
    loc = out["kept"]["pred_loc"]
    sd = out["kept"]["pred_unit_sd"]
    assert loc.shape == (2, 60, held.sum()) and sd.shape == loc.shape
    np.testing.assert_array_equal(out["kept"]["pred_y"], test.y)
    np.testing.assert_array_equal(out["kept"]["pred_group"], test.group)
    # The held-out rows' standardized errors have unit spread: the predictive sd joins the
    # sd of u and the Student-t noise's.
    sigma, nu = out["kept"]["sigma"].mean((0, 1)), out["kept"]["nu"].mean()
    total = np.sqrt(sd.mean((0, 1)) ** 2 + sigma[test.group] ** 2 * nu / (nu - 2))
    z = (test.y - loc.mean((0, 1))) / total
    assert 0.85 < z.std() < 1.15, z.std()
    # A unit with training rows is predicted more tightly than one with none.
    seen = train.pred["unit"] >= 0
    assert sd.mean((0, 1))[seen].mean() < 0.9 * sd.mean((0, 1))[~seen].mean()
    diag = drift.diagnostics(out["trace"], train.names)
    assert set(drift.HYP) <= set(diag["per_quantity"])
