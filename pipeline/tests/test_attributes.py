import json

import pytest

from steps.attributes import project


def record(description, **details):
    """A record of a one-bedroom ad with `description`, and `details` updating its
    propertyDetails."""
    return json.dumps(
        {
            "id": 1,
            "description": description,
            "propertyDetails": {"bedroomCount": 1, **details},
        }
    )


ALLOWED = '"allowed_restrictions_unknown"'


@pytest.mark.parametrize(
    "description, details, policy",
    [
        ("Sunny one bedroom. Pet\n fee $500 at signing.", {}, ALLOWED),
        ("A deposit per dog of $300.", {}, ALLOWED),
        ("Charges for cats: $25 a month.", {}, ALLOWED),
        # No pet fee says the building takes pets as well.
        ("Cozy studio, no pet fees!", {}, ALLOWED),
        ("No broker fee, no deposit for the gym.", {}, None),
        # A ban wins over a fee.
        ("No pets. Pet deposit required.", {}, '"not_allowed"'),
        # Evidence for and against pets leaves the policy unknown, fee or not.
        ("No pets allowed. Pets welcome. Pet fee $500.", {}, None),
        # A policy from the codes or the description's own reading stays.
        (
            "Pets on approval, pet fee $500.",
            {"amenities": {"list": ["PETS_ALLOWED"]}},
            '"approval_required"',
        ),
    ],
)
def test_pet_fee(description, details, policy):
    """A pet fee in the description gives pets allowed when nothing else gives a policy."""
    _, values = project(record(description, **details))
    assert values["pet_policy"] == policy
