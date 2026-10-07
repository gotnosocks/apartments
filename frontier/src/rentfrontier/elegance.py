"""Which of two designs is more elegant: holistic judgements by judge agents.

Ben, 2026-10-01: the research seeks the Pareto frontier of fit quality
(PSIS-LOO), fit time and elegance, and ties go to the more elegant model. He
chose holistic judgements by agents over a points rubric ("I prefer a
wholistic judgement to the described rubric approach"). Later the same day he
made the axis a modelling-oriented elegance target, not renter understanding:
one coherent generative story whose structure mirrors the data, few mechanisms
used consistently, no overlapping terms, few special cases, natural forms,
economy (`BRIEF`). On 2026-10-07 he added semantic validity: every term must
mean what its story says (`elegance-v2`).

**A design** is a model and a feature set (`design_id`: "model/feature set").
Data rules, samplers and settings do not change what a model says, so they are
not part of it.

**Judgements** are recorded in `JUDGEMENTS`, one line per pair of designs,
added by reviewed PRs:

    {"designs": [a, b], "verdict": a | b | "equal", "reason": ..., "brief": ...,
     "judges": [{"shown": [a, b], "verdict": ..., "reason": ...},
                {"shown": [b, a], "verdict": ..., "reason": ...}],
     "date": ..., "judge": ...}

**The protocol** (`brief`):
- Two judge agents work independently, each shown the pair in the opposite
  order, blind to scores and fit times.
- They read the two designs' definitions in the code.
- If they agree, their verdict stands. If they disagree, the pair is recorded
  as "equal": no clear difference (`combine`).

**Where it is used:**
- `compare` returns +1 (a is more elegant), 0 (equal), -1 (b is) or None (not
  judged).
- The board and `autoselect` break PSIS-LOO ties by it, then by fit time.
- On the frontier, a fit judged more elegant than one that beats it on accuracy
  and time survives. A pair not judged counts as equal.
- `autoselect` does not switch on a tie that an unjudged pair could decide;
  `pending` lists the pairs to judge.

`python -m rentfrontier.elegance pending` prints the pairs the current board
needs. `brief A B` prints a judge's instructions. `record ONE.json TWO.json`
combines two judges' answers (one or a list each) pair by pair and appends
them to `JUDGEMENTS`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
from pathlib import Path

from rentfrontier import data

JUDGEMENTS = data.REPO / "config" / "elegance-judgements.jsonl"
BRIEF_VERSION = "elegance-v2"


def design_id(entry) -> str:
    """ "model/feature set" of a board entry or a run record (an entry without
    them, such as a stand-in, is its own design)."""
    if "model" not in entry or "feature_set" not in entry:
        return str(entry.get("id"))
    return f"{entry['model']['name']}/{entry['feature_set']}"


@functools.lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        j = json.loads(line)
        a, b = j["designs"]
        if a == b or j["verdict"] not in (a, b, "equal"):
            raise ValueError(f"malformed elegance judgement: {line}")
        key = frozenset((a, b))
        if key in out:
            raise ValueError(f"two elegance judgements of {a} and {b}")
        out[key] = j
    return out


def judgements(path: Path = JUDGEMENTS) -> dict:
    """frozenset({a, b}) -> judgement record."""
    path = Path(path)
    return _load(str(path), path.stat().st_mtime if path.exists() else 0.0)


def compare(a: str, b: str, table=None) -> int | None:
    """+1 if design a is judged more elegant than b, -1 if b is, 0 if equal (or
    the same design), None if the pair has not been judged."""
    if a == b:
        return 0
    j = (judgements() if table is None else table).get(frozenset((a, b)))
    if j is None:
        return None
    return 0 if j["verdict"] == "equal" else (1 if j["verdict"] == a else -1)


def for_design(design: str, table=None) -> list:
    """The judged comparisons of one design, for the board and the site."""
    table = judgements() if table is None else table
    out = []
    for key, j in sorted(table.items(), key=lambda kv: sorted(kv[0])):
        if design not in key:
            continue
        (other,) = key - {design}
        verdict = (
            "equal"
            if j["verdict"] == "equal"
            else ("more elegant" if j["verdict"] == design else "less elegant")
        )
        out.append({"vs": other, "verdict": verdict, "reason": j["reason"]})
    return out


def _named(answer: dict) -> str:
    """A judge's reason with "Design 1" and "Design 2" replaced by the names."""
    one, two = answer["shown"]
    return answer["reason"].replace("Design 1", one).replace("Design 2", two)


def combine(first: dict, second: dict) -> dict:
    """One judgement from two judges' answers on the same pair."""
    a, b = sorted(first["shown"])
    if sorted(second["shown"]) != [a, b] or first["shown"] == second["shown"]:
        raise SystemExit(
            "the two judges must judge the same pair, shown in opposite orders"
        )
    agree = first["verdict"] == second["verdict"]
    verdict = first["verdict"] if agree else "equal"
    reason = (
        _named(first)
        if agree
        else "The judges disagreed, so no clear difference: "
        f"{first['verdict']} ({_named(first)}) / {second['verdict']} ({_named(second)})"
    )
    return {
        "designs": [a, b],
        "verdict": verdict,
        "reason": reason,
        "brief": BRIEF_VERSION,
        "judges": [first, second],
        "date": dt.datetime.now(dt.UTC).date().isoformat(),
        "judge": first.get("judge", "judge agent"),
    }


BRIEF = """You are judging which of two rent-model designs is MORE ELEGANT as a statistical model.
This is a holistic judgement, not a points count.

The project models NYC apartment asking rents (log rent per listing). Read the repository you are
given.

Design 1: {first}
Design 2: {second}

A design is two things:
- a model configuration: the MODELS entry with that name in frontier/src/rentfrontier/model.py, its
  comment, and how model.build_model uses its options;
- a feature set: the FEATURE_SETS entry in frontier/src/rentfrontier/features.py, the builders it
  calls (follow the `base=` chain) and their docstrings.

Read what you need. Do NOT look at scores, fit times, run results, the leaderboard or the research
plan's result sections. Judge the designs as models, blind to how well they fit.

Weigh, as a whole, what makes a model elegant to a statistician:
- semantic validity: every term means what the design's story says it means, under the conditions
  it is applied in. A term that reads other information (an earlier observation, a neighbour, a
  later date) must carry how that information relates to this listing; for example, a correction
  from a unit's earlier listing that ignores how long ago that listing was does not hold. A design
  with a term whose meaning does not hold is less elegant than one without it, whatever else it
  has;
- one coherent generative story whose structure mirrors the data (apartments within buildings within
  neighbourhoods, observed over time), not terms bolted on;
- few distinct mechanisms, used consistently (the same pooling idea at every level);
- no overlapping or competing terms; each term separately identifiable;
- few special cases: no one-off flags, hand-tuned cutoffs or patches for particular subsets of rows;
- natural rather than arbitrary forms for the likelihood, priors and scales;
- economy: the fewest structural choices (variance scales, components, hyperparameters) for what the
  model captures.

Implementation details that do not change what the model says are not part of elegance: samplers,
reparameterizations, knot spacing, centring, data cleaning. If neither design is clearly more
elegant, say "equal".

Answer with JSON only:
{{"shown": ["{first}", "{second}"], "verdict": "<one of the two designs, or equal>",
  "reason": "<two to four sentences a reviewer can check>"}}
"""


def brief(first: str, second: str) -> str:
    return BRIEF.format(first=first, second=second)


def pending(entries, rules=None, incumbent_run=None, hardware=None) -> list:
    """Unjudged pairs whose judgement could change what is served or what is
    on the research frontier:
    - among the fits autoselect could serve, pairs tied on PSIS-LOO with the
      top;
    - with `incumbent_run`, the pairs autoselect's decision is waiting on (a
      challenger tied with the incumbent, even outside the top's tie band);
    - among the frontier's candidates on the target hardware (exploration fits
      included), pairs where one fit beats the other on accuracy and fit time
      (the beaten one survives only if judged more elegant)."""
    from rentfrontier import autoselect, leaderboard

    served = autoselect.eligible(entries, rules)
    need = set()
    for pair in autoselect.tie_pairs(served):
        need.add(pair)
    hardware = autoselect.TARGET_HARDWARE if hardware is None else hardware
    cands = [
        e
        for e in entries
        if e.get("hardware_class", e.get("hardware")) == hardware
        and leaderboard.frontier_candidate(e)
    ]
    if incumbent_run is not None:
        decision = autoselect.decide(entries, incumbent_run, rules)
        need.update(tuple(p) for p in decision["pending_judgements"])
    for e in cands:
        for o in cands:
            if o is e:
                continue
            better = o["psis"]["delta"] >= e["psis"]["delta"] and (
                o["fit_seconds"] <= e["fit_seconds"]
            )
            if better:
                need.add(tuple(sorted((design_id(o), design_id(e)))))
    return sorted(p for p in need if p[0] != p[1] and compare(*p) is None)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    b = sub.add_parser("brief")
    b.add_argument("first")
    b.add_argument("second")
    r = sub.add_parser("record")
    r.add_argument("answers", type=Path, nargs=2)
    args = parser.parse_args(argv)
    if args.cmd == "brief":
        print(brief(args.first, args.second))
    elif args.cmd == "record":
        first, second = (
            {frozenset(x["shown"]): x for x in (v if isinstance(v, list) else [v])}
            for v in (json.loads(p.read_text()) for p in args.answers)
        )
        if first.keys() != second.keys():
            raise SystemExit("the two judges answered different pairs")
        lines = [combine(first[k], second[k]) for k in sorted(first, key=sorted)]
        done = judgements()
        for line in lines:
            if frozenset(line["designs"]) in done:
                raise SystemExit(f"{line['designs']} is already judged")
        with open(JUDGEMENTS, "a") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
        for line in lines:
            print(f"{line['designs'][0]} vs {line['designs'][1]}: {line['verdict']}")
    else:
        from rentfrontier import autoselect, leaderboard

        board = leaderboard.build(keep_dirs=True)
        incumbent = json.loads(autoselect.SELECTION.read_text())["run"]
        for a, b_ in pending(board["entries"], incumbent_run=incumbent):
            print(f"{a}\t{b_}")


if __name__ == "__main__":
    main()
