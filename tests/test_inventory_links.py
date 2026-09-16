import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from apartments.inventory_links import build_inventory_links


def test_build_inventory_links_recovers_html_and_preserves_source(tmp_path: Path):
    source = tmp_path / "inventory_rows"
    source.mkdir()
    db = duckdb.connect()
    try:
        db.execute("""CREATE TABLE rows AS SELECT * FROM (VALUES
          (1::BIGINT, 0::BIGINT, NULL::VARCHAR, 'listing', '<tr><td><a href="/rental/12">12</a></td></tr>', '{"url":null}'),
          (1::BIGINT, 1::BIGINT, NULL::VARCHAR, 'closing', '<tr><a href="/closing/33">sold</a></tr>', '{"url":null}'),
          (1::BIGINT, 2::BIGINT, NULL::VARCHAR, 'listing', '<tr>no units available</tr>', '{"url":null}'),
          (1::BIGINT, 3::BIGINT, NULL::VARCHAR, 'listing', '<tr><a href="/rental/1">one</a><a href="/rental/2">two</a></tr>', '{"url":null}'),
          (1::BIGINT, 4::BIGINT, 'https://streeteasy.com/rental/99', 'listing', '<tr><a href="/rental/12">twelve</a></tr>', '{"url":"https://streeteasy.com/rental/99"}')
        ) x(snapshot_id,row_index,listing_url,row_kind,row_html,record_json)""")
        db.execute("COPY rows TO ? (FORMAT PARQUET)", [str(source / "part.parquet")])
    finally:
        db.close()
    report = build_inventory_links(tmp_path)
    rows = pq.read_table(tmp_path / "inventory_row_links" / "derived.parquet").to_pylist()
    assert report["rows"] == 5
    assert report["recovered_legacy_links"] == 2
    assert report["ambiguous"] == 1
    assert report["mismatched_nonnull_record_url"] == 1
    assert rows[0]["listing_url"].endswith("/rental/12")
    assert rows[1]["row_kind"] == "closing"
    assert rows[2]["row_kind"] == "placeholder"
    assert json.loads(rows[3]["candidate_urls_json"]) == ["https://streeteasy.com/rental/1", "https://streeteasy.com/rental/2"]
    assert pq.read_table(source / "part.parquet").num_rows == 5
