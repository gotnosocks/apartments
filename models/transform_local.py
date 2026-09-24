"""Run the normal granular transform locally, including canonical unit grouping.

uv run --locked --extra model python models/transform_local.py --help
"""

import argparse
import concurrent.futures
import fcntl
import json
import multiprocessing
from pathlib import Path
import time

from apartments.granular_export import prepare, process_shard, finish, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--bodies", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / "complete.json").exists():
            raise ValueError("Dataset is complete; choose a new output ID")
        started = time.time()
        state = {
            "started_at": started,
            "root": str(root),
            "workers": args.workers,
            "completed_shards": 0,
        }

        def progress(phase, **data):
            state.update(phase=phase, updated_at=time.time(), **data)
            write_json(root / "progress.json", state)
            print(json.dumps(state), flush=True)

        try:
            progress("preparing")
            plan = prepare(args.snapshot, root, args.corrections)
            progress("transforming", total_shards=plan["shards"])
            counts = {}
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=args.workers,
                mp_context=multiprocessing.get_context("spawn"),
            ) as pool:
                futures = [
                    pool.submit(process_shard, args.snapshot, root, i, args.bodies)
                    for i in range(plan["shards"])
                ]
                for complete, future in enumerate(
                    concurrent.futures.as_completed(futures), 1
                ):
                    result = future.result()
                    for table, count in result["counts"].items():
                        counts[table] = counts.get(table, 0) + count
                    progress("transforming", completed_shards=complete, counts=counts)
            progress("finalizing")
            report = finish(root)
            progress(
                "complete",
                counts=report["tables"]["counts"],
                canonical_unit_association=report["canonical_unit_association"],
                elapsed_seconds=time.time() - started,
            )
        except BaseException as error:
            progress("failed", error=f"{type(error).__name__}: {error}")
            raise


if __name__ == "__main__":
    main()
