import sys, numpy as np

R = "/data1/apartments/frontier/runs/"
runs = {
    "asof2 real": "building-zones-floor-asof2-b0-latest-d5de95e7-dense-w1000",
    "fit 6 sim": "building-zones-floor-asof2-b0-latest-0e260c3a-sim-realistic-w1000",
    "fit 7 sim": "building-zones-floor-asof2-b0-latest-0e260c3a-sim-mundlak-w1000",
    "fit 8 real": "building-zones-floor-asof3-cap64-b0-latest-26504752-cap64-w1000",
    "fit 4 real": "building-zones-floor-asof3-unitmean-b0-latest-96a9156e-unitmean-jointamp-w1000",
}


def acf(x, L):
    x = x - x.mean()
    v = (x * x).mean()
    return np.array([(x[: len(x) - l] * x[l:]).mean() / v for l in range(L)])


def iat(x):
    a = np.mean([acf(c, 200) for c in x], 0)
    s = 1.0
    for l in range(1, 200, 2):  # Geyer initial positive pairs
        p = a[l] + (a[l + 1] if l + 1 < 200 else 0)
        if p < 0:
            break
        s += 2 * p
    return s, a


for lab, r in runs.items():
    z = np.load(R + r + "/posterior.npz")
    tr = {k[6:]: z[k] for k in z.files if k.startswith("trace/")}
    kp = {k[5:]: z[k] for k in z.files if k.startswith("kept/")}
    for zi, zn in ((0, "manhattan"), (1, "outer")):
        x = tr["amp"][..., zi]
        t, a = iat(x)
        cm = np.median(x, 1)
        print(
            f"{lab} amp[{zn}] chain medians {np.round(cm, 3)} IAT {t:.1f} acf1 {a[1]:.2f} acf5 {a[5]:.2f} acf20 {a[20]:.2f} acf50 {a[50]:.2f}"
        )
    xo = tr["amp"][..., 1].ravel()
    for k in ("bld_sd", "zone_level", "gp_amp", "gp_ls"):
        for j in range(tr[k].shape[-1]):
            print(
                f"   corr amp[outer], trace {k}[{j}]: {np.corrcoef(xo, tr[k][..., j].ravel())[0, 1]:+.2f}"
            )
    for k in ("tau", "nu", "g"):
        print(
            f"   corr amp[outer], trace {k}: {np.corrcoef(xo, tr[k].ravel())[0, 1]:+.2f}"
        )
    ko = kp["amp"][..., 1].ravel()
    for k in ("zone_var_f", "zone_var_b", "zone_sd", "bld_sd"):
        print(
            f"   corr amp[outer], kept {k}[outer]: {np.corrcoef(ko, kp[k][..., 1].ravel())[0, 1]:+.2f}  ratio sd {np.std(kp[k][..., 1]) / np.mean(kp[k][..., 1]):.3f}"
        )
    print(
        f"   amp[outer] marginal CV {xo.std() / xo.mean():.3f}; kept zone_var_f[outer] / amp^2 CV {np.std(kp['zone_var_f'][..., 1].ravel() / ko**2) / np.mean(kp['zone_var_f'][..., 1].ravel() / ko**2):.3f}"
    )
    # chain-level means of correlated quantities
    for k in ("bld_sd", "zone_level"):
        print(f"   chain means {k}[outer]: {np.round(tr[k][..., 1].mean(1), 4)}")
