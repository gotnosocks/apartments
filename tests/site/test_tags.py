"""The append-only tag ledger (`tags.py`), HTTP endpoints, exports and concurrency."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest

from apartments.site import tags
from apartments.site.web import create_app

GROVE = "the-grove-250-west-19th-street-new_york"


def _write_diag(root: Path) -> None:
    folder = root / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    ads_path = folder / "ads.parquet"
    hist_path = folder / "history.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TABLE a (listing_id VARCHAR, source VARCHAR, building VARCHAR, "
            "address VARCHAR, unit VARCHAR, day DATE, bedrooms DOUBLE, ask DOUBLE, "
            "model_median DOUBLE, miss DOUBLE, flags VARCHAR[], unit_id VARCHAR, "
            "square_feet DOUBLE, floor DOUBLE, prev_ask DOUBLE, prev_bedrooms DOUBLE)"
        )
        con.execute(
            "INSERT INTO a VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "1004",
                "market",
                GROVE,
                "250 West 19th Street",
                "11C",
                "2026-11-09",
                1.0,
                3500.0,
                4200.0,
                -1.85,
                ["ppsf", "ask_jump"],
                "u-1004",
                680.0,
                11.0,
                3300.0,
                2.0,
            ],
        )
        con.execute(f"COPY a TO '{ads_path}' (FORMAT parquet)")
        con.execute(
            "CREATE TABLE h (listing_id VARCHAR, building VARCHAR, unit_id VARCHAR, "
            "unit VARCHAR, day DATE, ask DOUBLE, bedrooms DOUBLE, full_baths DOUBLE, "
            "heldout BOOLEAN)"
        )
        con.execute(f"COPY h TO '{hist_path}' (FORMAT parquet)")
    finally:
        con.close()
    meta = {
        "model": "drift-building",
        "sha256": {
            "ads": hashlib.sha256(ads_path.read_bytes()).hexdigest(),
            "history": hashlib.sha256(hist_path.read_bytes()).hexdigest(),
        },
    }
    (folder / "meta.json").write_text(json.dumps(meta))


def test_vocabulary_append_snapshot_clear_and_cache(site_root):
    expected_codes = {
        "deal",
        "wrong_beds",
        "wrong_price",
        "wrong_unit",
        "not_apartment",
        "restricted",
        "duplicate",
        "data_other",
        "condition",
        "size_layout",
        "light_view_noise",
        "short_term",
        "fees_concession",
        "unmodeled_other",
    }
    assert set(tags.BY_CODE) == expected_codes
    assert not (site_root / "tags").exists()
    assert tags.current_tags(site_root) == {}

    # Without diagnostics, append creates the folder and records core fields.
    first = tags.append(site_root, "1001", "deal", "  bright corner  " + ("x" * 600))
    assert (site_root / "tags" / "tags.jsonl").is_file()
    assert len(first["note"]) == 500
    assert first["at"].endswith("Z") and len(first["at"]) == 20

    # Cached Ledger instance is reused when (mtime_ns, size) is unchanged.
    ledger_a = tags.load_ledger(site_root)
    ledger_b = tags.load_ledger(site_root)
    assert ledger_a is ledger_b

    # With diagnostics, append snapshots the ad's fields at write time.
    _write_diag(site_root)
    tags.append(site_root, "1004", "wrong_beds", "alcove studio")
    raw_line = json.loads(tags.ledger_path(site_root).read_text().splitlines()[-1])
    assert raw_line["address"] == "250 West 19th Street"
    assert raw_line["unit"] == "11C"
    assert raw_line["building"] == GROVE
    assert raw_line["bedrooms"] == 1.0
    assert raw_line["ask"] == 3500.0
    assert raw_line["model_median"] == 4200.0
    assert raw_line["miss"] == -1.85
    assert raw_line["flags"] == ["ppsf", "ask_jump"]
    assert raw_line["source"] == "market"
    assert raw_line["day"] == "2026-11-09"

    # Updating an earlier listing moves it to the top of newest-first order.
    tags.append(site_root, "1001", "condition", "dated kitchen")
    active = tags.current_tags(site_root)
    assert list(active) == ["1001", "1004"]
    assert active["1001"]["tag"] == "condition"

    # Clearing removes the active tag while keeping earlier lines for the listing.
    tags.append(site_root, "1004", "clear", "rechecked")
    assert list(tags.current_tags(site_root)) == ["1001"]
    cur_1004, earlier_1004 = tags.for_listing(site_root, "1004")
    assert cur_1004 is None
    assert [item["tag"] for item in earlier_1004] == ["clear", "wrong_beds"]


@pytest.mark.parametrize(
    ("listing_id", "code"),
    [
        ("", "deal"),
        ("abc", "deal"),
        ("12a", "deal"),
        ("-5", "deal"),
        ("١٢٣", "deal"),
        ("1004", ""),
        ("1004", "unknown_code"),
    ],
)
def test_bad_inputs_rejected(client, site_root, listing_id, code):
    with pytest.raises(tags.BadInput):
        tags.append(site_root, listing_id, code)
    resp = client.post("/tags", data={"listing_id": listing_id, "tag": code})
    assert resp.status_code == 400
    json_resp = client.post(
        "/tags",
        data={"listing_id": listing_id, "tag": code},
        headers={"Accept": "application/json"},
    )
    assert json_resp.status_code == 400
    assert "error" in json_resp.get_json()


def test_cross_origin_refusal_and_redirect_or_json_answers(client, site_root):
    # Cross-origin Origin, null Origin, and cross-origin Referer all return 403.
    for headers in (
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Referer": "https://evil.example/attack"},
        {"Origin": "https://evil.example", "Accept": "application/json"},
    ):
        denied = client.post(
            "/tags",
            data={"listing_id": "1004", "tag": "deal"},
            headers=headers,
        )
        assert denied.status_code == 403
    assert tags.current_tags(site_root) == {}

    # Same-host Origin/Referer with local `next` redirects 303 to `next`.
    ok = client.post(
        "/tags",
        data={
            "listing_id": "1004",
            "tag": "wrong_price",
            "note": "gross rent recorded",
            "next": "/deals?hood=Chelsea&page=2",
        },
        headers={
            "Origin": "http://localhost",
            "Referer": "http://localhost/deals?hood=Chelsea&page=2",
        },
    )
    assert ok.status_code == 303
    assert ok.headers["Location"].endswith("/deals?hood=Chelsea&page=2")

    # Unsafe external `next` falls back to `/listings/<id>`.
    for unsafe_next in ("https://evil.example/x", "//evil.example/x", "deals"):
        redir = client.post(
            "/tags",
            data={"listing_id": "1004", "tag": "deal", "next": unsafe_next},
        )
        assert redir.status_code == 303
        assert redir.headers["Location"].endswith("/listings/1004")

    # `Accept: application/json` returns `{listing_id, tag, label, group, note, at}`.
    js = client.post(
        "/tags",
        data={"listing_id": "1004", "tag": "short_term", "note": "3-month sublet"},
        headers={"Accept": "application/json"},
    )
    assert js.status_code == 200
    payload = js.get_json()
    assert payload["listing_id"] == "1004"
    assert payload["tag"] == "short_term"
    assert payload["label"] == "Short lease or furnished"
    assert payload["group"] == "unmodeled"
    assert payload["note"] == "3-month sublet"
    assert payload["at"].endswith("Z")

    # Listing page renders `tag_form` and earlier ledger lines inside `#tags`.
    listing_html = client.get("/listings/1004").get_data(as_text=True)
    tags_box = listing_html.split('id="tags" data-listing="1004"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "Your tag for this ad</h2>" in tags_box
    assert 'name="next" value="/listings/1004#tags"' in tags_box
    assert "<optgroup" in tags_box
    assert "Short lease or furnished" in tags_box
    assert 'class="tag-history"' in tags_box
    assert "gross rent recorded" in tags_box


def test_tags_for_ledger_page_and_exports(client, site_root):
    _write_diag(site_root)
    tags.append(site_root, "1004", "wrong_beds", "first note")
    tags.append(site_root, "1004", "not_apartment", "parking space")
    tags.append(site_root, "1001", "deal", "bright 1BR")
    tags.append(site_root, "1002", "condition", "needs paint")
    tags.append(site_root, "1002", "clear", "mistaken id")

    # Batch lookup `/tags/for` returns active tags + vocabulary and enforces 300 cap.
    batch = client.get("/tags/for?ids=1004,1001,1002,9999").get_json()
    assert set(batch["tags"]) == {"1004", "1001"}
    assert batch["tags"]["1004"]["tag"] == "not_apartment"
    assert len(batch["vocabulary"]) == 14
    too_many = ",".join(str(i) for i in range(1, 302))
    assert client.get(f"/tags/for?ids={too_many}").status_code == 400
    assert client.get("/tags/for?ids=1004,bad").status_code == 400

    # Ledger page shows counts, newest-first rows, snapshot fields and filters.
    ledger_html = client.get("/tags").get_data(as_text=True)
    assert "Deal (1)" in ledger_html and "Data error (1)" in ledger_html
    assert "Unmodeled (0)" in ledger_html
    assert 'href="/listings/1004"' in ledger_html
    assert "250 West 19th Street · 11C" in ledger_html
    assert "parking space" in ledger_html
    assert "$3,500" in ledger_html and "$4,200" in ledger_html
    assert "−1.85" in ledger_html and "price/ft²" in ledger_html
    assert "/tags.csv" in ledger_html and "/tags.jsonl" in ledger_html

    only_errors = client.get("/tags?group=data_error").get_data(as_text=True)
    assert "250 West 19th Street" in only_errors and "bright 1BR" not in only_errors
    only_deal = client.get("/tags?tag=deal").get_data(as_text=True)
    assert "bright 1BR" in only_deal and "parking space" not in only_deal

    # JSONL and CSV exports: active tags by default, every line with `?all=1`.
    jsonl_cur = [
        json.loads(line)
        for line in client.get("/tags.jsonl").get_data(as_text=True).splitlines()
    ]
    assert [r["listing_id"] for r in jsonl_cur] == ["1001", "1004"]
    assert jsonl_cur[1]["miss"] == -1.85

    jsonl_all = [
        json.loads(line)
        for line in client.get("/tags.jsonl?all=1").get_data(as_text=True).splitlines()
    ]
    assert len(jsonl_all) == 5
    assert jsonl_all[-1]["tag"] == "clear"

    csv_cur = list(
        csv.DictReader(io.StringIO(client.get("/tags.csv").get_data(as_text=True)))
    )
    assert [r["listing_id"] for r in csv_cur] == ["1001", "1004"]
    assert csv_cur[1]["flags"] == "ppsf;ask_jump"

    csv_all = list(
        csv.DictReader(
            io.StringIO(client.get("/tags.csv?all=1").get_data(as_text=True))
        )
    )
    assert len(csv_all) == 5


def test_concurrent_appends_preserve_every_json_line(tmp_path, write_estimates):
    root = tmp_path / "site"
    write_estimates(root)
    barrier = threading.Barrier(2)

    def worker(idx: int) -> None:
        barrier.wait(timeout=5)
        for step in range(25):
            lid = str(2000 + idx * 100 + step)
            tags.append(
                root, lid, "deal" if idx == 0 else "wrong_beds", f"w{idx}-{step}"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, 0), pool.submit(worker, 1)]
        for fut in futures:
            fut.result()

    raw_lines = tags.ledger_path(root).read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 50
    parsed = [json.loads(line) for line in raw_lines]
    assert len({item["listing_id"] for item in parsed}) == 50
    app = create_app(root)
    assert len(tags.current_tags(root)) == 50
    assert app.test_client().get("/tags").status_code == 200


def test_append_starts_a_new_line_after_an_unfinished_one(tmp_path):
    root = tmp_path / "site"
    tags.append(root, "1001", "deal", "first")
    path = tags.ledger_path(root)
    # A writer stopped partway through a record, so the file ends without a newline.
    with path.open("ab") as handle:
        handle.write(b'{"listing_id":"1002","tag":"de')
    tags.append(root, "1003", "wrong_beds", "third")
    tags.append(root, "1004", "deal", "fourth")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and lines[1] == '{"listing_id":"1002","tag":"de'
    assert [json.loads(lines[i])["listing_id"] for i in (0, 2, 3)] == [
        "1001",
        "1003",
        "1004",
    ]
    assert set(tags.current_tags(root)) == {"1001", "1003", "1004"}


def test_eastern_times_carry_the_zone():
    assert tags.eastern("2026-11-10T21:05:09Z") == "2026-11-10 16:05 ET"
    # Daylight time, and a day that changes on the way to Eastern time.
    assert tags.eastern("2026-07-01T02:30:00Z") == "2026-06-30 22:30 ET"
    assert tags.eastern(None) == "" and tags.eastern("not a time") == "not a time"


def test_ledger_rows_clear_show_eastern_time_and_explain_columns(client, site_root):
    _write_diag(site_root)
    tags.append(site_root, "1004", "wrong_beds", "first note")
    stored = json.loads((site_root / "tags" / "tags.jsonl").read_text())
    assert stored["at"].endswith("Z")

    page = client.get("/tags?group=data_error").get_data(as_text=True)
    assert tags.eastern(stored["at"]) in page and stored["at"][:19] not in page
    for header in ("Miss", "Source"):
        assert re.search(
            rf'<th scope="col"[^>]* title="[^"]{{20,}}">{header}</th>', page
        )
    form = page.split('<td class="c-clear"', 1)[1].split("</td>", 1)[0]
    assert 'method="post" action="/tags"' in form
    assert 'name="listing_id" value="1004"' in form
    assert 'name="tag" value="clear"' in form
    assert 'name="next" value="/tags?group=data_error"' in form
    assert ">Clear</button>" in form

    cleared = client.post(
        "/tags",
        data={"listing_id": "1004", "tag": "clear", "next": "/tags?group=data_error"},
    )
    assert cleared.status_code == 303
    assert cleared.headers["Location"].endswith("/tags?group=data_error")
    assert 'href="/listings/1004"' not in client.get("/tags").get_data(as_text=True)


def test_exports_carry_the_ad_snapshot_taken_at_write_time(client, site_root):
    _write_diag(site_root)
    tags.append(site_root, "1004", "deal", "bright")
    expected = {
        "unit_id": "u-1004",
        "square_feet": 680.0,
        "floor": 11.0,
        "prev_ask": 3300.0,
        "prev_bedrooms": 2.0,
        "url": "https://streeteasy.com/rental/1004",
    }
    stored = json.loads((site_root / "tags" / "tags.jsonl").read_text())
    line = json.loads(client.get("/tags.jsonl").get_data(as_text=True))
    for key, value in expected.items():
        assert stored[key] == value
        assert line[key] == value
    row = next(
        csv.DictReader(io.StringIO(client.get("/tags.csv").get_data(as_text=True)))
    )
    assert row["unit_id"] == "u-1004" and row["url"] == expected["url"]
    assert float(row["square_feet"]) == 680.0 and float(row["floor"]) == 11.0
    assert float(row["prev_ask"]) == 3300.0 and float(row["prev_bedrooms"]) == 2.0

    # An ad the diagnostics lack keeps empty snapshot cells.
    tags.append(site_root, "1001", "deal", "")
    rows = list(
        csv.DictReader(io.StringIO(client.get("/tags.csv").get_data(as_text=True)))
    )
    bare = next(r for r in rows if r["listing_id"] == "1001")
    assert bare["unit_id"] == "" and bare["square_feet"] == ""


def test_compact_tagger_says_saved_after_a_save():
    script = (Path(tags.__file__).parent / "static" / "tags.js").read_text()
    assert '"Saved"' in script and '"Cleared"' in script
    assert 'setAttribute("role", "status")' in script
    assert "FLASH_MS" in script and "setTimeout" in script
