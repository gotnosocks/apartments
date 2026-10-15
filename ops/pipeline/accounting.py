"""Wall time, CPU time and peak memory of data-pipeline steps, from systemd accounting, and
each recent Modal fit's data-prep seconds and dollars, from the Modal ledger and the fits' own
result files.

    python ops/pipeline/accounting.py journal --since "2026-10-15 11:00" [--match REGEX]
    python ops/pipeline/accounting.py modal [--last 15]

The journal subcommand reads every "Consumed ..." line systemd writes when a user unit or scope
stops (services from systemd-run, scopes from ops/job) and prints one markdown row per unit.
The modal subcommand joins each settled ledger entry to its run directory and prints the
`seconds.prepare` the fit recorded beside the seconds Modal billed, which it works out from the
settled cost and the hourly rate in ops/modal/cap.py for the fit's GPU. The billed time covers
the whole container, so it runs longer than preparation plus `seconds.fit_total`. Preparation
costs its own seconds at that rate.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import statistics
import subprocess
from pathlib import Path

LEDGER = Path("/data1/apartments/modal/ledger.jsonl")
RUNS = Path("/data1/apartments/frontier/runs")
CAP = Path(__file__).resolve().parents[1] / "modal" / "cap.py"
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


def rate(gpu: str) -> float:
    """Dollars an hour for a GPU name as nvidia-smi reports it, such as NVIDIA A100-SXM4-40GB."""
    spec = importlib.util.spec_from_file_location("cap", CAP)
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    if "A100" in gpu:
        return cap.USD_PER_HOUR["A100-80GB" if "80GB" in gpu else "A100-40GB"]
    return next(usd for key, usd in cap.USD_PER_HOUR.items() if key in gpu)


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
            gpu = (run.get("hardware") or {}).get("gpu")
            if spent.get("prepare") and gpu:
                hourly = rate(gpu)
                rows.append(
                    (
                        run["started_at"],
                        spent["prepare"],
                        usd / hourly * 3600,
                        usd,
                        spent["prepare"] * hourly / 3600,
                        name,
                    )
                )
    rows = sorted(rows)[-last:]
    print(
        "| started (UTC) | prepare s | billed s | prep share | settled $ | prep $ | fit |"
    )
    print("|---|--:|--:|--:|--:|--:|---|")
    for at, prep, billed, usd, prep_usd, name in rows:
        print(
            f"| {at[:16]} | {prep:.0f} | {billed:.0f} | {prep / billed:.1%} | {usd:.2f}"
            f" | {prep_usd:.2f} | {name[-40:]} |"
        )
    prep = [r[1] for r in rows]
    share = [r[1] / r[2] for r in rows]
    prep_usd = [r[4] for r in rows]
    print(
        f"\n{len(rows)} fits: median prepare {statistics.median(prep):.0f} s "
        f"(range {min(prep):.0f} to {max(prep):.0f}), median share of billed time "
        f"{statistics.median(share):.1%}, median settled ${statistics.median(r[3] for r in rows):.2f}, "
        f"prep about ${statistics.median(prep_usd):.2f} a fit and ${sum(prep_usd):.2f} in all"
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
