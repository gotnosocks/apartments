"""Coded fields an ad's own text states, for rows whose coded value is unknown.

    python -m rentfrontier.adfills elevator|pets

reads every row of data.DATASET_NB9 with its description (the NB9 description
files, `features._NB9_DESCRIPTIONS`) and writes
EXTERNAL_ROOT/adfills/<date>-<commit>/<field>.parquet (audit_id, the value the
text states, and the matched words) and its provenance file. Refuses a dirty
tree. The `elevator-from-ad-v1` and `pets-from-ad-v1` data rules read the files
and fill a row's field only where the coded value is unknown, so a known code
always stays.

The text states "no" when it says walk-up, flights up, no elevator, non-elevator
or that the building has no elevator, and "yes" when it mentions an elevator
any other way. A row whose text says both, or neither, gets no line.

For pets the builder takes `petstext.classify`'s class and writes its coded
level (`petstext.CODED`): "allowed_restrictions_unknown", "approval_required"
or "not_allowed". The coded field has no level for "no dogs", so a text of
that class gets no line.

Each row reads its own ad only, never another listing in its building."""

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from rentfrontier import data, descriptions, features, petstext
from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

ELEVATOR_NO = (
    r"walk[- ]?up|\bflights? (?:of stairs )?up\b|\bno elevator|\bnon[- ]elevator"
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


def pets(text: pd.Series) -> pd.DataFrame:
    """The coded pet level each text states, with the matched words; texts
    of class "none" or "no_dogs" are dropped."""
    found = petstext.classify(text)
    keep = found.isin(["no_pets", "case_by_case", "allowed"])
    text = text.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
    evidence = pd.Series(pd.NA, index=text.index, dtype=object)
    for name, pattern in petstext.CLASSES:
        rows = found.eq(name)
        evidence[rows] = _words(text[rows], pattern)
    out = pd.DataFrame({"pets": found.map(petstext.CODED), "evidence": evidence})
    return out[keep]


FIELDS = {"elevator": elevator, "pets": pets}


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
