import pandas as pd
from rentfrontier import renovated


def test_says_renovated_needs_a_fresh_renovation():
    assert renovated.says_renovated("amazingly newly renovated loft")
    assert renovated.says_renovated("gut-renovated 2br")
    assert renovated.says_renovated("brand new renovation throughout")
    assert not renovated.says_renovated("renovated lobby")
    assert not renovated.says_renovated("renovations in 2010")


def test_since_last_ad_reads_only_the_units_earlier_ads():
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 5 + ["u2", "u2", "u3", "u3"],
            "source_listing_id": [1, 1, 2, 3, 4, 5, 6, 7, 8],
            "price_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-02-01",  # a later price of the same ad
                    "2021-01-01",
                    "2022-01-01",
                    "2023-01-01",
                    "2020-01-01",
                    "2021-01-01",
                    "2020-01-01",
                    "2020-01-01",  # first captured with the previous ad
                ]
            ),
        }
    )
    text = pd.Series(
        [
            "nice flat",
            "nice flat",
            "Newly renovated flat",  # renovated since ad 1
            "newly renovated flat",  # its previous ad already said so
            "gut renovated",  # previous ad said so too
            "",
            "newly renovated",  # previous ad had no text: unknown
            "flat",
            "newly renovated",  # same capture time: not later
        ]
    )
    out = renovated.flags(frame, text)
    assert out.renovated.tolist() == [0, 0, 1, 1, 1, 0, 1, 0, 1]
    assert out.since_last_ad.tolist() == [0, 0, 1, 0, 0, 0, 0, 0, 0]
