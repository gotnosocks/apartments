from apartments.granular_report import render_report


def test_render_report_has_denominators_and_quality_limits():
    text = render_report(
        {
            "tables": {"counts": {"listing_observations": 4, "event_mentions": 3}},
            "listing_observations": {
                "by_listing_type": {"rental": 3, "sale": 1},
                "distinct_listing_identities": 3,
                "source_pairs": {"rental": 2, "sale": 1, "unknown": 0},
                "missingness_by_listing_type": {
                    "rental": {
                        "bedrooms": 1,
                        "bathrooms": 0,
                        "square_feet": 0,
                        "room_count": 2,
                    },
                    "sale": {
                        "bedrooms": 0,
                        "bathrooms": 1,
                        "square_feet": 0,
                        "room_count": 0,
                    },
                },
                "json_completeness_by_listing_type": {
                    "rental": {
                        "features_json": {"missing": 1, "empty": 1, "nonempty": 1}
                    }
                },
                "attribute_disagreement_count": 1,
                "source_pair_attribute_disagreement_count": 2,
            },
            "event_mentions": {
                "price": {"positive": 2},
                "dates": {"parseable": 3},
                "years": {"min": 2020, "max": 2024},
                "event_key": {"rows": 3, "distinct": 2, "duplicate_rows": 1},
            },
            "numeric": {
                "listing_observations": {"bedrooms": {"non_null": 4, "invalid": 1}}
            },
            "provenance": {
                "snapshot": "/archive/input.sqlite3",
                "version": "granular-v1",
                "corrections": {"enabled": False, "record_count": 0},
            },
            "limitations": ["capture time"],
        }
    )
    assert "66.7%" in text
    assert "missing 1 (33.3%)" in text
    assert "Distinct typed listing identities" in text
    assert "not verified physical units" in text
    assert "do not back-join the latest attributes" in text
    assert "Numeric quality flags" in text
    assert "Source snapshot" in text
