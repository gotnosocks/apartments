import pytest

from rentfrontier import cautions


@pytest.mark.parametrize(
    "text, codes",
    [
        # Phrases from ads on the market of 2026-11-09 (docs/notes/drift-2026-11-10.md).
        ("Below are income requirements for the unit", ["income"]),
        ("HPD regulated unit. Income range for this unit is", ["income"]),
        ("THIS IS AN AFFORDABLE UNIT. MAXIMUM INCOME ALLOWED", ["income"]),
        ("This is an income-restricted apartment", ["income"]),
        ("This home is INCOME RESTRICTED", ["income"]),
        ("Affordable Income HPD restricted", ["income"]),
        (
            "Give your practice its own front door. Three private offices",
            ["not_home"],
        ),
        ("available only to current owners at the building", ["owners_only"]),
        # Ordinary wording gives no code.
        ("Income must be 40x the monthly rent. Guarantors welcome.", []),
        ("Minimum annual income: 40x the monthly rent", []),
        ("$25 for each additional person, optional for income restricted units.", []),
        ("Standard Credit & Income guidelines apply", []),
        ("include move date, total household income, and credit scores", []),
        ("This affordable apartment is easy to set up as a 3BR", []),
        ("Co-Working Hub: Multiple private offices available 24/7", []),
        ("Flexible home office space. Gym for Owners only. Sorry.", []),
        ("Two Bedroom Two Bathroom Available Now! Central A/C (Per Room)", []),
        ("Home office nook, in-unit laundry, steps from the park.", []),
        ("Perfect for sharing with roommates. Owner pays heat.", []),
        ("", []),
        (None, []),
    ],
)
def test_from_text(text, codes):
    assert cautions.from_text(text) == codes


def test_ordered_lists_each_code_once_in_the_modules_order():
    assert cautions.ordered(["off_market", "income", "beds", "income"]) == [
        "income",
        "beds",
        "off_market",
    ]
    assert cautions.ordered([]) == []
    assert set(cautions.TEXT) < set(cautions.CODES)
