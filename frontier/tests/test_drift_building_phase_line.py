"""L1 with a level for each line of a building (`rentfrontier.drift_line` and
`rentfrontier.drift_building_phase_line`)."""

import dataclasses
import hashlib

import numpy as np
import pandas as pd
import pytest
import test_drift as td
import test_drift_local as tl

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building_phase,
    drift_building_phase_line,
    drift_line,
    drift_pool,
    run,
)

M = drift_building_phase_line
P = drift_building_phase.PHASES
# The line scale of the tests' states.
LINE_SD = 0.09


def _lines(full, k=3):
    """Each row's line when every building's units are dealt into `k` lines by their
    number, numbered from 0."""
    return np.unique(full.site * k + full.unit % k, return_inverse=True)[1]


def _split(full, line, every=8):
    """`td._split` with the lines: the training design, its rows to predict and the
    held-out mask. Held-out rows of units, or of lines, with no training row carry -1."""
    held = np.arange(len(full.y)) % every == 0

    def renumber(v):
        seen = np.unique(v[~held])
        return np.where(np.isin(v, seen), np.searchsorted(seen, v), -1), len(seen)

    unit, units = renumber(full.unit)
    line, lines = renumber(line)
    fields = {f.name: getattr(full, f.name) for f in dataclasses.fields(full)}
    d = drift_line.Design(
        **fields | dict(unit=unit, units=units), line=line, lines=lines
    )
    return drift_line.subset(d, ~held), drift_line.subset(d, held), held


def _phased(full, seed=4):
    rng = np.random.default_rng(seed)
    return dataclasses.replace(
        full, phase=rng.integers(0, len(P), len(full.y)), phases=P
    )


def _sampler(train, dof=None, weekly=True):
    settings = drift_line.Settings(
        chains=2, warmup=10, draws=10, site_block=7, level_dof=dof
    )
    groups = tl._groups(train) if weekly else drift.groups_of(train, ("building",))
    return drift_line.make_sampler(
        train, building_zones.Priors(), settings, groups=groups
    )


def _setup(dof=None, phases=False, seed=4):
    """A small lined design with the collapsed building term in weekly steps, as
    `tl._cells` builds L1's: the training design, the sampler's parts, one chain's state
    with random lines, and in the sampler's row order the rows' building, step and line, a
    random target, each building's surface value, the rows' covariance from the noise and
    u, and the lines' sums at the target."""
    full = td._design(per_unit=6)
    full = _phased(full) if phases else full
    train, _, _ = _split(full, _lines(full))
    _, init, _, parts = _sampler(train, dof)
    jax, jnp = b0._jax()
    rng = np.random.default_rng(seed)
    st = td._state(init, parts) | {
        "line": jnp.asarray(0.1 * rng.standard_normal(train.lines)),
        "line_sd": jnp.asarray(LINE_SD),
    }
    if phases:
        f = np.exp(0.2 * rng.standard_normal(len(P) - 1))
        st = st | {"phase_scale": jnp.asarray(f)}
    order = parts["order"]
    site = train.site[order]
    step = np.floor(drift.years(train)[order] * 52).astype(int)
    line = train.line[order]
    F = 0.1 * rng.standard_normal(len(parts["zone"]))
    tgt = F[site] + 0.2 * rng.standard_normal(len(site))
    cov, _, _ = td._dense_cov(train, parts, st)
    D = parts["data"]
    c = parts["weights"](D, st)
    om_d, om_off = parts["pair_weights"](D, *parts["unit_W"](D, st["hyp"], c))
    lt = parts["line_terms"](D, om_d, om_off, jnp.asarray(tgt))
    return dict(
        train=train,
        parts=parts,
        st=st,
        site=site,
        step=step,
        line=line,
        tgt=tgt,
        F=F,
        cov=cov,
        om=(om_d, om_off),
        lt=lt,
    )


def _line_cov(line, l2):
    return np.where(line[:, None] == line[None, :], l2, 0.0)


def test_lines_take_each_units_most_common_pair_and_its_latest_on_a_tie():
    day = pd.to_datetime(
        ["2026-01-01", "2026-02-01", "2026-03-01", "2026-03-01", "2026-04-01"]
        + ["2026-05-01", "2026-05-01", "2026-05-01", "2026-06-01"]
        + ["2026-07-01", "2026-07-02", "2026-07-03"]
    )
    frame = pd.DataFrame(
        {
            "building": list("aaaaabbbaccc"),
            "unit_id": ["1", "1", "1", "2", "2", "1", "1", None, "3", "1", "1", "1"],
            "bedrooms": [1, 1, 2, 2, 3, 0.4, 1, 1, 2, 2, 2, 1],
            "full_baths": [1, 1, 1, 1, 1, np.nan, np.nan, 1, 1, 1, 1, 1],
            "latest_day": day,
        }
    )
    held = np.zeros(len(frame), bool)
    held[[8, 9, 10]] = True
    line, lines = drift_line.line_index(frame, held)
    # Unit a|1 takes its two rows' (1, 1). Unit a|2's rows tie and its latest row's (3, 1)
    # wins; b|1's tie on the day too, and its later row's (1, none) wins. The row with no
    # unit_id is a unit of its own. c|1's two held-out rows outvote its training row. a|3's
    # line (2, 1) has no training row.
    np.testing.assert_array_equal(line, [0, 0, 0, 1, 1, 2, 2, 3, -1, 4, 4, 4])
    assert lines == 5
    keys = ["a|1|1", "a|3|1", "b|1|-1", "b|1|1", "c|2|1"]
    assert sorted(keys) == keys


def test_line_layout_places_every_pair_inside_its_buildings_block():
    s = _setup()
    lay, col = s["parts"]["line_layout"], s["parts"]["cell_layout"]
    line, site = s["line"], s["site"]
    # A pair is a line at one of its rows' cells.
    pair = lay["pair_of_row"]
    np.testing.assert_array_equal(lay["pair_line"][pair], line)
    np.testing.assert_array_equal(lay["pair_h"][pair], col["h"])
    np.testing.assert_array_equal(lay["line_site"][line], site)
    n_k = np.bincount(lay["pair_line"])
    assert len(lay["pp_a"]) == (n_k**2).sum() and n_k.max() > 1
    # The pairs of pairs of a line on its diagonal are its pairs' own cells in the flat H.
    diag = lay["pp_a"] == lay["pp_b"]
    first = np.zeros(len(lay["pair_line"]), int)
    first[pair] = np.arange(len(pair))
    np.testing.assert_array_equal(
        lay["pp_H"][diag], col["H_d"][first[lay["pp_a"][diag]]]
    )


@pytest.mark.parametrize("dof", [None, 4.0])
def test_level_loglik_matches_the_dense_density_with_the_lines_integrated_out(dof):
    s = _setup(dof=dof)
    parts, st, site, step, line, tgt, F, cov = (
        s[k] for k in ("parts", "st", "site", "step", "line", "tgt", "F", "cov")
    )
    _, jnp = b0._jax()
    zone, kap = parts["zone"], st.get("kap")

    def both(lb, par, l2):
        ours = parts["level_loglik"](
            parts["data"],
            jnp.exp(jnp.asarray(lb)),
            jnp.asarray(par),
            jnp.asarray(F),
            *s["om"],
            jnp.asarray(tgt),
            l2,
            kap,
        )
        V = (
            cov
            + tl._cell_cov(site, step, zone, np.asarray(lb), np.asarray(par), kap)
            + _line_cov(line, l2)
        )
        dev = tgt - F[site]
        dense = -0.5 * (np.linalg.slogdet(V)[1] + dev @ np.linalg.solve(V, dev))
        return float(ours), dense

    base = both([-1.8, -2.2], [-2.5, 1.0], LINE_SD**2)
    for lb, par, l2 in (
        ([-1.8, -2.2], [-2.5, 1.0], 0.2**2),
        ([-1.8, -2.2], [-2.5, 1.0], 0.02**2),
        ([-1.2, -2.6], [-1.7, 2.0], LINE_SD**2),
        ([-1.5, -2.0], [-2.0, -1.0], 0.15**2),
    ):
        ours, dense = both(lb, par, l2)
        np.testing.assert_allclose(ours - base[0], dense - base[1], rtol=1e-8)
        assert abs(dense - base[1]) > 1.0


def test_cell_system_on_the_corrected_sums_is_the_dense_conditional():
    s = _setup()
    parts, st, site, step, line, tgt, F, cov = (
        s[k] for k in ("parts", "st", "site", "step", "line", "tgt", "F", "cov")
    )
    _, jnp = b0._jax()
    zone = parts["zone"]
    lb, par = np.array([-1.8, -2.2]), np.array([-2.5, 1.0])
    s2, rho = np.exp(2 * par[0]), 1 / (1 + np.exp(-par[1]))
    b2 = np.exp(2 * lb)[zone]
    l2 = LINE_SD**2
    full = cov + _line_cov(line, l2)
    lay = parts["cell_layout"]
    T = parts["ars"][0]["T"]
    sums = parts["corrected"](parts["data"], s["lt"], l2)
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
            prior = np.zeros((1 + m, 1 + m))
            prior[0, 0] = b2[ids[k]]
            prior[1:, 1:] = s2 * rho ** np.abs(steps[:, None] - steps[None, :])
            B = np.zeros((len(rows), 1 + m))
            B[:, 0] = 1
            B[np.arange(len(rows)), 1 + np.searchsorted(steps, step[rows])] = 1
            S = B @ prior @ B.T + full[np.ix_(rows, rows)]
            gain = prior @ B.T @ np.linalg.inv(S)
            mu = np.r_[F[ids[k]], np.zeros(m)]
            mean = mu + gain @ (tgt[rows] - B @ mu)
            post = prior - gain @ B @ prior
            np.testing.assert_allclose(
                np.linalg.solve(L[k].T, x[k])[: 1 + m], mean, atol=1e-8
            )
            np.testing.assert_allclose(
                np.linalg.inv(L[k] @ L[k].T)[: 1 + m, : 1 + m], post, atol=1e-9
            )
            checked += 1
    assert checked > 10


def test_the_lines_given_the_levels_and_paths_are_the_dense_conditional():
    s = _setup()
    parts, train, site, step, line, tgt, cov = (
        s[k] for k in ("parts", "train", "site", "step", "line", "tgt", "cov")
    )
    _, jnp = b0._jax()
    rng = np.random.default_rng(2)
    T = parts["ars"][0]["T"]
    lev = 0.1 * rng.standard_normal(len(parts["zone"]))
    path = 0.05 * rng.standard_normal((len(parts["zone"]), T))
    l2 = LINE_SD**2
    mean, var = parts["line_cond"](
        parts["data"], s["lt"], l2, jnp.asarray(lev), jnp.asarray(path)
    )
    C = np.zeros((len(line), train.lines))
    C[np.arange(len(line)), line] = 1
    r = tgt - lev[site] - path[site, step]
    CW = np.linalg.solve(cov, C).T
    Q = np.eye(train.lines) / l2 + CW @ C
    # The units nest in the lines, so the lines are independent given the rest.
    assert np.abs(Q - np.diag(np.diag(Q))).max() < 1e-8 * np.abs(Q).max()
    np.testing.assert_allclose(np.asarray(var), 1 / np.diag(Q), rtol=1e-8)
    np.testing.assert_allclose(np.asarray(mean), (CW @ r) / np.diag(Q), atol=1e-9)


@pytest.mark.parametrize("dof", [None, 4.0])
def test_slow_system_is_the_dense_regression_with_the_lines_integrated_out(dof):
    s = _setup(dof=dof)
    parts, st, site, step, line, tgt, F, cov = (
        s[k] for k in ("parts", "st", "site", "step", "line", "tgt", "F", "cov")
    )
    jax, jnp = b0._jax()
    D = parts["data"]
    slow = parts["slow"]
    names = list(parts["slow_shares"])
    assert len(slow) > 10 and any(n.startswith("bed>=") for n in names)
    zone = parts["zone"]
    lb, par = np.array([-1.8, -2.2]), np.array([-2.5, 1.0])
    st = st | {
        "bld_sd": jnp.exp(jnp.asarray(lb)),
        "ar_par": st["ar_par"].at[0].set(jnp.asarray(par)),
    }
    l2 = LINE_SD**2
    om_d, om_off = s["om"]
    lt = s["lt"]
    sums = parts["corrected"](D, lt, l2)
    A, lin, _, _ = parts["slow_system"](
        D, st, om_d, om_off, lt, sums, jnp.asarray(tgt), jnp.asarray(F), l2
    )
    X = np.concatenate([np.asarray(x) for x in D["xs"]])[:, slow]
    full = (
        cov
        + tl._cell_cov(site, step, zone, lb, par, st.get("kap"))
        + _line_cov(line, l2)
    )
    np.testing.assert_allclose(np.asarray(A), X.T @ np.linalg.solve(full, X), rtol=1e-7)
    np.testing.assert_allclose(
        np.asarray(lin),
        X.T @ np.linalg.solve(full, tgt - F[site]),
        rtol=1e-7,
        atol=1e-7,
    )
    # The step moves theta, the target and the lines' sums together.
    theta, new_tgt, new_lt = parts["update_slow"](
        D,
        jax.random.PRNGKey(3),
        st,
        st["theta"],
        om_d,
        om_off,
        lt,
        jnp.asarray(tgt),
        jnp.asarray(F),
        l2,
    )
    sl_b = parts["slices"][0]
    step_b = np.asarray(theta[sl_b] - st["theta"][sl_b])
    assert np.abs(step_b[slow]).min() > 0
    np.testing.assert_array_equal(np.delete(step_b, slow), 0.0)
    np.testing.assert_allclose(np.asarray(new_tgt), tgt - X @ step_b[slow], atol=1e-10)
    want = parts["line_terms"](D, om_d, om_off, new_tgt)
    for k in ("h", "hl"):
        np.testing.assert_allclose(
            np.asarray(new_lt[k]), np.asarray(want[k]), atol=1e-8
        )


@pytest.mark.parametrize("dof,phases", [(None, False), (4.0, True)])
def test_scales_logp_matches_the_dense_density_as_every_scale_moves(dof, phases):
    s = _setup(dof=dof, phases=phases)
    parts, st, train, site, step, line, tgt, F = (
        s[k] for k in ("parts", "st", "train", "site", "step", "line", "tgt", "F")
    )
    _, jnp = b0._jax()
    m, sd = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (np.log(np.asarray(st["lam"])) - float(m)) / float(sd)
    par = np.array([-2.5, 1.0])
    s2, rho = np.exp(2 * par[0]), 1 / (1 + np.exp(-par[1]))
    path = np.where(
        site[:, None] == site[None, :],
        s2 * rho ** np.abs(step[:, None] - step[None, :]),
        0.0,
    )
    lf = np.log(np.asarray(st["phase_scale"])) if phases else np.zeros(0)

    def both(head, ll):
        x = np.r_[np.log(head), lf, ll]
        got = parts["scales_logp"](
            parts["data"],
            jnp.asarray(x),
            jnp.asarray(eta),
            jnp.asarray(tgt),
            st["bld_sd"],
            jnp.asarray(par),
            jnp.asarray(F),
            st.get("kap"),
        )
        l2 = np.exp(2 * ll)
        want = td._scales_want(
            train, parts, st, eta, tgt, F, x[:-1], extra=path + _line_cov(line, l2)
        )
        return float(got), want - l2 / (2 * drift_line.LINE_SD_PRIOR**2) + ll

    head = np.array([0.08, 0.1, 0.2, 0.05, 0.06, 0.07, 0.08, 4.0])
    base = both(head, np.log(LINE_SD))
    for h, ll in (
        (head, np.log(0.2)),
        (head, np.log(0.02)),
        (np.array([0.03, 0.2, 1.5, 0.05, 0.06, 0.07, 0.08, 4.0]), np.log(LINE_SD)),
        (np.array([0.05, 0.07, 0.6, 0.07, 0.05, 0.06, 0.1, 2.6]), np.log(0.15)),
    ):
        got, want = both(h, ll)
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_with_no_line_spread_the_collapsed_step_is_l1s():
    s = _setup(dof=4.0)
    parts, st, train, tgt, F = (s[k] for k in ("parts", "st", "train", "tgt", "F"))
    jax, jnp = b0._jax()
    settings = drift_line.Settings(
        chains=2, warmup=10, draws=10, site_block=7, level_dof=4.0
    )
    _, _, _, l1 = drift.make_sampler(
        train, building_zones.Priors(), settings, groups=tl._groups(train)
    )
    D, D1 = parts["data"], l1["data"]
    om_d, om_off = s["om"]
    tgt = jnp.asarray(tgt)
    ours = parts["corrected"](D, s["lt"], 0.0)
    theirs = l1["cell_sums"](D1, om_d, om_off, tgt)
    for (H, h), (H1, h1) in zip(ours, theirs):
        np.testing.assert_array_equal(np.asarray(H), np.asarray(H1))
        np.testing.assert_array_equal(np.asarray(h), np.asarray(h1))
    assert float(parts["line_loglik"](s["lt"], 0.0)) == 0.0
    # The same key draws the same spreads, levels and paths from either model's sums.
    key = jax.random.PRNGKey(5)
    for a, b in zip(
        parts["update_cells"](D, key, st, ours, jnp.asarray(F)),
        l1["update_cells"](D1, key, st, theirs, jnp.asarray(F)),
    ):
        np.testing.assert_array_equal(np.asarray(a), np.asarray(b))
    A, lin, _, _ = parts["slow_system"](
        D, st, om_d, om_off, s["lt"], ours, tgt, jnp.asarray(F), 0.0
    )
    A1, lin1, _ = l1["slow_system"](D1, st, om_d, om_off, theirs, tgt, jnp.asarray(F))
    np.testing.assert_allclose(np.asarray(A), np.asarray(A1), rtol=1e-10)
    np.testing.assert_allclose(
        np.asarray(lin), np.asarray(lin1), rtol=1e-10, atol=1e-10
    )
    # As line_sd goes to 0 the scale step's density is L1's plus line_sd's prior.
    m, sd = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (jnp.log(st["lam"]) - m) / sd
    par = st["ar_par"][0]
    tiny = -30.0
    for head in (
        np.log([0.08, 0.1, 0.2, 0.05, 0.06, 0.07, 0.08, 4.0]),
        np.log([0.03, 0.2, 1.5, 0.09, 0.04, 0.11, 0.05, 2.6]),
    ):
        ours = parts["scales_logp"](
            D, jnp.asarray(np.r_[head, tiny]), eta, tgt, st["bld_sd"], par, F, st["kap"]
        )
        theirs = l1["scales_logp"](
            D1, jnp.asarray(head), eta, tgt, st["bld_sd"], par, F, st["kap"]
        )
        np.testing.assert_allclose(float(ours) - tiny, float(theirs), rtol=1e-10)


def test_predict_adds_known_lines_and_widens_new_ones():
    full = td._design(per_unit=9)
    train, test, held = _split(full, _lines(full))
    pu, pl = train.pred["unit"], train.pred["line"]
    seen, known = pu >= 0, pl >= 0
    # The three cases: a unit with training rows, a new unit of a known line, a new line.
    assert seen.any() and (~seen & known).any() and (~known).any()
    assert not (seen & ~known).any()
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(4)
    T = parts["ars"][0]["T"]
    S = len(parts["zone"])
    st = td._state(init, parts) | {
        "theta": jnp.asarray(0.01 * rng.standard_normal(parts["G"])),
        "lev": jnp.asarray(0.1 * rng.standard_normal(S)),
        "line": jnp.asarray(0.1 * rng.standard_normal(train.lines)),
        "line_sd": jnp.asarray(LINE_SD),
        "ar": (jnp.asarray(0.05 * rng.standard_normal((S, T))),),
    }
    loc, sd, mean = (np.asarray(v) for v in parts["predict"](D, st))
    order = parts["order"]
    line_row = train.line[order]
    path = np.asarray(st["ar"][0]).ravel()
    lines = np.asarray(st["line"])
    e = np.asarray(
        D["y"]
        - parts["offsets"](D, st)
        - parts["all_means"](D, st["theta"])
        - st["lev"][D["site"]]
    )
    e = e - lines[line_row]
    V, _, _ = td._dense_cov(train, parts, st)
    ss, s_d, tau = np.exp(np.asarray(st["hyp"]))
    t, unit = drift.years(train)[order], train.unit[order]
    k = np.where(
        pu[:, None] == unit[None, :],
        ss**2
        + s_d**2 * np.exp(-np.abs(train.pred["years"][:, None] - t[None, :]) / tau),
        0.0,
    )
    want_mean = k @ np.linalg.solve(V, e)
    want_var = ss**2 + s_d**2 - np.einsum("pi,ip->p", k, np.linalg.solve(V, k.T))
    want_var = want_var + np.where(known, 0.0, LINE_SD**2)
    np.testing.assert_allclose(mean, want_mean, atol=1e-6)
    np.testing.assert_allclose(sd, np.sqrt(want_var), rtol=1e-5)
    np.testing.assert_allclose(sd[~seen & known], np.hypot(ss, s_d), rtol=1e-6)
    np.testing.assert_allclose(
        sd[~known], np.sqrt(ss**2 + s_d**2 + LINE_SD**2), rtol=1e-6
    )
    sl_b, sl_M, _, _ = parts["slices"]
    theta, lev = np.asarray(st["theta"]), np.asarray(st["lev"])
    alpha = train.names.index("alpha")
    others = [j for j in range(len(train.names)) if j != alpha]
    Mw = theta[sl_M]
    fixed = (
        test.x[:, others] @ theta[sl_b]
        + (1 - test.frac) * Mw[test.week]
        + test.frac * Mw[test.week + 1]
        + lev[test.site]
        + path[np.asarray(D["ar_pcell"][0])]
    )
    shift = np.where(known, lines[np.maximum(pl, 0)], 0.0)
    np.testing.assert_allclose(loc, fixed + mean + shift, atol=1e-5)


def test_a_run_recovers_a_planted_line_sd():
    truth = dict(unit_sd=0.06, line_sd=0.15)
    full = td._design(n=6000, per_unit=4)
    line = _lines(full, k=2)
    rng = np.random.default_rng(8)
    u = truth["unit_sd"] * rng.standard_normal(full.units)
    lv = truth["line_sd"] * rng.standard_normal(line.max() + 1)
    full = dataclasses.replace(full, y=full.y + u[full.unit] + lv[line])
    train, test, held = _split(full, line)
    settings = drift_line.Settings(chains=2, warmup=150, draws=300, keep_every=5)
    groups = drift.groups_of(train, ("building",))
    out = drift_line.run(
        train,
        building_zones.Priors(),
        settings,
        log=lambda m: None,
        gp=None,
        groups=groups,
    )
    for name in ("line_sd", "unit_sd"):
        x = out["trace"][name]
        assert x.shape == (2, 300) and np.ptp(x) > 0
        lo, hi = np.quantile(x, [0.001, 0.999])
        assert lo < truth[name] < hi, (name, lo, hi)
    assert out["kept"]["line_sd"].shape == (2, 60)
    # The held-out rows' predictions beat L1's, whose units alone carry the lines.
    plain = drift.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=300, keep_every=5),
        log=lambda m: None,
        gp=None,
        groups=groups,
    )
    loc = out["kept"]["pred_loc"].mean((0, 1))
    loc_plain = plain["kept"]["pred_loc"].mean((0, 1))
    ratio = np.mean((test.y - loc) ** 2) / np.mean((test.y - loc_plain) ** 2)
    assert ratio < 0.97, ratio
    diag = drift_line.diagnostics(out["trace"], train.names)
    assert "line_sd" in diag["per_quantity"]
    assert diag["max_rhat"] >= diag["per_quantity"]["line_sd"]["rhat"]
    summary = drift_line.summarize(out["kept"], train.names)
    assert set(summary["unit"]) == set(drift.HYP) | {"line_sd"}


# The sha256 of every traced and kept array of the run below on the CPU. A deliberate
# change to the line model's draws changes it.
LINE_RUN_SHA256 = "289629a8252591f8cce86b344926d4ed7db1de5a72ec1602f6329a9d9a34497f"


def test_a_lined_design_draws_what_it_drew_when_pinned():
    full = _phased(td._design(n=400, per_unit=9))
    train, _, _ = _split(full, _lines(full))
    out = M.run(
        train,
        building_zones.Priors(),
        drift_line.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    assert out["trace"]["line_sd"].shape == (2, 8)
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 9 + len(P) - 1
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == LINE_RUN_SHA256


def test_the_model_is_l1_with_the_lines():
    assert M.NAME == "drift-building-phase-line"
    assert M.LEVEL_DOF == drift_building_phase.LEVEL_DOF
    assert M.GROUPS == ("building",) and M.PHASES == P
    assert M.Settings is drift_line.Settings and M.Design is drift_line.Design
    assert '("drift-building-phase-line", "drift_building_phase_line")' in (
        open(run.__file__).read()
    )
    assert drift_pool.model_diagnostics({"model": {"name": M.NAME}}) is (
        drift_line.diagnostics
    )
    full = td._design(n=300)
    train, _, _ = _split(_phased(full), _lines(full))
    rec = M.run_record(train)
    assert rec["line"]["lines"] == train.lines and "phase" in rec
    assert set(drift_line.SLOW_COLUMNS) >= set(drift.Settings().slow_columns)
