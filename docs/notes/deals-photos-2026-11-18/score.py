"""Image read of the low outliers, part 4: the traits' shares among low ads and controls.

Joins a reader's lines to the draw through the blind labels, takes the first read of each
ad, and prints for each of the 21 traits its count and share among low ads and controls,
the difference in building-clustered standard errors, the agreement of the two reads on the
repeated ads, and whether it passes the bar in the note. The two grades follow. The group
labels are then shuffled between buildings holding the same number of ads, 5,000 times, to
count the flags chance gives. The last tables split the shares by pool and write the low
ads' guesses to `guesses.csv`.

Run: python score.py haiku
"""

import sys

import numpy as np
import pandas as pd
from pilot import CATS, OUT, reads

PLAN = "plan_fewer_beds plan_windowless plan_flex plan_through plan_levels plan_floor".split()
SHUFFLES = 5000


def traits(frame):
    """A 0/1 column for each category and plan trait, missing where the trait has no base.

    The plan traits are missing for an ad with no plan read. `plan_fewer_beds` is also
    missing for a studio record, which has no bedroom for the plan to drop.
    """
    out = pd.DataFrame(index=frame.index)
    for c in CATS:
        out[c] = frame.categories.map(lambda v, c=c: float(c in v))
    plan = frame.plan.astype(bool)
    beds = pd.to_numeric(frame.plan_bedrooms, errors="coerce")
    fewer = (beds < frame.bedrooms).astype(float)
    out["plan_fewer_beds"] = fewer.where(plan & beds.notna() & (frame.bedrooms >= 1))
    out["plan_windowless"] = (
        pd.to_numeric(frame.plan_windowless, errors="coerce").fillna(0) > 0
    ).where(plan)
    out["plan_flex"] = frame.plan_flex.map(lambda v: v is True).where(plan)
    out["plan_through"] = frame.plan_through.map(lambda v: v is True).where(plan)
    out["plan_levels"] = (
        pd.to_numeric(frame.plan_levels, errors="coerce").fillna(1) > 1
    ).where(plan)
    out["plan_floor"] = frame.plan_floor.map(
        lambda v: isinstance(v, str) and v.strip().lower() not in ("", "none", "null")
    ).where(plan)
    return out.astype(float)


def gap(x, low, cluster, n_clusters):
    """The low ads' mean of `x` less the controls', and its building-clustered SE."""
    ok = ~np.isnan(x)
    x, low, cluster = x[ok], low[ok], cluster[ok]
    if low.sum() == 0 or (~low).sum() == 0:
        return np.nan, np.nan
    a, b = x[low].mean(), x[~low].mean()
    pull = np.where(low, (x - a) / low.sum(), -(x - b) / (~low).sum())
    return a - b, np.sqrt((np.bincount(cluster, pull, n_clusters) ** 2).sum())


def flags(values, low, cluster, n_clusters, agree, grades):
    """The number of traits passing the bar plus the number of grades beyond 3 SEs."""
    count = 0
    for k in range(values.shape[1]):
        x = values[:, k]
        d, se = gap(x, low, cluster, n_clusters)
        if not se > 0:
            continue
        if k >= values.shape[1] - grades:
            count += abs(d / se) > 3
            continue
        ok = ~np.isnan(x)
        a, b = x[ok & low].mean(), x[ok & ~low].mean()
        count += (x[ok & low].sum() >= 20) and a >= 1.5 * b and d / se > 3 and agree[k]
    return count


if __name__ == "__main__":
    name = sys.argv[1]
    r = reads(name).reset_index()
    blind = pd.read_parquet(OUT / "blind.parquet")
    draw = pd.read_parquet(OUT / "draw.parquet")
    r = r.merge(blind, on="label", validate="1:1").merge(
        draw, on="listing_id", validate="m:1"
    )
    t = traits(r)
    for g in ("condition", "light"):
        t[g] = pd.to_numeric(r[g], errors="coerce")
    first = ~r.repeat.to_numpy()
    print(
        len(r),
        "reads,",
        first.sum(),
        "ads,",
        (first & (r.group == "low")).sum(),
        "low,",
        (first & (r.group != "low")).sum(),
        "controls,",
        (first & r.plan.astype(bool)).sum(),
        "with a plan",
    )

    # Agreement of the two reads of each repeated ad.
    twice = r[r.listing_id.isin(r.listing_id[r.repeat])]
    pairs = twice.groupby("listing_id").filter(lambda g: len(g) == 2)
    one = t.loc[pairs.index[~pairs.repeat]].set_axis(pairs.listing_id[~pairs.repeat])
    two = t.loc[pairs.index[pairs.repeat]].set_axis(pairs.listing_id[pairs.repeat])
    two = two.loc[one.index]
    alike = {}
    for c in t.columns:
        ok = one[c].notna() & two[c].notna()
        near = (one[c] - two[c]).abs() <= (1 if c in ("condition", "light") else 0)
        alike[c] = near[ok].mean() if ok.sum() else np.nan
    print(len(one), "ads read twice")

    f = r[first].reset_index(drop=True)
    v = t[first].to_numpy()
    low = (f.group == "low").to_numpy()
    cluster, names = pd.factorize(f.building)
    n = len(names)
    print(
        f"{'trait':28s} {'low n':>6s} {'low %':>6s} {'ctl n':>6s} {'ctl %':>6s} "
        f"{'ratio':>6s} {'SEs':>6s} {'agree':>6s}"
    )
    agree = []
    found = 0
    for k, c in enumerate(t.columns):
        x = v[:, k]
        ok = ~np.isnan(x)
        d, se = gap(x, low, cluster, n)
        a, b = x[ok & low].mean(), x[ok & ~low].mean()
        if c in ("condition", "light"):
            flag = abs(d / se) > 3
            print(
                f"{c:28s} mean low {a:.2f} ctl {b:.2f} SEs {d / se:+.1f} "
                f"within 1 on repeats {100 * alike[c]:.0f}% {'FLAG' if flag else ''}"
            )
            agree.append(True)
        else:
            agree.append(bool(alike[c] >= 0.8))
            flag = x[ok & low].sum() >= 20 and a >= 1.5 * b and d / se > 3 and agree[-1]
            print(
                f"{c:28s} {int(x[ok & low].sum()):6d} {100 * a:6.1f} "
                f"{int(x[ok & ~low].sum()):6d} {100 * b:6.1f} {a / b if b else np.inf:6.2f} "
                f"{d / se if se > 0 else np.nan:+6.1f} {100 * alike[c]:6.0f} {'FLAG' if flag else ''}"
            )
        found += bool(flag)

    # Chance: buildings holding the same number of ads swap their group labels.
    rng = np.random.default_rng(20261118)
    order = np.argsort(cluster, kind="stable")
    size = np.bincount(cluster)
    start = np.r_[0, np.cumsum(size)[:-1]]
    counts = []
    for _ in range(SHUFFLES):
        shuffled = np.empty_like(low)
        for s in np.unique(size):
            b = np.flatnonzero(size == s)
            src = rng.permutation(b)
            for j in range(s):
                shuffled[order[start[b] + j]] = low[order[start[src] + j]]
        counts.append(flags(v, shuffled, cluster, n, agree, 2))
    print(
        f"flags found {found}; by chance mean {np.mean(counts):.2f}, "
        f"share of shuffles with {found} or more {np.mean(np.array(counts) >= found):.4f}"
    )

    print("shares by pool, low ads (controls in brackets where the pool has them)")
    for pool, g in f.groupby("pool"):
        m = (f.pool == pool).to_numpy()
        print(f"  {pool}: {int((m & low).sum())} low, {int((m & ~low).sum())} controls")
        for k, c in enumerate(t.columns):
            x = v[:, k]
            a = np.nanmean(x[m & low]) if (m & low).any() else np.nan
            b = np.nanmean(x[m & ~low]) if (m & ~low).any() else np.nan
            scale = 1 if c in ("condition", "light") else 100
            print(f"    {c:28s} {scale * a:6.2f} ({scale * b:6.2f})")

    f.loc[low, ["label", "listing_id", "pool", "bedrooms", "guess", "note"]].to_csv(
        OUT / f"guesses-{name}.csv", index=False
    )
    none = f.guess.fillna("none").str.strip().str.lower().eq("none")
    print(
        f"reader gave a reason for {100 * (~none[low]).mean():.1f}% of low ads "
        f"and {100 * (~none[~low]).mean():.1f}% of controls"
    )
