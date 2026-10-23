import numpy as np
from test_building_zones import _design

from rentfrontier import amp_joint, b0, building_zones
from rentfrontier import building_zones_gibbs as bzg


def _toy(seed=0):
    """Two zones' waves at 60 buildings, centred over all of them as `wave_matrix` centres
    them, with levels drawn from the model."""
    rng = np.random.default_rng(seed)
    zone = np.repeat([0, 1], [25, 35])
    which = np.repeat([0, 1], [4, 6])
    Bc = np.zeros((60, 10))
    for z in (0, 1):
        Bc[np.ix_(zone == z, which == z)] = rng.standard_normal(
            ((zone == z).sum(), (which == z).sum())
        )
    Bc -= Bc.mean(0)
    sds = rng.uniform(0.5, 1.5, 10)
    amp, bsd = np.array([0.5, 0.3]), np.array([0.2, 0.25])
    w = rng.standard_normal(10) * amp[which] * sds
    eta = Bc @ w + rng.standard_normal(60) * bsd[zone]
    return Bc, sds, which, zone, bsd, eta


def _grid_posterior(Bc, sds, which, zone, bsd, eta, prior):
    """The amplitudes' posterior given the levels on a grid, from the levels' Gaussian density
    with the waves integrated out, and E[w | eta] under it."""
    g = np.linspace(0.01, 1.6, 160)
    logp = np.zeros((len(g), len(g)))
    Ew = np.zeros((len(g), len(g), len(sds)))
    Db = np.diag(bsd[zone] ** 2)
    for i, a0 in enumerate(g):
        for j, a1 in enumerate(g):
            dw = (np.array([a0, a1])[which] * sds) ** 2
            V = Bc @ np.diag(dw) @ Bc.T + Db
            _, logdet = np.linalg.slogdet(V)
            sol = np.linalg.solve(V, eta)
            logp[i, j] = -logdet / 2 - eta @ sol / 2 - (a0**2 + a1**2) / (2 * prior**2)
            Ew[i, j] = dw * (Bc.T @ sol)
    p = np.exp(logp - logp.max())
    p /= p.sum()
    return g, p, np.einsum("ij,ijk->k", p, Ew)


def test_step_draws_the_amplitudes_posterior_given_the_levels():
    jax, jnp = b0._jax()
    Bc, sds, which, zone, bsd, eta = _toy()
    prior = 0.3
    step = jax.jit(amp_joint.make_step(Bc, sds, which, zone, prior))

    def body(amp, key):
        amp, w = step(key, jnp.asarray(eta), jnp.asarray(bsd), amp)
        return amp, (amp, w)

    keys = jax.random.split(jax.random.PRNGKey(3), 6000)
    _, (amps, ws) = jax.lax.scan(body, jnp.asarray([0.9, 0.9]), keys)
    amps, ws = np.asarray(amps)[500:], np.asarray(ws)[500:]
    g, p, Ew = _grid_posterior(Bc, sds, which, zone, bsd, eta, prior)
    mean = np.array([p.sum(1) @ g, p.sum(0) @ g])
    sd = np.sqrt(np.array([p.sum(1) @ g**2, p.sum(0) @ g**2]) - mean**2)
    # 5,500 draws of a chain with little autocorrelation: the means agree to a few hundredths
    # of a posterior sd.
    assert np.all(np.abs(amps.mean(0) - mean) < 0.1 * sd), (amps.mean(0), mean, sd)
    assert np.all(np.abs(amps.std(0) / sd - 1) < 0.1), (amps.std(0), sd)
    assert np.allclose(ws.mean(0), Ew, atol=0.05 * np.abs(Ew).max())


def test_gibbs_sweep_runs_with_the_joint_step():
    d = _design(n=300, weeks=12, seed=4)
    out = bzg.run(
        d,
        building_zones.Priors(),
        bzg.Settings(chains=2, warmup=20, draws=20, keep_every=5, joint_amp=True),
        log=lambda m: None,
    )
    amp = out["trace"]["amp"]
    assert np.all(np.isfinite(amp)) and np.all(amp > 0)
    assert np.all(np.isfinite(out["kept"]["gp_w"]))
