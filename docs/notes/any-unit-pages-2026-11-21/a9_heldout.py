"""Held-out asks on marked pages against the same buildings' other pages and all ads, by half.

Held-out ads: the latest split's 189,647 (the l2bt run's `pred_scores.npz`; each is the
latest ad of a unit whose earlier ads trained the fit). `gap` is the log ask less the log
of the predicted median, `cover90` whether the ask lies between the 5% and 95% points,
`low` whether it lies below the 5% point. For the overlap mark the held-out ad's own pairs
are left out, so the mark rests on the page's other ads and the held-out ask plays no part
in it. Standard errors resample buildings (400 draws); a difference's SE comes from the
same draws.
"""

import duckdb
import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/any-unit"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"


def stats(d):
    g = d.gap.to_numpy()
    return np.array([g.mean(), g.std(), d.cover90.mean(), d.low.mean()])


def boot(d, groups, n=400, seed=0):
    """Point values and building-resampled SEs of each group's stats and of the marked
    group's differences from the others."""
    rng = np.random.default_rng(seed)
    b = d.building.astype("category")
    codes = b.cat.codes.to_numpy()
    nb = len(b.cat.categories)
    idx = [np.flatnonzero(codes == i) for i in range(nb)]
    masks = {k: d[k].to_numpy() for k in groups}
    arr = {k: d[["gap", "cover90", "low"]].to_numpy()[m] for k, m in masks.items()}
    pos = {k: np.flatnonzero(m) for k, m in masks.items()}
    point = {k: stats(d[masks[k]]) for k in groups}
    # per-building row lists inside each group
    inv = {}
    for k in groups:
        cc = codes[pos[k]]
        order = np.argsort(cc, kind="stable")
        bounds = np.searchsorted(cc[order], np.arange(nb + 1))
        inv[k] = (order, bounds)
    draws = {k: [] for k in groups}
    for _ in range(n):
        w = np.bincount(rng.integers(0, nb, nb), minlength=nb)
        for k in groups:
            order, bounds = inv[k]
            cnt = np.repeat(w, np.diff(bounds))
            x = arr[k][order]
            s = cnt.sum()
            m = (cnt * x[:, 0]).sum() / s
            sd = np.sqrt((cnt * (x[:, 0] - m) ** 2).sum() / s)
            draws[k].append(
                [m, sd, (cnt * x[:, 1]).sum() / s, (cnt * x[:, 2]).sum() / s]
            )
    draws = {k: np.array(v) for k, v in draws.items()}
    return point, draws


if __name__ == "__main__":
    s = np.load(f"{RUN}/pred_scores.npz", allow_pickle=True)
    q = s["q"]
    h = pd.DataFrame(
        {
            "listing_id": s["listing"].astype(str),
            "gap": s["y"] - s["pred"],
            "cover90": (s["y"] >= q[:, 1]) & (s["y"] <= q[:, 6]),
            "low": s["cdf"] < 0.05,
            "day": s["day"].astype(str),
        }
    )
    c = duckdb.connect()
    d = c.sql(f"""
    with ho as (select h.*, a.unit_id, a.building, a.half
                from h join '{OUT}/ads.parquet' a using (listing_id)),
    ov as (
      select p.unit_id, bool_or(p.shared >= 4 and p.ask_gap > 0.10) m_overlap
      from '{OUT}/pairs.parquet' p join ho on ho.unit_id = p.unit_id
      where p.l1 <> ho.listing_id and p.l2 <> ho.listing_id group by 1
    )
    select ho.*, coalesce(m.m_text, false) m_text, coalesce(ov.m_overlap, false) m_overlap
    from ho left join '{OUT}/marks.parquet' m using (unit_id) left join ov using (unit_id)
    """).df()
    d["m_any"] = d.m_text | d.m_overlap
    d.to_parquet(f"{OUT}/heldout.parquet")
    print(
        "held-out ads",
        len(d),
        "on text pages",
        int(d.m_text.sum()),
        "overlap pages",
        int(d.m_overlap.sum()),
        "either",
        int(d.m_any.sum()),
    )
    pd.set_option("display.width", 200)
    rows = []
    for mark in ("m_text", "m_overlap", "m_any"):
        for half in ("A", "B", "all"):
            x = d if half == "all" else d[d.half == half]
            mb = set(x.building[x[mark]])
            x = x.assign(
                marked=x[mark],
                same_bldg=~x[mark] & x.building.isin(mb),
                everyone=True,
            )
            groups = ["marked", "same_bldg", "everyone"]
            point, dr = boot(x, groups, seed=1)
            for k in groups:
                p, se = point[k], dr[k].std(axis=0)
                r = dict(
                    mark=mark[2:],
                    half=half,
                    group=k,
                    ads=int(x[k].sum()),
                    buildings=int(x.building[x[k]].nunique()),
                )
                for j, nm in enumerate(["gap", "sd", "cover90", "low"]):
                    r[nm] = (
                        f"{p[j]:+.3f} ({se[j]:.3f})"
                        if nm == "gap"
                        else f"{p[j]:.3f} ({se[j]:.3f})"
                    )
                if k != "marked":
                    dd = point["marked"] - p
                    dse = (dr["marked"] - dr[k]).std(axis=0)
                    r["diff sd"] = f"{dd[1]:+.3f} ({dse[1]:.3f})"
                    r["diff cover90"] = f"{dd[2]:+.3f} ({dse[2]:.3f})"
                    r["diff low"] = f"{dd[3]:+.3f} ({dse[3]:.3f})"
                rows.append(r)
    T = pd.DataFrame(rows)
    T.to_csv(__file__.rsplit("/", 1)[0] + "/heldout.csv", index=False)
    print(T.to_string(index=False))
