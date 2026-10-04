"""Build the research data for the rents site's Research section.

    python -m rentfrontier.dashboard [--out /data1/apartments/dashboard]

Reads the same records as `rentfrontier.leaderboard` (frontier runs, PyMC NUTS
screens, the promoted reference, rescores, annotations) plus git history, and
writes one `data.json`, which the site (`apartments.site`, docs/site.md) reads.
Nothing is fitted or scored here beyond the board's own paired comparisons and
autoselect's decision.

Time. Every board entry gets the time each split's result landed: frontier
runs `started_at` + prepare + fit seconds (the end of sampling; scoring and
writing the record take about another minute); PyMC screens the remote
worker's `finished_at`, else the result file's modification time. For every
moment a result landed, the board's own rules (`leaderboard.choose_best`,
`leaderboard.on_frontier`) are re-applied to the results available by then,
so the frontier and best shown for any date agree with what the board
would have said at that date. An entry counts from its row-split result (its
PSIS-LOO score is a function of that fit's saved draws, so it counts from
then too); its gate status uses only the splits available at that moment.

Keys. Board ids name a design, feature set, sampler and commit, so reruns of
one commit with other sampler settings (e.g. `-solo` timing runs) share an
id. Each entry gets a unique `key`: its id, plus its row-split run name when
the id is shared. The board's own ids are unchanged.

Publishing. Each build goes to <out>/builds/<stamp>/ and the `site` symlink
is swapped atomically, so a reader of <out>/site/data.json never sees a
partial build.
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

from . import autoselect, elegance, leaderboard, variance
from . import data as data_module

REPO = Path(__file__).resolve().parents[3]
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
    # The model ladder's simplest designs (model.LADDER; NUTS only).
    "L0-mean": "ladder: intercept only, Student-t noise",
    "L1-drift": "ladder: + one shared linear drift per year",
    "L2-trend": "ladder: shared quarterly market trend (replaces the drift)",
    "L3-season": "ladder: + calendar season",
    "L4-features": "ladder: + the listing features",
    "L5-building": "ladder: + building levels",
    "m0q": "m0 with a quarterly market trend",
    "m1q": "m1 with a quarterly market trend",
    "m6-nocurves": "m6 without bedroom curves",
    "m7-nocurves": "m7 without bedroom curves",
    "m8-nocurves": "m8 without bedroom curves",
}


def _other_cores(load: dict):
    """Cores other processes kept busy where the fit could run."""
    on_fit = load.get("other_cores_on_fit_cpus")
    return on_fit if on_fit is not None else load.get("other_cores")


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


def sizes_of(entry) -> dict | None:
    """The data sizes (rows, features, months, buildings, units) of an entry's
    rows fit, as its run record states them; None when it does not."""
    split = entry["splits"].get("rows") or next(iter(entry["splits"].values()))
    try:
        result = json.loads((Path(split["_dir"]) / "result.json").read_text())
    except (OSError, ValueError, KeyError):
        return None
    sizes = result.get("sizes")
    return sizes if isinstance(sizes, dict) else None


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
        v["fit_seconds"] = splits["rows"]["fit_seconds"]
        v["_entry"] = e
        out.append(v)
    return out


def snapshots(entries):
    """Board best and frontier (entry keys) per hardware class after each
    result landed. The frontier is per hardware: a fit time only competes with
    fit times on the same hardware."""
    paired = functools.lru_cache(maxsize=None)(leaderboard.paired_loo)
    times = sorted({s["_at"] for e in entries for s in e["splits"].values()})
    snaps = []
    for t in times:
        view = as_of(entries, t)
        by_class = {}
        for cls in sorted({v["hardware_class"] for v in view}):
            group = [v for v in view if v["hardware_class"] == cls]
            best = leaderboard.choose_best(group, paired=paired)
            flags = leaderboard.on_frontier(group)
            by_class[cls] = {
                "best": best["_key"] if best else None,
                "best_delta": best["psis"]["delta"] if best else None,
                "frontier": [v["_key"] for v, on in zip(group, flags) if on],
                "entries": len(group),
            }
        snaps.append({"at": iso(t), "entries": len(view), "by_class": by_class})
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


def psis_fields(ps):
    if not ps or ps.get("delta") is None:
        return None
    return {
        "delta": ps["delta"],
        "delta_se": ps["delta_se"],
        "delta_mcse": ps["delta_mcse"],
        "elpd": ps["elpd"],
        "elpd_se": ps["elpd_se"],
        "mcse": ps["mcse"],
        "draws": ps["draws"],
        "k_share": ps["pareto_k"]["share_over_threshold"],
        "k_threshold": ps["pareto_k"]["threshold"],
        "k_over": ps["pareto_k"]["over_threshold"],
        "validation": ps["validation"],
        # PSIS-LOO effective parameters (None for older LOO records).
        "p_loo": ps.get("p_loo"),
    }


def structure(e) -> str:
    """The model an entry fits, whichever sampler fit it: design and features
    (every sampler fits the designs in `model.MODELS`). A design without the
    listing features is keyed `<design>/none` whatever its run's feature-set
    label (NUTS records base-v1; the removed PyMC ladder recorded none)."""
    m = e["model"]
    uses_features = m.get("features", True) and e["feature_set"] != "none"
    return f"{m['name']}/{e['feature_set'] if uses_features else 'none'}"


def serve_check(e, rules) -> str | None:
    """Why an entry cannot be served (`autoselect.why_not`), or None if it
    can; a record that cannot be read gets a note instead of stopping the
    build."""
    try:
        return autoselect.why_not(e, rules)
    except (OSError, ValueError) as error:
        return f"its record cannot be read ({type(error).__name__})"
    except KeyError as error:
        return f"its record lacks a field ({error})"


def selection_decision(entries) -> dict | None:
    """The automatic selection's decision on the current board
    (`autoselect.decide` against the run `config/main-analysis.json` serves):
    keep or switch, why, and every fit it checked. None when there is no
    selection; an error note when the decision cannot be made."""
    try:
        selection = json.loads((REPO / "config" / "main-analysis.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(selection, dict):
        return None
    try:
        return autoselect.decide(entries, selection.get("run"))
    except (OSError, KeyError, ValueError, ArithmeticError) as error:
        # The board must build even if a pairing fails.
        return {"error": f"{type(error).__name__}: {error}"}


def data():
    board = leaderboard.build(keep_dirs=True)
    entries = assign_keys(board["entries"])
    rules = autoselect.current_rules()
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
                "structure": structure(e),
                "design": design,
                "design_text": DESIGNS.get(design, ""),
                # The design's ModelConfig as the run recorded it, and the data
                # sizes, for the site's equation, diagram and design matrix.
                "model": e["model"],
                "sizes": sizes_of(e),
                "feature_set": e["feature_set"],
                "commit": (e.get("commit") or "")[:7] or None,
                "sampler": e["sampler"],
                "chains": settings.get("chains"),
                "draws": settings.get("draws")
                if isinstance(settings.get("draws"), int)
                else None,
                "hardware": e["hardware"],
                "hardware_class": e["hardware_class"],
                "variance": (e.get("variance") or {}).get("intervals"),
                "fit_seconds": e["fit_seconds"],
                # Other work on the fit's own cores (ops/job pins a GPU job to
                # its core complex); runs before that have only the
                # machine-wide count, which is the same for an unpinned fit.
                "other_cores": _other_cores(e.get("contention") or {}),
                "cost_usd": e["cost_usd"],
                "grade": e["grade"],
                "passes_checks": e["passes_checks"],
                "frontier": e["frontier"],
                "current_best": e["current_best"],
                # The judge agents' pairwise elegance judgements of this
                # design (rentfrontier.elegance): [{vs, verdict, reason}].
                "elegance": e.get("elegance", []),
                # exploration (a short fit for the research frontier, never
                # served) or full, with draws, warmup, chains and subset.
                "tier": e.get("tier"),
                "why_not_served": serve_check(e, rules),
                "psis": psis_fields(e.get("psis")),
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
                        "divergences": s.get("divergences"),
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
        "current_best": {
            e["hardware_class"]: e["_key"] for e in entries if e["current_best"]
        },
        "variance_groups": [*variance.GROUPS, "residual"],
        "baseline": leaderboard.BASELINE,
        "baseline_key": next(
            (e["_key"] for e in entries if leaderboard.is_baseline(e)), None
        ),
        "reference": reference_entry(),
        "entries": out,
        "snapshots": snaps,
        "milestones": milestones(),
        "data_quality": data_quality(),
        "autoselect": selection_decision(entries),
        "exploration": exploration_summary(),
        # Every recorded elegance judgement (config/elegance-judgements.jsonl).
        "elegance_judgements": [
            j
            for _, j in sorted(
                elegance.judgements().items(), key=lambda kv: sorted(kv[0])
            )
        ],
        "footer": board.get("footer", []),
    }


# The review's actions (config/reviews/), as the listings site labels them.
QUARANTINE_ACTIONS = {
    "quarantine_nonresidential": "Not a home",
    "quarantine_location_conflict": "Placed elsewhere",
    "quarantine_product_scope": "Not a whole apartment on the open market",
    "quarantine_explicit_short_term_offer": "Short stay only",
    "quarantine_price_basis": "Ask is not the rent",
    "quarantine_attribute_conflict": "Bedrooms contradict the ad",
    "correct_bedrooms": "Bedrooms corrected from the ad",
    "correct_baths": "Baths corrected from the ad",
}


# What each data rule does, in plain words (the rule's docstring otherwise).
DATA_RULE_TEXT = {
    "unit-labels-v1": "One apartment, one id: unit labels StreetEasy writes differently "
    '("4-B" and "4B", "02" and "2") count as the same apartment. No listing is dropped.',
    "unit-labels-v2": "unit-labels-v1, and West Village apartments StreetEasy lists under "
    'two spellings of one label ("PH04" and "PH4"), joined where the apartment\'s own '
    "StreetEasy history lists ads under both. No listing is dropped.",
    "quarantine-v1": "Listings a review found are not an open-market lease of a whole "
    "Chelsea apartment at their address: offices and shops, ads that place the "
    "apartment elsewhere, SRO rooms, income-restricted and short-stay offers, and a "
    "few whose own ad contradicts the ask or the bedroom count.",
    "quarantine-v2": "quarantine-v1 and a second review: ads whose own words place the "
    "apartment at another address or on a street its building does not front, and "
    'bedroom counts the ad flatly contradicts (a "three-bedroom home" recorded as one '
    "bedroom).",
    "bedrooms-ad-v1": "Bedroom counts corrected from the listing's own ad: its first "
    'sentence states another count ("Bright 1 bedroom in Chelsea" recorded as two '
    "bedrooms), every count in the ad agrees, and the ad has no flex, den, office or "
    "conversion words. No listing is dropped.",
    "baths-ad-v1": "Bathroom counts corrected from the listing's own ad where it states "
    'more than the record ("2 bedroom, 2 bathroom" recorded with one bath), states one '
    "count only and does not mention shared baths or powder rooms. No listing is "
    "dropped.",
    "bedrooms-ad-v2": "bedrooms-ad-v1, and stricter: at least half of the apartment's "
    "other listings record the ad's count, and ads that place the apartment in the "
    "other neighbourhood or on another avenue are left alone. No listing is dropped.",
    "baths-ad-v2": "baths-ad-v1, and stricter: at least half of the apartment's other "
    "listings record the ad's count, ads placed elsewhere or whose bedroom count "
    "disagrees with the record are left alone, and no more than one bath beyond the "
    "bedrooms. No listing is dropped.",
    "fields-review-v1": "Bedroom and bath counts a review corrected by reading the "
    'listing\'s own ad ("huge alcove studio" recorded as a one-bedroom, "3br 2 bath" '
    "recorded with one bath). No listing is dropped.",
    "fields-review-v2": "fields-review-v1 and nine more counts a second review read in "
    'the listing\'s own ad ("mint renovated alcove studio" recorded as a one-bedroom). '
    "No listing is dropped.",
    "quarantine-v3": "quarantine-v2 and a third review, the first of West Village: ads "
    "that place the apartment elsewhere (Brooklyn's Grove and Bleecker Streets, Park "
    "Slope, Harlem, the Upper West Side), shops, restaurants and event spaces, a room, "
    "short-stay-only offers, and an ask the ad contradicts.",
}


def exploration_summary() -> dict | None:
    """The research's exploration header for the site (config/exploration.json:
    the goal, the tiers and what calibration has shown), with the dataset and
    the board's baseline; None without the file."""
    try:
        conf = json.loads((REPO / "config" / "exploration.json").read_text())
    except (OSError, ValueError):
        return None
    return {
        "as_of": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "dataset": Path(data_module.DATASET).name,
        "baseline": leaderboard.BASELINE,
        **conf,
    }


def data_quality() -> dict:
    """The data rules, what the row-dropping ones leave out (by action, from
    their files), and which rules the app's selected model uses."""
    try:
        selection = json.loads((REPO / "config" / "main-analysis.json").read_text())
    except (OSError, ValueError):
        selection = {}
    if not isinstance(selection, dict):
        selection = {}
    app_rules = selection.get("data_rules") or []
    if not isinstance(app_rules, list):
        app_rules = []
    rules = []
    for rule, fn in data_module.DATA_RULES.items():
        doc = DATA_RULE_TEXT.get(rule) or " ".join((fn.__doc__ or "").split())
        entry = {"rule": rule, "text": doc, "in_app_model": rule in app_rules}
        # The unit alias table (unit-labels-*) joins units; it has no per-row actions.
        if rule in data_module.RULE_SOURCES and rule.startswith("unit-labels-"):
            path = Path(data_module.RULE_SOURCES[rule])
            entry.update(
                file=str(path.relative_to(REPO))
                if path.is_relative_to(REPO)
                else str(path),
                groups=len(data_module.unit_aliases(path)),
            )
        elif rule in data_module.RULE_SOURCES:
            path = Path(data_module.RULE_SOURCES[rule])
            with open(path) as f:
                rows = [json.loads(line) for line in f if line.strip()]
            counts: dict[str, int] = {}
            for r in rows:
                counts[r["action"]] = counts.get(r["action"], 0) + 1
            # A dropping rule leaves its rows out; a corrections file keeps them.
            dropping = rule in data_module.DROPPING_RULES
            entry.update(
                file=str(path.relative_to(REPO))
                if path.is_relative_to(REPO)
                else str(path),
                **{"rows" if dropping else "corrected": len(rows)},
                buildings=len({r.get("building") for r in rows}),
                actions=[
                    {"action": a, "label": QUARANTINE_ACTIONS.get(a, a), "rows": n}
                    for a, n in sorted(counts.items(), key=lambda kv: -kv[1])
                ],
            )
        rules.append(entry)
    summary = {}
    if isinstance(selection.get("summary"), str):
        try:
            summary = json.loads(
                (Path(selection["summary"]) / "complete.json").read_text()
            )
        except (OSError, ValueError):
            summary = {}
    if not isinstance(summary, dict):
        summary = {}
    return {
        "app_run": selection.get("run"),
        "app_rules": app_rules,
        "app_rows": summary.get("rows"),
        "app_rows_in_fit": summary.get("rows_in_fit"),
        "rules": rules,
    }


def publish(out: Path):
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    builds = out / "builds"
    target = builds / stamp
    target.mkdir(parents=True)
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
