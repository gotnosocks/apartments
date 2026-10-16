"""Union of several areas' external snapshots, for a dataset that spans them.

    python -m rentfrontier.snapshots union <output.parquet> [--key COL] <input.parquet>...

I read each input, stack them in the order given and drop rows repeated
exactly. With `--key` I then keep the first row of each key value, so the
first input wins where two areas fetched the same lot or building at
different times, and I print how many rows that dropped. A `complete.json`
beside the output records the inputs' hashes and those counts."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _hashable(frame: pd.DataFrame) -> pd.DataFrame:
    # Lists and arrays (geometry is bytes, which hashes) compare by their text.
    out = frame.copy()
    for col in out.columns:
        if (
            out[col]
            .map(lambda v: isinstance(v, (list, dict)) or hasattr(v, "shape"))
            .any()
        ):
            out[col] = out[col].map(repr)
    return out


def union(output: Path, inputs: list[Path], key: str | None = None) -> dict:
    frames = [pd.read_parquet(p) for p in inputs]
    columns = list(frames[0].columns)
    for p, f in zip(inputs, frames):
        if list(f.columns) != columns:
            raise SystemExit(f"{p} has other columns than {inputs[0]}")
    stacked = pd.concat(frames, ignore_index=True)
    repeated = _hashable(stacked).duplicated()
    out = stacked[~repeated]
    conflicts = 0
    if key is not None:
        first = ~out[key].duplicated() | out[key].isna()
        conflicts = int((~first).sum())
        out = out[first]
    output.parent.mkdir(parents=True, exist_ok=True)
    out.reset_index(drop=True).to_parquet(output)
    complete = {
        "inputs": {str(p): _sha(p) for p in inputs},
        "rows": {str(p): len(f) for p, f in zip(inputs, frames)},
        "repeated": int(repeated.sum()),
        "key": key,
        "key_conflicts": conflicts,
        "output_rows": len(out),
        "output_sha256": _sha(output),
    }
    (output.parent / "complete.json").write_text(json.dumps(complete, indent=2) + "\n")
    return complete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["union"])
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--key")
    args = parser.parse_args(argv)
    print(json.dumps(union(args.output, args.inputs, args.key), indent=2))


if __name__ == "__main__":
    main()
