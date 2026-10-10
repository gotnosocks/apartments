"""Choose the served model by the board's metrics, without a human in the loop.

Ben, 2026-09-30: "automatically switch the dashboard to the best model according
to the metrics we've discussed. You do not need my approval to change the
dashboard model." The served model is the one `config/main-analysis.json`
selects. The listings site publishes it, and the dashboard's rent map and data
card follow it.

**Eligible fits.** A fit must meet all of these:
- It passes the convergence gate, has named additive contributions and has a
  PSIS-LOO score (`leaderboard.scored`).
- It ran on serving hardware (`SERVING_HARDWARE`: thelio's GPU, or a Modal
  A100 since full fits moved there, Ben 2026-10-06) within the fit window
  (`WINDOW_SECONDS`: Ben, 2026-10-01, "the full fit can take more than 30
  mins", with a 2-hour hard stop; exploratory fits on a subset must run under
  30 minutes, and are never served).
- It used the current data rules: the latest version of every rule family
  (`current_rules`). A fit on rows a later review has shown to be wrong is not
  served. Rules that give the same rows count as the same (Ben, 2026-10-08):
  a fit whose rows hash (`data.rows_sha256`, after its split and rules) equals
  that of the current rules on its dataset and split is eligible, so a new
  rule version that changes no row needs no refit.
- It is not a tuning fit on a subset of buildings (a `data.TUNING_PREFIX`
  rule): those are exploration only (Ben, 2026-10-01).
- It was fit on the current dataset (`data.DATASET`).
- Its feature set is not blocked as semantically invalid (`BLOCKED`): a term
  whose meaning does not hold is not served whatever it scores. Ben removes
  such a design by hand and the block keeps it out of `latestselect` too.

**The choice.** It follows the board's `choose_best` on the eligible fits
(Ben, 2026-10-01: ties go to the more elegant model):
1. Take the top paired PSIS-LOO, and the fits tied with it within two combined
   SE.
2. Among those, take the less descriptive (Ben, 2026-10-10, the Fable research
   review §3): a fit ranks ahead of a tied fit whose descriptive share
   (`variance`: neighbourhood labels + building + building over time + unit)
   is higher by more than the null, see `less_descriptive`. Fits are ordered
   by how many tied fits are clearly less descriptive than them, fewest first.
3. Among those, take the most elegant, by the judge agents' recorded pairwise
   judgements (`elegance`): fits are ordered by how many other tied fits are
   judged more elegant than them, fewest first (a cycle of judgements leaves
   its fits level).
4. Then take the fastest. Fit times within `TIME_TIE` of
   the fastest count as equal, and among them the higher PSIS-LOO wins, so
   run-to-run timing noise cannot decide.

**Against the incumbent,** the currently selected run:
- Fits ranked below an eligible incumbent are not tried.
- An eligible incumbent is kept unless the choice beats it clearly: better
  PSIS-LOO beyond the tie tolerance, or tied and clearly less descriptive, or
  tied, level on descriptive share and judged more elegant, or tied, level,
  judged equally elegant and faster by more than `TIME_TIE`. A tied challenger
  that is level on descriptive share and whose pair with the incumbent has not
  been judged is refused until it is (`elegance.pending` lists such pairs).
- A challenger is refused if its paired held-out score is below the
  incumbent's by more than two SE (the board's independent check), and the
  next eligible fit is tried.
- An ineligible incumbent (for example, superseded data rules) is replaced by
  the best challenger that passes that guard. If none passes, it stays.

`python -m rentfrontier.autoselect` prints the decision. With `--write
<summary bundle>`, it also writes the selection for a switch. The bundle must be
the chosen run's (`python -m rentfrontier.summary <run>`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import math
import re
from pathlib import Path

from rentfrontier import data, elegance, features, leaderboard

TARGET_HARDWARE = "thelio RTX 2060 SUPER"  # the research frontier's hardware
# Fit times compare only on the same hardware: a fit is "faster" than another
# only when both ran on the same class.
SERVING_HARDWARE = (TARGET_HARDWARE, "Modal A100")
WINDOW_SECONDS = (
    2 * 60 * 60
)  # full fits; subset (tuning) fits: 30 minutes, never served
TIME_TIE = 0.10
VARIANCE_ROOT = data.OUTPUT_ROOT / "variance"  # rentfrontier.variance records
EXPLAINED_ROOT = data.OUTPUT_ROOT / "explained"  # rentfrontier.explained records
SELECTION = data.REPO / "config" / "main-analysis.json"
# Feature sets removed from serving by hand as semantically invalid: every
# feature set whose name contains the key is refused, whatever its scores.
BLOCKED = {
    "prevprice": (
        "Ben, 2026-10-07: semantically invalid; the correction from the unit's "
        "previous listing's repricing does not depend on the time since that listing"
    ),
}


def blocked(feature_set) -> str | None:
    """Why a feature set is blocked from serving, or None."""
    for key, why in BLOCKED.items():
        if key in (feature_set or ""):
            return why
    return None


def current_rules(rules=None) -> frozenset:
    """The latest version of each data-rule family ("quarantine-v2" over
    "quarantine-v1")."""
    latest = {}
    for name in rules if rules is not None else data.DATA_RULES:
        if name.startswith(data.TUNING_PREFIX):
            continue  # tuning subsets are never part of the served rules
        m = re.fullmatch(r"(.+)-v(\d+)", name)
        family, version = (m.group(1), int(m.group(2))) if m else (name, 0)
        if family not in latest or version > latest[family][0]:
            latest[family] = (version, name)
    return frozenset(name for _, name in latest.values())


def _record(entry) -> dict:
    return json.loads(
        (Path(entry["splits"]["rows"]["_dir"]) / "result.json").read_text()
    )


def _rules(entry) -> frozenset:
    # Records from before data rules existed have none.
    return frozenset(_record(entry).get("data_rules", ()))


# apply_rules wants unit labels, then unit reviews, then unit splits, last.
_LAST = ("unit-labels-", "unit-reviews-", "unit-splits-")


def _rule_order(rule: str) -> tuple:
    return (next((i + 1 for i, p in enumerate(_LAST) if rule.startswith(p)), 0), rule)


@functools.cache
def _load(dataset: str):
    return data.load(Path(dataset))  # one load per dataset for every rule set


@functools.cache
def _rows_sha256(dataset: str, split: str, rules: tuple) -> str:
    frame, heldout = data.split_and_rules(_load(dataset).copy(), split, rules)
    return data.rows_sha256(frame, heldout)


def rows_sha256(record, rules=None) -> str | None:
    """The hash of a run's rows: as recorded, or rebuilt from its dataset, split
    and recorded rules. With `rules`, the hash of the rows those rules give on
    the run's dataset and split. None when the record names no dataset or split,
    or its rule files have changed."""
    if rules is None and record.get("rows_sha256"):
        return record["rows_sha256"]
    dataset, split = record.get("dataset"), record.get("split")
    if dataset is None or split is None:
        return None
    try:
        used = (
            data.recorded_rules(record)
            if rules is None
            else tuple(sorted(rules, key=_rule_order))
        )
        return _rows_sha256(str(Path(dataset).resolve()), split, used)
    except (SystemExit, ValueError):  # changed rule files, or rules out of order
        return None


def same_rows(record, rules) -> bool:
    """Whether a run's rows are the rows `rules` give (see the module docstring)."""
    mine = rows_sha256(record)
    return mine is not None and mine == rows_sha256(record, rules)


def why_not(e, rules) -> str | None:
    """Why an entry cannot be served, or None if it can."""
    if (e.get("tier") or {}).get("name", "full") != "full":
        return "it is an exploration fit (fewer draws or a subset), never served"
    if not e["passes_checks"]:
        return "it fails the convergence gate"
    if not e["interpretable"]:
        return "it has no named additive contributions"
    if e["hardware"] not in SERVING_HARDWARE or "rows" not in e["splits"]:
        return f"it did not run on the {' or '.join(SERVING_HARDWARE)} row split"
    # Before the score: a fit on another dataset is unscored because of it.
    dataset = _record(e).get("dataset")
    if dataset is not None and Path(dataset).resolve() != Path(data.DATASET).resolve():
        return f"it was fit on {Path(dataset).name}, not the current {Path(data.DATASET).name}"
    if not leaderboard.scored(e):
        return "it has no paired PSIS-LOO score"
    if e["fit_seconds"] > WINDOW_SECONDS:
        return "its fit took longer than the window"
    why = blocked(_record(e).get("feature_set"))
    if why is not None:
        return f"it is blocked as semantically invalid ({why})"
    if _record(e).get("feature_set") in features.READS_EARLIER_RENTS:
        return (
            "it reads earlier rents of the same unit or building, so its PSIS-LOO is not "
            "comparable; it is selected on the latest split"
        )
    tuning = sorted(r for r in _rules(e) if r.startswith(data.TUNING_PREFIX))
    if tuning:
        return f"it is a tuning fit on a subset ({', '.join(tuning)})"
    if _rules(e) != rules and not same_rows(_record(e), rules):
        used = " + ".join(sorted(_rules(e))) or "no data rules"
        return (
            f"it was fit with {used}, not the current {' + '.join(sorted(rules))}, "
            "and its rows differ"
        )
    try:
        data.recorded_rules(_record(e))  # the rule files are the ones it was fit on
    except SystemExit as err:
        return f"its data rules cannot be re-applied: {err}"
    return None


def eligible(entries, rules=None) -> list:
    """Entries that could be served (see the module docstring)."""
    rules = current_rules() if rules is None else rules
    return [e for e in entries if why_not(e, rules) is None]


def _split_tied(candidates, paired):
    """(fits tied with the top PSIS-LOO, the rest)."""
    if not candidates:
        return [], []
    top = max(candidates, key=lambda e: e["psis"]["delta"])
    tied, rest = [], []
    for e in candidates:
        if e is top:
            tied.append(e)
            continue
        d, se, mc = paired(e["psis"]["_dir"], top["psis"]["_dir"])
        (tied if abs(d) <= leaderboard.tie_tolerance(se, mc) else rest).append(e)
    return tied, rest


def tie_pairs(candidates, paired=leaderboard.paired_loo) -> set:
    """Pairs of designs among the fits tied with the top: the judgements the
    choice can need."""
    tied, _ = _split_tied(candidates, paired)
    ids = sorted({elegance.design_id(e) for e in tied})
    return {(a, b) for i, a in enumerate(ids) for b in ids[i + 1 :]}


def _latest(root: Path, prefix: str) -> dict | None:
    """The newest root/<prefix>-<commit>/result.json, or None."""
    paths = [
        d / "result.json"
        for d in (root.iterdir() if root.is_dir() else ())
        if d.name.startswith(f"{prefix}-")
        and "-" not in d.name[len(prefix) + 1 :]
        and (d / "result.json").exists()
    ]
    paths.sort(key=lambda p: p.stat().st_mtime)
    return json.loads(paths[-1].read_text()) if paths else None


def descriptive(e) -> dict | None:
    """The fit's variance record shares, if it has one with a descriptive share."""
    rec = _latest(VARIANCE_ROOT, _run(e))
    shares = (rec or {}).get("shares", {})
    return shares if "descriptive" in shares else None


def descriptive_null(base, other) -> float | None:
    """The descriptive-share drop `other` would show over `base` by chance, from the
    permutation null of the feature families it adds (`explained`, scored on base's
    building levels), or None when there is no such screen.

    Adding a family moves a share of the building levels' variance from
    "building" into "features": about the building share times the explained
    share of the levels. A permuted family explains up to null_95, so its drop is
    building share x null_95, summed over the families the candidate set adds."""
    if base["feature_set"] == other["feature_set"]:
        return None
    rec = _latest(EXPLAINED_ROOT, f"{_run(base)}-{other['feature_set']}")
    shares = descriptive(base)
    if rec is None or shares is None or not rec.get("families"):
        return None
    null = sum(max(f["null_95"], 0.0) for f in rec["families"].values())
    return shares["building"]["mean"] * null


def half_width(shares) -> float:
    d = shares["descriptive"]
    return (d["upper_90"] - d["lower_90"]) / 2


def less_descriptive(a, b) -> int:
    """1 if a's descriptive share is clearly below b's, -1 if clearly above, 0 if
    level or unknown (either fit has no variance record).

    Clearly: the drop exceeds the null. When one fit adds feature families to the
    other's and `explained` has screened them on the other's building levels, the
    null is that screen's permutation null (`descriptive_null`; the review's null
    is a fit with the family permuted across buildings, and the screen stands in
    for it without a fit). A fit's descriptive share also carries posterior
    noise, which a permuted-family fit would show too and the screen leaves
    out, so the drop must also exceed the larger of the two fits' 90% posterior
    half-widths. That half-width alone is the null for model-term tests (same
    feature set) and for families no screen covers."""
    sa, sb = descriptive(a), descriptive(b)
    if sa is None or sb is None:
        return 0
    drop = sb["descriptive"]["mean"] - sa["descriptive"]["mean"]
    lower, higher = (a, b) if drop > 0 else (b, a)
    null = max(half_width(sa), half_width(sb))
    family = descriptive_null(higher, lower)
    if family is not None:
        null = max(null, family)
    return 0 if abs(drop) <= null else (1 if drop > 0 else -1)


def more_descriptive_than(e, others) -> int:
    """How many of `others` are clearly less descriptive than e."""
    return sum(less_descriptive(o, e) == 1 for o in others)


def beaten(e, others) -> int:
    """How many of `others` are judged more elegant than e."""
    me = elegance.design_id(e)
    return sum(elegance.compare(elegance.design_id(o), me) == 1 for o in others)


def ranked(candidates, paired=leaderboard.paired_loo) -> list:
    """Candidates in the order the choice prefers them."""
    tied, rest = _split_tied(candidates, paired)
    if not tied:
        return []
    rank = {id(e): (more_descriptive_than(e, tied), beaten(e, tied)) for e in tied}
    fastest = {}
    for e in tied:
        key = (rank[id(e)], e["hardware"])
        fastest[key] = min(fastest.get(key, math.inf), e["fit_seconds"])

    def order(e):
        quick = e["fit_seconds"] <= fastest[(rank[id(e)], e["hardware"])] * (
            1 + TIME_TIE
        )
        return (rank[id(e)], not quick, -e["psis"]["delta"], e["fit_seconds"])

    tied.sort(key=order)
    rest.sort(key=lambda e: -e["psis"]["delta"])
    return tied + rest


def _run(entry) -> str:
    return entry["splits"]["rows"]["run"]


def decide(
    entries,
    incumbent_run: str | None,
    rules=None,
    paired=leaderboard.paired_loo,
    heldout=leaderboard.paired,
) -> dict:
    """keep or switch, with the reason and the comparisons behind it.

    Challengers are tried in ranked order. Against a scored incumbent, each must
    pass the held-out guard, and must clearly beat an eligible incumbent. The
    first one that does is chosen. An incumbent that cannot be paired (not on
    the board, or unscored) gives no guard, so the top-ranked fit is chosen."""
    rules = current_rules() if rules is None else rules
    candidates = eligible(entries, rules)
    order = ranked(candidates, paired)
    incumbent = next(
        (e for e in entries if "rows" in e["splits"] and _run(e) == incumbent_run), None
    )
    inc_why = (
        "the selected run is not on the board"
        if incumbent is None
        else why_not(incumbent, rules)
    )
    inc_ok = inc_why is None
    comparable = incumbent is not None and leaderboard.scored(incumbent)
    out = {
        "incumbent": incumbent_run,
        "incumbent_eligible": inc_ok,
        "incumbent_why_not": inc_why,
        "rules": sorted(rules),
        "eligible": [
            {
                "run": _run(e),
                "psis_delta": e["psis"]["delta"],
                "fit_seconds": e["fit_seconds"],
            }
            for e in order
        ],
        "checked": [],
        # Tied pairs no judge agent has judged yet (rentfrontier.elegance).
        "pending_judgements": sorted(
            p for p in tie_pairs(candidates, paired) if elegance.compare(*p) is None
        ),
    }
    for e in order:
        if e is incumbent:
            # Fits ranked below an eligible incumbent do not replace it.
            if inc_ok:
                break
            continue
        check = {"run": _run(e)}
        out["checked"].append(check)
        won = "it clearly beats the incumbent"
        if comparable:
            d, se, mc = paired(e["psis"]["_dir"], incumbent["psis"]["_dir"])
            tol = leaderboard.tie_tolerance(se, mc)
            h, hse = heldout(
                Path(e["splits"]["rows"]["_dir"]),
                Path(incumbent["splits"]["rows"]["_dir"]),
            )
            check.update(psis=d, psis_pm=math.hypot(se, mc), heldout=h, heldout_se=hse)
            if h < -2 * hse:
                check["refused"] = "held-out worse than the incumbent by more than 2 SE"
                continue
            tied = abs(d) <= tol
            plain = less_descriptive(e, incumbent) if tied else 0
            check["less_descriptive"] = plain
            if inc_ok and plain == -1:
                check["refused"] = (
                    "tied with the incumbent, and clearly more descriptive"
                )
                continue
            judged = elegance.compare(
                elegance.design_id(e), elegance.design_id(incumbent)
            )
            check["elegance"] = judged
            less_desc = plain == 1
            more_elegant = tied and plain == 0 and judged == 1
            faster = (
                tied
                and plain == 0
                and judged == 0
                and e["hardware"] == incumbent["hardware"]
                and e["fit_seconds"] < incumbent["fit_seconds"] * (1 - TIME_TIE)
            )
            if inc_ok and tied and plain == 0 and judged is None:
                check["refused"] = (
                    "tied with the incumbent, and the pair has no elegance "
                    "judgement yet (rentfrontier.elegance pending)"
                )
                pair = tuple(
                    sorted((elegance.design_id(e), elegance.design_id(incumbent)))
                )
                if pair not in out["pending_judgements"]:
                    out["pending_judgements"].append(pair)
                continue
            if inc_ok and not (d > tol or less_desc or more_elegant or faster):
                check["refused"] = "does not clearly beat the eligible incumbent"
                continue
            won = (
                "its PSIS-LOO is clearly better than the incumbent's"
                if d > tol
                else "it ties the incumbent on PSIS-LOO and its descriptive share is "
                "clearly lower"
                if less_desc
                else "it ties the incumbent on PSIS-LOO and is judged more elegant"
                if more_elegant
                else "it ties the incumbent on PSIS-LOO, is judged as elegant, and is "
                f"more than {TIME_TIE:.0%} faster"
            )
        why = won if inc_ok else f"the incumbent cannot be served: {inc_why}"
        out.update(action="switch", run=_run(e), reason=why)
        return out
    if inc_ok:
        reason = (
            "no eligible fit clearly beats the incumbent and passes the held-out guard"
            if out["checked"]
            else "the incumbent is the only eligible fit"
            if len(order) == 1
            else "the incumbent ranks first"
        )
    else:
        reason = (
            "no eligible challenger passes the held-out guard"
            if out["checked"]
            else "no eligible fit"
        ) + f"; the incumbent stays although {inc_why}"
    out.update(action="keep", run=incumbent_run, reason=reason)
    return out


def single_listing_coverage(summary: Path) -> float | None:
    """Share of fit rows whose unit has no other fit row with the ask inside
    the 95% predictive range (PIT between 0.025 and 0.975, the site's
    calibration measure)."""
    import pandas as pd

    rows = pd.read_parquet(summary / "rows.parquet")
    one = rows[rows.in_fit & rows.unit_fit_rows.eq(1) & rows.pit.notna()]
    if one.empty:
        return None
    return float(one.pit.between(0.025, 0.975, inclusive="neither").mean())


def selection_record(
    run_dir: Path, summary: Path, loo_dir: Path, decision: dict
) -> dict:
    """The `config/main-analysis.json` record that selects `summary`."""
    result = json.loads((run_dir / "result.json").read_text())
    complete = json.loads((summary / "complete.json").read_text())
    if complete.get("run") != result["name"]:
        raise SystemExit(f"{summary} is not a bundle of {result['name']}")
    loo = json.loads((loo_dir / "result.json").read_text())
    d = result["diagnostics"]
    checked = next(c for c in decision["checked"] if c["run"] == result["name"])
    vs = (
        f" Against the previous selection on the rows both keep: PSIS-LOO "
        f"{checked['psis']:+.1f} ± {checked['psis_pm']:.1f}, held-out "
        f"{checked['heldout']:+.1f} ± {checked['heldout_se']:.1f}."
        if "psis" in checked
        else ""
    )
    hardware = leaderboard.hardware_class(result)
    coverage = single_listing_coverage(summary)
    uncertainty = (
        "Conditional posterior uncertainty; source errors, omitted features and "
        "incomplete market coverage remain separate."
        + (
            f" Estimates for a unit's only listing are under-covered "
            f"({coverage * 100:.1f}% in the 95% predictive range)."
            if coverage is not None
            else ""
        )
    )
    return {
        "version": "main-analysis-selection-v2",
        "model_family": "frontier_summary",
        "summary": str(summary),
        "summary_manifest_sha256": data.sha256(summary / "complete.json"),
        "summary_commit": complete["commit"],
        "run": result["name"],
        "run_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "data_rules": list(result["data_rules"]),
        # Relative to the checkout, as earlier selections record it.
        "dataset": re.sub(r"^.*?(data/model/)", r"\1", str(result["dataset"])),
        "source_observations_sha256": result["dataset_observations_sha256"],
        "gate": {
            "passes": d["passes"],
            "max_rhat": d["max_rhat"],
            "min_ess": d["min_ess"],
            "divergences": d.get("divergences"),
            "group_rhat_max": d.get("group_rhat_max"),
        },
        "psis_loo": {
            "elpd_loo": loo["elpd_loo"],
            "elpd_loo_se": loo["elpd_loo_se"],
            "loo_commit": loo["commit"],
        },
        "selected_by": f"rentfrontier.autoselect, {dt.datetime.now(dt.UTC).date().isoformat()} "
        "(Ben, 2026-09-30: switch automatically by the agreed metrics)",
        "selection_reason": f"Chosen by the automatic rule because {decision['reason']}. "
        f"{result['sampler'].capitalize()} {result['model']['name']} + "
        f"{result['feature_set']} with {' + '.join(result['data_rules'])}, "
        f"{result['seconds']['fit_total']:,.0f} s on {hardware}.{vs}",
        "uncertainty": uncertainty,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--selection", type=Path, default=SELECTION)
    parser.add_argument(
        "--write", type=Path, metavar="SUMMARY", help="write the selection for a switch"
    )
    args = parser.parse_args(argv)
    incumbent = json.loads(args.selection.read_text())["run"]
    board = leaderboard.build(keep_dirs=True)
    decision = decide(board["entries"], incumbent)
    print(json.dumps(decision, indent=2, default=str))
    if args.write:
        if decision["action"] != "switch":
            raise SystemExit("the decision is to keep the incumbent; nothing written")
        entry = next(
            e
            for e in board["entries"]
            if "rows" in e["splits"] and _run(e) == decision["run"]
        )
        record = selection_record(
            Path(entry["splits"]["rows"]["_dir"]),
            args.write,
            Path(entry["psis"]["_dir"]),
            decision,
        )
        args.selection.write_text(json.dumps(record, indent=2) + "\n")
        print(f"wrote {args.selection}")


if __name__ == "__main__":
    main()
