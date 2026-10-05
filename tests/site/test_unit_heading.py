"""A unit is headed by the label its listings use most often."""

from apartments.site.build import unit_heading


def rows(*labels):
    return [{"unit_label": label} for label in labels]


def test_most_common_label_wins():
    assert unit_heading(rows("4U", "4U", "004U")) == "4U"


def test_ties_go_to_the_shorter_then_the_newest():
    assert unit_heading(rows("004U", "4U")) == "4U"
    assert unit_heading(rows("3A", "3B")) == "3B"


def test_no_labels():
    assert unit_heading(rows(None, None)) is None
