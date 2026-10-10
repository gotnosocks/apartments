"""The pet policy an ad's text states, as of the row's day.

Most listings leave the coded pet policy unknown, though the description often
says "pets ok", "cats only" or "no dogs". `classify` reads the class from the
text; `asof_pets` takes the row's own class, else the building's latest stated
class from strictly earlier days, so a row never reads a later listing. Reads
no rents."""

import numpy as np
import pandas as pd

# A ban on all pets. "no pet fee" and "no pet deposit" are not bans.
NO_PETS = (
    r"\bnot? (?:pets?|animals?)\b"
    r"(?! ?(?:fees?|deposits?|rent|charges?|restrictions?|weight|limit|size)\b)"
    r"|\bpets? (?:are )?(?:not|never) (?:allowed|permitted|accepted|welcome)"
    r"|\bnot pet[- ]friendly|\bpet[- ]free\b|\bno[- ]pet (?:building|policy)"
    r"|\bsorry,? no pets?\b|\bpets?: ?no\b"
)
# Cats but no dogs.
NO_DOGS = (
    r"\bno dogs?\b|\bdogs? (?:are )?(?:not|never) (?:allowed|permitted|accepted)"
    r"|\bcats? only\b|\bonly cats?\b"
)
# Pets subject to approval, size or number.
CASE = (
    r"case[- ]by[- ]case"
    r"|(?:pets?|dogs?)[^.]{0,40}(?:upon|with|subject to) (?:\w+ )?approval"
    r"|approval[^.]{0,20}pets?|pets? (?:considered|negotiable)"
    r"|small (?:dogs?|pets?) (?:only|ok|okay|allowed|welcome|considered)"
    r"|(?:one|1) (?:small )?(?:dog|pet|cat) (?:allowed|ok|max)"
)
# Pets allowed, or a pet fee or building pet amenity that implies it. "dog
# run" is left out: ads name the neighbourhood's dog runs too.
ALLOWED = (
    r"(?<!not )(?<!no )\bpets? (?:are )?(?:welcome|allowed|ok|okay|accepted|permitted)\b"
    r"|\bpet[- ]friendly\b|\bdog[- ]friendly\b|\bdogs? (?:are )?(?:welcome|allowed|ok|okay)\b"
    r"|\bcats? and dogs? (?:are )?(?:welcome|allowed|ok)"
    r"|\bdogs? and cats? (?:are )?(?:welcome|allowed|ok)"
    r"|\bpet (?:fee|deposit|rent)\b"
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
