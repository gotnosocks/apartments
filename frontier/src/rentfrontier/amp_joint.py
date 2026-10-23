"""A joint draw of each zone's map amplitude and the map's wave coefficients, given the building
levels, for the blocked Gibbs sweeps of `rentfrontier.building_zones_gibbs` and
`rentfrontier.building_zones_floor_asof2_unit`.

In those sweeps the levels and waves enter the model as

    eta_s ~ Normal(F_s, b_z(s)^2),   F = Bc w,   w_j ~ Normal(0, amp_z(j)^2 sd_j^2),

and the sweep draws amp given w alone (`update_amp`). The data fix F closely, but many waves
of the outer zone are short and barely touched by the data, so their w_j / sd_j follow amp
through their prior and amp can only move as far as one draw of those waves lets it. In the
as-of floor fits amp[outer] has an integrated autocorrelation time of 6 to 7 sweeps, about
twice that of every other traced quantity.

With `Settings.joint_amp` on, the sweep replaces that step with this one, run after the
levels are drawn:

1. I integrate w out of the levels' prior. Writing Lambda = diag(1 / (amp_z(j) sd_j)^2)
   + Bc' diag(1 / b^2) Bc and h = Bc' (eta / b^2), the levels' log density given the
   amplitudes is, up to a constant,
       -sum_z K_z log amp_z - log det(Lambda) / 2 + h' Lambda^-1 h / 2,
   with K_z the number of zone z's waves.
2. Each zone's log amplitude in turn gets a slice update on that density, plus the
   HalfNormal(`priors.amp`) prior and the log scale's Jacobian. The waves are centred on the
   row-weighted mean over every building, so a zone's waves reach other zones' buildings as a
   constant and the zones' densities don't separate; I update them one at a time.
3. I draw w ~ Normal(Lambda^-1 h, Lambda^-1) at the new amplitudes.

Nothing else in the model reads w, so (amp, w) given the levels, the spreads and the rest is a
block of the posterior, and the step leaves the posterior unchanged. The theta block of the
next sweep draws w again with the levels integrated out, so the new w only changes this
sweep's outputs (`gp_w`, the field F and the building deviations).
"""

from __future__ import annotations

import numpy as np

from . import b0


def make_step(
    Bc: np.ndarray, sds: np.ndarray, which: np.ndarray, zone: np.ndarray, prior
):
    """The step for waves `Bc` (buildings x waves) with spectral sds `sds`, each wave's zone
    `which`, each building's zone `zone` and the HalfNormal scale `prior` of the amplitudes.
    The returned function takes (key, eta, bld_sd, amp) for one chain and returns (amp, w)."""
    jax, jnp = b0._jax()
    nz = int(zone.max()) + 1
    # Bc' Bc over each zone's buildings, so that Bc' diag(1 / b^2) Bc = sum_z BtB_z / b_z^2.
    BtB = jnp.asarray(np.stack([Bc[zone == z].T @ Bc[zone == z] for z in range(nz)]))
    Bc_j = jnp.asarray(Bc)
    sds_j = jnp.asarray(sds)
    which_j = jnp.asarray(which)
    zone_j = jnp.asarray(zone)
    cnt = jnp.asarray(np.bincount(which, minlength=nz), dtype=float)

    def system(amp, bsd):
        """Lambda at amplitudes `amp` and spreads `bsd`, with its diagonal scaling."""
        A = jnp.einsum("z,zjk->jk", 1 / bsd**2, BtB) + jnp.diag(
            1 / (amp[which_j] * sds_j) ** 2
        )
        s = 1 / jnp.sqrt(jnp.diag(A))
        return jnp.linalg.cholesky(A * s[:, None] * s[None, :]), s

    def logp_amp(amp, bsd, h):
        """The levels' log density given `amp`, with w integrated out, up to a constant."""
        L, s = system(amp, bsd)
        hs = h * s
        u = jax.scipy.linalg.solve_triangular(L, hs, lower=True)
        logdet = 2 * jnp.sum(jnp.log(jnp.diag(L))) - 2 * jnp.sum(jnp.log(s))
        return -cnt @ jnp.log(amp) - logdet / 2 + u @ u / 2

    def step(key, eta, bsd, amp):
        h = Bc_j.T @ (eta / bsd[zone_j] ** 2)
        keys = jax.random.split(key, nz + 1)
        for z in range(nz):

            def logp(la, z=z, amp=amp):
                a = amp.at[z].set(jnp.exp(la[0]))
                prior_z = -(a[z] ** 2) / (2 * prior**2) + la[0]
                return (logp_amp(a, bsd, h) + prior_z)[None]

            la = b0.slice_vec(keys[z], jnp.log(amp[z])[None], logp, 0.1)[0]
            amp = amp.at[z].set(jnp.exp(la))
        L, s = system(amp, bsd)
        mean = jax.scipy.linalg.cho_solve((L, True), h * s)
        dev = jax.scipy.linalg.solve_triangular(
            L.T, jax.random.normal(keys[nz], h.shape), lower=False
        )
        return amp, (mean + dev) * s

    return step
