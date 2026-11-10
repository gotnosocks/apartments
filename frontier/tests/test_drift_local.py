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
        12,
        "nbhd",
        4,
    )
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
