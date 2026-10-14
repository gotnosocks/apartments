"""Coded fields an ad's own text states, for rows whose coded value is unknown.

    python -m rentfrontier.adfills elevator

reads every row of data.DATASET_NB9 with its description (the NB9 description
files, `features._NB9_DESCRIPTIONS`) and writes
EXTERNAL_ROOT/adfills/<date>-<commit>/elevator.parquet (audit_id, the value the
text states, and the matched words) and provenance.json. Refuses a dirty tree.
The `elevator-from-ad-v1` data rule reads the file and fills a row's elevator
only where the coded value is unknown, so a known code always stays.

The text states "no" when it says walk-up, flights up, no elevator (also "no
laundry or elevator"), non-elevator or that the building has no elevator, and
"yes" when it mentions an elevator any other way. A "walk up" to a street or
with "no stairs to walk up" says nothing about the building. A row whose text says both, or neither, gets no line. Each row
reads its own ad only, never another listing in its building."""

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from rentfrontier import data, descriptions, features
from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

# "walk up" also describes the walk to a street ("a short walk up to astor
# place") or its absence ("no stairs to walk up"), so those uses are left out.
ELEVATOR_NO = (
    r"(?<!no )(?<!to )(?<!minute )(?<!short )\bwalk[- ]?up(?! to\b)(?! the\b)"
    r"|\bflights? (?:of stairs )?up\b|\bno[- ]elevator|\bnon[- ]elevator"
    r"|\bno (?:[\w-]+ ){1,3}(?:or|nor) (?:an? )?elevators?\b"
    r"|\bwithout (?:an? )?elevator|\bnot an elevator"
    r"|\b(?:does not|doesn't|do not) have (?:an? )?elevator"
)
ELEVATOR_YES = r"(?<!no )(?<!non-)(?<!non )(?<!without an )(?<!without )\belevators?\b"


def _words(text: pd.Series, pattern: str) -> pd.Series:
    """The first match of `pattern` in each text, with up to 30 characters
    either side, or NaN."""
    return text.str.extract(f"(.{{0,30}}(?:{pattern}).{{0,30}})", expand=False)


def elevator(text: pd.Series) -> pd.DataFrame:
    """ "yes" or "no" for each text stating exactly one of them, with the
    matched words; texts stating both or neither are dropped."""
    text = text.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
    no = text.str.contains(ELEVATOR_NO, regex=True)
    # "no elevator" also contains "elevator", so a "no" text counts as "yes"
    # only when it names an elevator again outside the "no" phrase.
    rest = text.str.replace(ELEVATOR_NO, " ", regex=True)
    yes = rest.str.contains(ELEVATOR_YES, regex=True)
    out = pd.DataFrame(
        {
            "elevator": pd.Series("no", index=text.index).where(no, "yes"),
            "evidence": _words(text, ELEVATOR_NO).where(no, _words(text, ELEVATOR_YES)),
        }
    )
    return out[no ^ yes]


FIELDS = {"elevator": elevator}


def main(argv: list[str]):
    (field,) = argv
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    frame = data.load(data.DATASET_NB9)
    sources = tuple(Path(p) for p in features._NB9_DESCRIPTIONS.values())
    token = descriptions.SOURCES.set(sources)
    try:
        text = pd.Series(descriptions.attach(frame).to_numpy(), index=frame.index)
    finally:
        descriptions.SOURCES.reset(token)
    out = FIELDS[field](text)
    out.insert(0, "audit_id", frame.audit_id[out.index])
    out.insert(2, "coded", frame[field][out.index])
    out_dir = EXTERNAL_ROOT / "adfills" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{field}.parquet"
    out.to_parquet(path, index=False)
    (out_dir / f"{field}.provenance.json").write_text(
        json.dumps(
            {
                "built_at": started.isoformat(),
                "commit": commit,
                "dataset": str(data.DATASET_NB9),
                "descriptions": [str(p) for p in sources],
                "rows": len(out),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}: {len(out)} rows")
    print(pd.crosstab(out[field], out.coded).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
