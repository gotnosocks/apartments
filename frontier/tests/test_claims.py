import pandas as pd

from rentfrontier import features


def test_claimed_areas_own_other_and_landmarks():
    text = pd.Series(
        [
            "sunny one bedroom in the heart of the east village.",
            "located in prime greenwich village, steps to the park.",
            "great studio in chelsea near the high line.",
            "steps from chelsea market and union square park.",
            "charming home in the west village.",
            "renovated two bedroom in soho.",
            "walk to the flatiron building from this gem.",
        ]
    )
    label = pd.Series(
        [
            "Gramercy Park",
            "West Village",
            "Chelsea",
            "Chelsea",
            "Greenwich Village",
            "Flatiron",
            "Flatiron",
        ]
    )
    got = features.claimed_areas(text, label)
    assert got["names East Village"].tolist() == [1, 0, 0, 0, 0, 0, 0]
    # Greenwich Village is a West Village listing's own; West Village is
    # another area to a Greenwich Village listing.
    assert got["names its own neighbourhood"].tolist() == [0, 1, 1, 0, 0, 0, 0]
    assert got["names West Village"].tolist() == [0, 0, 0, 0, 1, 0, 0]
    assert got["names Greenwich Village"].sum() == 0
    # SoHo shares "another area"; landmarks are not claims.
    assert got["names another area"].tolist() == [0, 0, 0, 0, 0, 1, 0]
    assert not got.iloc[3].any() and not got.iloc[6].any()


def test_claim_sets_pair_with_the_location_split():
    for name, base in (
        ("nb5p3-claim-v1", "nb5p3-loc-v1"),
        ("nb5p3-claimnolabel-v1", "nb5p3-locnolabel-v1"),
    ):
        assert features.FEATURE_SETS[name].keywords["base"] == base
        assert features.NB4_SETS[name] == "nb5-plutoasof-v3"
        assert features.description_files(name) == features.description_files(base)
