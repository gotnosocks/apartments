import json

import pandas as pd

from rentfrontier import listing_outcomes as lo


def _raw(changes, price, status, on, off):
    return json.dumps(
        {
            "status": status,
            "onMarketAt": on,
            "offMarketAt": off,
            "pricing": {
                "price": price,
                "priceChanges": [
                    {"changedAt": f"2026-0{i + 1}-01T00:00:00Z", "price": p}
                    for i, p in enumerate(changes)
                ],
            },
        }
    )


def test_record_outcomes_counts_cuts_and_days():
    got = lo.record_outcomes(
        _raw(
            [5000, 4900, 4900, 4950, 4800], 4800, "RENTED", "2026-01-01", "2026-03-02"
        ),
        0.0,
    )
    assert got["first_ask"] == 5000 and got["final_ask"] == 4800
    assert (got["n_changes"], got["n_cuts"], got["n_raises"]) == (3, 2, 1)
    assert got["days_listed"] == 60 and not got["still_listed"]


def test_record_outcomes_counts_an_active_listing_to_its_capture():
    at = pd.Timestamp("2026-01-11", tz="UTC").timestamp()
    got = lo.record_outcomes(_raw([3000], 3000, "ACTIVE", "2026-01-01", None), at)
    assert got["still_listed"] and got["days_listed"] == 10 and got["n_cuts"] == 0


def test_attach_matches_on_source_listing_id(tmp_path):
    table = pd.DataFrame({"listing_id": ["7", "8"], **{c: [1, 2] for c in lo.COLUMNS}})
    table.to_parquet(tmp_path / "o.parquet")
    frame = pd.DataFrame({"source_listing_id": [8, 9]})
    got = lo.attach(frame, str(tmp_path / "o.parquet"))
    assert got.final_ask.iloc[0] == 2 and pd.isna(got.final_ask.iloc[1])


def test_record_outcomes_leaves_a_stale_off_market_day_uncounted():
    got = lo.record_outcomes(
        _raw([3000], 3000, "RENTED", "2026-02-01", "2026-01-01"), 0.0
    )
    assert got["days_listed"] is None
