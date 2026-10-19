"""B0.1: the B0 baseline sampled with BlackJAX's ChEES-HMC in place of B0's Gibbs sampler.

B0.1 is B0's model with B0's design, priors and scoring (`rentfrontier.b0` has the model in
full). Only the inference differs. I write the model's joint density as a NumPyro model, take
its log density on the unconstrained scale from NumPyro, and hand that to BlackJAX: ChEES
adaptation tunes the step size, trajectory length and a diagonal mass matrix across chains,
and dynamic HMC then draws with a jittered step count that every chain shares. Everything
runs in float64. B0's Gibbs devices go back to the distributions they stand for:

- the residuals are Student-t(nu, mu_i, sigma_g(i)) directly, with no latent weights w_i;
- the slope shocks are Student-t(nu_T, 0, tau) directly, with no latent lambda_w;
- nu_T keeps its Gamma(2, 1) prior cut at nu_T > 1, as a factor on a site bounded below by 1.

HMC moves in the levels m_w = alpha + L_w for w = 1..W rather than in the shocks. Weekly
data pin those levels down, while alpha and the trend share a level only through L_0 = 0, so
in B0's own coordinates alpha and every L_w run along a ridge (their posterior correlation
was -0.999 on the 2026-10-18 fit). I write the trend's prior as the density of its shocks at
the shocks the levels imply. Taking the levels to the slope deviations z = S - g and then to
the shocks eta_w = z_w - rho z_{w-1} is a triangular linear map with unit diagonal, so the
change of coordinates has unit Jacobian, and the model stays B0's.

    python -m rentfrontier.run --model b0.1 --split latest --name NAME [--chains 16 ...]
        [--learning-rate 0.025] [--max-leapfrog-steps 1000]
    python -m rentfrontier.loo NAME

The run saves the same kept draws as B0 (beta, g, L, nu, sigma, h, rho, tau, nu_t, eta), so
`rentfrontier.loo` scores it with `b0.score`.
"""

from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass

import numpy as np

from . import b0

NAME = "b0.1"


@dataclass(frozen=True)
class Settings:
    # ChEES adapts from statistics pooled across chains. A gradient over every training row
    # took 0.050 s for 4 chains and 0.084 s for 16 on thelio's 8 GB GPU, which ran out of
    # memory at 32.
    chains: int = 16
    warmup: int = 1000
    draws: int = 1000
    keep_every: int = 10
    seed: int = 20261019
    learning_rate: float = (
        0.025  # Adam on the log trajectory length, as BlackJAX's example
    )
    initial_step_size: float = 0.001
    target_accept: float = 0.651  # BlackJAX's default for jittered HMC
    max_leapfrog_steps: int = 1000
    # Rounds of draws between progress lines.
    chunks: int = 10

    def to_dict(self):
        return dataclasses.asdict(self)


def model(d: b0.Design, priors: b0.Priors):
    """The B0 model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_beta, s_beta = b0.prior_arrays(priors, d.names)
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x[:, 1:])  # every column but the intercept
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)

    def fn():
        beta = numpyro.sample("beta", dist.Normal(m_beta, s_beta).to_event(1))
        g = numpyro.sample("g", dist.Normal(*priors.g))
        h = numpyro.sample(
            "h", dist.LogNormal(priors.log_h[0], priors.log_h[1])
        )  # half-life in weeks
        tau = numpyro.sample("tau", dist.Exponential(tau_rate))
        nu_t = numpyro.sample(
            "nu_t",
            dist.ImproperUniform(constraints.greater_than(priors.nu_t_min), (), ()),
        )
        numpyro.factor(
            "nu_t_prior", dist.Gamma(priors.nu_t[0], priors.nu_t[1]).log_prob(nu_t)
        )
        nu = numpyro.sample("nu", dist.Gamma(priors.nu[0], priors.nu[1]))
        sigma = numpyro.sample(
            "sigma", dist.HalfNormal(priors.sigma).expand([4]).to_event(1)
        )
        # alpha + L_w at grid points 1..W.
        level = numpyro.sample(
            "level", dist.ImproperUniform(constraints.real, (), (W,))
        )
        alpha = beta[0]
        L = jnp.concatenate([jnp.zeros(1), level - alpha])
        rho = 0.5 ** (1 / h)
        z = jnp.diff(L) - g  # z_0..z_{W-1}
        eta = z[1:] - rho * z[:-1]
        numpyro.factor(
            "trend_prior",
            dist.Normal(0, tau / jnp.sqrt(1 - rho**2)).log_prob(z[0])
            + dist.StudentT(nu_t, 0, tau).log_prob(eta).sum(),
        )
        numpyro.deterministic("L", L)
        numpyro.deterministic("rho", rho)
        numpyro.deterministic("eta", eta)
        full = jnp.concatenate([alpha[None], level])
        mu = x @ beta[1:] + (1 - frac) * full[week] + frac * full[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: b0.Design, priors: b0.Priors, chains: int, seed: int) -> dict:
    """Unconstrained starting points, one per chain, scattered as B0 scatters its own."""
    rng = np.random.default_rng(seed)
    m_beta, _ = b0.prior_arrays(priors, d.names)
    beta = np.tile(m_beta, (chains, 1))
    beta[:, 0] = np.mean(d.y)
    beta += 0.01 * rng.standard_normal(beta.shape)
    nu_t = 4.0 * np.exp(0.2 * rng.standard_normal(chains))
    return {
        "beta": beta,
        "g": np.full(chains, priors.g[0]),
        "h": np.log(52) + 0.3 * rng.standard_normal(chains),
        "tau": np.log(2e-4) + 0.3 * rng.standard_normal(chains),
        "nu_t": np.log(nu_t - priors.nu_t_min),
        "nu": np.log(10) + 0.3 * rng.standard_normal(chains),
        "sigma": np.log(0.3) + 0.2 * rng.standard_normal((chains, 4)),
        "level": np.repeat(beta[:, :1], d.weeks, axis=1),
    }


KEPT = ("beta", "g", "L", "nu", "sigma", "h", "rho", "tau", "nu_t", "eta")


def log_density(d: b0.Design, priors: b0.Priors):
    """The model's log density on the unconstrained scale, a function of a dict of sites, and
    the map from an unconstrained point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(
    d: b0.Design, priors: b0.Priors, settings: Settings, log=print, checkpoint=None
) -> dict:
    """Sample the posterior of design `d` with BlackJAX's ChEES-HMC. Returns what `b0.run`
    returns, plus the sampler's tuning, step counts and divergences. After each round of
    draws, `checkpoint` (if given) gets the same for the draws so far."""
    jax, jnp = b0._jax()
    import blackjax
    import optax
    from blackjax.adaptation.base import get_filter_adapt_info_fn

    t0 = time.perf_counter()
    logdensity, constrain = log_density(d, priors)
    init = {
        k: jnp.asarray(v)
        for k, v in initial_values(d, priors, settings.chains, settings.seed).items()
    }
    key_warm, key_draw = jax.random.split(jax.random.PRNGKey(settings.seed))
    warmup = blackjax.chees_adaptation(
        logdensity,
        settings.chains,
        target_acceptance_rate=settings.target_accept,
        max_leapfrog_steps=settings.max_leapfrog_steps,
        mass_matrix_estimation="diagonal",
        adaptation_info_fn=get_filter_adapt_info_fn(
            info_keys={"is_divergent", "num_integration_steps"}
        ),
    )
    (state, params), warm = warmup.run(
        key_warm,
        init,
        settings.initial_step_size,
        optax.adam(settings.learning_rate),
        settings.warmup,
        # Sizes the Halton sequence behind the step-count jitter, so it runs through warmup
        # and every draw without repeating.
        max_sampling_steps=settings.draws,
    )
    warm_steps = np.asarray(warm.info.num_integration_steps)
    warm_divergent = np.asarray(warm.info.is_divergent)
    warmup_seconds = time.perf_counter() - t0
    step_size = float(params["step_size"])
    leapfrog = int(params["integration_steps_params"][0])
    log(
        f"warmup {warmup_seconds:.0f}s: step size {step_size:.3g}, up to {leapfrog} leapfrog "
        f"steps per draw, {warm_steps.mean():.0f} on average in warmup, "
        f"{int(warm_divergent.sum())} divergences"
    )
    kernel = blackjax.dynamic_hmc(logdensity, **params)
    per = settings.draws // settings.chunks
    assert per * settings.chunks == settings.draws, "draws must be a multiple of chunks"

    @jax.jit
    def chunk(key, state):
        def one(state, key):
            state, info = jax.vmap(kernel.step)(
                jax.random.split(key, settings.chains), state
            )
            kept = jax.vmap(constrain)(state.position)
            return state, (
                {k: kept[k] for k in KEPT},
                info.num_integration_steps,
                info.is_divergent,
                info.acceptance_rate,
            )

        return jax.lax.scan(one, state, jax.random.split(key, per))

    def output(samples, steps, divergent, accept):
        sampling_seconds = time.perf_counter() - t1
        every = {k: np.concatenate([c[k] for c in samples], axis=1) for k in KEPT}
        steps = np.concatenate(steps, axis=1)
        divergent = np.concatenate(divergent, axis=1)
        # Every chain takes the same jittered step count, so a draw's count is one gradient
        # for all chains at once.
        grads = int(warm_steps[:, 0].sum() + steps[0].sum())
        chees = {
            "step_size": step_size,
            "max_leapfrog_steps": leapfrog,
            "warmup_mean_steps": float(warm_steps.mean()),
            "mean_steps": float(steps.mean()),
            "acceptance": float(np.concatenate(accept, axis=1).mean()),
            "divergences": int(divergent.sum()),
            "warmup_divergences": int(warm_divergent.sum()),
            "gradients": grads,
            "seconds_per_gradient": (warmup_seconds + sampling_seconds) / grads,
        }
        keep = slice(settings.keep_every - 1, None, settings.keep_every)
        return {
            "trace": {k: every[k] for k in b0.TRACED},
            "kept": {k: v[:, keep] for k, v in every.items()},
            "seconds": {"warmup": warmup_seconds, "sampling": sampling_seconds},
            "result": {"chees": chees},
        }

    samples, steps, divergent, accept = [], [], [], []
    t1 = time.perf_counter()
    for i, key in enumerate(jax.random.split(key_draw, settings.chunks)):
        state, (s, n, div, acc) = chunk(key, state)
        # Draws come out as (draw, chain, ...); b0 keeps (chain, draw, ...).
        samples.append({k: np.swapaxes(np.asarray(v), 0, 1) for k, v in s.items()})
        steps.append(np.asarray(n).T)
        divergent.append(np.asarray(div).T)
        accept.append(np.asarray(acc).T)
        last = samples[-1]
        log(
            f"draws {(i + 1) * per}/{settings.draws}: {steps[-1].mean():.0f} leapfrog steps "
            f"per draw, acceptance {accept[-1].mean():.2f}, nu {last['nu'][:4, -1].round(2)}, "
            f"h {last['h'][:4, -1].round(1)}, tau {last['tau'][:4, -1]}, "
            f"{time.perf_counter() - t0:.0f}s"
        )
        if i + 1 < settings.chunks and checkpoint is not None:
            checkpoint(output(samples, steps, divergent, accept))
    out = output(samples, steps, divergent, accept)
    chees = out["result"]["chees"]
    log(
        f"sampling {out['seconds']['sampling']:.0f}s, {chees['mean_steps']:.0f} leapfrog "
        f"steps per draw, acceptance {chees['acceptance']:.2f}, "
        f"{chees['divergences']} divergences"
    )
    return out


def main_run(argv) -> None:
    """`rentfrontier.run --model b0.1`: fit B0.1 on the split's training rows and save it."""
    parser = b0.run_parser()
    parser.prog = "rentfrontier.run --model b0.1"
    parser.set_defaults(model=NAME)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--max-leapfrog-steps", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline-blackjax",
    )
