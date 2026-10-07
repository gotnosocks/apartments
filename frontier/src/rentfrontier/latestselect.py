"""Serve a design whose features read earlier rents, by the latest-split pair.

Ben, 2026-10-05 (leak-free feature evaluation, docs/leak-free-scoring.md): a
feature set in `features.READS_EARLIER_RENTS` reads the same unit's earlier
asks, so its PSIS-LOO is inflated and `autoselect` refuses it. Such a design is
judged instead on the latest-listing split, paired against the served design:

- **The pair.** Two full-tier runs on `--split latest`: the reference has the
  served run's model and feature set; the candidate has the same model and a
  feature set in `READS_EARLIER_RENTS`. Both on the current dataset and data
  rules, both pass the convergence gate, so they hold out the same rows.
- **The decision.** The candidate's paired held-out ELPD on those rows must
  beat the reference by more than two SE (`leaderboard.paired`).
- **Blocked sets.** A feature set in `autoselect.BLOCKED` (semantically
  invalid, removed by hand) is never a candidate or a served fit.
- **The served fit.** A full-tier rows-split run of the candidate design, which
  must meet every autoselect condition except the PSIS-LOO ones (`autoselect.
  why_not` refuses it only for reading earlier rents). Its summary bundle is
  what the site publishes.

`python -m rentfrontier.latestselect --candidate RUN --reference RUN --serve RUN`
prints the decision; `--write <summary bundle>` also writes the selection, whose
reason records the latest-split comparison (PSIS-LOO is recorded but marked as
not comparable).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rentfrontier import autoselect, data, features, leaderboard

RUNS = data.OUTPUT_ROOT / "runs"
LOO = data.OUTPUT_ROOT / "loo"
READS_REASON = "it reads earlier rents of the same unit"


def _result(run: str) -> dict:
    return json.loads((RUNS / run / "result.json").read_text())


def _problems_latest(r: dict, rules) -> list[str]:
    out = []
    if r.get("split") != "latest":
        out.append("not on the latest split")
    if leaderboard.tier_of(r)["name"] != "full":
        out.append("not a full-tier fit")
    if not r["diagnostics"]["passes"]:
        out.append("fails the convergence gate")
    if Path(r["dataset"]).resolve() != Path(data.DATASET).resolve():
        out.append("not on the current dataset")
    if frozenset(r.get("data_rules", ())) != rules:
        out.append("not on the current data rules")
    out += _rules_reapply(r)
    return out


def _rules_reapply(r: dict) -> list[str]:
    """As autoselect.why_not's last check: the run's rule files must still be
    the ones it recorded."""
    try:
        data.recorded_rules(r)
    except SystemExit as err:
        return [f"its data rules cannot be re-applied ({err})"]
    return []


def decide(
    candidate: str,
    reference: str,
    serve: str,
    incumbent: dict,
    rules=None,
    paired=leaderboard.paired,
) -> dict:
    """switch or keep, with the checks behind it."""
    rules = autoselect.current_rules() if rules is None else rules
    c, ref, s = _result(candidate), _result(reference), _result(serve)
    problems = {
        "candidate": _problems_latest(c, rules),
        "reference": _problems_latest(ref, rules),
        "serve": [],
    }
    if c["feature_set"] not in features.READS_EARLIER_RENTS:
        problems["candidate"].append("its feature set does not read earlier rents")
    for role, r in (("candidate", c), ("serve", s)):
        why = autoselect.blocked(r["feature_set"])
        if why is not None:
            problems[role].append(f"blocked as semantically invalid ({why})")
    if c["model"]["name"] != ref["model"]["name"]:
        problems["candidate"].append("a different model from the reference")
    if (ref["model"]["name"], ref["feature_set"]) != (
        incumbent["model"],
        incumbent["feature_set"],
    ):
        problems["reference"].append("not the served design")
    if (s["model"]["name"], s["feature_set"]) != (c["model"]["name"], c["feature_set"]):
        problems["serve"].append("not the candidate's design")
    # autoselect.why_not stops at the earlier-rents refusal, before these.
    if s.get("split") != "rows":
        problems["serve"].append("not on the rows split")
    if Path(s["dataset"]).resolve() != Path(data.DATASET).resolve():
        problems["serve"].append("not on the current dataset")
    if frozenset(s.get("data_rules", ())) != rules:
        problems["serve"].append("not on the current data rules")
    problems["serve"] += _rules_reapply(s)
    board = leaderboard.build(keep_dirs=True)
    entry = next(
        (
            e
            for e in board["entries"]
            if "rows" in e["splits"] and e["splits"]["rows"]["run"] == serve
        ),
        None,
    )
    if entry is None:
        problems["serve"].append("not on the board")
    else:
        why = autoselect.why_not(entry, rules)
        # The block is reported above.
        if why is not None and not why.startswith((READS_REASON, "it is blocked")):
            problems["serve"].append(why)
    out = {
        "candidate": candidate,
        "reference": reference,
        "serve": serve,
        "incumbent": incumbent["run"],
        "problems": problems,
    }
    if any(problems.values()):
        out.update(action="keep", reason="the latest-split pair is not valid")
        return out
    h, hse = paired(RUNS / candidate, RUNS / reference)
    out.update(heldout=h, heldout_se=hse)
    if h <= 2 * hse:
        out.update(
            action="keep",
            reason="the candidate does not beat the served "
            "design by more than two SE on the latest split",
        )
        return out
    out.update(
        action="switch",
        run=serve,
        reason=(
            f"{READS_REASON}, and on the latest-listing split it beats the served "
            f"design by {h:+.1f} ± {hse:.1f} held-out ELPD (more than two SE; "
            f"{c['feature_set']} against {ref['feature_set']}, "
            f"{candidate} against {reference}). Its PSIS-LOO is not comparable"
        ),
        _entry=entry,
    )
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--candidate", required=True, help="latest-split run, reads earlier rents"
    )
    parser.add_argument(
        "--reference", required=True, help="latest-split run, served design"
    )
    parser.add_argument(
        "--serve", required=True, help="rows-split run of the candidate design"
    )
    parser.add_argument("--selection", type=Path, default=autoselect.SELECTION)
    parser.add_argument("--write", type=Path, metavar="SUMMARY")
    args = parser.parse_args(argv)
    incumbent = json.loads(args.selection.read_text())
    decision = decide(args.candidate, args.reference, args.serve, incumbent)
    entry = decision.pop("_entry", None)
    print(json.dumps(decision, indent=2, default=str))
    if args.write:
        if decision["action"] != "switch":
            raise SystemExit("the decision is to keep the incumbent; nothing written")
        record = autoselect.selection_record(
            Path(entry["splits"]["rows"]["_dir"]),
            args.write,
            Path(entry["psis"]["_dir"]),
            {"reason": decision["reason"], "checked": [{"run": args.serve}]},
        )
        record["selected_by"] = (
            record["selected_by"].replace(
                "rentfrontier.autoselect", "rentfrontier.latestselect"
            )
            + "; Ben, 2026-10-05: leak-free comparison for features that read earlier rents"
        )
        record["latest_pair"] = {
            "candidate": args.candidate,
            "reference": args.reference,
            "heldout": decision["heldout"],
            "heldout_se": decision["heldout_se"],
        }
        args.selection.write_text(json.dumps(record, indent=2) + "\n")
        print(f"wrote {args.selection}")


if __name__ == "__main__":
    main()
