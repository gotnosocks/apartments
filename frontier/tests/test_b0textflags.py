import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0textflags
from rentfrontier.b0data import sha256

# Paraphrases of ads the readers of docs/notes/text-flags-2026-11-13.md judged.
INCOME_YES = [
    "This unit is income restricted at 130% AMI, rent stabilized.",
    "Leasing now through the NYC Housing Connect lottery, apply today.",
    "The rental needs approval from the state agency HDC, which takes about two weeks.",
    "The HDFC co-op sets an income cap of $175,000 for one person.",
    "Applicants must fall below the following income caps. Maximum cap: $412,440.",
    "Income limits: 1 person $96,316 to $147,420, 2 people $96,316 to $168,480.",
    "Income guideline: minimum for this unit $91,530, maximum for 2 HH $146,125.",
    "This is an affordable unit, so applicants must meet set income requirements.",
    # A negation elsewhere in the ad leaves the match.
    "No fee income restricted apartments, call the office to apply.",
    "No fee. All units are income restricted and applicants must qualify.",
    "This is an income restriction unit. Non-income restricted units are also available.",
]
INCOME_NO = [
    "Application fee $20, optional for income restricted units. Bright one bedroom.",
    "Standard credit and income guidelines apply, guarantors welcome.",
    "Tenants need 40x the rent in annual income and a 700 credit score.",
    "You've won the lottery with this renovated rent stabilized one bedroom!",
    "Affordable luxury two bedroom in prime Williamsburg, steps to the L.",
    "Section 8 and CityFHEPS vouchers are accepted for this two bedroom.",
    "Contact Jonathan Ben-Ami to set up a viewing of this one bedroom.",
    # A negation just before the only match, as in the ads of
    # docs/notes/income-flag-2026-11-14.md.
    "Rent-stabilized apartment. No income restrictions. No pets allowed.",
    "Rare rent-stabilized (no income cap) building with a gym and a roof deck.",
    "A well-maintained HDFC cooperative without any income limits for renters.",
]
SHARED_YES = [
    "Amazing studio with shared bathroom, all utilities included.",
    "Single room in a prime Upper West Side building. Shared bath in hallway.",
    "The bathroom is shared with one other tenant on the floor.",
    "This apartment has a shared kitchen with one other person, private bath.",
    "Small SRO unit with a private bath and no kitchen.",
    "An unfurnished single room occupancy apartment near the park.",
    "Each floor features an updated, shared bathroom cleaned every week.",
    "A private room for rent in a three bedroom near the G train.",
    "Roommate matching provided. Room pricing: room 1 $1,350, room 2 $1,400.",
    "I'm looking for a roommate to take the second bedroom of my Astoria apartment.",
    "You will be living with two friendly housemates in a big brownstone.",
]
SHARED_NO = [
    "Perfect for roommates, with two queen bedrooms and a windowed kitchen.",
    "If you're looking for roommates in Brooklyn we can help you find them.",
    "The two secondary bedrooms share a bath in the hall, great closets.",
    "The other two bedrooms have a shared bath with a soaking tub.",
    "Bringing this former SRO back to life as bright, renovated lofts.",
    "Shared roof deck, shared laundry and a communal kitchen in the lounge.",
    "Spacious two bedroom with a dining/living room for rent in Crown Heights.",
    "Kitchen and bath are shared between the two bedrooms of this duplex.",
    "Roommate change fees apply. Two bedroom, one bath, heat included.",
]


@pytest.mark.parametrize("text", INCOME_YES)
def test_income_v2_marks_income_restricted_units(text):
    assert b0textflags.flags(text) == (True, True, False)


@pytest.mark.parametrize("text", INCOME_NO)
def test_income_v2_leaves_market_ads(text):
    assert b0textflags.flags(text)[1] is False


@pytest.mark.parametrize("text", SHARED_YES)
def test_shared_v2_marks_rooms_and_shared_facilities(text):
    assert b0textflags.flags(text) == (True, False, True)


@pytest.mark.parametrize("text", SHARED_NO)
def test_shared_v2_leaves_whole_apartments(text):
    assert b0textflags.flags(text)[2] is False


# INCOME_V2 as it built the -textflags copy of L1's dataset, whose manifest records it. The
# pattern starts from b0income.INCOME, so an edit to that Deals caution fails here before it
# changes a rebuild.
INCOME_V2_BUILT = (
    r"(?<!optional for )income[- ]restrict"
    r"|(?<!optional for income )restricted (?:unit|apartment|rental)"
    r"|income (?:limit|eligib)"
    r"|(?:maximum|max)\.? (?:annual |household |allowable |allowed )?income"
    r"|\bhpd\b(?! violation)"
    r"|affordable housing"
    r"|housing connect"
    r"|(?:housing|hpd|affordable|421-?a) lottery"
    r"|lottery (?:unit|apartment|rental)"
    r"|(?<!mon )(?<!bel )(?<!ben-)(?<!ben )\bami\b"
    r"|(?:low|middle|moderate)[- ]income"
    r"|median income"
    r"|\bhdc\b"
    r"|income caps?\b"
    r"|max(?:imum)?\.? (?:income )?for (?:a )?[1-9] ?(?:person|people|persons|hh|household)"
    r"|\b[1-9] ?(?:person|people|persons|ppl|hh|household)s?(?: household)?:? ?-? ?\$ ?"
    r"\d{2,3},?\d{3}"
    r"|is an affordable unit"
)
# The negation and the patterns of TERMS as they built the copy on 2026-11-14.
_PCT = r"(\d{2,3})(?:\.\d+)? ?(?:%|percent)"
_PCT_RANGE = r"(?: ?(?:-|to|and|or|/|&) ?(\d{2,3})(?:\.\d+)? ?(?:%|percent))?"
_USD = r"\$+ ?(\d{1,3}(?:, ?\d{3})+(?:\.\d+)?|\d{2,7}(?:\.\d+)?k?)"
BUILT = {
    "NEGATION": r"\b(?:no|not|non|without)[- ](?:(?:an?|any)[- ])?$",
    "AMI_PCT": _PCT
    + _PCT_RANGE
    + r" (?:of (?:the )?)?(?:\(?ami\b|area median|median income)"
    + r"|\bami(?: level| band| tier| limit| category)?:? ?(?:of |at |is )?"
    + _PCT
    + _PCT_RANGE
    + r"|\b(\d{2,3}) ami ?%",
    "TIED": r"this (?:unit|apartment|apt|home|residence)\b[^.]{0,40}$",
    "INCOME_MIN": r"(?:\bmin(?:imum|\.)?|at least|no less than)"
    r"(?: combined| annual| household| yearly| gross| total)*(?: income)?"
    r"(?: requirements?| required| limit)?(?: for this unit)?(?: is| of)?[ :*-]*"
    + _USD,
    "INCOME_MAX": r"(?:\bmax(?:imum|imim|\.)?|not exceed|cannot exceed|can not exceed"
    r"|no more than|must be below|income below)(?:(?!min)[^$.]){0,40}?[ :*-]*" + _USD,
    "INCOME_BETWEEN": r"(?:between|range|bracket)[^$.]{0,30}?"
    + _USD
    + r"(?: min)?,? ?(?:and|-|to) ?"
    + _USD,
    "INCOME_MAX_AFTER": _USD + r" max\b",
}


def test_income_v2_is_the_pattern_the_copy_was_built_with():
    assert b0textflags.INCOME_V2.pattern == INCOME_V2_BUILT
    for name, pattern in BUILT.items():
        assert getattr(b0textflags, name).pattern == pattern, name
    assert b0textflags.NEGATED_WINDOW == 16
    assert b0textflags.TIED_WINDOW == 60


NAN = float("nan")
# (description, ami_pct_text, ami_tiers_text, income_min_text, income_max_text), from ads
# among the rows INCOME_V2 marks.
TERM_CASES = [
    ("This is an income restricted apartment at 165% AMI.", 165, 1, NAN, NAN),
    (
        "AMI: 110% Asset limit: $155,320 Minimum income: $113,000 Maximum income: "
        "1-person household: $108,790 2-person household: $124,300",
        110,
        1,
        113_000,
        108_790,
    ),
    (
        "Must meet the max income per household of 120 percent area median income (AMI).",
        120,
        1,
        NAN,
        NAN,
    ),
    (
        "Studio to 3BR from $1,096 to $3,703 (70%-130% AMI income requirements).",
        NAN,
        2,
        NAN,
        NAN,
    ),
    (
        "Units at 80% and 130% AMI. This unit is at 130% AMI, call to apply.",
        130,
        2,
        NAN,
        NAN,
    ),
    ("HDFC income restrictions apply. 175 AMI % family of one.", 175, 1, NAN, NAN),
    ("Contact Ami Ray to view this income restricted one bedroom.", NAN, 0, NAN, NAN),
    (
        "Minimum household income: $83,538 Maximum income (varies with household "
        "size): $187,110",
        NAN,
        0,
        83_538,
        187_110,
    ),
    (
        "Your household income must be between $78,694 and $220,344.",
        NAN,
        0,
        78_694,
        220_344,
    ),
    (
        "HDC approval needed. Income must be between $70k and $197k annual.",
        NAN,
        0,
        70_000,
        197_000,
    ),
    (
        "Income restrictions apply. $119,570 max income for single occupant.",
        NAN,
        0,
        NAN,
        119_570,
    ),
    (
        "Income restricted. Minimum 2 people, security deposit of $500.",
        NAN,
        0,
        NAN,
        NAN,
    ),
]


@pytest.mark.parametrize("case", TERM_CASES)
def test_terms_read_the_tier_and_the_income_band(case):
    text, *want = case
    assert b0textflags.terms(text) == pytest.approx(tuple(want), nan_ok=True)


def test_a_short_text_is_unknown_and_unmarked():
    assert b0textflags.flags("SRO, HDC") == (False, False, False)


def test_a_dash_or_line_break_counts_as_plain_text():
    assert b0textflags.flags("Studio with shared\nbathroom, near the A and C.")[2]
    assert b0textflags.flags("This unit is income–restricted; call to apply.")[1]


INC, SHR, MKT = INCOME_YES[2], SHARED_YES[0], INCOME_NO[1]
TIER = INC + " This unit is at 130% AMI, with a minimum income of $90,000."
NEGATED = INCOME_NO[-3]
# (listing, collected_at, last_collected_at, description), one record each.
RECORDS = [
    # Listing 12's newer record and listing 13's older record come in the first row group.
    ("12", 4.0, 4.0, INC),
    ("13", 1.0, 1.0, MKT),
    ("1", 1.0, 1.0, TIER),
    ("2", 1.0, 1.0, SHR),
    ("3", 1.0, 1.0, MKT),
    ("4", 1.0, 1.0, "SRO, HDC"),
    # The later record of listing 7 drops the shared bath, by last_collected_at.
    ("7", 3.0, 3.0, SHR),
    ("7", 2.0, 5.0, MKT),
    ("8", 1.0, 1.0, None),
    ("11", 1.0, None, SHR),
    ("12", 2.0, 2.0, MKT),
    ("13", 3.0, 3.0, INC),
    # A record with neither time is no listing's latest.
    ("14", None, None, SHR),
    ("15", 1.0, 1.0, NEGATED),
]


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [int(r[0]) for r in RECORDS],
                "collected_at": [r[1] for r in RECORDS],
                "last_collected_at": [r[2] for r in RECORDS],
                "raw_listing_json": [
                    json.dumps({} if r[3] is None else {"description": r[3]})
                    for r in RECORDS
                ],
            }
        ),
        path,
        row_group_size=4,
    )
    ids = [1, 1, 2, 3, 4, 7, 8, 10, 11, 12, 13, 14, 15]
    rows = pd.DataFrame(
        {
            "listing_id": ids,
            "latest_ask": [3000.0 + i for i in range(len(ids))],
            # The old flags, as b0data's patterns would set them on some of these rows.
            "income_restricted": [False, False, False, True, False, False]
            + [False] * 6
            + [True],
            "shared_space": [False, False, True, False, False, True] + [False] * 7,
        }
    )
    d = tmp_path / "src"
    d.mkdir()
    rows.to_parquet(d / "rows.parquet")
    rows.iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_textflags_adds_both_columns_from_each_listings_latest_description(
    src, tmp_path
):
    out = tmp_path / "out"
    manifest = b0textflags.textflags(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    before = pd.read_parquet(src / "rows.parquet")
    new = ["income_restricted_v2", "shared_space_v2"]
    pd.testing.assert_frame_equal(rows.drop(columns=new + b0textflags.TERMS), before)
    got = {i: (a, b) for i, a, b in zip(rows.listing_id, *(rows[c] for c in new))}
    assert got == {
        1: (True, False),
        2: (False, True),
        3: (False, False),
        4: (False, False),  # too short to count as a description
        7: (False, False),  # the later record is a market ad
        8: (False, False),  # no description
        10: (False, False),  # no record
        11: (False, True),  # dated by collected_at alone
        12: (True, False),  # its first row group holds its latest record
        13: (True, False),  # its last row group holds its latest record
        14: (False, False),  # its only record has no time
        15: (False, False),  # "no income restrictions"
    }
    # Listing 1's description states its tier and a minimum income, and listings 12 and 13
    # state neither.
    one, rest = rows[rows.listing_id == 1], rows[rows.listing_id != 1]
    assert (one.ami_pct_text == 130).all() and (one.ami_tiers_text == 1).all()
    assert (one.income_min_text == 90_000).all() and one.income_max_text.isna().all()
    assert rest.ami_pct_text.isna().all() and (rest.ami_tiers_text == 0).all()
    assert rest.income_min_text.isna().all() and rest.income_max_text.isna().all()
    assert rows.ami_tiers_text.dtype == "int16"
    assert (out / "set_aside.parquet").exists()
    entry = manifest["textflags"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["listings_read"] == 10
    assert entry["rows_described"] == 9
    income, shared = (
        entry["columns"]["income_restricted_v2"],
        entry["columns"]["shared_space_v2"],
    )
    assert income["old_flag"] == "income_restricted"
    assert income["pattern"] == b0textflags.INCOME_V2.pattern
    assert income["negation"] == b0textflags.NEGATION.pattern
    # Listing 1's two rows and listings 12 and 13 gain, listings 3 and 15 lose.
    assert (income["rows_marked"], income["rows_gained"], income["rows_lost"]) == (
        4,
        4,
        2,
    )
    # Listing 11 gains, listing 7 loses, listing 2 keeps its mark.
    assert (shared["rows_marked"], shared["rows_gained"], shared["rows_lost"]) == (
        2,
        1,
        1,
    )
    terms = entry["terms"]
    assert (terms["rows_with_ami_pct"], terms["rows_with_several_tiers"]) == (2, 0)
    assert (terms["rows_with_income_min"], terms["rows_with_income_max"]) == (2, 0)
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    with pytest.raises(FileExistsError):
        b0textflags.textflags(src, out)


def test_textflags_refuses_records_that_do_not_match_the_manifest(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0textflags.textflags(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()
