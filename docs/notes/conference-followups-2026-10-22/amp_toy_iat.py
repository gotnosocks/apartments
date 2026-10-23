"""amp IAT on the gibbs test's simulated design, centred step against the joint step."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "tests"))
from test_b0 import frame_of
from test_b0_4 import registry_of
from test_whitened_zones import nj_registry_of
from test_building_zones_gibbs import _simulated
from rentfrontier import building_zones, whitened_zones, building_zones_gibbs as bzg


def iat(x):
    x = x - x.mean()
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac /= ac[0]
    t = 1.0
    for k in range(1, n - 1, 2):
        p = ac[k] + ac[k + 1]
        if p < 0:
            break
        t += 2 * p
    return t


frame, _ = frame_of(n=6000, weeks=40, seed=9)
d = whitened_zones.design(frame, registry=registry_of(), nj_registry=nj_registry_of())
d = whitened_zones.subset(d, np.ones(len(d.y), bool))
pri = building_zones.Priors()
d, truth = _simulated(d, pri)
for joint in (False, True):
    out = bzg.run(
        d,
        pri,
        bzg.Settings(chains=4, warmup=300, draws=2000, keep_every=10, joint_amp=joint),
        log=lambda m: None,
    )
    a = out["trace"]["amp"]
    res = []
    for z in range(a.shape[-1]):
        res.append(
            (
                round(float(np.mean([iat(a[c, :, z]) for c in range(a.shape[0])])), 2),
                round(float(np.median(a[..., z])), 3),
            )
        )
    print(
        "joint" if joint else "centred",
        res,
        "truth",
        truth["amp"],
        "s/sweep",
        round(out["result"]["gibbs"]["seconds_per_sweep"], 4),
        flush=True,
    )
