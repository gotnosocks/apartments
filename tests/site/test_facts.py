"""Diagnostics reader (`facts.py`) and the rebuilt listing detail page."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from apartments.site import facts
from apartments.site.web import create_app

GROVE = "the-grove-250-west-19th-street-new_york"

AD_TYPES = {
    "listing_id": "VARCHAR",
    "source": "VARCHAR",
    "building": "VARCHAR",
    "address": "VARCHAR",
    "unit_id": "VARCHAR",
    "unit": "VARCHAR",
    "neighbourhood": "VARCHAR",
    "day": "DATE",
    "status": "VARCHAR",
    "bedrooms": "DOUBLE",
    "full_baths": "DOUBLE",
    "half_baths": "DOUBLE",
    "ask": "DOUBLE",
    "model_median": "DOUBLE",
    "model_lo95": "DOUBLE",
    "model_lo80": "DOUBLE",
    "model_lo50": "DOUBLE",
    "model_hi50": "DOUBLE",
    "model_hi80": "DOUBLE",
    "model_hi95": "DOUBLE",
    "gap": "DOUBLE",
    "pit": "DOUBLE",
    "z": "DOUBLE",
    "unit_ads": "BIGINT",
    "building_ads": "BIGINT",
    "basis": "VARCHAR",
    "prev_ask": "DOUBLE",
    "prev_day": "DATE",
    "prev_bedrooms": "DOUBLE",
    "square_feet": "DOUBLE",
    "floor": "DOUBLE",
    "months_free": "DOUBLE",
    "first_ask": "DOUBLE",
    "days_on_market": "DOUBLE",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "flags": "VARCHAR[]",
    "doorman": "VARCHAR",
}

HISTORY_TYPES = {
    "listing_id": "VARCHAR",
    "building": "VARCHAR",
    "unit_id": "VARCHAR",
    "unit": "VARCHAR",
    "day": "DATE",
    "ask": "DOUBLE",
    "bedrooms": "DOUBLE",
    "full_baths": "DOUBLE",
    "heldout": "BOOLEAN",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_parquet(path: Path, schema: dict[str, str], rows: list[dict]) -> None:
    names = list(schema)
    con = duckdb.connect()
    try:
        cols = ", ".join(f'"{k}" {t}' for k, t in schema.items())
        con.execute(f"CREATE TABLE t ({cols})")
        if rows:
            con.executemany(
                f"INSERT INTO t VALUES ({', '.join('?' * len(names))})",
                [[r.get(k) for k in names] for r in rows],
            )
        quoted = str(path).replace("'", "''")
        con.execute(f"COPY t TO '{quoted}' (FORMAT parquet)")
    finally:
        con.close()


def ad_row(listing_id: str = "1004", **overrides) -> dict:
    base = {
        "listing_id": listing_id,
        "source": "market",
        "building": GROVE,
        "address": "250 West 19th Street",
        "unit_id": "u-1004",
        "unit": "11C",
        "neighbourhood": "chelsea",
        "day": "2026-11-09",
        "status": "ACTIVE",
        "bedrooms": 1.0,
        "full_baths": 1.0,
        "half_baths": 0.0,
        "ask": 3500.0,
        "model_median": 3400.0,
        "model_lo95": 2380.0,
        "model_lo80": 2720.0,
        "model_lo50": 3060.0,
        "model_hi50": 3740.0,
        "model_hi80": 4080.0,
        "model_hi95": 4420.0,
        "gap": 0.029,
        "pit": 0.6,
        "z": 0.25,
        "unit_ads": 2,
        "building_ads": 14,
        "basis": "unit",
        "prev_ask": 3300.0,
        "prev_day": "2024-06-01",
        "prev_bedrooms": 1.0,
        "square_feet": 680.0,
        "floor": 11.0,
        "months_free": 0.0,
        "first_ask": 3800.0,
        "days_on_market": 19.0,
        "latitude": 40.742,
        "longitude": -73.997,
        "flags": ["ppsf", "ask_jump"],
        "doorman": "full-time",
    }
    return base | overrides


def history_row(
    listing_id: str,
    building: str = GROVE,
    unit_id: str = "u-1004",
    unit: str = "11C",
    day: str = "2024-06-01",
    ask: float = 3300.0,
    bedrooms: float = 1.0,
    full_baths: float = 1.0,
    heldout: bool = False,
) -> dict:
    return {
        "listing_id": listing_id,
        "building": building,
        "unit_id": unit_id,
        "unit": unit,
        "day": day,
        "ask": ask,
        "bedrooms": bedrooms,
        "full_baths": full_baths,
        "heldout": heldout,
    }


def write_diagnostics(
    root: Path,
    ads: list[dict] | None = None,
    history: list[dict] | None = None,
    sha_override: dict[str, str] | None = None,
    sha_style: str = "dict",
) -> Path:
    folder = root / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    ads_path = folder / "ads.parquet"
    hist_path = folder / "history.parquet"
    _write_parquet(ads_path, AD_TYPES, [ad_row()] if ads is None else ads)
    default_history = [
        history_row("901", day="2022-05-01", ask=3000.0),
        history_row("902", day="2024-06-01", ask=3300.0),
        history_row(
            "1001",
            unit_id="u-1001",
            unit="4A",
            day="2021-06-01",
            ask=2600.0,
            heldout=True,
        ),
        history_row(
            "905",
            unit_id="u-905",
            unit="7B",
            day="2025-03-15",
            ask=3450.0,
            heldout=False,
        ),
        history_row(
            "1002",
            unit_id="u-1002",
            unit="2A",
            day="2024-01-01",
            ask=5200.0,
            bedrooms=2.0,
            heldout=True,
        ),
    ]
    _write_parquet(
        hist_path, HISTORY_TYPES, default_history if history is None else history
    )
    shas = {
        "ads.parquet": _sha256(ads_path),
        "history.parquet": _sha256(hist_path),
    }
    if sha_override:
        shas.update(sha_override)
    meta: dict = {
        "model": "drift-building",
        "scoring_day": "2026-11-09",
        "published": "2026-11-10T12:00:00Z",
        "features": [
            {
                "name": "square_feet",
                "label": "Square feet",
                "kind": "number",
                "level": "ad",
            },
            {"name": "floor", "label": "Floor", "kind": "number", "level": "unit"},
            {
                "name": "months_free",
                "label": "Free months",
                "kind": "number",
                "level": "ad",
            },
            {
                "name": "days_on_market",
                "label": "Days on market",
                "kind": "number",
                "level": "ad",
            },
            {
                "name": "doorman",
                "label": "Doorman",
                "kind": "category",
                "level": "building",
            },
        ],
    }
    if sha_style == "stem":
        meta["sha256"] = {
            "ads": shas["ads.parquet"],
            "history": shas["history.parquet"],
        }
    elif sha_style == "flat":
        meta["ads_sha256"] = shas["ads.parquet"]
        meta["history_sha256"] = shas["history.parquet"]
    else:
        meta["sha256"] = shas
    (folder / "meta.json").write_text(json.dumps(meta, indent=2))
    return folder


def test_absent_folder_returns_none_and_listing_page_renders(client, site_root):
    assert facts.load(site_root) is None
    page = client.get("/listings/1004").get_data(as_text=True)
    main = page.split('<main id="main"', 1)[1]
    # The tag card follows the header block and holds the no-JS tag form.
    card = main.index('<section class="card tag-card" id="tags" data-listing="1004"')
    assert main.index('id="range"') < card < main.index('id="the-ad"')
    assert "Your tag for this ad</h2>" in main[card:]
    # One range bar, no duplicate quantile table, no repeating figure cards.
    assert page.count('class="istrip"') == 1
    assert 'class="figures"' not in page
    assert "Half of expected asks (50%)" not in page
    # Run name and convergence appear only inside collapsed Technical details.
    before_details, details_block = page.split(
        "<summary>Technical details</summary>", 1
    )
    assert "drift-market-run" not in before_details
    assert "convergence test" not in before_details
    assert "drift-market-run" in details_block
    assert "passed the convergence test" in details_block
    # Panels stand cleanly when diagnostics are absent.
    assert 'id="the-ad"' in page and "not published yet" in page
    assert 'id="evidence"' in page and 'id="basis"' in page


@pytest.mark.parametrize("sha_style", ["dict", "stem", "flat"])
def test_load_accepts_sha_formats_and_refuses_mismatch(
    tmp_path, write_estimates, sha_style
):
    root = tmp_path / "site"
    write_estimates(root)
    write_diagnostics(root, sha_style=sha_style)
    loaded = facts.load(root)
    assert loaded is not None
    assert loaded.ad("1004")["unit"] == "11C"

    # A mismatched parquet hash refuses the folder with a 503.
    write_diagnostics(root, sha_override={"history.parquet": "0" * 64})
    with pytest.raises(facts.Refused):
        facts.load(root)
    client = create_app(root).test_client()
    response = client.get("/listings/1004")
    assert response.status_code == 503
    assert "do not match" in response.get_data(as_text=True)

    # Next clean publish replaces the refused stamp.
    write_diagnostics(root)
    assert client.get("/listings/1004").status_code == 200


def test_listing_page_shows_ad_facts_flags_and_building_evidence(client, site_root):
    write_diagnostics(site_root)
    page = client.get("/listings/1004").get_data(as_text=True)
    assert 'id="tags" data-listing="1004"' in page
    assert "250 West 19th Street · 11C" in page

    ad_panel = page.split('id="the-ad"', 1)[1].split("</section>", 1)[0]
    assert "680 ft²" in ad_panel
    assert "<dt>Floor</dt>" in ad_panel and "<dd>11</dd>" in ad_panel
    assert "$3,800 (cut $300, 8%)" in ad_panel
    assert "<dt>Days on market</dt>" in ad_panel and "<dd>19</dd>" in ad_panel
    assert "<dt>Doorman</dt>" in ad_panel and "<dd>full-time</dd>" in ad_panel
    assert "price/ft²" in ad_panel and "ask jump" in ad_panel

    ev_panel = page.split('id="evidence"', 1)[1].split("</section>", 1)[0]
    assert (
        "From <strong>2</strong> earlier ads the model trained on for this unit"
        in ev_panel
    )
    assert 'class="chart history-chart"' in ev_panel
    assert 'class="dot s2 this-ad"' in ev_panel
    # Unit's earlier ads table is newest first: Jun 1, 2024 before May 1, 2022.
    unit_table = ev_panel.split("<h3>This unit's earlier ads</h3>", 1)[1].split(
        "</table>", 1
    )[0]
    assert unit_table.index("Jun 1, 2024") < unit_table.index("May 1, 2022")
    # Same-bedroom (1 BR) ads in other units appear newest first; 2 BR ad 1002 is excluded.
    bldg_table = ev_panel.split("<h3>Other 1 BR ads in this building</h3>", 1)[1].split(
        "</table>", 1
    )[0]
    assert bldg_table.index("7B") < bldg_table.index("4A")
    assert 'href="/listings/1001"' in bldg_table
    assert "2A" not in bldg_table


def test_history_lists_are_capped_at_thirty_newest_first(tmp_path):
    root = tmp_path / "site"
    hist = [
        history_row(
            f"u-{i}",
            unit_id="u-1004",
            unit="11C",
            day=f"2023-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            ask=3000.0 + i,
        )
        for i in range(35)
    ] + [
        history_row(
            f"b-{i}",
            unit_id=f"other-{i}",
            unit=f"{i}B",
            day=f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            ask=3100.0 + i,
        )
        for i in range(35)
    ]
    write_diagnostics(root, history=hist)
    table = facts.load(root)
    assert table is not None
    ev = table.evidence(
        listing_id="1004",
        building=GROVE,
        unit_id="u-1004",
        bedrooms=1.0,
        current_day="2026-11-09",
        current_ask=3500.0,
        beds_text="1 BR",
    )
    assert ev["unit_total"] == 35 and len(ev["unit_rows"]) == 30
    assert ev["building_total"] == 35 and len(ev["building_rows"]) == 30
    assert ev["unit_rows"][0]["day"] > ev["unit_rows"][-1]["day"]
    assert ev["building_rows"][0]["day"] > ev["building_rows"][-1]["day"]


def test_basis_sentence_and_unknown_flags():
    unit_text = str(facts.basis_sentence(3, 20, "unit"))
    bldg_text = str(facts.basis_sentence(0, 8, "building"))
    area_text = str(facts.basis_sentence(0, 2, "area"))
    assert "3" in unit_text and "narrower" in unit_text
    assert "8" in bldg_text and "training ads in the building" in bldg_text
    assert "only 2 training ads in the building" in area_text
    items = facts.flag_items(["ppsf", "ppsf", "future_detector"])
    assert [i["code"] for i in items] == ["ppsf", "future_detector"]
    assert items[1]["label"] == "future_detector"


def test_csv_cell_quotes_formula_text_and_leaves_numbers():
    assert facts.csv_cell('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert facts.csv_cell("@cmd") == "'@cmd"
    assert facts.csv_cell("-2 West Street") == "'-2 West Street"
    assert facts.csv_cell("12 West Street") == "12 West Street"
    assert facts.csv_cell(-1.5) == -1.5
    assert facts.csv_cell(None) is None


def test_building_chart_data_escapes_angle_brackets():
    series = [
        {
            "listing_id": "905",
            "unit_id": "u-905",
            "unit": "7B</script><script>alert(1)",
            "day": "2025-03-15",
            "ask": 3450.0,
        }
    ]
    svg = str(
        facts.building_asks_svg(
            series,
            listing_id="1004",
            unit_id="u-1004",
            current_day="2026-11-09",
            current_ask=3500.0,
            beds_text="1 BR",
        )
    )
    embedded = svg.split('<script type="application/json"', 1)[1]
    data = embedded.split(">", 1)[1].split("</script>", 1)[0]
    assert "<" not in data and "7B\\u003c/script" in data
    assert svg.count("</script>") == 1 and "<script>alert" not in svg
