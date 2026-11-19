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
        (
            "INCOME REQUIREMENTS: 1 person $70,000 to $140,000. 2 people $80,000",
            ["income"],
        ),
        ("Units at 130% AMI. Income\u2013restricted, through HPD.", ["income"]),
        ("this is an income\u00a0restricted home", ["income"]),
        ("Commercial use permitted: retail, office or gallery.", ["not_home"]),
        (
            "This is a lease takeover of present tenancy that expires July 31, 2027.",
            ["takeover"],
        ),
        ("Lease takeover inquire for video", ["takeover"]),
        ("Looking for someone to take over my current lease", ["takeover"]),
        ("Lease reassignment. Available November 1 - June 14", ["takeover"]),
        ("Lease assignment through May, option to renew", ["takeover"]),
        ("We are assigning our lease, which runs to June.", ["takeover"]),
        ("Takeover of the lease through August 31", ["takeover"]),
        ("Lease take-over: taking over my lease gets you a low rent", ["takeover"]),
        ("Gut reno lease takeover, lease re-assignment by the landlord", ["takeover"]),
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
        ("Income requirement: 40x the monthly rent", []),
        (
            "Income Requirements: Tenants should earn an average yearly income of 40 x",
            [],
        ),
        ("Income qualifications: 40 times the rent, or a guarantor at 80x.", []),
        ("optional for\n  income restricted units", []),
        ("No HPD violations. Steps from Mon Ami cafe. Not for commercial use.", []),
        ("Residential only, no commercial use allowed.", []),
        (
            "Income qualifications are simple and the building is friendly to guarantors "
            "and to students: 40x the rent.",
            [],
        ),
        ("Home office nook, in-unit laundry, steps from the park.", []),
        ("Sublets OK. Subletting is allowed after one year.", []),
        ("No short term rentals, 12 months is the minimum.", []),
        (
            "Unit not available to lease until 11/17/2026. Lease ends: March 31, 2028",
            [],
        ),
        ("Admin fee for lease transfers: $200. No lease assignments.", []),
        ("The tenant may not assign the lease.", []),
        ("Tenant may not reassign the lease.", []),
        ("No reassignment of lease.", []),
        ("Tenant cannot assign the lease.", []),
        ("No re-assignment of lease.", []),
        ("You may not re-assign the lease.", []),
        ("Early release assignments are handled by the office.", []),
        ("Perfect for sharing with roommates. Owner pays heat.", []),
        ("", []),
        (None, []),
    ],
)
def test_from_text(text, codes):
    assert cautions.from_text(text) == codes


def test_plain_folds_case_spaces_and_dashes():
    assert cautions.plain("Income\u2013Restricted\n\n  UNIT\u00a0here") == (
        "income-restricted unit here"
    )


def test_ordered_lists_each_code_once_in_the_modules_order():
    assert cautions.ordered(["off_market", "income", "beds", "income"]) == [
        "income",
        "beds",
        "off_market",
    ]
    assert cautions.ordered([]) == []
    assert set(cautions.TEXT) < set(cautions.CODES)


def test_net_ask_marks_an_odd_page_price_that_is_a_round_first_ask_less_free_months():
    first = [4100, 7400, 4100, 4100, 4110, 4100, 4000, float("nan")]
    page = [3618, 6783, 3618, 3600, 3627, 3999, 3667, 3618]
    free = [None, 0, 2, None, None, None, None, None]
    # 3,618 is 4,100 less 2 months of 17; 6,783 is 7,400 less 1 of 12. Coded free months,
    # a round page price, a first ask that is not round and a price ending in 9 are left
    # alone. 3,667 is 4,000 less 1 of 12.
    got = cautions.net_ask(
        first, page, [float("nan") if f is None else f for f in free]
    )
    assert got.tolist() == [True, True, False, False, False, False, True, False]


def test_raised_marks_ads_of_other_units_of_a_building_with_a_recent_raised_ad():
    building = ["a", "a", "a", "b", "b", "c", "c", "a"]
    unit = ["u1", "u2", "u1", "u3", "u4", "u5", None, None]
    opened = ["2026-08-01", "2026-10-01", "2026-10-01", "2025-10-01", "2026-10-01"]
    opened += ["2026-10-01", "2026-10-01", "2026-10-01"]
    first = [3000.0, 2500, 2500, 3000, 2500, 2500, 3000, 2500]
    ask = [3450.0, 2500, 2500, 3600, 2500, 2500, 3600, 2500]
    # Building a: u1's first ad is raised 15%, so u2 and the ad with no unit are marked and
    # u1's own ads are not. Building b: the raised ad opened over a year before the day.
    # Building c: the raised ad has no unit and does not count.
    got = cautions.raised(building, unit, opened, first, ask, "2026-11-01")
    assert got.tolist() == [False, True, False, False, False, False, False, True]


def test_raised_needs_the_full_rise():
    got = cautions.raised(
        ["a", "a"],
        ["u1", "u2"],
        ["2026-10-01"] * 2,
        [3000.0, 2500],
        [3449.0, 2500],
        "2026-11-01",
    )
    assert got.tolist() == [False, False]
