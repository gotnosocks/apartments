import numpy as np, pandas as pd

f = pd.read_parquet("/data1/apartments/tmp/suspect/lowrent/screen.parquet")
f["unit"] = f.canonical_unit_url
lr = np.log(f.asking_rent)
f["lr"] = lr


# leave-row-out median of the same unit's other asks (rent used only to evaluate the flags)
def other_med(g):
    v = g.lr.values
    out = np.full(len(v), np.nan)
    if len(v) > 1:
        for i in range(len(v)):
            out[i] = np.median(np.delete(v, i))
    return pd.Series(out, index=g.index)


f["oth"] = f.groupby("unit", group_keys=False).apply(other_med)
f["dev"] = f.lr - f.oth
f["far"] = f.dev.abs() > np.log(2)
for name, m in [
    ("all", np.ones(len(f), bool)),
    ("revised", f.revised),
    ("withdrawn", f.withdrawn),
    ("rented", f.rented),
    ("neither", ~(f.revised | f.withdrawn)),
]:
    g = f[m & f.oth.notna()]
    print(
        f"{name:10s} n={int(m.sum()):6d} with_other={len(g):6d} far(>2x)={g.far.mean():.4f} n_far={int(g.far.sum())} sd_dev={g.dev.std():.3f}"
    )
f.to_parquet("/data1/apartments/tmp/suspect/lowrent/screen2.parquet")
