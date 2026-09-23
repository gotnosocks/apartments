"""Screen recall and evidence offsets; matches must not become scope decisions."""

import pytest

from docs.analysis.scripts.screen_commercial_offer_language import matches


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Loft available for all commercial uses", "commercial_word"),
        ("FULLY BUILT OUT RECORDING STUDIO READY TO GO", "recording_studio"),
        ("We are renting the space daily and weekly.", "daily_weekly"),
        (
            "Gallery/office commercial condo for showroom and retail events",
            "retail_showroom",
        ),
        (
            "2000 square feet of ground floor retail space for short term lease.",
            "retail_showroom",
        ),
        ("Small studio for Professional Use", "business_use"),
    ],
)
def test_known_scope_leads_are_retained(text, expected):
    assert expected in {m["pattern"] for m in matches(text)}


def test_context_and_unicode_offsets_preserve_negation_and_amenity_qualification():
    text = "🌆 Renovated home. No solely commercial uses; commercial-grade stove. Home office space."
    found = matches(text)
    assert len(found) == 3
    for m in found:
        assert text[m["start"] : m["end"]] == m["literal"]
        assert "No solely commercial uses" in m["context"]
        assert set(m) == {"pattern", "start", "end", "literal", "context"}


def test_no_match_is_not_an_assigned_residential_class():
    assert matches("A sunny apartment near a bakery.") == []
