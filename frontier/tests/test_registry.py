import pytest
from rentfrontier.registry import distance_m, slug_address


@pytest.mark.parametrize(
    "slug, address",
    [
        ("136-west-17-street-new_york", "136 West 17 Street"),
        ("755-6-avenue-new_york", "755 6 Avenue"),
        ("beatrice-105-west-29th-street-new_york", "105 West 29th Street"),
        ("300-west-21st-st-new_york", "300 West 21st Street"),
        ("505-west-19th", "505 West 19th Street"),
        ("520-west-28th-by-zaha-hadid", "520 West 28th Street"),
        ("1-broadway-new_york", "1 Broadway"),
        ("ava-high-line", None),
        ("21-chelsea", None),
    ],
)
def test_slug_address(slug, address):
    assert slug_address(slug) == address


def test_distance_is_metres():
    # 0.001 degrees of latitude is about 111 m.
    assert distance_m(40.74, -74.0, 40.741, -74.0) == pytest.approx(111.2, rel=0.01)
