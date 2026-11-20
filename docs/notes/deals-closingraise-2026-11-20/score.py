"""Score a closing-raise backtest run against its uncleaned twin on the held-out ads.

    score.py --old RUN --new RUN [--old-dataset DIR] [--new-dataset DIR] [--runs DIR]

Groups and the acceptance rule are those of docs/notes/deals-closingraise-2026-11-20.md.
RUN is a run name under --runs or any unique substring of one ("range-j", "cr-j").

Each run's per-ad scores come from `rentfrontier.drift_score.score_run` (the function
`drift_deals.validate` and the published validation.json use), which reads only the run's
posterior.npz. The datasets give group membership and nothing else:
- changed target: the held-out row's `latest_ask` differs between the two datasets;
- closing-raise unit: an unchanged-target held-out row whose non-null (building, unit_id)
  has a training row (`open == False`) with `latest_ask_how == "latest, before closing
  raise"` in the new (cleaned) dataset. This reads no held-out rent.

A dataset defaults to the one the run's result.json names (`drift_score.dataset_dir`, hash
checked). `--new-dataset` overrides it, for a dry run of the old run against itself.

The new run is also scored at the old target on the changed-target ads, through
`drift_score.score_rows` on those rows with the old run's `pred_y`.

Writes `<old>__<new>.parquet` (one row per held-out ad) and `.json` (the table) beside
this file.
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_score
from rentfrontier.b0closingraise import HOW
from rentfrontier.clusterse import cluster_se

HERE = Path(__file__).resolve().parent
RUNS = Path("/data1/apartments/frontier/runs")
COLS = ["listing_id", "building", "unit_id", "open", "latest_ask", "latest_ask_how"]
Q = list(drift_score.Q)
I05, I10, I90, I95 = (Q.index(v) for v in (0.05, 0.1, 0.9, 0.95))


def find_run(runs: Path, name: str) -> Path:
    if (runs / name / "posterior.npz").exists():
        return runs / name
    hits = [p for p in runs.glob(f"*{name}*") if (p / "posterior.npz").exists()]
    if len(hits) != 1:
        raise SystemExit(f"{name}: {len(hits)} runs with a posterior.npz match")
    return hits[0]


def dataset_of(run_dir: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    d = drift_score.dataset_dir(run_dir)
    if d is None:
        raise SystemExit(
            f"the dataset of {run_dir.name} is not here, or its rows changed"
        )
    return d


def gate(run_dir: Path) -> dict:
    """Worst split R-hat and least bulk ESS as the run's result.json records them."""
    diag = json.loads((run_dir / "result.json").read_text()).get("diagnostics", {})
    found = {}

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, (int, float)) and any(
            s in path.lower() for s in ("rhat", "r_hat", "ess")
        ):
            found[path] = node

    walk(diag)
    rhat = [v for k, v in found.items() if k.lower().endswith("rhat")]
    ess = [v for k, v in found.items() if k.lower().endswith("ess")]
    return {
        "quantities": len(rhat),
        "worst_rhat": max(rhat, default=None),
        "least_ess": min(ess, default=None),
    }


def score_at(run_dir: Path, rows: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The run's log predictive density of held-out rows `rows` at `y`, by
    `drift_score.score_rows` on the arrays `drift_score.score_run` reads."""
    z = np.load(run_dir / "posterior.npz")
    flat = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:])  # noqa: E731
    loc, usd, sig, nu = (
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma"),
        flat("nu"),
    )
    group = z["kept/pred_group"]
    factor = phase = None
    if "kept/pred_phase" in z:
        phase, factor = z["kept/pred_phase"], flat("phase_scale")
    out = []
    for a in range(0, len(rows), drift_score.CHUNK):
        r = rows[a : a + drift_score.CHUNK]
        s = sig[:, group[r]]
        if phase is not None:
            s = s * factor[:, phase[r]]
        part = drift_score.score_rows(loc[:, r], usd[:, r], s, nu, y[a : a + len(r)])
        out.append(part["elpd"])
    return np.concatenate(out) if out else np.zeros(0)


def held(run_dir: Path, dataset: Path):
    frame = pd.read_parquet(dataset / "rows.parquet", columns=COLS)
    h = np.load(run_dir / "posterior.npz")["heldout"]
    if len(h) != len(frame):
        raise SystemExit(f"{run_dir.name}: heldout mask does not fit {dataset}")
    if not frame.open.to_numpy()[h].all() or h.sum() != frame.open.sum():
        raise SystemExit(f"{run_dir.name}: held-out rows are not the open rows")
    return frame, frame[h].reset_index(drop=True)


def per_ad(res: dict, prefix: str) -> dict:
    y, q = res["y"], res["q"]
    return {
        f"y_{prefix}": y,
        f"elpd_{prefix}": res["elpd"],
        f"cdf_{prefix}": res["cdf"],
        f"pred_{prefix}": res["pred"],
        f"q05_{prefix}": q[:, I05],
        f"q10_{prefix}": q[:, I10],
        f"q90_{prefix}": q[:, I90],
        f"q95_{prefix}": q[:, I95],
        f"below05_{prefix}": y < q[:, I05],
        f"in80_{prefix}": (y >= q[:, I10]) & (y <= q[:, I90]),
        f"in90_{prefix}": (y >= q[:, I05]) & (y <= q[:, I95]),
        f"abs_err_{prefix}": np.abs(y - res["pred"]),
    }


def paired(t: pd.DataFrame, a: str, b: str) -> dict:
    """Sum of b - a with its building-clustered and iid SEs."""
    d = (t[b] - t[a]).to_numpy(float)
    se = cluster_se(d, t.building.to_numpy()) if len(d) else float("nan")
    iid = float(d.std(ddof=1) * np.sqrt(len(d))) if len(d) > 1 else float("nan")
    tot = float(d.sum())
    return {"d": tot, "se_building": se, "se_iid": iid, "z": tot / se if se else np.nan}


def block(t: pd.DataFrame) -> dict:
    """One group's figures in both runs, each at its own target."""
    out = {"n": int(len(t)), "buildings": int(t.building.nunique())}
    for p in ("old", "new"):
        out[p] = {
            "elpd": float(t[f"elpd_{p}"].sum()),
            "below05": int(t[f"below05_{p}"].sum()),
            "below05_share": float(t[f"below05_{p}"].mean()),
            "cdf_below_0.05": int((t[f"cdf_{p}"] < 0.05).sum()),
            "cover80": float(t[f"in80_{p}"].mean()),
            "cover90": float(t[f"in90_{p}"].mean()),
            "median_abs_error": float(t[f"abs_err_{p}"].median()),
        }
    out["d_elpd"] = paired(t, "elpd_old", "elpd_new")
    for k in ("below05", "in80", "in90", "abs_err"):
        d = (t[f"{k}_new"].astype(float) - t[f"{k}_old"].astype(float)).to_numpy()
        se = cluster_se(d, t.building.to_numpy()) / len(d) if len(d) else np.nan
        out[f"d_{k}_mean"] = {"d": float(d.mean()), "se_building": float(se)}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--old-dataset")
    p.add_argument("--new-dataset")
    p.add_argument("--runs", default=str(RUNS))
    p.add_argument("--out", default=str(HERE))
    args = p.parse_args(argv)
    t0 = time.time()
    runs = Path(args.runs)
    old_dir, new_dir = find_run(runs, args.old), find_run(runs, args.new)
    old_data = dataset_of(old_dir, args.old_dataset)
    new_data = dataset_of(new_dir, args.new_dataset)
    print(f"old {old_dir.name}\n    {old_data}\nnew {new_dir.name}\n    {new_data}")

    _, ho = held(old_dir, old_data)
    fn, hn = held(new_dir, new_data)
    if not (ho.listing_id.to_numpy() == hn.listing_id.to_numpy()).all():
        raise SystemExit("the two runs' held-out ads differ or are in another order")

    # Groups, from the datasets alone.
    changed = ho.latest_ask.to_numpy() != hn.latest_ask.to_numpy()
    train = fn[~fn.open.to_numpy() & (fn.latest_ask_how == HOW).to_numpy()]
    train = train[train.building.notna() & train.unit_id.notna()]
    keys = set(zip(train.building, train.unit_id))
    keyed = (hn.building.notna() & hn.unit_id.notna()).to_numpy()
    in_unit = np.array(
        [k and (b, u) in keys for k, b, u in zip(keyed, hn.building, hn.unit_id)]
    )
    repriced_buildings = set(
        fn.building[~fn.open.to_numpy() & (fn.latest_ask_how == HOW).to_numpy()]
    )
    in_building = hn.building.isin(repriced_buildings).to_numpy()
    group = np.where(changed, "changed", np.where(in_unit, "cr_unit", "rest"))

    old = drift_score.score_run(old_dir)
    new = old if new_dir == old_dir else drift_score.score_run(new_dir)
    same_run_data = drift_score.dataset_dir(new_dir) == new_data
    for res, h, name, check in (
        (old, ho, "old", True),
        (new, hn, "new", same_run_data),
    ):
        if check and not np.allclose(res["y"], np.log(h.latest_ask.to_numpy(float))):
            raise SystemExit(f"{name}: the run's targets are not its dataset's asks")
    if not same_run_data:
        print("NOTE: --new-dataset is not the new run's own dataset (dry run): the new")
        print("      run's targets are its own, and the datasets only define groups.")

    t = pd.DataFrame(
        {
            "listing_id": ho.listing_id.astype(str),
            "building": ho.building.astype(str),
            "unit_id": ho.unit_id,
            "group": group,
            "changed_target": changed,
            "cr_unit": in_unit & ~changed,
            "repriced_building": in_building,
            "ask_old_dataset": ho.latest_ask.to_numpy(float),
            "ask_new_dataset": hn.latest_ask.to_numpy(float),
            **per_ad(old, "old"),
            **per_ad(new, "new"),
        }
    )
    t["d_elpd"] = t.elpd_new - t.elpd_old
    # The new run at the old target, on the changed-target ads.
    rows = np.flatnonzero(changed)
    t["elpd_new_at_old_y"] = t.elpd_new
    t.loc[rows, "elpd_new_at_old_y"] = score_at(new_dir, rows, old["y"][rows])
    t["abs_err_new_at_old_y"] = np.abs(t.y_old - t.pred_new)
    same = np.flatnonzero(~changed)[: drift_score.CHUNK]
    redo = score_at(new_dir, same, new["y"][same])
    if not np.allclose(redo, new["elpd"][same], atol=1e-9):
        raise SystemExit("score_at does not reproduce score_run")

    unchanged = t[~t.changed_target]
    groups = {
        "all held-out": t,
        "unchanged target": unchanged,
        "closing-raise unit": t[t.group == "cr_unit"],
        "remaining": t[t.group == "rest"],
        "  rest, repriced bldg": t[(t.group == "rest") & t.repriced_building],
        "  rest, other bldg": t[(t.group == "rest") & ~t.repriced_building],
        "changed target (own y)": t[t.group == "changed"],
    }
    out = {k.strip(): block(v) for k, v in groups.items()}
    ch = t[t.group == "changed"]
    out["changed target, new at old y"] = {
        "n": int(len(ch)),
        "d_elpd": paired(ch, "elpd_old", "elpd_new_at_old_y"),
        "median_abs_error_old": float(ch.abs_err_old.median()),
        "median_abs_error_new": float(ch.abs_err_new_at_old_y.median()),
        "median_log_target_change": float((ch.y_new - ch.y_old).median()),
    }
    full = {p: drift_score.summary(r) for p, r in (("old", old), ("new", new))}

    print(
        f"\ntraining rows repriced: {int((~fn.open & (fn.latest_ask_how == HOW)).sum()):,}"
    )
    print("\nd_elpd = new - old, summed; SE clustered by building; z = d / SE")
    head = f"{'group':<24}{'n':>6}{'elpd old':>10}{'elpd new':>10}{'d_elpd':>9}{'SE':>7}{'z':>7}"
    print(head)
    for k in groups:
        b = out[k.strip()]
        d = b["d_elpd"]
        print(
            f"{k:<24}{b['n']:>6,}{b['old']['elpd']:>10.1f}{b['new']['elpd']:>10.1f}"
            f"{d['d']:>+9.1f}{d['se_building']:>7.1f}{d['z']:>+7.2f}"
        )
    x = out["changed target, new at old y"]
    d = x["d_elpd"]
    print(
        f"{'changed, new at old y':<24}{x['n']:>6,}{'':>10}{'':>10}"
        f"{d['d']:>+9.1f}{d['se_building']:>7.1f}{d['z']:>+7.2f}"
    )
    print(
        f"\n{'group':<24}{'<5% old':>14}{'<5% new':>14}{'80% o/n':>14}{'90% o/n':>14}"
        f"{'MAE o/n':>16}"
    )
    for k in groups:
        b = out[k.strip()]
        o, n = b["old"], b["new"]
        print(
            f"{k:<24}"
            f"{o['below05']:>5} {o['below05_share']:>7.2%}"
            f"{n['below05']:>6} {n['below05_share']:>7.2%}"
            f"{o['cover80']:>8.3f}/{n['cover80']:.3f}"
            f"{o['cover90']:>8.3f}/{n['cover90']:.3f}"
            f"{o['median_abs_error']:>9.4f}/{n['median_abs_error']:.4f}"
        )
    print(
        f"changed, at old y: median abs error old {x['median_abs_error_old']:.4f}, new "
        f"{x['median_abs_error_new']:.4f}; median log target change "
        f"{x['median_log_target_change']:+.4f}"
    )
    print("\nfull held-out summary (drift_score.summary), each run at its own target:")
    for k, v in full.items():
        print(f"  {k}: {json.dumps(v)}")
    gates = {"old": gate(old_dir), "new": gate(new_dir)}
    print("\nconvergence figures in result.json (check the gate there):")
    for k, v in gates.items():
        print(f"  {k}: {json.dumps(v)[:400]}")

    u, c, r = out["unchanged target"], out["closing-raise unit"], out["remaining"]
    rule = {
        "(a) d_elpd > 0 on unchanged-target ads": u["d_elpd"]["d"] > 0,
        "(b) d_elpd > 0 on closing-raise-unit ads": c["d_elpd"]["d"] > 0,
        "(c) d_elpd / SE >= -1.0 on remaining ads": r["d_elpd"]["z"] >= -1.0
        or r["d_elpd"]["d"] == 0,
    }
    print(
        "\nacceptance rule (the convergence gate is a fourth condition, not judged here):"
    )
    for k, v in rule.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    if new_dir == old_dir:
        print(
            "  (a run against itself: every difference is 0, so (a) and (b) read FAIL)"
        )

    stem = (
        Path(args.out) / f"{old_dir.name.split('-')[-1]}__{new_dir.name.split('-')[-1]}"
    )
    stem = stem.with_name(
        f"{args.old.replace('/', '_')}__{args.new.replace('/', '_')}"
        if len(args.old) < 40 and len(args.new) < 40
        else stem.name
    )
    t.to_parquet(f"{stem}.parquet", index=False)
    Path(f"{stem}.json").write_text(
        json.dumps(
            {
                "old": old_dir.name,
                "new": new_dir.name,
                "old_dataset": str(old_data),
                "new_dataset": str(new_data),
                "groups": out,
                "full": full,
                "rule": rule,
                "gate": gates,
            },
            indent=2,
            default=float,
        )
    )
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    print(
        f"\nwrote {stem}.parquet and .json; {time.time() - t0:.0f} s, peak RSS {peak:.2f} GB"
    )


if __name__ == "__main__":
    main()
