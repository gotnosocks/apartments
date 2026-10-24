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
    "description, policy, text",
    [
        ("Sunny one bedroom. Pet\n fee $500 at signing.", None, ALLOWED),
        ("No broker fee, no deposit for the gym.", None, None),
        # The chain's evidence reads a ban, and the text reads one too.
        ("No pets. Pet deposit required.", '"not_allowed"', '"not_allowed"'),
        # Evidence for and against pets leaves the policy unknown, and the text reads the ban.
        ("No pets allowed. Pets welcome. Pet fee $500.", None, '"not_allowed"'),
        # The coded field has no level for a building taking cats and no dogs.
        ("Cats only, no dogs. Pet fee $25 a month.", None, None),
        (
            "Pets on approval, pet fee $500.",
            '"approval_required"',
            '"approval_required"',
        ),
    ],
)
def test_pet_text(description, policy, text):
    """The record's pet policy comes from the chain's reading, and `pet_policy_text` from the
    description's."""
    _, values = project(record(description))
    assert values["pet_policy"] == policy
    assert values["pet_policy_text"] == text


@pytest.mark.parametrize(
    "description, text",
    [
        ("A five-story walk-up.", "false"),
        ("Elevator building.", "true"),
        ("Steps from the park.", None),
    ],
)
def test_elevator_text(description, text):
    _, values = project(record(description))
    assert values["elevator_text"] == text
