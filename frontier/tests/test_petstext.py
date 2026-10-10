import pandas as pd

from rentfrontier import petstext


def test_classify_reads_bans_restrictions_and_permissions():
    text = pd.Series(
        [
            "Sorry, no pets.",
            "pets allowed *** (cats only)",
            "Pet friendly building, but sorry, no dogs",
            "pets on a case-by-case basis",
            "pet friendly, no pet fee",
            "no broker fee, no pet deposits",
            "$50 per month pet fee",
            "steps from the hudson river park dog run",
            "cats allowed",
            "no dogs over 25 lbs",
            "no pet policy restrictions, pets ok",
            "no pets over 15 lbs",
            "no cats or dogs",
            "no pet fees",
            None,
        ]
    )
    assert petstext.classify(text).tolist() == [
        "no_pets",
        "no_dogs",
        "no_dogs",
        "case_by_case",
        "allowed",
        "allowed",
        "allowed",
        "none",
        "allowed",
        "case_by_case",
        "allowed",
        "case_by_case",
        "no_pets",
        "allowed",
        "none",
    ]


def test_asof_pets_reads_only_earlier_days_in_the_building():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "a", "b", "a"],
            "price_at": [
                "2020-01-05",
                "2020-01-01",
                "2020-01-05",
                "2020-01-09",
                "2020-01-09",
                "2020-01-03",
            ],
        }
    )
    text = pd.Series(["", "", "no dogs", "", "", "pets ok"])
    out = petstext.asof_pets(frame, text)
    # Row 0 (Jan 5) sees Jan 3's "pets ok", not the same day's "no dogs"; row
    # 1 has no earlier ad; row 3 (Jan 9) sees Jan 5's; building b has none.
    assert out.pets.tolist() == [
        "allowed",
        "none",
        "no_dogs",
        "no_dogs",
        "none",
        "allowed",
    ]
    assert out.source.tolist() == ["building", "none", "own", "building", "none", "own"]


def test_overlay_pets_fills_unknown_and_narrows_allowed_to_no_dogs():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "b", "c", "c"],
            "price_at": [
                "2020-01-01",
                "2020-01-05",
                "2020-01-01",
                "2020-01-01",
                "2020-01-01",
                "2020-01-01",
            ],
            "pets": [
                "unknown",
                "unknown",
                "allowed_restrictions_unknown",
                "not_allowed",
                "unknown",
                "unknown",
            ],
        }
    )
    text = pd.Series(
        ["no dogs", "", "pets allowed (cats only)", "pets ok", "case by case", ""]
    )
    out = petstext.overlay_pets(frame, text)
    # A known "not allowed" stays even when the ad says pets ok.
    assert out.pets.tolist() == [
        "no_dogs",
        "no_dogs",
        "no_dogs",
        "not_allowed",
        "approval_required",
        "unknown",
    ]
    assert out.source.tolist() == [
        "text",
        "building text",
        "text",
        "coded",
        "text",
        "coded",
    ]
