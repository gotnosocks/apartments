import pandas as pd

from rentfrontier import elevfill


def test_asof_elevator_reads_only_earlier_days_in_the_building():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "a", "b", "a"],
            "price_at": [
                "2020-01-05",
                "2020-01-01",
                "2020-01-05",
                "2020-01-09",
                "2020-01-09",
                "2020-01-03",
            ],
            "elevator": ["unknown", "unknown", "no", "unknown", "unknown", "yes"],
        }
    )
    out = elevfill.asof_elevator(frame)
    # Row 0 (Jan 5) sees Jan 3's "yes", not the same day's "no"; row 1 has no
    # earlier statement; row 3 (Jan 9) sees Jan 5's "no"; building b has none.
    assert out.elevator.tolist() == ["yes", "unknown", "no", "no", "unknown", "yes"]
    assert out.source.tolist() == ["building", "none", "own", "building", "none", "own"]
