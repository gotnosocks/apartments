"""The elevator and the pet policy an ad's description states, as the chain's ad fills read them.

The chain fills an unknown elevator and an unknown pet policy from the row's own description, in
the rules `elevator-from-ad-v1` and `pets-from-ad-v2`. Those rules read files that
`rentfrontier.adfills` wrote for NB9's rows from the page crawl's descriptions. This module reads
each API record's description with the same patterns, copied from `rentfrontier.adfills` and
`rentfrontier.petstext`, so the pipeline can fill every ad and the fit can drop both rules.
`pipeline/tests/test_adtext.py` runs the chain's pandas functions beside these on the same texts
and expects the same readings.

Both readings start from the text in lower case, with each run of white space made a single
space.

For the elevator, `elevator` gives False when the text says walk-up, two or more flights up, no
elevator, non-elevator or that the building has no elevator. It gives True when the text names
an elevator any other way. A "walk up" to a street, or "no stairs to walk up", says nothing
about the building. A text saying both, or neither, gives None.

For pets, `pets` starts from the class `classify` reads. It tries the patterns of "no_pets",
"no_dogs", "case_by_case" and "allowed" in turn and takes the first to match. `pets` then makes
the chain's corrections:

  - a pet fee, deposit, rent or charge of any kind counts as pets allowed when the text states
    no other class. That holds for "no pet fees" and for a pet fee in a list of charges as well;
  - "case by case" about guarantors or short stays, and "no board approval" or "fast approvals"
    about the application, get set aside;
  - a size or number limit alone ("small dogs only") counts as allowed;
  - pets with someone's approval, permission or consent count as approval required;
  - "dogs aren't allowed", "pets: no dogs" and "no doggies" count as no dogs;
  - "no board approval or pets", "no smoking or pets" and "no other pets" give no allowed or
    approval reading.

It returns the class's coded level from `CODED`. The coded field has no level for "no dogs", so a
text of that class gives None, as does a text with no class.
"""

import re

# A size limit ("no dogs over 25 lbs") restricts pets rather than banning them.
SIZE = r"(?:over|above|larger|bigger|heavier|more than|weighing)\b"
# A ban on all pets. "no pet fee" and "no pet deposit" are not bans.
NO_PETS = (
    r"\bnot? (?:pets?|animals?)\b"
    r"(?! ?(?:fees?|deposits?|rent|charges?|restrictions?|weight|limit|size"
    r"|policy restrictions?)\b)(?! " + SIZE + ")"
    r"|\bno (?:cats? (?:or|and|nor) dogs?|dogs? (?:or|and|nor) cats?)\b"
    r"|\bpets? (?:are )?(?:not|never) (?:allowed|permitted|accepted|welcome)"
    r"|\bnot pet[- ]friendly|\bpet[- ]free\b"
    r"|\bno[- ]pet (?:building|policy)\b(?! restrictions?)"
    r"|\bsorry,? no pets?\b|\bpets?: ?no\b"
)
# Cats but no dogs.
NO_DOGS = (
    r"\bno dogs?\b(?! " + SIZE + ")"
    r"|\bdogs? (?:are )?(?:not|never) (?:allowed|permitted|accepted)"
    r"|\bcats? only\b|\bonly cats?\b"
)
# Pets subject to approval, size or number.
CASE = (
    r"case[- ]by[- ]case"
    r"|(?:pets?|dogs?)[^.]{0,40}(?:upon|with|subject to) (?:\w+ )?approval"
    r"|approval[^.]{0,20}pets?|pets? (?:considered|negotiable)"
    r"|small (?:dogs?|pets?) (?:only|ok|okay|allowed|welcome|considered)"
    r"|(?:one|1) (?:small )?(?:dog|pet|cat) (?:allowed|ok|max)"
    r"|\bno (?:pets?|dogs?|animals?) " + SIZE
)
# Pets allowed, or a pet fee or building pet amenity implying it. "dog run" is left out, since
# ads name the neighbourhood's dog runs too.
ALLOWED = (
    r"(?<!not )(?<!no )\bpets? (?:are )?(?:welcome|allowed|ok|okay|accepted|permitted)\b"
    r"|\bpet[- ]friendly\b|\bdog[- ]friendly\b|\bdogs? (?:are )?(?:welcome|allowed|ok|okay)\b"
    r"|\bcats? and dogs? (?:are )?(?:welcome|allowed|ok)"
    r"|(?<!no )\bcats? (?:are )?(?:welcome|allowed|ok|okay|permitted)\b"
    r"|\bdogs? and cats? (?:are )?(?:welcome|allowed|ok)"
    r"|\bpet (?:fees?|deposits?|rent)\b"
    r"|\bpet (?:spa|wash|care|grooming|washing station)\b|\bpets? (?:are )?fine\b"
)
# Most restrictive first: an ad saying "pets allowed" and "no dogs" reads as no dogs.
CLASSES = (
    ("no_pets", NO_PETS),
    ("no_dogs", NO_DOGS),
    ("case_by_case", CASE),
    ("allowed", ALLOWED),
)
# The coded pet level of each class. The coded field has no level for "no dogs".
CODED = {
    "allowed": "allowed_restrictions_unknown",
    "case_by_case": "approval_required",
    "no_pets": "not_allowed",
}

# "walk up" also describes the walk to a street ("a short walk up to astor place") or its
# absence ("no stairs to walk up"), so those uses are left out, along with "walk-ups" in
# general. "One flight up" often leads to a roof deck, a terrace or a bedroom, and coded rows
# call 12% of them elevator buildings, so only two or more flights count, and only with no such
# space after them in the sentence.
_FLIGHTS = r"(?:two|three|four|five|six|[2-6])"
_UPSTAIRS_SPACE = r"roof|terrace|deck|bedroom|loft|lounge|garden|gym|amenit|duplex"
ELEVATOR_NO = (
    r"(?<!no )(?<!not a )(?<!not an )(?<!n't a )(?<!to )(?<!minute )(?<!short )\bwalk[- ]?up\b(?! to\b)(?! the\b)"
    rf"|\b{_FLIGHTS} (?:short |easy |small )?flights (?:of stairs )?up\b"
    rf"(?![^.]{{0,60}}(?:{_UPSTAIRS_SPACE}))"
    r"|\bno[- ]elevator|\bnon[- ]elevator"
    r"|\bno (?!damage\b)(?:[\w-]+ ){1,3}(?:or|nor) (?:an? )?elevators?\b"
    r"|\bwithout (?:an? )?elevator|\bnot an elevator"
    r"|\b(?:does not|doesn't|do not) have (?:an? )?elevator"
)
ELEVATOR_YES = r"(?<!no )(?<!non-)(?<!non )(?<!without an )(?<!without )\belevators?\b"

# "case by case" in an ad often describes guarantors, short stays or a conversion, so a
# case-by-case class needs a pet word or a weight near it, or one of `CASE`'s approval phrases.
_PET = r"(?:pets?|dogs?|cats?|animals?|lbs|pounds)"
CASE_PETS = (
    _PET
    + r".{0,80}case[- ]by[- ]case|case[- ]by[- ]case.{0,40}"
    + _PET
    + r"|(?:pets?|dogs?)[^.]{0,40}(?:upon|with|subject to) (?:\w+ )?approval"
    r"|approval[^.]{0,20}pets?|pets? (?:considered|negotiable)"
    r"|small (?:dogs?|pets?) considered"
)
# A size or number limit with no approval wording. `CASE` reads these as case by case, while
# rows with a code and such an ad are coded allowed.
PET_LIMIT = (
    r"small (?:dogs?|pets?) (?:only|ok|okay|allowed|welcome)"
    r"|(?:one|1) (?:small )?(?:dog|pet|cat) (?:allowed|ok|max)"
    r"|\bno (?:pets?|dogs?|animals?) " + SIZE
)
# A pet fee of any kind means the building takes pets in some form, and so does "no pet fees":
# of NB9's rows with a pet code and such wording, 1,065 of 1,066 are coded allowed. `ALLOWED`
# reads "pet fee", "pet deposit" and "pet rent", and this adds the other spellings.
PET_FEE = (
    r"\bpets? (?:fees?|deposits?|rent|charges?)\b|\bpet[- ](?:fee|deposit)s?\b"
    r"|\b(?:fees?|deposits?|charges?) (?:for|per) (?:pets?|dogs?|cats?)\b"
)
# "cats are ok, dogs aren't allowed" bans dogs, and `NO_DOGS` misses the contraction.
DOGS_BANNED = (
    r"\bdogs? (?:are )?(?:(?:aren['’]?t )+|are not |not |never )(?:allowed|permitted|accepted)"
    r"|\bno dogs? (?:allowed|permitted|accepted)\b|\bno dogg(?:y|ie|ys|ies)\b"
    r"|(?<!or )\bnot dogs?\b|\bdogs? not (?:allowed|permitted|accepted|ok)\b"
)
# "pets with landlord's approval" puts pets subject to approval, and `CASE` misses the
# possessive.
PET_APPROVAL = (
    r"\b(?:pets?|dogs?|cats?)\b[^.]{0,40}\b(?:upon|on|with|subject to|requires?|needs?)"
    r" (?:[\w'’]+ ){0,2}(?:approval|permission|consent)\b"
)
# "no board approval or pets", "no smoking or pets allowed" and "no other pets allowed" most
# likely ban pets, but read as allowed.
NO_APPROVAL_OR_PETS = (
    r"\bno (?:[\w-]+,? ){1,3}(?:or|nor) (?:pets?|dogs?|animals?)\b"
    r"|\bno other (?:pets?|dogs?|animals?)\b"
)
# "no pet dogs" and "pets: no dogs" ban one kind of pet, and `NO_PETS` reads them as no pets.
NO_PET_KIND = r"\bno pets? (?:dogs?|cats?)\b|\bpets?: ?no (?!pets?\b|animals?\b)[a-z]+"
# "no board approval" and "easy approval" are about the application, and `CASE` reads them as
# pets subject to approval when a pet word follows.
APPLICATION_APPROVAL = r"\b(?:no|easy|fast|quick) (?:board )?approvals?\b"

_CLASSES = tuple((name, re.compile(pattern)) for name, pattern in CLASSES)
_SPACE = re.compile(r"\s+")
_NO = re.compile(ELEVATOR_NO)
_YES = re.compile(ELEVATOR_YES)
_NO_PETS = re.compile(NO_PETS)
_ALLOWED = re.compile(ALLOWED)
_CASE_PETS = re.compile(CASE_PETS)
_PET_LIMIT = re.compile(PET_LIMIT)
_PET_FEE = re.compile(PET_FEE)
_DOGS_BANNED = re.compile(DOGS_BANNED)
_PET_APPROVAL = re.compile(PET_APPROVAL)
_NO_APPROVAL_OR_PETS = re.compile(NO_APPROVAL_OR_PETS)
_NO_PET_KIND = re.compile(NO_PET_KIND)
_APPLICATION_APPROVAL = re.compile(APPLICATION_APPROVAL)


def normalize(text):
    """The text in lower case, each run of white space made a single space."""
    return _SPACE.sub(" ", (text or "").lower())


def classify(text):
    """The pet class a normalized text states, or "none"."""
    for name, pattern in _CLASSES:
        if pattern.search(text):
            return name
    return "none"


def elevator(text):
    """True or False for a description stating one of them, else None."""
    text = normalize(text)
    no = _NO.search(text) is not None
    # "no elevator" also contains "elevator", so a "no" text counts as "yes" only when it names
    # an elevator again outside the "no" phrase.
    yes = _YES.search(_NO.sub(" ", text)) is not None
    return None if no == yes else yes


def pets(text):
    """The coded pet level a description states, else None."""
    text = normalize(text)
    found = classify(text)
    fee = _PET_FEE.search(text) is not None
    if found == "none" and fee:
        found = "allowed"
    no_pets = _NO_PETS.search(_NO_PET_KIND.sub(" ", text)) is not None
    allowed = _ALLOWED.search(text) is not None or fee
    application = _APPLICATION_APPROVAL.sub(" ", text)
    case = _CASE_PETS.search(application) is not None
    limit = found == "case_by_case" and not case and _PET_LIMIT.search(text) is not None
    allowed = allowed or limit
    if found == "case_by_case" and not case and allowed:
        found = "allowed"
    approval = (
        found == "allowed"
        and not case
        and _PET_APPROVAL.search(application) is not None
    )
    if approval:
        found = "case_by_case"
        case = True
    if found == "allowed" and _DOGS_BANNED.search(text):
        found = "no_dogs"
    keep = (
        (found == "allowed" and allowed)
        or (found == "no_pets" and no_pets)
        or (found == "case_by_case" and case)
    )
    if found != "no_pets" and _NO_APPROVAL_OR_PETS.search(text):
        keep = False
    return CODED[found] if keep else None
