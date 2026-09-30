import pytest
from rentfrontier import registry
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


def test_apply_overrides_regeocodes_only_the_named_buildings(monkeypatch):
    import pandas as pd
    import pytest

    base = pd.DataFrame(
        {
            "building": ["a", "b"],
            "method": ["reverse", "address"],
            "query": [None, "1 West 1 Street"],
            "label": ["2 WEST 2 STREET", "1 WEST 1 STREET"],
            "bbl": ["1000010001", "1000020002"],
            "bin": ["1000001", "1000002"],
            "pad_version": ["25a", "25a"],
            "latitude": [40.0, 40.1],
            "longitude": [-74.0, -74.1],
            "distance_m": [30.0, 2.0],
        }
    )

    def fake_get(path, params):
        assert path == "search"
        return {
            "features": [
                # A near miss first: another house number on the street.
                {
                    "properties": {
                        "label": "5 WEST 3 STREET, New York, NY, USA",
                        "addendum": {"pad": {"bbl": "1", "bin": "1", "version": "26c"}},
                    },
                    "geometry": {"coordinates": [-74.2, 40.2]},
                },
                {
                    "properties": {
                        "label": "3 WEST 3 STREET, New York, NY, USA",
                        "addendum": {
                            "pad": {
                                "bbl": "1000037501",
                                "bin": "1000003",
                                "version": "26c",
                            }
                        },
                    },
                    "geometry": {"coordinates": [-74.3, 40.3]},
                },
            ]
        }

    monkeypatch.setattr(registry, "_get", fake_get)
    out = registry.apply_overrides(
        base, [{"building": "a", "address": "3 West 3 Street"}]
    )
    a = out.set_index("building").loc["a"]
    assert a.method == "override" and a.bbl == "1000037501" and a.bin == "1000003"
    assert a.query == "3 West 3 Street" and a.latitude == 40.3
    assert (
        out.set_index("building").loc["b"].to_dict()
        == base.set_index("building").loc["b"].to_dict()
    )
    with pytest.raises(SystemExit, match="not in the base registry"):
        registry.apply_overrides(
            base, [{"building": "z", "address": "3 West 3 Street"}]
        )
