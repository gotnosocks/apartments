import dataclasses

import numpy as np
import pandas as pd
import test_drift as td

from rentfrontier import b0, building_zones, drift, drift_building, drift_local


def _groups(train, per_year=52):
    """The buildings' local-drift term of `train`, in steps of 1 / `per_year` years: the
    simulated frames span 30 weeks, so the tests use weekly steps."""
    (g,) = drift.groups_of(train, ("building",))
    return [g | {"per_year": per_year}]


def _sampler(train, groups):
    settings = drift.Settings(chains=2, warmup=10, draws=10, site_block=7)
    return drift.make_sampler(train, building_zones.Priors(), settings, groups=groups)


def _ar_cov(sd, rho, steps):
    lag = np.abs(np.arange(steps)[:, None] - np.arange(steps)[None, :])
    return sd**2 * rho**lag


def test_groups_of_numbers_the_rows_and_the_rows_to_predict():
    full = td._design()
    full = dataclasses.replace(full, nbhd=full.site % 5)
    train, test, _ = td._split(full)
    b, n = drift.groups_of(train, drift_local.GROUPS)
    assert (b["name"], b["per_year"], n["name"], n["per_year"]) == (
        "building",
        4,
        "nbhd",
        4,
    )
    assert b["collapsed"] and not n["collapsed"]
    np.testing.assert_array_equal(b["row"], train.site)
    np.testing.assert_array_equal(b["pred"], test.site)
    np.testing.assert_array_equal(n["row"], train.site % 5)
    np.testing.assert_array_equal(n["pred"], test.site % 5)
    assert b["size"] == len(drift.site_zone(train)) and n["size"] == 5
    assert drift_building.GROUPS == ("building",)
    record = drift.run_record(train, drift_local.GROUPS)
    assert set(record["local"]) == {"building", "nbhd"}
    assert "local" not in drift.run_record(train)


def test_ar_filter_and_draw_match_the_dense_gaussian():
    train, _, _ = td._split(td._design())
    _, _, _, parts = _sampler(train, _groups(train))
    jax, jnp = b0._jax()
    rng = np.random.default_rng(3)
    G, T = 4, 7
    sd, rho = 0.07, 0.8
    par = jnp.asarray([np.log(sd), np.log(rho / (1 - rho))])
    # Some cells hold no row.
    C = rng.gamma(2.0, 200.0, (G, T)) * (rng.random((G, T)) < 0.6)
    R = C * rng.normal(0, 0.1, (G, T))
    ll, mf, pf = parts["ar_filter"](par, jnp.asarray(C), jnp.asarray(R))
    K = _ar_cov(sd, rho, T)
    want_ll, means, covs = 0.0, [], []
    for g in range(G):
        # The integral of Normal(a; 0, K) exp(-a'Ca / 2 + R'a) over a.
        cov = np.linalg.inv(np.linalg.inv(K) + np.diag(C[g]))
        _, logdet = np.linalg.slogdet(np.eye(T) + K @ np.diag(C[g]))
        want_ll += -0.5 * logdet + 0.5 * R[g] @ cov @ R[g]
        means.append(cov @ R[g])
        covs.append(cov)
    np.testing.assert_allclose(float(ll), want_ll, rtol=1e-9)
    # The last step's filtered moments are the smoothed ones.
    np.testing.assert_allclose(np.asarray(mf)[-1], [m[-1] for m in means], atol=1e-10)
    np.testing.assert_allclose(np.asarray(pf)[-1], [c[-1, -1] for c in covs], rtol=1e-8)
    keys = jax.random.split(jax.random.PRNGKey(0), 20000)
    paths = np.asarray(jax.vmap(lambda k: parts["ar_draw"](k, par, mf, pf))(keys))
    assert paths.shape == (20000, G, T)
    for g in range(G):
        scale = np.sqrt(np.diag(covs[g]))
        assert np.abs(paths[:, g].mean(0) - means[g]).max() < 0.03 * scale.max()
        emp = np.cov(paths[:, g].T)
        assert np.abs(emp - covs[g]).max() < 0.04 * scale.max() ** 2


def test_predict_adds_the_paths_and_takes_them_from_the_training_rows():
    full = td._design()
    train, test, _ = td._split(full)
    groups = _groups(train)
    _, init, _, parts = _sampler(train, groups)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = td._state(init, parts)
    rng = np.random.default_rng(4)
    (a,) = parts["ars"]
    path = 0.05 * rng.standard_normal((a["size"], a["T"]))
    st = st | {
        "theta": jnp.asarray(0.01 * rng.standard_normal(parts["G"])),
        "lev": jnp.asarray(0.1 * rng.standard_normal(st["lev"].shape[0])),
    }
    with_path = st | {"ar": (jnp.asarray(path),)}
    order = parts["order"]
    step = np.floor(drift.years(train)[order] * 52).astype(int)
    at_rows = path[train.site[order], step]
    np.testing.assert_allclose(np.asarray(parts["offsets"](D, with_path)), at_rows)
    loc, sd, mean = (np.asarray(v) for v in parts["predict"](D, with_path))
    # The same as predicting from y less the paths with no paths, plus the paths at the
    # rows to predict.
    bare = st | {"ar": (jnp.zeros_like(with_path["ar"][0]),)}
    loc0, sd0, mean0 = (
        np.asarray(v)
        for v in parts["predict"](D | {"y": D["y"] - jnp.asarray(at_rows)}, bare)
    )
    pstep = np.floor(train.pred["years"] * 52).astype(int)
    np.testing.assert_allclose(mean, mean0, atol=1e-9)
    np.testing.assert_allclose(sd, sd0, atol=1e-9)
    np.testing.assert_allclose(loc, loc0 + path[test.site, pstep], atol=1e-5)
    assert np.abs(path[test.site, pstep]).max() > 0.01


def test_recovers_a_planted_building_process():
    truth = dict(ss=0.08, sd=0.1, tau=0.15, ar_sd=0.2, rho=0.9)
    full = td._design(n=6000, per_unit=4)
    rng = np.random.default_rng(6)
    t, unit = drift.years(full), full.unit
    u = np.zeros(len(full.y))
    for k in range(full.units):
        rows = np.flatnonzero(unit == k)
        dt = np.abs(t[rows][:, None] - t[rows][None, :])
        K = truth["ss"] ** 2 + truth["sd"] ** 2 * np.exp(-dt / truth["tau"])
        u[rows] = rng.multivariate_normal(np.zeros(len(rows)), K)
    step = np.floor(t * 52).astype(int)
    sites, steps = int(full.site.max()) + 1, int(step.max()) + 1
    paths = rng.multivariate_normal(
        np.zeros(steps), _ar_cov(truth["ar_sd"], truth["rho"], steps), sites
    )
    full = dataclasses.replace(full, y=full.y + u + paths[full.site, step])
    train, test, held = td._split(full)
    out = drift.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=300, keep_every=5),
        log=lambda m: None,
        gp=None,
        groups=_groups(train),
    )
    for name, key in (
        ("unit_sd", "ss"),
        ("drift_sd", "sd"),
        ("building_ar_sd", "ar_sd"),
        ("building_ar_rho", "rho"),
    ):
        x = out["trace"][name]
        assert x.shape == (2, 300) and np.ptp(x) > 0
        lo, hi = np.quantile(x, [0.001, 0.999])
        assert lo < truth[key] < hi, (name, lo, hi)
    assert out["kept"]["building_ar_sd"].shape == (2, 60)
    # The held-out rows' standardized errors have unit spread, and the predictions follow
    # the planted paths.
    loc = out["kept"]["pred_loc"].mean((0, 1))
    sd = out["kept"]["pred_unit_sd"].mean((0, 1))
    sigma, nu = out["kept"]["sigma"].mean((0, 1)), out["kept"]["nu"].mean()
    spread = out["kept"]["pred_loc"].var((0, 1))
    total = np.sqrt(sd**2 + spread + sigma[test.group] ** 2 * nu / (nu - 2))
    z = (test.y - loc) / total
    assert 0.85 < z.std() < 1.15, z.std()
    plain = drift.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=300, keep_every=5),
        log=lambda m: None,
        gp=None,
    )
    # What the term adds to the predictions follows the planted paths at the held-out rows
    # (the plain fit's unit drift already follows part of them), and brings the predictions
    # closer.
    loc_plain = plain["kept"]["pred_loc"].mean((0, 1))
    planted = paths[test.site, step[held]]
    corr = np.corrcoef(loc - loc_plain, planted)[0, 1]
    assert corr > 0.25, corr
    assert np.mean((test.y - loc) ** 2) < 0.99 * np.mean((test.y - loc_plain) ** 2)
    diag = drift.diagnostics(out["trace"], train.names)
    assert {"building_ar_sd", "building_ar_rho"} <= set(diag["per_quantity"])
    assert set(drift.summarize(out["kept"], train.names)["local"]) == {
        "building_ar_sd",
        "building_ar_rho",
    }


def test_rows_with_no_neighbourhood_share_a_group_of_their_own():
    frame = pd.DataFrame({"neighbourhood": ["b", None, "a", "b", np.nan]})
    np.testing.assert_array_equal(drift.nbhd_index(frame), [2, 0, 1, 2, 0])
    whole = pd.DataFrame({"neighbourhood": ["b", "a", "b"]})
    np.testing.assert_array_equal(drift.nbhd_index(whole), [1, 0, 1])


def test_update_local_sums_the_cells_and_swaps_the_paths():
    full = td._design()
    full = dataclasses.replace(full, nbhd=full.site % 5)
    train, _, _ = td._split(full)
    groups = [
        g | {"per_year": per_year}
        for g, per_year in zip(drift.groups_of(train, drift_local.GROUPS), (52, 26))
    ]
    _, init, _, parts = _sampler(train, groups)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = td._state(init, parts)
    rng = np.random.default_rng(8)
    n = len(train.y)
    old = tuple(
        jnp.asarray(0.05 * rng.standard_normal((a["size"], a["T"])))
        for a in parts["ars"]
    )
    st = st | {"ar": old}
    c = rng.gamma(2.0, 200.0, n)
    r = 0.1 * rng.standard_normal(n)
    order = parts["order"]
    t = drift.years(train)[order]
    rows = (train.site[order], train.nbhd[order])
    # The cell sums are the rows' sums by group and step.
    for k, (a, per_year) in enumerate(zip(parts["ars"], (52, 26))):
        cell = rows[k] * a["T"] + np.floor(t * per_year).astype(int)
        C, R = parts["ar_sums"](D, k, jnp.asarray(c), jnp.asarray(r))
        size = a["size"] * a["T"]
        np.testing.assert_allclose(
            np.asarray(C).ravel(), np.bincount(cell, c, size), rtol=1e-10
        )
        np.testing.assert_allclose(
            np.asarray(R).ravel(), np.bincount(cell, c * r, size), atol=1e-8
        )
    keys = jax.random.split(jax.random.PRNGKey(2), 2)
    r_new, ar, ar_par = parts["update_local"](
        D, keys, st, jnp.asarray(c), jnp.asarray(r)
    )
    assert len(ar) == len(ar_par) == 2
    # The rows' remainder plus the paths is the same before and after: only the paths moved.
    before = r + np.asarray(parts["offsets"](D, st))
    after = np.asarray(r_new) + np.asarray(parts["offsets"](D, st | {"ar": ar}))
    np.testing.assert_allclose(after, before, atol=1e-10)
    for new, was in zip(ar, old):
        assert new.shape == was.shape and float(jnp.abs(new - was).max()) > 1e-3
    # The second term is drawn given the first one's new path: its sums are those of the
    # remainder with the first path swapped.
    a = parts["ars"][0]
    cell0 = rows[0] * a["T"] + np.floor(t * 52).astype(int)
    swapped = r + np.asarray(old[0]).ravel()[cell0] - np.asarray(ar[0]).ravel()[cell0]
    tgt = swapped + np.asarray(old[1]).ravel()[np.asarray(D["ar_cell"][1])]
    C1, R1 = parts["ar_sums"](D, 1, jnp.asarray(c), jnp.asarray(tgt))
    _, mf, pf = parts["ar_filter"](ar_par[1], C1, R1)
    k3 = jax.random.split(keys[1], 3)[2]
    np.testing.assert_allclose(
        np.asarray(parts["ar_draw"](k3, ar_par[1], mf, pf)),
        np.asarray(ar[1]),
        atol=1e-9,
    )


def test_a_slice_that_only_shrinks_leaves_its_target_unchanged():
    # `b0.slice_vec` steps out a fixed count on each side, which narrows the draws when
    # the slice is longer than that. The scale updates here use no stepping out.
    jax, jnp = b0._jax()

    def logp(x):
        return -0.5 * x * x

    def spread(width, steps_out):
        def step(x, key):
            return b0.slice_vec(key, x, logp, width, steps_out=steps_out), None

        key = jax.random.PRNGKey(0)
        x0 = jax.random.normal(key, (4000,))
        x, _ = jax.lax.scan(step, x0, jax.random.split(jax.random.fold_in(key, 1), 400))
        return float(jnp.var(x))

    for width in (0.2, 5.0):
        assert 0.93 < spread(width, 0) < 1.07, width
    assert spread(0.2, 4) < 0.85


def _cells(seed=4, drop=()):
    """A small design with the collapsed building term in weekly steps: the sampler's parts,
    one chain's state, and in the sampler's row order the rows' building and step, a random
    target, each building's surface value and the rows' covariance from the noise and u.
    The buildings in `drop` lose their training rows."""
    full = td._design()
    train, _, _ = td._split(full)
    if len(drop):
        train = drift.subset(train, ~np.isin(train.site, drop))
    _, init, _, parts = _sampler(train, _groups(train))
    jax, jnp = b0._jax()
    st = td._state(init, parts)
    rng = np.random.default_rng(seed)
    order = parts["order"]
    site = train.site[order]
    step = np.floor(drift.years(train)[order] * 52).astype(int)
    F = 0.1 * rng.standard_normal(len(parts["zone"]))
    tgt = F[site] + 0.2 * rng.standard_normal(len(site))
    cov, _, _ = td._dense_cov(train, parts, st)
    D = parts["data"]
    c = parts["weights"](D, st)
    om_d, om_off = parts["pair_weights"](D, *parts["unit_W"](D, st["hyp"], c))
    sums = parts["cell_sums"](D, om_d, om_off, jnp.asarray(tgt))
    return parts, st, site, step, tgt, F, cov, sums


def test_cell_layout_places_every_row_and_pair():
    site = np.array([0, 0, 0, 2, 2, 2, 2, 5])
    step = np.array([3, 3, 7, 0, 1, 1, 4, 2])
    pi, pj = np.array([0, 1, 4, 5]), np.array([1, 0, 5, 4])
    lay = drift.cell_layout(site, step, pi, pj, size=7, steps=8, pads=(1, 2))
    assert [b["gap"].shape for b in lay["buckets"]] == [(1, 1), (1, 2), (1, 3)]
    np.testing.assert_array_equal(lay["buckets"][1]["gap"], [[0, 4]])
    np.testing.assert_array_equal(lay["buckets"][2]["gap"], [[0, 1, 3]])
    np.testing.assert_array_equal(lay["buckets"][2]["cells"], [[16, 17, 20]])
    np.testing.assert_array_equal(lay["buckets"][0]["sites"], [5])
    assert lay["size_H"] == 1 + 4 + 9 and lay["size_h"] == 1 + 2 + 3
    # Building 0 is the bucket of two: its rows sit at cells 0, 0 and 1.
    np.testing.assert_array_equal(lay["H_d"][:3], [1, 1, 4])
    np.testing.assert_array_equal(lay["h"], [1, 1, 2, 3, 4, 4, 5, 0])
    # The pairs (0, 1) and (1, 0) share cell 0 of building 0; (4, 5) cell 1 of building 2.
    np.testing.assert_array_equal(lay["H_o"], [1, 1, 5 + 4, 5 + 4])
    assert lay["active"].sum() == 6 and lay["active"][[3, 7, 16, 17, 20, 42]].all()


def _cell_cov(site, step, zone, lb, par):
    """The rows' covariance from the buildings' levels and paths."""
    same = site[:, None] == site[None, :]
    b2 = np.exp(2 * lb)[zone[site]]
    rho = 1 / (1 + np.exp(-par[1]))
    lag = np.abs(step[:, None] - step[None, :])
    return np.where(same, b2[:, None] + np.exp(2 * par[0]) * rho**lag, 0.0)


def test_cell_loglik_matches_the_dense_density():
    parts, st, site, step, tgt, F, cov, sums = _cells()
    _, jnp = b0._jax()
    zone = parts["zone"]

    def both(lb, par):
        """Each zone's log density: ours, and the dense one over the zone's rows (rows of
        two buildings are independent given the surface)."""
        ours = parts["cell_loglik"](
            parts["data"], jnp.asarray(lb), jnp.asarray(par), sums, jnp.asarray(F)
        )
        full = cov + _cell_cov(site, step, zone, np.asarray(lb), par)
        dense = []
        for z in range(len(lb)):
            rows = np.flatnonzero(zone[site] == z)
            dev = (tgt - F[site])[rows]
            sub = full[np.ix_(rows, rows)]
            dense.append(
                -0.5 * (np.linalg.slogdet(sub)[1] + dev @ np.linalg.solve(sub, dev))
            )
        return np.asarray(ours), np.array(dense)

    base = both([-1.8, -2.2], [-2.5, 1.0])
    assert len(base[0]) == 2 and min(np.bincount(zone[site], minlength=2)) > 50
    for lb, par in (
        ([-1.2, -2.2], [-2.5, 1.0]),
        ([-1.8, -2.9], [-1.7, 1.0]),
        ([-2.0, -2.0], [-3.0, 3.5]),
        ([-1.5, -2.5], [-2.0, -1.0]),
    ):
        ours, dense = both(lb, par)
        np.testing.assert_allclose(ours - base[0], dense - base[1], rtol=1e-8)
        assert np.abs(dense - base[1]).max() > 1.0


def test_cell_system_matches_the_dense_conditional():
    parts, st, site, step, tgt, F, cov, sums = _cells()
    jax, jnp = b0._jax()
    zone = parts["zone"]
    lb, par = np.array([-1.8, -2.2]), np.array([-2.5, 1.0])
    s2, rho = np.exp(2 * par[0]), 1 / (1 + np.exp(-par[1]))
    b2 = np.exp(2 * lb)[zone]
    lay = parts["cell_layout"]
    T = parts["ars"][0]["T"]
    checked = 0
    for (H, h), b in zip(sums, lay["buckets"]):
        ids = b["sites"]
        L, x, _ = parts["cell_system"](
            jnp.asarray(par),
            jnp.asarray(b2[ids]),
            jnp.asarray(F[ids]),
            H,
            h,
            jnp.asarray(b["gap"]),
        )
        L, x = np.asarray(L), np.asarray(x)
        for k in range(0, len(ids), max(1, len(ids) // 6)):
            rows = np.flatnonzero(site == ids[k])
            steps = np.unique(step[rows])
            m = len(steps)
            np.testing.assert_array_equal(b["cells"][k, :m], ids[k] * T + steps)
            # The building's state (level, path at its cells): prior, then the rows.
            prior = np.zeros((1 + m, 1 + m))
            prior[0, 0] = b2[ids[k]]
            prior[1:, 1:] = s2 * rho ** np.abs(steps[:, None] - steps[None, :])
            B = np.zeros((len(rows), 1 + m))
            B[:, 0] = 1
            B[np.arange(len(rows)), 1 + np.searchsorted(steps, step[rows])] = 1
            S = B @ prior @ B.T + cov[np.ix_(rows, rows)]
            gain = prior @ B.T @ np.linalg.inv(S)
            mu = np.r_[F[ids[k]], np.zeros(m)]
            mean = mu + gain @ (tgt[rows] - B @ mu)
            post = prior - gain @ B @ prior
            Q = L[k] @ L[k].T
            np.testing.assert_allclose(
                np.linalg.solve(L[k].T, x[k])[: 1 + m], mean, atol=1e-8
            )
            np.testing.assert_allclose(
                np.linalg.inv(Q)[: 1 + m, : 1 + m], post, atol=1e-9
            )
            checked += 1
    assert checked > 10


def test_fill_path_draws_the_steps_between_the_cells():
    full = td._design()
    train, _, _ = td._split(full)
    _, _, _, parts = _sampler(train, _groups(train))
    jax, jnp = b0._jax()
    par = jnp.asarray([np.log(0.2), 1.5])
    rho = 1 / (1 + np.exp(-1.5))
    active = np.array([[0, 1, 0, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0]], bool)
    at = np.array([[9.0, 0.3, 9.0, 9.0, -0.1, 9.0, 9.0], [9.0] * 7])
    draws = np.asarray(
        jax.vmap(
            lambda k: parts["fill_path"](k, par, jnp.asarray(at), jnp.asarray(active))
        )(jax.random.split(jax.random.PRNGKey(5), 20000))
    )
    np.testing.assert_array_equal(draws[:, 0, [1, 4]], np.tile([0.3, -0.1], (20000, 1)))
    cov = _ar_cov(0.2, rho, 7)
    pin, free = [1, 4], [0, 2, 3, 5, 6]
    gain = cov[np.ix_(free, pin)] @ np.linalg.inv(cov[np.ix_(pin, pin)])
    mean = gain @ np.array([0.3, -0.1])
    post = cov[np.ix_(free, free)] - gain @ cov[np.ix_(pin, free)]
    np.testing.assert_allclose(draws[:, 0, free].mean(0), mean, atol=0.006)
    np.testing.assert_allclose(np.cov(draws[:, 0, free].T), post, atol=0.002)
    # A path with no cell is a draw from the prior.
    np.testing.assert_allclose(np.cov(draws[:, 1].T), cov, atol=0.003)


def test_update_cells_places_the_joint_draw_and_keeps_the_prior_where_no_row_is():
    full = td._design()
    drop = np.unique(full.site)[[3, 40]]
    parts, st, site, step, tgt, F, cov, sums = _cells(drop=drop)
    jax, jnp = b0._jax()
    D = parts["data"]
    a = parts["ars"][0]
    lay = parts["cell_layout"]
    zone = np.asarray(parts["zone"])
    st = st | {"ar": (jnp.zeros((a["size"], a["T"])),)}
    key = jax.random.PRNGKey(3)
    bsd, lev, par, path = parts["update_cells"](D, key, st, sums, jnp.asarray(F))
    assert float(jnp.abs(bsd - st["bld_sd"]).min()) > 0
    assert float(jnp.abs(par - st["ar_par"][0]).min()) > 0
    bsd, lev, path = np.asarray(bsd), np.asarray(lev), np.asarray(path)
    assert np.isfinite(lev).all() and np.isfinite(path).all()
    # A replay of the draw with the step's own keys: each building's state is
    # L^-T (x + noise) at the scales the step returns, its level first, then its cells.
    _, _, k3, k4 = jax.random.split(key, 4)
    keys = jax.random.split(k4, len(sums) + 1)
    b2 = bsd[zone] ** 2
    seen = np.zeros(len(zone), bool)
    for kk, (H, h), b in zip(keys[1:], sums, lay["buckets"]):
        ids = b["sites"]
        L, x, _ = parts["cell_system"](
            par, jnp.asarray(b2[ids]), jnp.asarray(F[ids]), H, h, jnp.asarray(b["gap"])
        )
        eps = np.asarray(jax.random.normal(kk, x.shape))
        L, x = np.asarray(L), np.asarray(x)
        for k in range(len(ids)):
            z = np.linalg.solve(L[k].T, x[k] + eps[k])
            steps = np.unique(step[site == ids[k]])
            np.testing.assert_allclose(lev[ids[k]], z[0], atol=1e-12)
            np.testing.assert_allclose(
                path[ids[k], steps], z[1 : 1 + len(steps)], atol=1e-12
            )
        seen[ids] = True
    # A building with no row keeps its prior: its level is the surface plus b times the
    # step's noise, and it has no cell.
    assert set(np.flatnonzero(~seen)) >= set(drop) and not seen[drop].any()
    prior = F + np.sqrt(b2) * np.asarray(jax.random.normal(k3, (len(zone),)))
    np.testing.assert_allclose(lev[~seen], prior[~seen], atol=1e-12)
    active = np.asarray(lay["active"]).reshape(a["size"], a["T"])
    assert not active[drop].any() and np.abs(path[drop]).min() > 0
    np.testing.assert_array_equal(np.asarray(D["ar_cell"][0]), site * a["T"] + step)
    assert active.sum() == len(np.unique(site * a["T"] + step))
