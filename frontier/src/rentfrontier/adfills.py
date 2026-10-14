"""Coded fields an ad's own text states, for rows whose coded value is unknown.

    python -m rentfrontier.adfills elevator|pets

reads every row of data.DATASET_NB9 with its description (the NB9 description
files, `features._NB9_DESCRIPTIONS`) and writes
EXTERNAL_ROOT/adfills/<date>-<commit>/<field>.parquet (audit_id, the value the
text states, and the matched words) and its provenance file. Refuses a dirty
tree. The `elevator-from-ad-v1` and `pets-from-ad-v1` data rules read the files
and fill a row's field only where the coded value is unknown, so a known code
always stays.

The text states "no" when it says walk-up, two or more flights up, no
elevator (also "no laundry or elevator"), non-elevator or that the building
has no elevator, and "yes" when it mentions an elevator any other way. A "walk
up" to a street or with "no stairs to walk up" says nothing about the
building. A row whose text says both, or neither, gets no line.

For pets the builder takes `petstext.classify`'s class and writes its coded
level (`petstext.CODED`): "allowed_restrictions_unknown", "approval_required"
or "not_allowed". The coded field has no level for "no dogs", so a text of
that class gets no line. Reading samples of ads turned up classifier readings
that `pets` corrects:
  - "case by case" about guarantors or short stays, and "no board approval"
    or "fast approvals" about the application, get set aside;
  - a size or number limit alone ("small dogs only") fills as allowed, which
    matches how rows with a code and such an ad are coded;
  - pets with someone's approval, permission or consent fill as approval
    required;
  - "no pet fees" and a pet fee in a list of charges don't count as pets
    allowed;
  - "pets: no dogs", "dogs aren't allowed", "cats but not dogs" and "no
    doggies" read as no dogs,
    so they get no line;
  - "no board approval or pets", "no smoking or pets" and "no other pets" get
    no allowed or approval line.

Each row reads its own ad only, never another listing in its building."""

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from rentfrontier import data, descriptions, features, petstext
from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

# "walk up" also describes the walk to a street ("a short walk up to astor
# place") or its absence ("no stairs to walk up"), so those uses are left out,
# along with "walk-ups" in general. "One flight up" often leads to a roof deck,
# a terrace or a bedroom, and coded rows call 12% of them elevator buildings,
# so only two or more flights count, and only with no such space after them in
# the sentence.
_FLIGHTS = r"(?:two|three|four|five|six|[2-6])"
_UPSTAIRS_SPACE = r"roof|terrace|deck|bedroom|loft|lounge|garden|gym|amenit|duplex"
ELEVATOR_NO = (
    r"(?<!no )(?<!to )(?<!minute )(?<!short )\bwalk[- ]?up\b(?! to\b)(?! the\b)"
    rf"|\b{_FLIGHTS} (?:short |easy |small )?flights (?:of stairs )?up\b"
    rf"(?![^.]{{0,60}}(?:{_UPSTAIRS_SPACE}))"
    r"|\bno[- ]elevator|\bnon[- ]elevator"
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


# "case by case" in an ad often describes guarantors, short stays or a
# conversion, so a case-by-case class needs a pet word or a weight near it,
# or one of `petstext.CASE`'s approval phrases.
_PET = r"(?:pets?|dogs?|cats?|animals?|lbs|pounds)"
CASE_PETS = (
    _PET
    + r".{0,80}case[- ]by[- ]case|case[- ]by[- ]case.{0,40}"
    + _PET
    + r"|(?:pets?|dogs?)[^.]{0,40}(?:upon|with|subject to) (?:\w+ )?approval"
    r"|approval[^.]{0,20}pets?|pets? (?:considered|negotiable)"
    r"|small (?:dogs?|pets?) considered"
)
# A size or number limit with no approval wording. `petstext.CASE` reads these
# as case by case, while rows with a code and such an ad are coded allowed.
PET_LIMIT = (
    r"small (?:dogs?|pets?) (?:only|ok|okay|allowed|welcome)"
    r"|(?:one|1) (?:small )?(?:dog|pet|cat) (?:allowed|ok|max)"
    r"|\bno (?:pets?|dogs?|animals?) " + petstext.SIZE
)


# "no pet fees" says nothing about which pets a building takes, and
# `petstext.ALLOWED` reads it as pets allowed, so an allowed class needs
# other words.
NO_PET_FEE = r"\bno pet (?:fees?|deposits?|rent)\b"
# A pet fee in a list of possible charges with no amount ("late fees, pet fees,
# insufficient funds", "pet fees or deposits may apply") is boilerplate, and
# says nothing about this building's pets either. A pet fee with its amount
# ("pet fee: $25 per pet") stays.
FEE_LIST = r"\bpet (?:fees?|deposits?),(?! ?\d)|\bpet fees? or deposits? may apply"
# "cats are ok, dogs aren't allowed" bans dogs, and `petstext.NO_DOGS` misses
# the contraction.
DOGS_BANNED = (
    r"\bdogs? (?:are )?(?:(?:aren['’]?t )+|are not |not |never )(?:allowed|permitted|accepted)"
    r"|\bno dogs? (?:allowed|permitted|accepted)\b|\bno dogg(?:y|ie|ys|ies)\b"
    r"|(?<!or )\bnot dogs?\b|\bdogs? not (?:allowed|permitted|accepted|ok)\b"
)
# "pets with landlord's approval" puts pets subject to approval, and
# `petstext.CASE` misses the possessive.
PET_APPROVAL = (
    r"\b(?:pets?|dogs?|cats?)\b[^.]{0,40}\b(?:upon|on|with|subject to|requires?|needs?)"
    r" (?:[\w'’]+ ){0,2}(?:approval|permission|consent)\b"
)
# "no board approval or pets", "no smoking or pets allowed" and "no other pets
# allowed" most likely ban pets, but read as allowed.
NO_APPROVAL_OR_PETS = (
    r"\bno (?:[\w-]+,? ){1,3}(?:or|nor) (?:pets?|dogs?|animals?)\b"
    r"|\bno other (?:pets?|dogs?|animals?)\b"
)
# "no pet dogs" and "pets: no dogs" ban one kind of pet, and `petstext.NO_PETS`
# reads them as no pets.
NO_PET_KIND = r"\bno pets? (?:dogs?|cats?)\b|\bpets?: ?no (?!pets?\b|animals?\b)[a-z]+"
# "no board approval" and "easy approval" are about the application, and
# `petstext.CASE` reads them as pets subject to approval when a pet word follows.
APPLICATION_APPROVAL = r"\b(?:no|easy|fast|quick) (?:board )?approvals?\b"


def pets(text: pd.Series) -> pd.DataFrame:
    """The coded pet level each text states, with the matched words.

    The class comes from `petstext.classify`, with these corrections:
      - a case-by-case text needs a pet word or weight near the phrase
        (`CASE_PETS`), once approval of the application is set aside
        (`APPLICATION_APPROVAL`); failing that it counts as allowed when it
        says so, and otherwise gets no line;
      - an allowed text needs words besides "no pet fees" (`NO_PET_FEE`) or
        a pet fee in a list of charges (`FEE_LIST`);
      - a no-pets text needs a ban besides "no pet dogs" or "pets: no dogs"
        (`NO_PET_KIND`);
      - a case-by-case text giving only a size or number limit ("small dogs
        only", "one pet allowed", "no dogs over 25 lbs") counts as allowed
        (`PET_LIMIT`), as rows with a code and such an ad are coded;
      - an allowed text saying pets need someone's approval, permission or consent counts as case
        by case (`PET_APPROVAL`), and one saying dogs aren't allowed counts
        as no dogs (`DOGS_BANNED`).
    Texts of class "none" or "no_dogs", and texts saying "no board approval
    or pets", "no smoking or pets" or "no other pets" (`NO_APPROVAL_OR_PETS`),
    get no line."""
    found = petstext.classify(text)
    text = text.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
    no_pets = text.str.replace(NO_PET_KIND, " ", regex=True).str.contains(
        petstext.NO_PETS, regex=True
    )
    allowed = (
        text.str.replace(NO_PET_FEE, " ", regex=True)
        .str.replace(FEE_LIST, " ", regex=True)
        .str.contains(petstext.ALLOWED, regex=True)
    )
    case = text.str.replace(APPLICATION_APPROVAL, " ", regex=True).str.contains(
        CASE_PETS, regex=True
    )
    limit = found.eq("case_by_case") & ~case & text.str.contains(PET_LIMIT, regex=True)
    allowed |= limit
    found = found.mask(found.eq("case_by_case") & ~case & allowed, "allowed")
    approval = text.str.replace(APPLICATION_APPROVAL, " ", regex=True).str.contains(
        PET_APPROVAL, regex=True
    )
    approval &= found.eq("allowed") & ~case
    found = found.mask(approval, "case_by_case")
    case |= approval
    found = found.mask(
        found.eq("allowed") & text.str.contains(DOGS_BANNED, regex=True), "no_dogs"
    )
    keep = (
        (found.eq("allowed") & allowed)
        | (found.eq("no_pets") & no_pets)
        | (found.eq("case_by_case") & case)
    ) & ~(found.ne("no_pets") & text.str.contains(NO_APPROVAL_OR_PETS, regex=True))
    evidence = pd.Series(pd.NA, index=text.index, dtype=object)
    for name, pattern in petstext.CLASSES:
        rows = found.eq(name)
        evidence[rows] = _words(text[rows], pattern)
    evidence[approval] = _words(text[approval], PET_APPROVAL)
    evidence[limit] = _words(text[limit], PET_LIMIT)
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
