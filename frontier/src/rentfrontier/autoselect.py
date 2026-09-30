"""Choose the served model by the board's metrics, without a human in the loop.

Ben, 2026-09-30: "automatically switch the dashboard to the best model according
to the metrics we've discussed. You do not need my approval to change the
dashboard model." The served model is the one `config/main-analysis.json`
selects. The listings site publishes it, and the dashboard's rent map and data
card follow it.

**Eligible fits.** A fit must meet all of these:
- It passes the convergence gate, has named additive contributions and has a
  PSIS-LOO score (`leaderboard.scored`).
- It ran on the target hardware (`TARGET_HARDWARE`) within the fit window
  (`WINDOW_SECONDS`).
- It used the current data rules: the latest version of every rule family
  (`current_rules`). A fit on rows a later review has shown to be wrong is not
  served.

**The choice.** It follows the board's `choose_best` on the eligible fits:
1. Take the top paired PSIS-LOO, and the fits tied with it within two combined
   SE.
2. Among those, take the fastest. Fit times within `TIME_TIE` of the fastest
   count as equal, and among them the higher PSIS-LOO wins, so run-to-run timing
   noise cannot decide.

**Against the incumbent,** the currently selected run:
- An eligible incumbent is kept unless the choice beats it clearly: better
  PSIS-LOO beyond the tie tolerance, or tied and faster by more than
  `TIME_TIE`.
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
import json
import math
import re
from pathlib import Path

from rentfrontier import data, leaderboard

TARGET_HARDWARE = "thelio RTX 2060 SUPER"
WINDOW_SECONDS = 30 * 60
TIME_TIE = 0.10
SELECTION = data.REPO / "config" / "main-analysis.json"
UNCERTAINTY = (
    "Conditional posterior uncertainty; source errors, omitted features and "
    "incomplete market coverage remain separate. Estimates for a unit's only "
    "listing are under-covered (91.6% in the 95% predictive range)."
)


def current_rules(rules=None) -> frozenset:
    """The latest version of each data-rule family ("quarantine-v2" over
    "quarantine-v1")."""
    latest = {}
    for name in rules if rules is not None else data.DATA_RULES:
        family, version = re.fullmatch(r"(.+)-v(\d+)", name).groups()
        if int(version) > latest.get(family, (0, ""))[0]:
            latest[family] = (int(version), name)
    return frozenset(name for _, name in latest.values())


def _rules(entry) -> frozenset:
    run_dir = Path(entry["splits"]["rows"]["_dir"])
    # Records from before data rules existed have none.
    record = json.loads((run_dir / "result.json").read_text())
    return frozenset(record.get("data_rules", ()))


def why_not(e, rules) -> str | None:
    """Why an entry cannot be served, or None if it can."""
    if not e["passes_checks"]:
        return "it fails the convergence gate"
    if not e["interpretable"]:
        return "it has no named additive contributions"
    if not leaderboard.scored(e):
        return "it has no paired PSIS-LOO score"
    if e["hardware"] != TARGET_HARDWARE or "rows" not in e["splits"]:
        return f"it did not run on the {TARGET_HARDWARE} row split"
    if e["fit_seconds"] > WINDOW_SECONDS:
        return "its fit took longer than the window"
    if _rules(e) != rules:
        used = " + ".join(sorted(_rules(e))) or "no data rules"
        return f"it was fit with {used}, not the current {' + '.join(sorted(rules))}"
    return None


def eligible(entries, rules=None) -> list:
    """Entries that could be served (see the module docstring)."""
    rules = current_rules() if rules is None else rules
    return [e for e in entries if why_not(e, rules) is None]


def ranked(candidates, paired=leaderboard.paired_loo) -> list:
    """Candidates in the order the choice prefers them."""
    if not candidates:
        return []
    top = max(candidates, key=lambda e: e["psis"]["delta"])
    tied, rest = [], []
    for e in candidates:
        if e is top:
            tied.append(e)
            continue
        d, se, mc = paired(e["psis"]["_dir"], top["psis"]["_dir"])
        (tied if abs(d) <= leaderboard.tie_tolerance(se, mc) else rest).append(e)
    fastest = min(e["fit_seconds"] for e in tied)

    def order(e):
        quick = e["fit_seconds"] <= fastest * (1 + TIME_TIE)
        return (not quick, -e["psis"]["delta"], e["fit_seconds"])

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
    """keep or switch, with the reason and the comparisons behind it."""
    candidates = eligible(entries, rules)
    order = ranked(candidates, paired)
    incumbent = next(
        (e for e in entries if "rows" in e["splits"] and _run(e) == incumbent_run), None
    )
    rules = current_rules() if rules is None else rules
    inc_ok = incumbent is not None and any(e is incumbent for e in candidates)
    inc_why = (
        "there is no incumbent"
        if incumbent is None
        else why_not(incumbent, rules) or "it is eligible"
    )
    out = {
        "incumbent": incumbent_run,
        "incumbent_eligible": inc_ok,
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
    }
    for e in order:
        if e is incumbent:
            if inc_ok:
                out.update(
                    action="keep", run=incumbent_run, reason="the incumbent ranks first"
                )
                return out
            continue
        check = {"run": _run(e)}
        if incumbent is not None:
            d, se, mc = paired(e["psis"]["_dir"], incumbent["psis"]["_dir"])
            tol = leaderboard.tie_tolerance(se, mc)
            h, hse = heldout(
                Path(e["splits"]["rows"]["_dir"]),
                Path(incumbent["splits"]["rows"]["_dir"]),
            )
            check.update(psis=d, psis_pm=math.hypot(se, mc), heldout=h, heldout_se=hse)
            if h < -2 * hse:
                check["refused"] = "held-out worse than the incumbent by more than 2 SE"
                out["checked"].append(check)
                continue
            if inc_ok:
                clearly_better = d > tol
                faster = abs(d) <= tol and e["fit_seconds"] < incumbent[
                    "fit_seconds"
                ] * (1 - TIME_TIE)
                if not (clearly_better or faster):
                    check["refused"] = "does not clearly beat the eligible incumbent"
                    out["checked"].append(check)
                    out.update(
                        action="keep",
                        run=incumbent_run,
                        reason="no eligible fit clearly beats the incumbent",
                    )
                    return out
        out["checked"].append(check)
        why = (
            f"the incumbent cannot be served: {inc_why}"
            if not inc_ok
            else "it clearly beats the incumbent"
        )
        out.update(action="switch", run=_run(e), reason=why)
        return out
    out.update(
        action="keep",
        run=incumbent_run,
        reason="no eligible challenger passes the held-out guard"
        if out["checked"]
        else "no eligible fit",
    )
    return out


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
        f"Gibbs {result['model']['name']} + {result['feature_set']} with "
        f"{' + '.join(result['data_rules'])}, {result['seconds']['fit_total']:,.0f} s "
        f"on the RTX 2060.{vs}",
        "uncertainty": UNCERTAINTY,
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
