"""Write a B0 dataset with a column marking the rows of penthouse apartments by their text.

    python -m rentfrontier.b0penthouse SRC OUT

S14 (`docs/notes/unusual-units-2026-11-13.md`) read each listing's description for a
penthouse, a garden apartment and a floor of a townhouse. Asks of ads calling the unit a
penthouse in their text scatter about as much wider than L1 expects as the asks of duplex ads
do. Resampling buildings put a multiplier on L1's noise scale and unit sd at 1.2 to 1.5 for
those penthouses without duplexes, and at 1.3 to 1.4 for duplexes without penthouses. So D1
(`rentfrontier.drift_building_phase_duplex`) gives both marks its one factor, and this script
puts S14's text pattern into a dataset as the column `penthouse`, beside the column `duplex`
from `rentfrontier.b0duplex`.

The column leaves the unit label out. L1 already has a `unit:penthouse` column from a label
starting PH, and S14 found the ads matched by the label alone close to L1's median, where a
wider scale for them gained 8 ± 7 elpd.

I read the records file of SRC's own pipeline build (the manifest's `build.records`, checked
against its SHA-256) a row group at a time, as `b0duplex` does. For each listing of SRC I keep
its latest record, by the later of `collected_at` and `last_collected_at`, and I skip a record
with neither time. In that record's description I count

1. the mentions of the word penthouse (`PEN`), and
2. the mentions naming an amenity, a plural or a style in place of the apartment (`PEN_EXCL`:
   "penthouse lounge", "penthouse-level amenities", "at the penthouse level", "penthouse roof
   deck", "penthouses", "penthouse residences", "penthouse-style" and the like).

Each exclusion contains a mention of the word, so it cancels only the mention it covers, and I
mark the listing when the mentions outnumber the exclusions. An ad offering a penthouse in a
building with a penthouse lounge keeps its mark. The patterns are S14's, copied from
`docs/notes/unusual-units-2026-11-13/u1_text.py` since library code imports nothing from
`docs/notes`, and I count them with pyarrow's RE2, as S14 did. A listing gets false when its
latest record has no description longer than `b0data.MIN_DESCRIPTION` characters, and so does a
listing missing from the records.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the boolean column `penthouse` added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `penthouse` entry giving
  SRC's path and rows SHA-256, the rule and its patterns, the listings read, the rows whose
  listing has a description and the rows marked.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .b0data import MIN_DESCRIPTION, sha256

PEN = r"(?i)\bpenthouse"
PEN_EXCL = (
    r"(?i)\bpenthouses\b"
    r"|\b(?:at|located on) the penthouse[- ]level"
    r"|\bpenthouse[- ](?:level[- ]|floor[- ]|rooftop[- ]|roof[- ]?top[- ]|sky[- ]|amenity[- ])?"
    r"(?:lounge|fitness|gym|health|club|amenit|viewing|sun ?deck|roof|pool|spa\b|lobby|party"
    r"|game|media|screening|co-?work|work ?space|library|bar\b|garden|social|entertain"
    r"|common|shared|resident|laundry|storage|style|like|quality|feel|views?\b|calib"
    r"|finish|apartments\b|residences\b|homes\b|units\b|collection|suites\b|suite of)"
)


def marks(texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """For each text, whether it is longer than MIN_DESCRIPTION characters, and whether it is
    that long and has more mentions of a penthouse than exclusions."""
    a = pa.array(texts, pa.string())

    def count(pattern):
        return pc.count_substring_regex(a, pattern).to_numpy(zero_copy_only=False)

    known = pc.utf8_length(a).to_numpy(zero_copy_only=False) > MIN_DESCRIPTION
    return known, known & (count(PEN) > count(PEN_EXCL))


def latest_marks(path: Path, ids: set[str]) -> pd.DataFrame:
    """For each listing in `ids` with a record in the records file `path`, `known` and
    `penthouse` from `marks` on the description of its latest record. I read the record
    texts of a row group only for the rows I keep, and keep the marks alone."""
    seen: dict[str, tuple[float, bool, bool]] = {}
    file = pq.ParquetFile(path)
    names = set(file.schema_arrow.names)
    times = [c for c in ("collected_at", "last_collected_at") if c in names]
    for group in range(file.num_row_groups):
        head = file.read_row_group(group, columns=["listing_id", *times])
        lid = [str(x) for x in head["listing_id"].to_pylist()]
        at = [
            max((t for t in ts if t is not None), default=None)
            for ts in zip(*(head[c].to_pylist() for c in times))
        ]
        # DuckDB's arg_max in `b0data` passes over a record with a null time.
        keep = [
            i in ids and t is not None and (i not in seen or seen[i][0] < t)
            for i, t in zip(lid, at)
        ]
        if not any(keep):
            continue
        raws = file.read_row_group(group, columns=["raw_listing_json"]).filter(
            pa.array(keep)
        )
        texts = []
        for raw in raws["raw_listing_json"].to_pylist():
            listing = json.loads(raw) if raw else {}
            texts.append(str(listing.get("description") or ""))
        known, pen = marks(texts)
        rows = [(i, t) for i, t, k in zip(lid, at, keep) if k]
        for (i, t), k, p in zip(rows, known, pen):
            # A listing twice in a row group keeps its later record.
            if i not in seen or seen[i][0] < t:
                seen[i] = (t, bool(k), bool(p))
        del raws, texts
    return pd.DataFrame(
        [(i, k, p) for i, (_, k, p) in seen.items()],
        columns=["listing_id", "known", "penthouse"],
    ).set_index("listing_id")


def penthouse(src: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    records = manifest["build"]["records"]
    if sha256(Path(records["path"])) != records["sha256"]:
        raise SystemExit(f"{records['path']} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    read = latest_marks(Path(records["path"]), set(lid))
    known = lid.map(read.known).eq(True).to_numpy()
    frame["penthouse"] = lid.map(read.penthouse).eq(True).to_numpy()
    # OUT is made after the read of the records, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "penthouse": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "the description of the listing's latest record mentions a penthouse "
            "more times than it names a penthouse amenity, plural or style; the unit label "
            "is not read (S14, docs/notes/unusual-units-2026-11-13.md)",
            "patterns": {"pen": PEN, "pen_excl": PEN_EXCL},
            "listings_read": len(read),
            "rows_described": int(known.sum()),
            "rows_marked": int(frame.penthouse.sum()),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(penthouse(args.src, args.out)["penthouse"], indent=2))


if __name__ == "__main__":
    main()
