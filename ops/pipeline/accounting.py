"""Wall time, CPU time and peak memory of data-pipeline steps, from systemd accounting, and
each recent Modal fit's data-prep seconds and dollars, from the Modal ledger and the fits' own
result files.

    python ops/pipeline/accounting.py journal --since "2026-10-15 11:00" [--match REGEX]
    python ops/pipeline/accounting.py modal [--last 15]

The journal subcommand reads every "Consumed ..." line systemd writes when a user unit or scope
stops (services from systemd-run, scopes from ops/job) and prints one markdown row per unit.
The modal subcommand joins each settled ledger entry to its run directory and prints the
`seconds.prepare` and `seconds.fit_total` the fit recorded, beside the settled cost. The fit's
timer starts after preparation ends, so the share is prepare / (prepare + fit_total).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path

LEDGER = Path("/data1/apartments/modal/ledger.jsonl")
RUNS = Path("/data1/apartments/frontier/runs")
CONSUMED = re.compile(
    r"^(?P<at>\S+) \S+ \S+: (?P<unit>\S+): Consumed (?P<cpu>.+?) CPU time over (?P<wall>.+?) "
    r"wall clock time, (?P<mem>\S+) memory peak(?:, (?P<swap>\S+) memory swap peak)?"
)
UNITS = {"d": 86400, "h": 3600, "min": 60, "s": 1, "ms": 0.001, "us": 1e-6}
SIZES = {"B": 2**-30, "K": 2**-20, "M": 2**-10, "G": 1, "T": 2**10}


def seconds(text: str) -> float:
    """Seconds in a systemd duration such as `1h 5min 678ms`."""
    return sum(
        float(n) * UNITS[u] for n, u in re.findall(r"([\d.]+)(d|h|min|ms|us|s)", text)
    )


def gib(text: str | None) -> float:
    if not text:
        return 0.0
    return (
        float(text[:-1]) * SIZES[text[-1]] if text[-1] in SIZES else float(text) / 2**30
    )


def journal(since: str, until: str | None, match: str | None) -> None:
    cmd = ["journalctl", "--user", "--no-pager", "-o", "short-iso", "--since", since]
    if until:
        cmd += ["--until", until]
    lines = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    print("| stopped | unit | wall | CPU | peak GiB | swap GiB |")
    print("|---|---|--:|--:|--:|--:|")
    for line in lines.splitlines():
        m = CONSUMED.match(line)
        if not m or (match and not re.search(match, m["unit"])):
            continue
        print(
            f"| {m['at'][:16]} | {m['unit']} | {seconds(m['wall']) / 60:.1f} min"
            f" | {seconds(m['cpu']) / 60:.1f} min | {gib(m['mem']):.1f}"
            f" | {gib(m['swap']):.1f} |"
        )


def modal(last: int) -> None:
    settled = {}
    for line in LEDGER.read_text().splitlines():
        entry = json.loads(line)
        if entry.get("kind") == "settle":
            settled[entry["name"]] = entry["usd"]
    rows = []
    for name, usd in settled.items():
        result = RUNS / name / "result.json"
        if result.exists():
            run = json.loads(result.read_text())
            spent = run.get("seconds") or {}
            if spent.get("prepare") and spent.get("fit_total"):
                rows.append(
                    (run["started_at"], spent["prepare"], spent["fit_total"], usd, name)
                )
    rows = sorted(rows)[-last:]
    print("| started | prepare s | fit s | prep share | settled $ | fit |")
    print("|---|--:|--:|--:|--:|---|")
    for at, prep, total, usd, name in rows:
        print(
            f"| {at[:16]} | {prep:.0f} | {total:.0f} | {prep / (prep + total):.1%} | {usd:.2f} | {name[-40:]} |"
        )
    prep = [r[1] for r in rows]
    share = [r[1] / (r[1] + r[2]) for r in rows]
    usd = [r[3] for r in rows]
    print(
        f"\n{len(rows)} fits: median prepare {statistics.median(prep):.0f} s "
        f"(range {min(prep):.0f} to {max(prep):.0f}), median share {statistics.median(share):.1%}, "
        f"median settled ${statistics.median(usd):.2f}, prep dollars about "
        f"${sum(s * u for s, u in zip(share, usd)):.2f} in all"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("journal")
    j.add_argument("--since", required=True)
    j.add_argument("--until")
    j.add_argument("--match")
    m = sub.add_parser("modal")
    m.add_argument("--last", type=int, default=15)
    args = parser.parse_args()
    if args.cmd == "journal":
        journal(args.since, args.until, args.match)
    else:
        modal(args.last)


if __name__ == "__main__":
    main()
