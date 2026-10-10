"""The pet policy an ad's text states, as of the row's day.

Most listings leave the coded pet policy unknown, though the description often
says "pets ok", "cats only" or "no dogs". `classify` reads the class from the
text; `asof_pets` takes the row's own class, else the building's latest stated
class from strictly earlier days, so a row never reads a later listing. Reads
no rents."""

import numpy as np
import pandas as pd

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
# Pets allowed, or a pet fee or building pet amenity that implies it. "dog
# run" is left out: ads name the neighbourhood's dog runs too.
ALLOWED = (
    r"(?<!not )(?<!no )\bpets? (?:are )?(?:welcome|allowed|ok|okay|accepted|permitted)\b"
    r"|\bpet[- ]friendly\b|\bdog[- ]friendly\b|\bdogs? (?:are )?(?:welcome|allowed|ok|okay)\b"
    r"|\bcats? and dogs? (?:are )?(?:welcome|allowed|ok)"
    r"|(?<!no )\bcats? (?:are )?(?:welcome|allowed|ok|okay|permitted)\b"
    r"|\bdogs? and cats? (?:are )?(?:welcome|allowed|ok)"
    r"|\bpet (?:fees?|deposits?|rent)\b"
    r"|\bpet (?:spa|wash|care|grooming|washing station)\b|\bpets? (?:are )?fine\b"
)
# Most restrictive first: an ad saying "pets allowed" and "no dogs" is no_dogs.
CLASSES = (
    ("no_pets", NO_PETS),
    ("no_dogs", NO_DOGS),
    ("case_by_case", CASE),
    ("allowed", ALLOWED),
)


def classify(text: pd.Series) -> pd.Series:
    """The pet class each description states, or "none"."""
    text = text.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
    out = pd.Series("none", index=text.index, dtype=object)
    for name, pattern in reversed(CLASSES):
        out[text.str.contains(pattern, regex=True)] = name
    return out


def asof_pets(frame: pd.DataFrame, text: pd.Series) -> pd.DataFrame:
    """The row's text pet class and its source: "own" when the row's ad states
    one, "building" when taken from an earlier listing in the building, else
    "none" with class "none"."""
    own = classify(text).to_numpy()
    stated = own != "none"
    day = pd.to_datetime(frame.price_at, utc=True).dt.floor("D")
    rows = pd.DataFrame(
        {
            "building": frame.building.to_numpy(),
            "day": day.to_numpy(),
            "value": own,
            "i": np.arange(len(frame)),
        }
    )
    latest = (
        rows[stated]
        .sort_values(["day", "i"], kind="stable")
        .groupby(["building", "day"], sort=False)
        .value.last()
        .reset_index()
        .sort_values("day", kind="stable")
    )
    found = pd.merge_asof(
        rows[["building", "day", "i"]].sort_values("day", kind="stable"),
        latest,
        on="day",
        by="building",
        allow_exact_matches=False,
    ).sort_values("i")
    earlier = found.value.to_numpy()
    filled = ~stated & pd.notna(earlier)
    pets = np.where(stated, own, np.where(filled, earlier, "none"))
    source = np.where(stated, "own", np.where(filled, "building", "none"))
    return pd.DataFrame({"pets": pets, "source": source}, index=frame.index)


# The coded pet level each text class sets. The coded field has no "no dogs"
# level, so the text adds one.
CODED = {
    "allowed": "allowed_restrictions_unknown",
    "case_by_case": "approval_required",
    "no_dogs": "no_dogs",
    "no_pets": "not_allowed",
}


def overlay_pets(frame: pd.DataFrame, text: pd.Series) -> pd.DataFrame:
    """The coded pet policy updated from the ad text, and its source for audit.
    A known coded policy stays, except that "allowed" becomes "no_dogs" when
    the row's own ad says no dogs or cats only ("text"). An unknown one takes
    the text class from the row's own ad or the building's earlier ads
    (`asof_pets`; "text" or "building text"); else it stays unknown."""
    asof = asof_pets(frame, text)
    coded = frame.pets.to_numpy()
    mapped = asof.pets.map(CODED).to_numpy()
    fill = (coded == "unknown") & (asof.pets.to_numpy() != "none")
    narrow = (
        (coded == "allowed_restrictions_unknown")
        & asof.source.eq("own").to_numpy()
        & (asof.pets.to_numpy() == "no_dogs")
    )
    pets = np.where(fill | narrow, mapped, coded)
    source = np.where(
        fill & asof.source.eq("building").to_numpy(),
        "building text",
        np.where(fill | narrow, "text", "coded"),
    )
    return pd.DataFrame({"pets": pets, "source": source}, index=frame.index)
