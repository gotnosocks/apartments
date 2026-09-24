"""Build the research-progress dashboard: a static site over the leaderboard.

    python -m rentfrontier.dashboard [--out /data1/apartments/dashboard]

Reads the same records as `rentfrontier.leaderboard` (frontier runs, PyMC NUTS
screens, the promoted reference, rescores, annotations) plus git history, and
writes a self-contained static site: the page sources in `dashboard/` at the
repo root and one generated `data.json`. Nothing is fitted or scored here
beyond the board's own paired comparisons.

Time. Every board entry gets the time each split's result landed: frontier
runs `started_at` + prepare + fit seconds (the end of sampling; scoring and
writing the record take about another minute); PyMC screens the remote
worker's `finished_at`, else the result file's modification time. For every
moment a result landed, the board's own rules (`leaderboard.choose_best`,
`leaderboard.on_frontier`) are re-applied to the results available by then,
so the dashboard's frontier and best at any date agree with what the board
would have said at that date. An entry counts from its row-split result; its
gate status and fit time use only the splits available at that moment.

Keys. Board ids name a design, feature set, sampler and commit, so reruns of
one commit with other sampler settings (e.g. `-solo` timing runs) share an
id. Each entry gets a unique `key`: its id, plus its row-split run name when
the id is shared. The board's own ids are unchanged.

Publishing. Each build goes to <out>/builds/<stamp>/ and the `site` symlink
is swapped atomically, so a server of <out>/site never sees a partial build.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import functools
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import leaderboard

REPO = Path(__file__).resolve().parents[3]
SITE_SOURCE = REPO / "dashboard"
OUT = Path("/data1/apartments/dashboard")
KEEP_BUILDS = 3

# Short descriptions of each design, from the model-line hand-offs.
DESIGNS = {
    "m0-base": "base: 44 features, month trend, season, building and unit effects, Student-t noise",
    "m1-walk": "+ per-building half-year random walk",
    "m4-walk-bedtime-bedslope": "+ bedroom-group market curves and per-building bedroom slope",
    "m5-quarterly": "+ estimated noise ν (≈2), quarterly bedroom curves",
    "m5-nocurves": "m5 without bedroom curves (ablation)",
    "m5-noslope": "m5 without the per-building bedroom slope (ablation)",
    "m5-nu5": "m5 with ν fixed at 5 (ablation)",
    "m6-slopes": "+ per-building slopes on size and 2/3 baths",
    "m7-tunits": "+ Student-t unit effects",
    "m8-drift": "+ per-unit linear drift",
    "nuts-bslope": "PyMC: + per-building bedroom slope",
    "nuts-nu": "PyMC: + estimated noise ν",
    "nuts-bslope-nu": "PyMC: bedroom slope + estimated ν",
    "nuts-cand2": "PyMC candidate 2 (combined screen design)",
    "nuts-cand3": "PyMC candidate 3: as-of attribute flags, size_missing slope, citywide walk",
    "nuts-uslope": "PyMC: + per-unit slope",
    "nuts-hwalk-noise": "PyMC: walk with a noise-scale variant",
    "nuts-bcov": "PyMC: building covariance variant",
    "nuts-level": "PyMC: level variant",
}


def git(*args, cwd=REPO) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).isoformat(timespec="milliseconds")


def assign_keys(entries):
    """A unique ``_key`` per entry (see the module docstring)."""
    counts = {}
    for e in entries:
        counts[e["id"]] = counts.get(e["id"], 0) + 1
    for e in entries:
        if counts[e["id"]] == 1:
            e["_key"] = e["id"]
        else:
            split = e["splits"].get("rows") or next(iter(e["splits"].values()))
            e["_key"] = f"{e['id']} [{split['run']}]"
    keys = [e["_key"] for e in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("Board entries could not be given unique keys")
    return entries


def parse_pr(subject):
    """(title, number) for a squash-merge subject ending in "(#N)", else None."""
    m = re.fullmatch(r"(.*) \(#(\d+)\)", subject)
    return (m.group(1), int(m.group(2))) if m else None


def completed_at(split: dict) -> dt.datetime:
    folder = Path(split["_dir"])
    result = json.loads((folder / "result.json").read_text())
    if "started_at" in result:
        start = dt.datetime.strptime(result["started_at"], "%Y-%m-%dT%H:%M:%S%z")
        seconds = result["seconds"]
        return start + dt.timedelta(
            seconds=seconds.get("prepare", 0.0) + seconds["fit_total"]
        )
    remote = folder / "remote-run.json"
    if remote.exists():
        finished = (json.loads(remote.read_text()).get("result") or {}).get(
            "finished_at"
        )
        if finished:
            return dt.datetime.fromisoformat(finished)
    return dt.datetime.fromtimestamp((folder / "result.json").stat().st_mtime, dt.UTC)


def as_of(entries, t):
    """Entries as the board would have seen them at time t."""
    out = []
    for e in entries:
        splits = {k: s for k, s in e["splits"].items() if s["_at"] <= t}
        if "rows" not in splits:
            continue
        v = copy.copy(e)
        v["splits"] = splits
        v["passes_checks"] = all(s["passes"] for s in splits.values())
        v["fit_seconds"] = max(s["fit_seconds"] for s in splits.values())
        v["_entry"] = e
        out.append(v)
    return out


def snapshots(entries):
    """Board best and frontier (entry keys) after each result landed."""
    paired = functools.lru_cache(maxsize=None)(leaderboard.paired)
    times = sorted({s["_at"] for e in entries for s in e["splits"].values()})
    snaps = []
    for t in times:
        view = as_of(entries, t)
        best = leaderboard.choose_best(view, paired=paired)
        flags = leaderboard.on_frontier(view)
        snaps.append(
            {
                "at": iso(t),
                "best": best["_key"] if best else None,
                "best_rows_delta": best["splits"]["rows"]["delta"] if best else None,
                "frontier": [v["_key"] for v, on in zip(view, flags) if on],
                "entries": len(view),
            }
        )
    return snaps


def milestones():
    """Merged PRs and app-model selection changes on this checkout's history."""
    out = []
    log = git("log", "--first-parent", "HEAD", "--format=%H%x1f%aI%x1f%s")
    for line in log.splitlines():
        sha, at, subject = line.split("\x1f")
        pr = parse_pr(subject)
        if pr:
            out.append(
                {
                    "kind": "pr",
                    "at": iso(dt.datetime.fromisoformat(at)),
                    "sha": sha[:7],
                    "pr": pr[1],
                    "title": pr[0],
                }
            )
    log = git(
        "log", "HEAD", "--format=%H%x1f%aI%x1f%s", "--", "config/main-analysis.json"
    )
    for line in log.splitlines():
        sha, at, subject = line.split("\x1f")
        try:
            selection = json.loads(git("show", f"{sha}:config/main-analysis.json"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        model = selection.get("experiment") or selection.get("summary") or ""
        out.append(
            {
                "kind": "selection",
                "at": iso(dt.datetime.fromisoformat(at)),
                "sha": sha[:7],
                "title": subject,
                "model": Path(model).name,
                "family": selection.get("model_family"),
            }
        )
    return sorted(out, key=lambda m: m["at"])


def reference_entry():
    p = leaderboard.PROMOTED
    folder = leaderboard.REFERENCES["rows"].parent
    at = dt.datetime.fromtimestamp((folder / "result.json").stat().st_mtime, dt.UTC)
    return {
        "id": p["id"],
        "label": "Promoted PyMC model (reference)",
        "description": p["description"],
        "rows_elpd": p["rows"]["elpd"],
        "units_elpd": p["units"]["elpd"],
        "fit_seconds": p["fit_seconds"],
        "fit_note": p["fit_seconds_note"],
        "hardware": p["hardware"],
        "available_at": iso(at),
    }


def data():
    board = leaderboard.build(keep_dirs=True)
    entries = assign_keys(board["entries"])
    for e in entries:
        for s in e["splits"].values():
            s["_at"] = completed_at(s)
    snaps = snapshots(entries)
    out = []
    for e in entries:
        design = e["model"]["name"]
        settings = e.get("sampler_settings") or {}
        out.append(
            {
                "id": e["id"],
                "key": e["_key"],
                "line": e["line"],
                "design": design,
                "design_text": DESIGNS.get(design, ""),
                "feature_set": e["feature_set"],
                "commit": (e.get("commit") or "")[:7] or None,
                "sampler": e["sampler"],
                "chains": settings.get("chains"),
                "draws": settings.get("draws")
                if isinstance(settings.get("draws"), int)
                else None,
                "hardware": e["hardware"],
                "fit_seconds": e["fit_seconds"],
                "cost_usd": e["cost_usd"],
                "grade": e["grade"],
                "passes_checks": e["passes_checks"],
                "frontier": e["frontier"],
                "current_best": e["current_best"],
                "note": e["note"],
                "annotations": e.get("annotations", []),
                "available_at": iso(e["splits"]["rows"]["_at"])
                if "rows" in e["splits"]
                else None,
                "splits": {
                    k: {
                        "run": s["run"],
                        "delta": s["delta"],
                        "delta_se": s["delta_se"],
                        "elpd": s["elpd"],
                        "max_rhat": s["max_rhat"],
                        "min_ess": s["min_ess"],
                        "group_rhat_max": s.get("group_rhat_max"),
                        "passes": s["passes"],
                        "fit_seconds": s["fit_seconds"],
                        "completed_at": iso(s["_at"]),
                        "rescore": s.get("rescore"),
                    }
                    for k, s in e["splits"].items()
                },
            }
        )
    head = git("rev-parse", "HEAD")
    return {
        "generated_at": iso(dt.datetime.now(dt.UTC)),
        "builder_commit": head[:7],
        "builder_dirty": bool(git("status", "--porcelain")),
        "timezone": "America/New_York",
        "gate": {
            "rhat": leaderboard.GATE_RHAT,
            "ess": leaderboard.GATE_ESS,
            "all_effects_rhat": 1.05,
        },
        "current_best": next((e["_key"] for e in entries if e["current_best"]), None),
        "reference": reference_entry(),
        "entries": out,
        "snapshots": snaps,
        "milestones": milestones(),
        "footer": board.get("footer", []),
    }


def publish(out: Path):
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    builds = out / "builds"
    target = builds / stamp
    shutil.copytree(SITE_SOURCE, target)
    (target / "data.json").write_text(json.dumps(data(), indent=1))
    link = out / "site"
    tmp = out / f".site-{stamp}"
    os.symlink(target, tmp)
    os.replace(tmp, link)
    for old in sorted(builds.iterdir())[:-KEEP_BUILDS]:
        shutil.rmtree(old)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"published {publish(args.out)}")


if __name__ == "__main__":
    main()
