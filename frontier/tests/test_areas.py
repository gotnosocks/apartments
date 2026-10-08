import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from rentfrontier import areas


def _page(title: str) -> str:
    return json.dumps(
        {"id": "1", "pageTitle": title, "area": "$79"}, separators=(",", ":")
    )


def test_page_area_reads_the_area_the_title_names():
    assert (
        areas.page_area(_page("16 West 16th Street in Flatiron : Sales")) == "Flatiron"
    )
    assert (
        areas.page_area(
            _page("The Vanguard Chelsea at 77 West 24th Street in Flatiron : Sales")
        )
        == "Flatiron"
    )
    assert (
        areas.page_area(_page("1 Irving Place in Gramercy Park : Sales"))
        == "Gramercy Park"
    )
    assert areas.page_area(_page("No area here")) is None
    assert areas.page_area(None) is None


def test_build_keeps_each_buildings_last_snapshot_in_the_two_areas(tmp_path):
    (tmp_path / "building_observations").mkdir()
    table = pa.Table.from_pandas(
        pd.DataFrame(
            {
                "snapshot_id": [1, 2, 1, 1, 1],
                "building_slug": ["a", "a", "b", "c", "d"],
                "latitude": [40.7, 40.7, 40.73, 40.67, 40.74],
                "longitude": [-73.99, -73.99, -73.98, -73.98, -73.99],
                "raw_building_json": [
                    _page("1 A St in Gramercy Park : x"),
                    _page("1 A St in Flatiron : x"),
                    _page("2 B St in Gramercy Park : x"),
                    _page("172 5th Avenue in Park Slope : x"),
                    None,
                ],
            }
        )
    )
    pq.write_table(table, tmp_path / "building_observations" / "part.parquet")
    out, left_out = areas.build(str(tmp_path))
    assert out[["building", "area"]].values.tolist() == [
        ["a", "Flatiron"],
        ["b", "Gramercy Park"],
    ]
    assert left_out == {"Park Slope": 1, "(no title)": 1}
