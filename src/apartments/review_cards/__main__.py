"""Build a review queue: `python -m apartments.review_cards build QUEUE --out DIR`.

QUEUE is one of the modules in `QUEUES`. DIR defaults to the site's `review/queues` folder on
thelio, and the queue lands in `DIR/QUEUE/`.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from . import common as c

QUEUES = {
    "outliers": "outliers",
    "studio-beds": "studio_beds",
    "held-sets": "held_sets",
    "unit-joins": "unit_joins",
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m apartments.review_cards")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a queue's meta.json and cards.jsonl")
    build.add_argument("queue", choices=sorted(QUEUES))
    build.add_argument("--out", type=Path, default=c.SITE / "review" / "queues")
    build.add_argument("--datasets", type=Path, default=c.DATASETS)
    build.add_argument("--diagnostics", type=Path, default=c.SITE / "diagnostics")
    build.add_argument("--ledger", type=Path, default=c.REPO / "pipeline" / "ledger")
    build.add_argument("--sprint", type=Path, default=c.SPRINT)
    build.add_argument("--memory", default="2GB")
    args = parser.parse_args(argv)
    sources = c.Sources(
        datasets=args.datasets,
        diagnostics=args.diagnostics,
        ledger=args.ledger,
        sprint=args.sprint,
        memory=args.memory,
    )
    module = importlib.import_module(f"{__package__}.{QUEUES[args.queue]}")
    folder = module.main(args.out, sources)
    print(folder)


if __name__ == "__main__":
    main()
