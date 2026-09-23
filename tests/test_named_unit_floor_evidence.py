"""Exact full own descriptions copied from the reviewed source issues artifact.

The fixed source hashes prevent accidental shortening of scope context. These
are advertisement claims, including disagreements with existing label proxies.
"""

import hashlib

import pytest

from apartments.attribute_evidence import (
    extract_attribute_evidence as extract,
    NAMED_UNIT_FLOOR_RULE,
)

REVIEWED_DESCRIPTIONS = {
    "4968706": (
        "4e4d07f0e23ba97138348692220176669787df6ea666458f6a19ac17d2150e25",
        "\nWelcome to Apartment 1C on the third floor at 300 West 17th Street - a stunning, one bedroom in the heart of Chelsea. This unique space features soaring ceilings, exposed brick walls, living room with lots of windows full of light, beautiful built in cabinets and expansive windows that flood the apartment with natural light. Enjoy the warmth of hardwood floors throughout, all stainless steel appliances in the well-appointed kitchen that includes a dishwasher. Lots of storage space! The apartment offers abundant storage with multiple closets and built-in shelves, with king size plus bedroom,, all located in a well-maintained elevator building. Ideally situated by Chelsea Market, Union Square Greenmarket, NYU, FIT, SVA, and Parsons, this location offers easy access to some of the city's most vibrant neighborhoods including Union Square, Greenwich Village, the Flatiron District, and the Meatpacking District. This is HDFC - Applicants who wish to qualify must meet the 120 percent Area Median Income (AMI) max income and use a guarantor if their income is below 40 times the rent. This is a rare opportunity to live in a character-filled loft with modern conveniences in one of Manhattan's most desirable areas. No board approval $20 application fee that's it.",
        3,
    ),
    "4810936": (
        "36aa300bf16d51fac6e8d3e5c125c932bb01a57ffc1356869e1f9e86a1ecc81d",
        "Welcome to Apartment 1A on the second floor at 300 West 17th Street - a stunning, one bedroom in the heart of Chelsea. This one bedroom can easily be flexed into a two bedroom with a temp wall. This unique space features soaring ceilings, exposed brick walls, living room with beautiful built in cabinets and expansive windows that flood the apartment with natural light. Enjoy the warmth of hardwood floors throughout, a convenient in-unit washer and dryer, and a newly installed dishwasher with all stainless steel appliances in the well-appointed kitchen. The apartment offers abundant storage with multiple closets and built-in shelves, all located in a well-maintained elevator building.\n\nIdeally situated by Chelsea Market, Union Square Greenmarket, NYU, FIT, SVA, and Parsons, this location offers easy access to some of the city's most vibrant neighborhoods including Union Square, Greenwich Village, the Flatiron District, and the Meatpacking District. This is HDFC - Applicants who wish to qualify must meet the 120 percent Area Median Income (AMI) and use a guarantor if their income is below 40 times the rent. This is a rare opportunity to live in a character-filled loft with modern conveniences in one of Manhattan's most desirable areas.\n\nNo board approval $20 application fee thats it.",
        2,
    ),
    "4817705": (
        "3b83d3e0a2fcffd76b7644f9da4011155bb4adbdf81565f6b03cf654c16c8a19",
        "Welcome to Apartment 2D on the third floor at 300 West 17th Street - a stunning, one bedroom in the heart of Chelsea. This unique space features soaring ceilings, exposed brick walls, living room with beautiful built in cabinets and expansive windows that flood the apartment with natural light. Enjoy the warmth of hardwood floors throughout,  all stainless steel appliances in the well-appointed kitchen. Lots of storage space! The apartment offers abundant storage with multiple closets and built-in shelves, all located in a well-maintained elevator building.\n\nIdeally situated by Chelsea Market, Union Square Greenmarket, NYU, FIT, SVA, and Parsons, this location offers easy access to some of the city's most vibrant neighborhoods including Union Square, Greenwich Village, the Flatiron District, and the Meatpacking District. This is HDFC - Applicants who wish to qualify must meet the 120 percent Area Median Income (AMI) maximum income and use a guarantor if their income is below 40 times the rent. This is a rare opportunity to live in a character-filled loft with modern conveniences in one of Manhattan's most desirable areas.\nNo board approval $20 application fee thats it.\n",
        3,
    ),
    "4902655": (
        "5e31093fc62ae5da9572e8cc12f93cf0ea16afd078f8cc9e126b03289df0e153",
        "Welcome to Apartment 1b on the second floor at 300 West 17th Street - a stunning, one bedroom in the heart of Chelsea. This two bedroom has a wonderful pre war charm. This unique space features living room with expansive windows that flood the apartment with natural light. Enjoy the warmth of hardwood floors throughout, a renovated kitchen with a kitchen window and all new stainless steel appliances in the well-appointed kitchen including dishwasher. The apartment offers abundant storage with multiple closets and built-in shelves, all located in a well-maintained elevator building.\n\nIdeally situated by Chelsea Market, Union Square Greenmarket, NYU, FIT, SVA, and Parsons, this location offers easy access to some of the city's most vibrant neighborhoods including Union Square, Greenwich Village, the Flatiron District, and the Meatpacking District. \n\nThis is HDFC - Applicants who wish to qualify must meet the max income per house hold of 120 percent Area Median Income (AMI) and use a guarantor if their income is below 40 times the rent. This is a rare opportunity to live in a character-filled loft with modern conveniences in one of Manhattan's most desirable areas.\nNo board approval $20 application fee that's it.\n\n",
        2,
    ),
}


def floor_claims(result):
    return [e for e in result["evidence"] if e["attribute"] == "advertised_floor"]


@pytest.mark.parametrize("ad", sorted(REVIEWED_DESCRIPTIONS))
def test_full_reviewed_own_descriptions_with_exact_hashes_and_spans(ad):
    checksum, description, floor = REVIEWED_DESCRIPTIONS[ad]
    assert hashlib.sha256(description.encode()).hexdigest() == checksum
    result = extract({"description": description})
    assert result["version"] == "attribute-evidence-v8"
    assert result["attributes"]["advertised_floor"] == floor
    assert result["attributes"]["physical_floor"] is None
    assert result["attributes"]["floors_above_ground"] is None
    (claim,) = floor_claims(result)
    assert claim["rule"] == NAMED_UNIT_FLOOR_RULE
    assert claim["source_path"] == "/description"
    assert claim["start"] == description.index("Apartment")
    assert description[claim["start"] : claim["end"]] == claim["literal"]
    assert claim["literal"].startswith("Apartment ")
    assert claim["literal"].endswith(" floor")


ORDINALS = (
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
    "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth"
).split()


@pytest.mark.parametrize(
    "ordinal,floor",
    list(zip(ORDINALS, range(1, 21)))
    + [
        ("1st", 1),
        ("2nd", 2),
        ("3rd", 3),
        ("4th", 4),
        ("11th", 11),
        ("12th", 12),
        ("13th", 13),
        ("21st", 21),
        ("102nd", 102),
        ("111th", 111),
        ("18", 18),
    ],
)
def test_explicit_floor_token_not_label_digits(ordinal, floor):
    result = extract(
        {
            "description": f"Welcome to Apartment 9B on the {ordinal} floor with bright windows."
        }
    )
    assert result["attributes"]["advertised_floor"] == floor


@pytest.mark.parametrize(
    "prefix", ["", "Welcome to ", "\n\tWelcome to ", "\r\n Welcome\tto\n"]
)
@pytest.mark.parametrize("dwelling", ["Apartment 1b", "UNIT #23", "Residence S9K"])
def test_optional_welcome_case_labels_and_whitespace_exact_offsets(prefix, dwelling):
    description = prefix + dwelling + " on third floor – sunny cafés nearby."
    result = extract({"description": description})
    (claim,) = floor_claims(result)
    assert claim["value"] == 3
    assert claim["start"] == len(prefix)
    assert description[claim["start"] : claim["end"]] == dwelling + " on third floor"


@pytest.mark.parametrize(
    "description",
    [
        "Photos: Welcome to Apartment 1A on the second floor.",
        "Model apartment: Apartment 1A on the second floor.",
        "This photo shows Apartment 1A on the second floor.",
        "Welcome to this Apartment 1A on the second floor.",
        "Welcome to model Apartment 1A on the second floor.",
        "Welcome to Apartment model on the second floor.",
        "Welcome to Apartment 1A on the second floor, a model unit for this building.",
        "Welcome to Apartment 1A on the second floor, shown as a reference for this unit.",
        "Welcome to Apartment 1A on the second floor in the photos of this apartment.",
        "Welcome to Apartment 1A on the second floor\nshown in the photos of this apartment.",
        "Welcome to Apartment 1A on the second floor, our shared residents lounge.",
        "Welcome to Apartment 1A on the second floor, now a fitness amenity.",
        "Welcome to Apartment 1A on the second floor, the building lobby.",
        "Welcome to Apartment 1A on the second floor, if available.",
        "Welcome to Apartment 1A on the second floor, which might become available.",
        "Welcome to Apartment 1A on the second floor, assuming this is correct.",
        "Welcome to Apartment 1A on the second floor, supposedly.",
        "Welcome to Apartment 1A on the second floor, perhaps.",
        "Welcome to Apartment 1A on the second floor, not the advertised residence.",
        "Welcome to Apartment 1A on the second floor, which isn't the offered unit.",
        "Welcome to Apartment 1A on the second floor, unlike this unit 2D.",
        "Welcome to Apartment 1A on the second floor rather than the offered 2B.",
        "Welcome to Apartment 1A on the second floor, compared with 2D.",
        "Welcome to Apartment 1A on the second floor, another unit in the building.",
        "Welcome to Apartment 1A on the second floor? Please confirm.",
        "Welcome! Apartment 1A on the second floor.",
        "Other unit features. Apartment 1A on the second floor.",
        "Building Amenities:\nApartment 1A on the second floor.",
        "Welcome to Apartment 1A. Walk up one flight.",
        "Welcome to Apartment 1A on the forth floor.",
        "Welcome to Apartment 1A on the twenty-first floor.",
        "Welcome to Apartment 1A on the 2st floor.",
        "Welcome to Apartment 1A on the 11st floor.",
        "Welcome to Apartment 1A on the zero floor.",
        "Welcome to Apartment 1A on the 0th floor.",
        "Second floor sunny apartment.",
        "Welcome to Apartment 1A on two flights.",
    ],
)
def test_reference_shared_uncertain_comparison_and_out_of_scope_intros(description):
    result = extract({"description": description})
    assert result["attributes"]["advertised_floor"] is None
    assert not floor_claims(result)


@pytest.mark.parametrize(
    "tail",
    [
        " Photos are of the same unit on the 3rd floor.",
        "\nModel photos show a similar layout.",
        " The shared gym is on the fifth floor.",
        " Other apartments are also available.",
        " No photos are available.",
    ],
)
def test_unrelated_later_sentences_do_not_suppress_initial_own_claim(tail):
    description = "Welcome to Apartment 1A on the second floor." + tail
    result = extract({"description": description})
    assert result["attributes"]["advertised_floor"] == 2
    assert [e["value"] for e in floor_claims(result)] == [2]


def test_structured_conflict_and_unrelated_attributes_are_preserved():
    raw = {
        "propertyDetails": {"floor": 1, "physicalFloor": 1, "bedroomCount": 2},
        "description": "Welcome to Apartment 1A on the second floor. In-unit laundry. Elevator building.",
    }
    result = extract(raw)
    assert result["attributes"]["advertised_floor"] is None
    assert result["conflicts"]["advertised_floor"] == [1, 2]
    assert result["attributes"]["physical_floor"] == 1
    assert result["attributes"]["bedrooms"] == 2
    assert result["attributes"]["laundry_type"] == "in_unit"
    assert result["attributes"]["elevator"] is True
    assert [e["source_path"] for e in floor_claims(result)] == [
        "/propertyDetails/floor",
        "/description",
    ]


def test_two_incompatible_own_description_claims_remain_conflicted():
    result = extract(
        {
            "description": "Apartment 1A on the second floor. This unit is on the 3rd floor."
        }
    )
    assert result["attributes"]["advertised_floor"] is None
    assert set(result["conflicts"]["advertised_floor"]) == {2, 3}
    assert len(floor_claims(result)) == 2
