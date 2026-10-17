"""NUTS on the global coefficients and the log scales, with each building's
local effects integrated out (`marginal`), and exact draws of everything else.

This is the sampler of docs/model/gpu-inference-direction-2026-10-17.md. Each
transition runs these updates in turn:

1. NumPyro's NUTS moves the global coefficients and every log scale, given
   the row weights `lam` and the unit weights `kappa`, on `marginal.log_target`.
   The coefficients enter whitened by a pilot estimate of their conditional
   precision (`whitening`), so the adapted diagonal mass matrix only has to
   cover the scales.
2. Each global block's scale is drawn with the block divided by its scale
   held fixed (`block_scales`), still with the local effects integrated out.
   NUTS moves a scale and its block together only slowly where they trade
   off, as in a funnel.
3. The building blocks and the unit effects are drawn from their Gaussian
   conditional (`marginal.draw_locals`).
4. nu is drawn with the row weights integrated out, by an independence
   Metropolis step from a grid proposal (`draw_log_nu`), then the row weights
   given nu.
5. The unit weights are drawn given the unit effects (Student-t units with a
   fixed unit_nu).
6. Interweaving moves rescale each noise group's sigma together with its rows'
   weights, and unit_scale together with the unit weights (`interweave`).
   Each is an exact draw of the scale with the weight divided by the squared
   scale held fixed, which is the direction NUTS cannot move along while the
   weights stay fixed.

Steps 3 to 6 repeat `local_sweeps` times. Each sweep costs about as much as
one leapfrog step, and a unit with a single row needs many of them to move
its effect, its weight and its row's weight, which all explain the same
residual. After the sweeps the NUTS state takes the new coefficients and log
scales, and its potential and gradient are recomputed for the new weights, as
in NumPyro's HMCGibbs.

`run` mirrors `gibbs.run`: the retained draws go through `collect.collect`
with `gibbs.site_values`, so the held-out scores, traces and gate diagnostics
come out in the same form.
"""

import time
from dataclasses import asdict, dataclass

import jax
import jax.numpy as jnp
import numpy as np
from jax.scipy.linalg import solve_triangular
from numpyro.infer.hmc import hmc

from rentfrontier import collect as collect_module
from rentfrontier import gibbs, marginal
from rentfrontier import model as model_module

# Support of nu's grid proposal, on log nu. The prior Gamma(2, scale 10) puts
# about 0.5% of its mass below 0.5 and 1e-8 above 200.
NU_LO, NU_HI = float(np.log(0.5)), float(np.log(200.0))


@dataclass
class Settings:
    chains: int = 4
    warmup: int = 500
    # Warmup transitions before the whitening is recomputed at the current
    # state; NUTS adapts afresh over the rest of the warmup.
    pilot: int = 150
    draws: int = 1000
    keep_every: int = 50
    seed: int = 20261017
    target_accept: float = 0.8
    max_tree_depth: int = 8
    nu_steps: int = 3  # independence Metropolis steps per local sweep
    interweave: bool = True
    local_sweeps: int = 1  # sweeps of steps 3 to 6 per transition
    block_scales: bool = True
    trace_groups: int = 32
    chain_batch: int = 0  # vectorise this many chains at a time (0 = all)
    collect_segments: int = 1

    def to_dict(self):
        d = asdict(self)
        del d["collect_segments"]
        return d


def check_design(d: gibbs.Design):
    marginal.check_design(d)
    if d.noise_x is not None or (d.unit_t and d.unit_nu_fixed is None):
        raise ValueError(
            "marginal NUTS covers per-group noise without noise_x, and Student-t "
            "units only with a fixed unit_nu"
        )


def noise_groups(d: gibbs.Design):
    """Each row's noise group and the group scale names."""
    if d.noise_group is None:
        return jnp.zeros(d.y.shape[0], jnp.int32), ("sigma",)
    return d.noise_group, d.group_noise_names


def whitening(d, g, s, lam, kappa):
    """The conditional mean g0 of the global coefficients given the scales and
    weights, and wt = L^-T for their conditional precision L L'. The log
    target is quadratic in g, so its Hessian comes exactly from one
    forward-over-reverse product per column, and one Newton step from any g
    lands on the mean."""

    def f(gg):
        return marginal.log_marginal(d, gg, s, lam, kappa) + marginal.log_global_prior(
            d, gg, s
        )

    grad = jax.grad(f)
    p = g.shape[0]
    neg_h = jax.lax.map(
        lambda v: jax.jvp(grad, (g,), (v,))[1], jnp.eye(p), batch_size=8
    )
    h = -0.5 * (neg_h + neg_h.T)
    chol = jnp.linalg.cholesky(h)
    step = jax.scipy.linalg.cho_solve((chol, True), grad(g))
    wt = solve_triangular(chol.T, jnp.eye(p), lower=False)
    return g + step, wt, chol


def nu_log_target(x, e, sig):
    """log p(log nu = x | e, sigma) up to a constant, with the row weights
    integrated out: Student-t rows, the Gamma(2, scale 10) prior and the
    Jacobian of log nu."""
    nu = jnp.exp(x)
    return (
        jnp.sum(collect_module.student_t_logpdf(e, nu, sig))
        + jax.scipy.stats.gamma.logpdf(nu, 2.0, scale=10.0)
        + x
    )


def nu_proposal(f):
    """Cell edges (257,) and log masses (256,) of the grid density for the
    log target `f` of log nu:
    1. a coarse grid of 64 cells over [NU_LO, NU_HI] locates the mode;
    2. 33 points around the best coarse cell give the mode and the curvature
       by a parabola;
    3. 256 cells over the mode +- 8 sd carry a piecewise-constant density
       exp(f at the cell's centre).
    Each grid point costs one pass over the rows."""
    fmap = lambda xs: jax.lax.map(f, xs)
    coarse = jnp.linspace(NU_LO, NU_HI, 65)
    hc = coarse[1] - coarse[0]
    fc = fmap(0.5 * (coarse[1:] + coarse[:-1]))
    centre = coarse[jnp.argmax(fc)] + 0.5 * hc
    hm = hc / 8
    mid = centre + hm * jnp.arange(-16, 17)
    fm = fmap(mid)
    j = jnp.clip(jnp.argmax(fm), 1, 31)
    f0, f1, f2 = fm[j - 1], fm[j], fm[j + 1]
    # Curvature at most that of a coarse cell's width, so a flat or noisy
    # stretch still gives a finite spread.
    curv = jnp.minimum((f2 - 2 * f1 + f0) / hm**2, -1.0 / hc**2)
    mode = jnp.clip(mid[j] - (f2 - f0) / (2 * hm * curv), mid[j] - hm, mid[j] + hm)
    sd = 1.0 / jnp.sqrt(-curv)
    edges = jnp.clip(mode + sd * jnp.linspace(-8, 8, 257), NU_LO, NU_HI)
    widths = jnp.diff(edges)
    ff = fmap(0.5 * (edges[1:] + edges[:-1]))
    log_w = jnp.where(widths > 0, ff + jnp.log(jnp.maximum(widths, 1e-300)), -jnp.inf)
    return edges, log_w


def nu_log_q(v, edges, log_w):
    """Log density at v of the proposal: the grid density (0.9) mixed with the
    uniform on [NU_LO, NU_HI] (0.1)."""
    widths = jnp.diff(edges)
    k = jnp.clip(jnp.searchsorted(edges, v, side="right") - 1, 0, widths.shape[0] - 1)
    inside = (v >= edges[0]) & (v < edges[-1]) & (widths[k] > 0)
    dens = log_w[k] - jnp.log(jnp.maximum(widths[k], 1e-300))
    fine = jnp.where(
        inside, jnp.log(0.9) + dens - jax.scipy.special.logsumexp(log_w), -jnp.inf
    )
    return jnp.logaddexp(fine, jnp.log(0.1 / (NU_HI - NU_LO)))


def draw_log_nu(key, x, e, sig, steps):
    """Independence Metropolis on log nu from `nu_proposal`. The proposal
    depends on the residuals and scales only, never on the current x, so the
    Metropolis-Hastings ratio corrects it exactly. Its uniform part lets a
    chain far from the mode return in one accepted step."""
    f = lambda v: nu_log_target(v, e, sig)
    edges, log_w = nu_proposal(f)
    widths = jnp.diff(edges)

    def mh(carry, k):
        x, fx, acc = carry
        k1, k2, k3, k4, k5 = jax.random.split(k, 5)
        cell = jax.random.categorical(k1, log_w)
        fine = edges[cell] + widths[cell] * jax.random.uniform(k2)
        prop = jnp.where(
            jax.random.uniform(k3) < 0.9,
            fine,
            jax.random.uniform(k4, minval=NU_LO, maxval=NU_HI),
        )
        fp = f(prop)
        ratio = fp - fx + nu_log_q(x, edges, log_w) - nu_log_q(prop, edges, log_w)
        ok = jnp.log(jax.random.uniform(k5)) < ratio
        return (jnp.where(ok, prop, x), jnp.where(ok, fp, fx), acc + ok), None

    (x, _, acc), _ = jax.lax.scan(
        mh, (x, f(x), jnp.zeros(())), jax.random.split(key, steps)
    )
    return x, acc / steps


def interweave(key, d, s, lam, kappa, nu):
    """Exact draws of each noise group's sigma^2 with omega = lam / sigma^2
    held fixed, and of unit_scale^2 with pi = kappa / unit_scale^2 held fixed.
    Under half-normal(sd) priors on the scales and Gamma(nu / 2, rate nu / 2)
    weights, the squared scale tau has the conditional

        tau ~ Gamma(n nu / 2 + 1 / 2, rate nu sum(omega) / 2 + 1 / (2 sd^2))

    over the group's n rows (or the J units with unit_nu). The likelihood
    reads only omega (and the unit prior only pi), so neither enters."""
    grp, names = noise_groups(d)
    k1, k2 = jax.random.split(key)
    sig = jnp.stack([s[n] for n in names])
    omega = lam / sig[grp] ** 2
    n_g = jax.ops.segment_sum(jnp.ones_like(lam), grp, len(names))
    sum_w = jax.ops.segment_sum(omega, grp, len(names))
    sd = jnp.asarray([d.prior_sd[n] for n in names])
    tau = jax.random.gamma(k1, n_g * nu / 2 + 0.5) / (nu * sum_w / 2 + 1 / (2 * sd**2))
    new = dict(s)
    new.update({n: jnp.sqrt(tau[i]) for i, n in enumerate(names)})
    lam = omega * tau[grp]
    if d.unit_t:
        nu_u = d.unit_nu_fixed
        pi = kappa / s["unit_scale"] ** 2
        tau_u = jax.random.gamma(k2, d.n_units * nu_u / 2 + 0.5) / (
            nu_u * jnp.sum(pi) / 2 + 1 / (2 * d.prior_sd["unit_scale"] ** 2)
        )
        new["unit_scale"] = jnp.sqrt(tau_u)
        kappa = pi * tau_u
    return new, lam, kappa


def block_scales(key, f, g, s, blocks, prior_sd):
    """Draws of each global block's scale in turn, with z = g_B / s held fixed.

    The block's prior N(0, s^2 R^-1) puts on z a prior free of s, so given z
    the scale has the density of its half-normal(sd) prior times exp(f) at
    g_B = s z. `f` (the marginal) is quadratic in g and reads no global block
    scale, so along that line it is a quadratic in s with slope grad f . v and
    curvature v' H v, for v the block's z placed in a vector of zeros: a
    truncated normal. After each draw the gradient moves by the step times
    H v, which keeps the next block's slope exact. Returns the new g and
    scales."""
    grad = jax.grad(f)
    vs = jnp.stack(
        [jnp.zeros_like(g).at[sl].set(g[sl] / s[n]) for n, (sl, _) in blocks.items()]
    )
    gr = grad(g)
    hv = jax.vmap(lambda v: jax.jvp(grad, (g,), (v,))[1])(vs)
    new = dict(s)
    for i, (n, k) in enumerate(zip(blocks, jax.random.split(key, len(blocks)))):
        curv = -(vs[i] @ hv[i])
        prec = curv + 1.0 / prior_sd[n] ** 2
        mean = (gr @ vs[i] + curv * s[n]) / prec
        sd = jax.lax.rsqrt(prec)
        draw = mean + sd * jax.random.truncated_normal(k, -mean / sd, jnp.inf)
        g = g + (draw - s[n]) * vs[i]
        gr = gr + (draw - s[n]) * hv[i]
        new[n] = draw
    return g, new


def unpack(d, x, g0, wt):
    """Global coefficients and scales from a NUTS position (whitened
    coefficients, then log scales in `d.scale_names` order)."""
    p = d.n_global
    g = g0 + wt @ x[:p]
    s = {n: jnp.exp(x[p + i]) for i, n in enumerate(d.scale_names)}
    return g, s


def site_state(d, st):
    """The Gibbs state `gibbs.site_values` reads, from a marginal NUTS state."""
    g, s = unpack(d, st["hmc"].z, st["g0"], st["wt"])
    return {
        **s,
        "theta": g,
        "local": st["local"],
        "unit": st["unit"],
        "nu": st["nu"],
        "unit_nu": jnp.asarray(d.unit_nu_fixed if d.unit_t else 0.0),
        "drift": jnp.zeros(d.n_units),
    }


def run(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    settings: Settings,
    log=print,
):
    if not jax.config.jax_enable_x64:
        raise RuntimeError("marginal NUTS needs float64 (jax_enable_x64)")
    t0 = time.perf_counter()
    d = gibbs.build_design(prep, config, dense=False)
    check_design(d)
    arrays, rebuild = gibbs.design_arrays(d)
    names = list(d.scale_names)
    p, n, J = d.n_global, d.y.shape[0], d.n_units
    chains = settings.chains

    def potential_gen(values, lam, kappa, g0, wt):
        dd = rebuild(values)

        def potential(x):
            log_s = {k: x[p + i] for i, k in enumerate(names)}
            return -marginal.log_target(dd, g0 + wt @ x[:p], log_s, lam, kappa)

        return potential

    init_kernel, sample_kernel = hmc(potential_fn_gen=potential_gen, algo="NUTS")

    def step(key, st, values):
        dd = rebuild(values)
        k_nuts, k_b, k_s = jax.random.split(key, 3)
        args = (values, st["lam"], st["kappa"], st["g0"], st["wt"])
        hs = sample_kernel(st["hmc"], model_args=args)
        g, s = unpack(dd, hs.z, st["g0"], st["wt"])
        if settings.block_scales and dd.global_blocks:
            s_m = s
            g, s = block_scales(
                k_b,
                lambda gg: marginal.log_marginal(dd, gg, s_m, st["lam"], st["kappa"]),
                g,
                s,
                dd.global_blocks,
                dd.prior_sd,
            )

        def sweep(carry, k):
            s, lam, kappa, nu, _, _, acc = carry
            k_l, k_u, k_f, k_nu, k_lam, k_kap, k_w = jax.random.split(k, 7)
            theta_l, u = marginal.draw_locals(
                dd,
                g,
                s,
                lam,
                kappa,
                jax.random.normal(k_l, (dd.n_buildings, dd.n_local)),
                jax.random.normal(k_u, (J,)),
                jax.random.normal(k_f, (dd.n_buildings, dd.n_fill)),
            )
            local = gibbs.local_value(theta_l, dd.building, dd.slots, dd.slot_values)
            e = dd.y - gibbs.global_value(dd, g) - local - u[dd.unit]
            sig = gibbs.sigma_rows(dd, s)
            if dd.nu_fixed is None:
                x_nu, nu_acc = draw_log_nu(k_nu, jnp.log(nu), e, sig, settings.nu_steps)
                nu = jnp.exp(x_nu)
            else:
                nu_acc = jnp.ones(())
            lam = jax.random.gamma(k_lam, (nu + 1) / 2, (n,)) / (
                (nu + (e / sig) ** 2) / 2
            )
            if dd.unit_t:
                nu_u = dd.unit_nu_fixed
                kappa = jax.random.gamma(k_kap, (nu_u + 1) / 2, (J,)) / (
                    (nu_u + (u / s["unit_scale"]) ** 2) / 2
                )
            if settings.interweave:
                s, lam, kappa = interweave(k_w, dd, s, lam, kappa, nu)
            return (s, lam, kappa, nu, theta_l, u, acc + nu_acc), None

        carry = (s, st["lam"], st["kappa"], st["nu"], st["local"], st["unit"])
        (s, lam, kappa, nu, theta_l, u, acc), _ = jax.lax.scan(
            sweep, (*carry, jnp.zeros(())), jax.random.split(k_s, settings.local_sweeps)
        )
        x_g = (
            solve_triangular(st["wt"], g - st["g0"], lower=False)
            if settings.block_scales and dd.global_blocks
            else hs.z[:p]
        )
        z = jnp.concatenate([x_g, jnp.log(jnp.stack([s[k] for k in names]))])
        pe, z_grad = jax.value_and_grad(
            potential_gen(values, lam, kappa, st["g0"], st["wt"])
        )(z)
        hs = hs._replace(z=z, z_grad=z_grad, potential_energy=pe)
        st = {
            **st,
            "hmc": hs,
            "lam": lam,
            "kappa": kappa,
            "nu": nu,
            "local": theta_l,
            "unit": u,
        }
        info = {
            "accept_prob": hs.accept_prob,
            "num_steps": hs.num_steps.astype(jnp.float64),
            "diverging": hs.diverging.astype(jnp.float64),
            "step_size": hs.adapt_state.step_size,
            "nu_accept": acc / settings.local_sweeps,
        }
        return st, info

    def vmapped(fn):
        return lambda *a: collect_module.batched(fn, chains, settings.chain_batch)(*a)

    def pilot(values, g, s, lam, kappa):
        dd = rebuild(values)
        return vmapped(lambda g_, s_, l_, k_: whitening(dd, g_, s_, l_, k_))(
            g, s, lam, kappa
        )

    def start(values, x, lam, kappa, g0, wt, keys, n_warm, step_size, inv_mass):
        """NUTS states for all chains, adapting over `n_warm` transitions. Each
        call jits afresh: `init_kernel` sets the warmup length that
        `sample_kernel` reads while it traces."""

        def one(x_, l_, k_, g0_, wt_, key_, m_, values, step_size):
            return init_kernel(
                x_,
                n_warm,
                step_size=step_size,
                inverse_mass_matrix=m_,
                target_accept_prob=settings.target_accept,
                max_tree_depth=settings.max_tree_depth,
                model_args=(values, l_, k_, g0_, wt_),
                rng_key=key_,
            )

        return jax.jit(lambda *a: jax.vmap(one, in_axes=(0,) * 7 + (None, None))(*a))(
            x, lam, kappa, g0, wt, keys, inv_mass, values, step_size
        )

    def warm(values, states, keys, length):
        def one(st, key):
            return jax.lax.scan(
                lambda c, k: step(k, c, values), st, jax.random.split(key, length)
            )

        return vmapped(one)(states, keys)

    key = jax.random.PRNGKey(settings.seed)
    k_init, k_h1, k_w1, k_h2, k_w2, k_draw = jax.random.split(key, 6)
    init = gibbs.init_states(d, k_init, chains)
    s0 = {k: init[k] for k in names}
    lam0, kappa0 = jnp.ones((chains, n)), jnp.ones((chains, J))
    g0, wt, _ = jax.jit(pilot)(arrays, jnp.zeros((chains, p)), s0, lam0, kappa0)
    x0 = jnp.concatenate(
        [jnp.zeros((chains, p)), jnp.log(jnp.stack([s0[k] for k in names], 1))], 1
    )
    setup_seconds = time.perf_counter() - t0
    log(f"setup {setup_seconds:.1f}s P={p} scales={len(names)} rows={n}")

    t0 = time.perf_counter()
    n1, n2 = settings.pilot, settings.warmup - settings.pilot
    ones = jnp.ones((chains, p + len(names)))
    hs = start(
        arrays,
        x0,
        lam0,
        kappa0,
        g0,
        wt,
        jax.random.split(k_h1, chains),
        n1,
        1.0,
        ones,
    )
    states = {
        "hmc": hs,
        "g0": g0,
        "wt": wt,
        "lam": lam0,
        "kappa": kappa0,
        "nu": init["nu"]
        if d.nu_fixed is not None
        else jnp.clip(init["nu"], 0.6, 150.0),
        "local": jnp.zeros((chains, d.n_buildings, d.n_local)),
        "unit": jnp.zeros((chains, J)),
    }

    def report(phase, info):
        info = {k: np.asarray(v) for k, v in info.items()}
        log(
            f"{phase}: accept {info['accept_prob'][:, -50:].mean():.2f} "
            f"leapfrogs {info['num_steps'][:, -50:].mean():.1f} "
            f"divergent {int(info['diverging'].sum())} "
            f"step {info['step_size'][:, -1].round(4).tolist()} "
            f"nu accept {info['nu_accept'].mean():.2f}"
        )

    states, info = jax.jit(warm, static_argnums=3)(
        arrays, states, jax.random.split(k_w1, chains), n1
    )
    report("warmup 1", info)

    # Whiten again at the current state, keeping each chain's coefficients.
    hs = states["hmc"]
    g_now = jax.vmap(lambda x, a, b: a + b @ x[:p])(hs.z, states["g0"], states["wt"])
    s_now = {k: jnp.exp(hs.z[:, p + i]) for i, k in enumerate(names)}
    g0, wt, chol = jax.jit(pilot)(arrays, g_now, s_now, states["lam"], states["kappa"])
    zg = jnp.einsum("cqp,cq->cp", chol, g_now - g0)  # L' (g - g0)
    x1 = jnp.concatenate([zg, hs.z[:, p:]], 1)
    inv_mass = jnp.concatenate(
        [jnp.ones((chains, p)), hs.adapt_state.inverse_mass_matrix[:, p:]], 1
    )
    hs = start(
        arrays,
        x1,
        states["lam"],
        states["kappa"],
        g0,
        wt,
        jax.random.split(k_h2, chains),
        n2,
        float(np.median(np.asarray(hs.adapt_state.step_size))),
        inv_mass,
    )
    states = {**states, "hmc": hs, "g0": g0, "wt": wt}
    states, info = jax.jit(warm, static_argnums=3)(
        arrays, states, jax.random.split(k_w2, chains), n2
    )
    report("warmup 2", info)
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    log(
        f"warmup {warmup_seconds:.1f}s "
        + " ".join(
            f"{k}={float(np.median(np.exp(states['hmc'].z[:, p + i]))):.4f}"
            for i, k in enumerate(names)
        )
        + f" nu={float(np.median(states['nu'])):.3f}"
    )

    t0 = time.perf_counter()
    out = collect_module.collect(
        step,
        lambda st, values: gibbs.site_values(rebuild(values), site_state(d, st)),
        states,
        k_draw,
        prep,
        settings.draws,
        settings.keep_every,
        jnp.float64,
        settings.seed,
        settings.trace_groups,
        vmap=lambda fn: collect_module.batched(fn, chains, settings.chain_batch),
        consts=arrays,
        segments=settings.collect_segments,
    )
    sampling_seconds = time.perf_counter() - t0
    tr = out["trace"]
    log(
        f"sampling {sampling_seconds:.1f}s accept {tr['accept_prob'].mean():.2f} "
        f"leapfrogs {tr['num_steps'].mean():.1f} "
        f"divergent {int(tr['diverging'].sum())} nu accept {tr['nu_accept'].mean():.2f}"
    )
    out["seconds"] = {
        "setup": setup_seconds,
        "warmup": warmup_seconds,
        "sampling": sampling_seconds,
    }
    out["dtype"] = "float64"
    out["sampler"] = "marginal-nuts"
    return out
