"""Export a building-zones-floor run's predicted log rent for held-out first-ask rows, per
posterior draw, at two dates: the first ask (the row's price_at) and the last ask (the row's
latest_day in the base dataset).

    python export_first_ask_draws.py RUN DATASET OUTDIR [--rows heldout-first-ask]
        [--draws 200] [--chunk 20000] [--validate 2000]

RUN is a run name under the frontier runs folder, DATASET the dataset that run was fitted on.
For each selected row and each thinned draw d, the script computes the mean the likelihood
centres the row's log rent on, as the Gibbs sweep and simulate.mean write it:

    mu_d = x beta_d + (1 - frac) L_d[week] + frac L_d[week + 1] + F_d[site] + bld_d[site]

1. `b0.linear_predictor` gives x beta + L(t).
2. F_d = Bc w_d, with Bc from `building_zones.wave_matrix` of the training rows' sites: the
   surface the sweep draws, centred on the training rows' share.
3. bld_d is the kept building effect, so F + bld is the building's level eta.

The full design (1.9M rows x 114 columns) does not fit the 3 GB limit, so the script builds
`building_zones_floor.design` on a smaller frame: the selected rows plus the first row of every
building, in the dataset's order. Every building then appears in the same order as in the full
frame, so the sites and the map bases come out the same, and each row's columns read only that
row and the lookup tables. A column left out of the smaller design is zero on all its rows. The
training share comes from the full frame's training rows.

To move a row to another date, the script runs `b0.design` on the chunk's rows with
`latest_day` set to that date and the run's grid start, and takes the walk's week and fraction
and the season harmonics (sin1, cos1, sin2, cos2) from it. No other column reads latest_day.

The rows (`--rows heldout-first-ask`) are the latest split's held-out rows whose
`latest_ask_how` is "first ask" in the first-ask dataset; the split is checked against the
run's saved mask and against heldout_ids.json. OUTDIR gets chunk_NNNN.npz files (listing_id,
audit_id, y, mu_first and mu_last as float32 (draws, rows), the dates and their grid positions)
and manifest.json.

With --validate N the script checks the first N rows two ways:
- `simulate.mean` with `simulate.surface` on the smaller design, at the row's own latest_day,
  for every exported draw, against the exported mean at the same date;
- a second smaller design over another frame (the same rows plus 100k other rows), whose
  columns and sites for those rows must match the first.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import b0, building_zones, building_zones_floor, simulate, splits

RUNS = Path("/data1/apartments/frontier/runs")
BASE_DATASET = Path(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
FIRSTASK_DATASET = Path(str(BASE_DATASET) + "-firstask")
SEASON = ("sin1", "cos1", "sin2", "cos2")
KEYS = ("beta", "L", "gp_w", "bld")


def peak_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def thinned(n: int, draws: int) -> np.ndarray:
    """`draws` indices spread evenly over the n flattened (chain-major) kept draws."""
    return np.linspace(0, n - 1, draws).round().astype(int)


def load_kept(run_dir: Path, draws: int):
    with np.load(run_dir / "posterior.npz") as z:
        names = [str(n) for n in z["names"]]
        heldout = z["heldout"]
        shape = z["kept/beta"].shape
        idx = thinned(shape[0] * shape[1], draws)
        kept = {}
        for k in KEYS:
            v = z[f"kept/{k}"]
            kept[k] = v.reshape(-1, *v.shape[2:])[idx].astype(float)
    return names, heldout, idx, shape[:2], kept


def small_design(frame, rows, start, extra=None):
    """building_zones_floor.design on `rows` plus every building's first row (plus `extra`),
    in frame order. Returns the design and each frame row's position in it (-1 if absent)."""
    keep = ~frame.building.duplicated().to_numpy()
    keep[rows] = True
    if extra is not None:
        keep[extra] = True
    d = building_zones_floor.design(frame[keep], start)
    pos = np.full(len(frame), -1)
    pos[keep] = np.arange(keep.sum())
    return d, pos


def aligned_x(d, p: np.ndarray, names: list[str]) -> np.ndarray:
    """The design's rows `p` with its columns placed in the run's column order."""
    missing = set(d.names) - set(names)
    if missing:
        raise SystemExit(f"columns outside the run's design: {sorted(missing)}")
    x = np.zeros((len(p), len(names)))
    x[:, [names.index(n) for n in d.names]] = d.x[p]
    return x


def dated(d, x, p, frame_rows: pd.DataFrame, day: pd.Series, weeks: int, names):
    """A b0.Design of the chunk's rows with the season columns, week and frac at `day`."""
    db = b0.design(frame_rows.assign(latest_day=day.to_numpy()), d.start)
    if db.start != d.start:
        raise ValueError("the chunk's grid start differs from the run's")
    if (db.week >= weeks).any():
        raise ValueError("a date falls past the run's weekly grid")
    x = x.copy()
    for n in SEASON:
        x[:, names.index(n)] = db.x[:, db.names.index(n)]
    return b0.Design(
        y=d.y[p],
        x=x,
        group=d.group[p],
        week=db.week,
        frac=db.frac,
        weeks=weeks,
        names=names,
        start=d.start,
        count={},
    )


def mean(dd, kept: dict, Bw: np.ndarray, site: np.ndarray) -> np.ndarray:
    """(draws, rows) mu at the chunk design `dd`, given the chunk's surface values Bw."""
    mu = b0.linear_predictor(dd, kept, 0, len(dd.y))
    mu += Bw
    mu += kept["bld"][:, site]
    return mu


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("dataset", type=Path)
    p.add_argument("outdir", type=Path)
    p.add_argument("--rows", default="heldout-first-ask", choices=["heldout-first-ask"])
    p.add_argument("--draws", type=int, default=200)
    p.add_argument("--chunk", type=int, default=20000)
    p.add_argument("--validate", type=int, default=0)
    p.add_argument("--base-dataset", type=Path, default=BASE_DATASET)
    p.add_argument("--firstask-dataset", type=Path, default=FIRSTASK_DATASET)
    p.add_argument("--limit", type=int, help="export only the first N selected rows")
    a = p.parse_args(argv)
    t0 = time.perf_counter()
    run_dir = RUNS / a.run
    result = json.loads((run_dir / "result.json").read_text())
    if Path(result["dataset"]) != a.dataset:
        raise SystemExit(f"{a.run} was fitted on {result['dataset']}")
    if result["model"]["name"] != building_zones_floor.NAME:
        raise SystemExit(f"{a.run} is a {result['model']['name']} run")

    frame = b0.load_frame(a.dataset)
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("the dataset changed since the run")
    names, heldout, idx, (chains, per_chain), kept = load_kept(run_dir, a.draws)
    held = splits.SPLITS[result["split"]](frame)
    if not np.array_equal(held, heldout):
        raise SystemExit("the rebuilt split differs from the run's")
    weeks = kept["L"].shape[1] - 1
    if weeks != result["sizes"]["weeks"]:
        raise SystemExit("the walk's length differs from the run's grid")

    # Row selection and the two dates, from the first-ask and base datasets.
    fa = pd.read_parquet(
        a.firstask_dataset / "rows.parquet",
        columns=["audit_id", "latest_ask_how", "latest_day"],
    )
    base = pd.read_parquet(
        a.base_dataset / "rows.parquet", columns=["audit_id", "latest_day"]
    )
    for other in (fa, base):
        if not np.array_equal(other.audit_id.to_numpy(), frame.audit_id.to_numpy()):
            raise SystemExit("the datasets' rows differ in order or identity")
    ids = set(json.loads((a.firstask_dataset / "heldout_ids.json").read_text()))
    if not np.array_equal(frame.listing_id.astype(int).isin(ids).to_numpy(), held):
        raise SystemExit("heldout_ids.json differs from the latest split")
    rows = np.flatnonzero(held & (fa.latest_ask_how == "first ask").to_numpy())
    if a.limit:
        rows = rows[: a.limit]
    day_first = pd.Series(pd.to_datetime(frame.price_at, utc=True).dt.date)
    day_last = base.latest_day
    if not (day_first.iloc[rows].to_numpy() == fa.latest_day.iloc[rows].to_numpy()).all():
        raise SystemExit("the first-ask dataset's latest_day is not the price_at date")
    own = day_first if a.dataset == a.firstask_dataset else day_last
    if not (own.iloc[rows].to_numpy() == frame.latest_day.iloc[rows].to_numpy()).all():
        raise SystemExit("the run's own latest_day is neither export date")
    del fa, base

    start = pd.Timestamp(result["grid_start"])
    d, pos = small_design(frame, rows, start)
    if d.start != start:
        raise SystemExit("the rebuilt grid start differs from the run's")
    # Every building's site, from its first row, and the training rows' share of each site.
    first_row = np.flatnonzero(~frame.building.duplicated().to_numpy())
    site_of = pd.Series(d.site[pos[first_row]], index=frame.building.iloc[first_row])
    train_site = frame.building[~held].map(site_of).to_numpy().astype(np.int64)
    B, _ = building_zones.wave_matrix(dataclasses.replace(d, site=train_site))
    t_design = time.perf_counter() - t0
    print(f"design {t_design:.0f}s, {len(d.y)} rows, peak {peak_gb():.2f} GB", flush=True)

    a.outdir.mkdir(parents=True, exist_ok=True)
    timings = []
    for c, lo in enumerate(range(0, len(rows), a.chunk)):
        t1 = time.perf_counter()
        r = rows[lo : lo + a.chunk]
        p_ = pos[r]
        fr = frame.iloc[r]
        site = d.site[p_]
        x = aligned_x(d, p_, names)
        Bw = kept["gp_w"] @ B[site].T
        d1 = dated(d, x, p_, fr, day_first.iloc[r], weeks, names)
        d2 = dated(d, x, p_, fr, day_last.iloc[r], weeks, names)
        np.savez(
            a.outdir / f"chunk_{c:04d}.npz",
            listing_id=frame.listing_id.to_numpy()[r].astype(str),
            audit_id=frame.audit_id.to_numpy()[r].astype(str),
            row=r,
            y=d.y[p_],
            mu_first=mean(d1, kept, Bw, site).astype(np.float32),
            mu_last=mean(d2, kept, Bw, site).astype(np.float32),
            day_first=np.asarray(pd.to_datetime(day_first.iloc[r]), "datetime64[D]"),
            day_last=np.asarray(pd.to_datetime(day_last.iloc[r]), "datetime64[D]"),
            week_first=d1.week + d1.frac,
            week_last=d2.week + d2.frac,
        )
        timings.append(time.perf_counter() - t1)
        print(
            f"chunk {c}: {len(r)} rows {timings[-1]:.1f}s peak {peak_gb():.2f} GB",
            flush=True,
        )

    check = None
    if a.validate:
        r = rows[: a.validate]
        p_ = pos[r]
        # simulate.mean on the smaller design at the row's own latest_day, draw by draw.
        share = np.bincount(train_site, minlength=B.shape[0]).astype(float)
        share /= share.sum()
        basis = [s["basis"] for s in d.surfaces]
        sub = dataclasses.replace(
            d,
            y=d.y[p_],
            x=aligned_x(d, p_, names),
            group=d.group[p_],
            week=d.week[p_],
            frac=d.frac[p_],
            site=d.site[p_],
        )
        dd = dated(d, sub.x, p_, frame.iloc[r], own.iloc[r], weeks, names)
        mu = mean(dd, kept, kept["gp_w"] @ B[sub.site].T, sub.site)
        gap = 0.0
        for j in range(len(idx)):
            F = simulate.surface(basis, share, kept["gp_w"][j])
            ref = simulate.mean(sub, kept["beta"][j], kept["L"][j], F, kept["bld"][j])
            gap = max(gap, float(np.abs(ref - mu[j]).max()))
        # A second smaller design over another frame gives the same rows the same columns.
        rng = np.random.default_rng(0)
        extra = rng.choice(len(frame), 100_000, replace=False)
        d2_, pos2 = small_design(frame, r, start, extra)
        x2 = aligned_x(d2_, pos2[r], names)
        same_x = float(np.abs(x2 - sub.x).max())
        same_site = bool(np.array_equal(d2_.site[pos2[r]], sub.site))
        same_basis = all(
            np.array_equal(s1["basis"], s2["basis"])
            for s1, s2 in zip(d.surfaces, d2_.surfaces)
        )
        check = {
            "rows": len(r),
            "draws": len(idx),
            "date": "first ask" if own is day_first else "base latest_day",
            "max_abs_gap_vs_simulate_mean": gap,
            "second_design_max_abs_x_gap": same_x,
            "second_design_same_sites": same_site,
            "second_design_same_bases": same_basis,
            "residual_mean_at_own_date": float((sub.y - mu.mean(0)).mean()),
        }
        print("validate", check, flush=True)

    manifest = {
        "run": a.run,
        "dataset": str(a.dataset),
        "base_dataset": str(a.base_dataset),
        "firstask_dataset": str(a.firstask_dataset),
        "commit": result["commit"],
        "grid_start": result["grid_start"],
        "weeks": weeks,
        "kept_shape": [chains, per_chain],
        "draw_indices": idx.tolist(),
        "draw_index_note": "into kept draws flattened chain-major (chain * per_chain + i)",
        "rows": int(len(rows)),
        "row_selection": "latest split held out (equal to heldout_ids.json) with "
        "latest_ask_how == 'first ask' in the first-ask dataset",
        "dates": {
            "mu_first": "price_at as a UTC date (the first ask)",
            "mu_last": "latest_day in the base dataset (the last ask)",
            "run_own_date": "mu_first" if own is day_first else "mu_last",
        },
        "y": "log latest_ask of the run's dataset (the response the run was fitted to)",
        "mean": "b0.linear_predictor (x beta + (1-frac) L[week] + frac L[week+1]) + "
        "(Bc w)[site] with Bc = building_zones.wave_matrix on the training rows' sites + "
        "bld[site]; x from building_zones_floor.design on the selected rows plus every "
        "building's first row; season columns, week and frac from b0.design at each date",
        "chunks": len(timings),
        "chunk_rows": a.chunk,
        "seconds": {
            "design": t_design,
            "chunks": sum(timings),
            "total": time.perf_counter() - t0,
        },
        "peak_rss_gb": peak_gb(),
        "validation": check,
    }
    (a.outdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: manifest[k] for k in ("rows", "seconds", "peak_rss_gb")}))


if __name__ == "__main__":
    main()
