"""Tests for the Workbench section (`apartments.site.workbench`)."""

from __future__ import annotations

import csv
import hashlib
import html as html_lib
import io
import json
import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import duckdb
import pytest
from markupsafe import escape

from apartments.site import tags, workbench
from apartments.site.web import create_app

GROVE = "the-grove-250-west-19th-street-new_york"
W23 = "134-west-23-street-new_york"
BANK = "10-bank-street-new_york"
BERRY = "55-berry-street-brooklyn"


def _feature(name, label, kind, level, *, in_model=False, after=False) -> dict:
    return {
        "name": name,
        "label": label,
        "kind": kind,
        "level": level,
        "in_model": in_model,
        "after": after,
    }


FEATURES = [
    _feature("square_feet", "Square feet", "number", "unit", in_model=True),
    _feature("floor", "Floor", "number", "unit", in_model=True),
    _feature("months_free", "Months free", "number", "ad"),
    _feature("days_on_market", "Days on market", "number", "ad", after=True),
    _feature("doorman_type", "Doorman", "category", "building"),
    _feature("has_outdoor", "Outdoor space", "flag", "unit"),
    _feature("year_built", "Year built", "number", "building", in_model=True),
]

AD_SCHEMA = {
    "listing_id": "VARCHAR",
    "source": "VARCHAR",
    "building": "VARCHAR",
    "address": "VARCHAR",
    "unit_id": "VARCHAR",
    "unit": "VARCHAR",
    "neighbourhood": "VARCHAR",
    "day": "VARCHAR",
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
    "miss": "DOUBLE",
    "z": "DOUBLE",
    "unit_ads": "BIGINT",
    "building_ads": "BIGINT",
    "basis": "VARCHAR",
    "prev_ask": "DOUBLE",
    "prev_day": "VARCHAR",
    "prev_bedrooms": "DOUBLE",
    "square_feet": "DOUBLE",
    "floor": "DOUBLE",
    "months_free": "DOUBLE",
    "first_ask": "DOUBLE",
    "days_on_market": "DOUBLE",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "flags": "VARCHAR[]",
    "doorman_type": "VARCHAR",
    "has_outdoor": "BOOLEAN",
    "year_built": "DOUBLE",
}

BUILDING_SCHEMA = {
    "building": "VARCHAR",
    "address": "VARCHAR",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "neighbourhood": "VARCHAR",
    "zone": "VARCHAR",
    "level": "DOUBLE",
    "level_sd": "DOUBLE",
    "train_ads": "BIGINT",
    "heldout_ads": "BIGINT",
    "heldout_gap": "DOUBLE",
    "heldout_miss": "DOUBLE",
    "heldout_z": "DOUBLE",
    "doorman_type": "VARCHAR",
    "year_built": "DOUBLE",
}

HISTORY_SCHEMA = {
    "listing_id": "VARCHAR",
    "building": "VARCHAR",
    "unit_id": "VARCHAR",
    "unit": "VARCHAR",
    "day": "VARCHAR",
    "ask": "DOUBLE",
    "bedrooms": "DOUBLE",
    "full_baths": "DOUBLE",
    "heldout": "BOOLEAN",
    "market": "BOOLEAN",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_parquet(path: Path, schema: dict[str, str], rows: list[dict]) -> None:
    names = list(schema)
    con = duckdb.connect()
    cols = ", ".join(f'"{k}" {t}' for k, t in schema.items())
    con.execute(f"CREATE TABLE t ({cols})")
    if rows:
        con.executemany(
            f"INSERT INTO t VALUES ({', '.join('?' * len(names))})",
            [[r.get(k) for k in names] for r in rows],
        )
    con.execute(f"COPY t TO '{path}' (FORMAT parquet)")
    con.close()


def make_ad_row(
    listing_id: str,
    *,
    source: str = "latest",
    building: str = GROVE,
    address: str = "250 West 19th Street",
    unit_id: str = "u1",
    unit: str = "11C",
    neighbourhood: str = "chelsea",
    day: str = "2026-06-01",
    bedrooms: float = 1.0,
    ask: float = 3000.0,
    model_median: float = 3000.0,
    z: float = 0.0,
    miss: float | None = None,
    unit_ads: int = 0,
    building_ads: int = 8,
    basis: str | None = None,
    prev_ask: float | None = None,
    prev_day: str | None = None,
    prev_bedrooms: float | None = None,
    square_feet: float | None = 700.0,
    floor: float | None = 5.0,
    months_free: float | None = 0.0,
    days_on_market: float | None = 14.0,
    flags: list[str] | None = None,
    doorman_type: str | None = "full_time",
    has_outdoor: bool | None = False,
    year_built: float | None = 1986.0,
) -> dict:
    gap = math.log(ask / model_median)
    if basis is None:
        basis = (
            "unit" if unit_ads > 0 else ("building" if building_ads >= 5 else "area")
        )
    pit = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return {
        "listing_id": listing_id,
        "source": source,
        "building": building,
        "address": address,
        "unit_id": unit_id,
        "unit": unit,
        "neighbourhood": neighbourhood,
        "day": day,
        "status": "ACTIVE" if source == "market" else "RENTED",
        "bedrooms": bedrooms,
        "full_baths": 1.0,
        "half_baths": 0.0,
        "ask": ask,
        "model_median": model_median,
        "model_lo95": round(model_median * 0.75, 0),
        "model_lo80": round(model_median * 0.85, 0),
        "model_lo50": round(model_median * 0.92, 0),
        "model_hi50": round(model_median * 1.08, 0),
        "model_hi80": round(model_median * 1.15, 0),
        "model_hi95": round(model_median * 1.25, 0),
        "gap": gap,
        "pit": pit,
        "miss": z if miss is None else miss,
        "z": z,
        "unit_ads": unit_ads,
        "building_ads": building_ads,
        "basis": basis,
        "prev_ask": prev_ask,
        "prev_day": prev_day,
        "prev_bedrooms": prev_bedrooms,
        "square_feet": square_feet,
        "floor": floor,
        "months_free": months_free,
        "first_ask": ask,
        "days_on_market": days_on_market,
        "latitude": 40.742,
        "longitude": -73.998,
        "flags": flags or [],
        "doorman_type": doorman_type,
        "has_outdoor": has_outdoor,
        "year_built": year_built,
    }


def default_ads() -> list[dict]:
    return [
        # 1001: extreme low ask, beds_jump, ask_jump (seen unit)
        make_ad_row(
            "1001",
            source="latest",
            building=GROVE,
            address="250 West 19th Street",
            unit_id="u1",
            unit="11-C",
            neighbourhood="chelsea",
            day="2026-06-01",
            bedrooms=2.0,
            ask=2000.0,
            model_median=4000.0,
            z=-4.5,
            unit_ads=2,
            building_ads=10,
            prev_ask=4100.0,
            prev_day="2024-05-01",
            prev_bedrooms=1.0,
            square_feet=500.0,
            floor=11.0,
            months_free=1.0,
            days_on_market=45.0,
            flags=["beds_conflict", "beds_jump", "ask_jump", "extreme"],
            doorman_type="full_time",
            has_outdoor=False,
            year_built=1986.0,
        ),
        # 1002: non-unit basis, large square_feet -> positive gap
        make_ad_row(
            "1002",
            source="latest",
            building=GROVE,
            address="250 West 19th Street",
            unit_id="u2",
            unit="2A",
            neighbourhood="chelsea",
            day="2026-07-01",
            bedrooms=2.0,
            ask=4800.0,
            model_median=4000.0,
            z=2.2,
            unit_ads=0,
            building_ads=10,
            square_feet=1100.0,
            floor=2.0,
            months_free=0.0,
            days_on_market=10.0,
            flags=[],
            doorman_type="full_time",
            has_outdoor=True,
            year_built=1986.0,
        ),
        # 1003: non-unit basis, small square_feet -> negative gap
        make_ad_row(
            "1003",
            source="latest",
            building=W23,
            address="134 West 23rd Street",
            unit_id="u3",
            unit="4F",
            neighbourhood="chelsea",
            day="2026-05-15",
            bedrooms=0.0,
            ask=2100.0,
            model_median=2500.0,
            z=-1.8,
            unit_ads=0,
            building_ads=6,
            square_feet=450.0,
            floor=4.0,
            months_free=0.0,
            days_on_market=20.0,
            flags=["ppsf"],
            doorman_type="none",
            has_outdoor=False,
            year_built=1920.0,
        ),
        # 1004: market ad, non-unit basis, large square_feet -> positive gap
        make_ad_row(
            "1004",
            source="market",
            building=BANK,
            address="10 Bank Street",
            unit_id="u4",
            unit="6B",
            neighbourhood="west-village",
            day="2026-11-09",
            bedrooms=3.0,
            ask=9200.0,
            model_median=8000.0,
            z=1.9,
            unit_ads=0,
            building_ads=8,
            square_feet=1250.0,
            floor=6.0,
            months_free=0.0,
            days_on_market=7.0,
            flags=["building_side"],
            doorman_type="full_time",
            has_outdoor=True,
            year_built=1960.0,
        ),
        # 1005: market ad, area basis, small square_feet -> negative gap
        make_ad_row(
            "1005",
            source="market",
            building=BERRY,
            address="55 Berry Street",
            unit_id="u5",
            unit="3L",
            neighbourhood="williamsburg",
            day="2026-11-08",
            bedrooms=1.0,
            ask=2700.0,
            model_median=3200.0,
            z=-1.6,
            unit_ads=0,
            building_ads=2,
            square_feet=520.0,
            floor=3.0,
            months_free=1.5,
            days_on_market=30.0,
            flags=[],
            doorman_type="none",
            has_outdoor=False,
            year_built=2010.0,
        ),
        # 1006: latest ad, area basis, missing square_feet and doorman
        make_ad_row(
            "1006",
            source="latest",
            building=BERRY,
            address="55 Berry Street",
            unit_id="u6",
            unit="1A",
            neighbourhood="williamsburg",
            day="2026-04-10",
            bedrooms=1.0,
            ask=3150.0,
            model_median=3100.0,
            z=0.3,
            unit_ads=0,
            building_ads=2,
            square_feet=None,
            floor=None,
            months_free=None,
            days_on_market=12.0,
            flags=[],
            doorman_type=None,
            has_outdoor=None,
            year_built=2010.0,
        ),
    ]


def default_buildings() -> list[dict]:
    return [
        {
            "building": GROVE,
            "address": "250 West 19th Street",
            "latitude": 40.742,
            "longitude": -73.998,
            "neighbourhood": "chelsea",
            "zone": "mn-chelsea-1",
            "level": 0.12,
            "level_sd": 0.03,
            "train_ads": 15,
            "heldout_ads": 6,
            "heldout_gap": -0.18,
            "heldout_miss": -2.5,
            "heldout_z": -2.5,
            "doorman_type": "full_time",
            "year_built": 1986.0,
        },
        {
            "building": W23,
            "address": "134 West 23rd Street",
            "latitude": 40.743,
            "longitude": -73.994,
            "neighbourhood": "chelsea",
            "zone": "mn-chelsea-1",
            "level": -0.08,
            "level_sd": 0.04,
            "train_ads": 6,
            "heldout_ads": 2,
            "heldout_gap": -0.10,
            "heldout_miss": -1.2,
            "heldout_z": -1.2,
            "doorman_type": "none",
            "year_built": 1920.0,
        },
        {
            "building": BANK,
            "address": "10 Bank Street",
            "latitude": 40.736,
            "longitude": -74.002,
            "neighbourhood": "west-village",
            "zone": "mn-wv-1",
            "level": 0.18,
            "level_sd": 0.03,
            "train_ads": 12,
            "heldout_ads": 5,
            "heldout_gap": 0.14,
            "heldout_miss": 1.9,
            "heldout_z": 1.9,
            "doorman_type": "full_time",
            "year_built": 1960.0,
        },
        {
            "building": BERRY,
            "address": "55 Berry Street",
            "latitude": 40.719,
            "longitude": -73.961,
            "neighbourhood": "williamsburg",
            "zone": "bk-wburg-1",
            "level": -0.05,
            "level_sd": 0.05,
            "train_ads": 2,
            "heldout_ads": 2,
            "heldout_gap": -0.07,
            "heldout_miss": -0.6,
            "heldout_z": -0.6,
            "doorman_type": "none",
            "year_built": 2010.0,
        },
    ]


def default_history() -> list[dict]:
    return [
        # Unit u1 in GROVE: 3 ads, label mismatch (11c vs 11-C), bed conflict (1 vs 2)
        {
            "listing_id": "901",
            "building": GROVE,
            "unit_id": "u1",
            "unit": "11c",
            "day": "2022-05-01",
            "ask": 3800.0,
            "bedrooms": 1.0,
            "full_baths": 1.0,
            "heldout": False,
        },
        {
            "listing_id": "902",
            "building": GROVE,
            "unit_id": "u1",
            "unit": "11c",
            "day": "2024-05-01",
            "ask": 4100.0,
            "bedrooms": 1.0,
            "full_baths": 1.0,
            "heldout": False,
        },
        {
            "listing_id": "1001",
            "building": GROVE,
            "unit_id": "u1",
            "unit": "11-C",
            "day": "2026-06-01",
            "ask": 2000.0,
            "bedrooms": 2.0,
            "full_baths": 1.0,
            "heldout": True,
        },
        # Unit u2 in GROVE: clean unit
        {
            "listing_id": "1002",
            "building": GROVE,
            "unit_id": "u2",
            "unit": "2A",
            "day": "2026-07-01",
            "ask": 4800.0,
            "bedrooms": 2.0,
            "full_baths": 1.0,
            "heldout": True,
        },
        # Unit u3 in W23
        {
            "listing_id": "1003",
            "building": W23,
            "unit_id": "u3",
            "unit": "4F",
            "day": "2026-05-15",
            "ask": 2100.0,
            "bedrooms": 0.0,
            "full_baths": 1.0,
            "heldout": True,
        },
    ]


def write_diagnostics(
    root: Path,
    *,
    ads: list[dict] | None = None,
    buildings: list[dict] | None = None,
    history: list[dict] | None = None,
    features: list[dict] | None = None,
    sha_override: dict[str, str] | None = None,
) -> Path:
    folder = root / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    ads_rows = default_ads() if ads is None else ads
    bld_rows = default_buildings() if buildings is None else buildings
    hist_rows = default_history() if history is None else history

    _write_parquet(folder / "ads.parquet", AD_SCHEMA, ads_rows)
    _write_parquet(folder / "buildings.parquet", BUILDING_SCHEMA, bld_rows)
    _write_parquet(folder / "history.parquet", HISTORY_SCHEMA, hist_rows)

    shas = {
        "ads": _sha256(folder / "ads.parquet"),
        "buildings": _sha256(folder / "buildings.parquet"),
        "history": _sha256(folder / "history.parquet"),
    }
    if sha_override:
        shas.update(sha_override)

    meta = {
        "model": "drift-building",
        "runs": {"latest": "drift-latest-run", "market": "drift-market-run"},
        "datasets": {"latest": "latest-v1", "market": "market-v1"},
        "gate": {
            "latest": {"passes": True, "max_rhat": 1.004, "min_ess": 812.0},
            "market": {"passes": True, "max_rhat": 1.006, "min_ess": 655.0},
        },
        "scoring_day": "2026-11-09",
        "published": "2026-11-10T12:00:00Z",
        "features": FEATURES if features is None else features,
        "counts": {
            "ads": len(ads_rows),
            "buildings": len(bld_rows),
            "history": len(hist_rows),
        },
        "sha256": shas,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2))
    return folder


@pytest.fixture
def wb_client(tmp_path):
    root = tmp_path / "site"
    write_diagnostics(root)
    app = create_app(root)
    app.config["TESTING"] = True
    return app.test_client()


def _triage_ids(html: str) -> list[str]:
    return re.findall(r'href="/listings/(\d+)"', html)


def test_overview_counts_calibration_signals_and_flags(wb_client, monkeypatch):
    # The fixture holds 6 ads, so the marks need a lower floor to appear.
    monkeypatch.setattr(workbench, "MIN_CALIBRATION_ADS", 1)
    resp = wb_client.get("/workbench")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Counts by source and basis
    assert "drift-building" in html
    assert 'href="/workbench/triage?source=latest"' in html
    assert 'href="/workbench/triage?source=market"' in html
    assert 'href="/workbench/triage?basis=unit"' in html
    assert 'href="/workbench/triage?basis=building"' in html
    assert 'href="/workbench/triage?basis=area"' in html

    # Calibration table slices and off-nominal markings
    assert 'id="calibration"' in html
    assert "off nominal" in html
    assert 'class="off-nominal"' in html

    # Top signals with SVG dot-and-whisker strips
    assert 'id="top-signals"' in html
    assert "Square feet" in html and "Outdoor space" in html
    assert 'class="signal-strip"' in html

    # Detector flags linking to triage queue
    for flag, (label, rule) in workbench.FLAGS.items():
        assert f'href="/workbench/triage?flag={flag}"' in html
        assert f">{label}</a>" in html
        assert rule in html.replace("&#39;", "'")
    assert ">beds_jump<" not in html and ">building_side<" not in html

    # The complete neighbourhood table is collapsed.
    assert '<details class="table-view" id="calibration-hoods">' in html
    assert "All 3 neighbourhoods" in html

    # Signals with no model term lead the list, and each row shows its group.
    top = html[html.index('id="top-signals"') :]
    assert top.index("Outdoor space") < top.index("Square feet")
    assert "No term in the model" in top and "Already a term" in top


def test_small_slices_are_never_marked_off_nominal(wb_client):
    html = wb_client.get("/workbench").get_data(as_text=True)
    assert 'class="off-nominal"' not in html
    assert "few ads" in html


def test_overview_lists_only_off_nominal_neighbourhoods(tmp_path):
    root = tmp_path / "site"
    # 120 Chelsea asks far outside the ranges, and 120 West Village asks spread so
    # that 50%, 80% and 95% of them sit inside the matching ranges.
    spread = [3000.0] * 10 + [3360.0] * 6 + [3600.0] * 3 + [3900.0]
    ads = [
        make_ad_row(str(3000 + i), neighbourhood="chelsea", ask=6000.0)
        for i in range(120)
    ] + [
        make_ad_row(
            str(4000 + i),
            neighbourhood="west-village",
            building=BANK,
            ask=spread[i % 20],
        )
        for i in range(120)
    ]
    write_diagnostics(root, ads=ads)
    client = create_app(root).test_client()
    html = client.get("/workbench").get_data(as_text=True)
    shown, collapsed = html[html.index('id="calibration"') :].split(
        'id="calibration-hoods"', 1
    )
    assert "nb=chelsea" in shown and "nb=west-village" not in shown
    assert "nb=chelsea" in collapsed and "nb=west-village" in collapsed
    assert "1 of 2 neighbourhoods are off nominal" in shown


def test_signals_page_tabulates_features_and_clusters_se_by_building(wb_client):
    resp = wb_client.get("/workbench/signals")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    for f in FEATURES:
        assert f["label"] in html
        assert f'href="/workbench/signals/{f["name"]}"' in html
        assert f"<code>{f['name']}</code>" not in html
    assert 'class="signal-strip"' in html
    assert "<h1>Signals</h1>" in html

    # The table is split by whether the model has a term and by timing.
    none_at = html.index('id="signals-none"')
    term_at = html.index('id="signals-term"')
    after_at = html.index('id="signals-after"')
    assert none_at < term_at < after_at
    for heading, note in workbench.SIGNAL_GROUPS.values():
        assert heading in html and note in html
    assert none_at < html.index("Months free") < term_at
    assert term_at < html.index("Year built") < after_at
    assert after_at < html.index("Days on market")

    # Scope control: default is non_unit (basis != unit).
    # In non_unit scope, listing 1001 (basis=unit) is excluded, so 5 ads remain.
    assert "4 / 5" in html  # square_feet has 4 non-missing out of 5 non-unit ads

    # Switching scope to 'all' includes listing 1001 (6 total ads, 5 non-missing).
    all_html = wb_client.get("/workbench/signals?scope=all").get_data(as_text=True)
    assert "5 / 6" in all_html

    # Switching scope to 'market' keeps only the 2 market ads (1004 and 1005).
    mkt_html = wb_client.get("/workbench/signals?scope=market").get_data(as_text=True)
    assert "2 / 2" in mkt_html

    # Filtering by bedrooms and neighbourhood
    nb_html = wb_client.get("/workbench/signals?nb=Chelsea&beds=2").get_data(
        as_text=True
    )
    assert "1 / 1" in nb_html


def test_list_views_cap_a_many_level_category(tmp_path):
    root = tmp_path / "site"
    # 9 building classes of 40 ads in 10 buildings each, with gaps growing by class,
    # plus a class of 5 ads with the largest gap of all.
    ads = []
    for k in range(9):
        for i in range(40):
            row = make_ad_row(
                str(5000 + 100 * k + i),
                building=f"b-{k}-{i % 10}",
                doorman_type=f"class_{k}",
            )
            row["gap"] = 0.02 * k + 0.001 * (i % 10)
            ads.append(row)
    for i in range(5):
        row = make_ad_row(
            str(9000 + i), building=f"rare-{i}", doorman_type="class_rare"
        )
        row["gap"] = 0.9 + 0.01 * i
        ads.append(row)
    write_diagnostics(root, ads=ads)

    diag = workbench.load(root)
    signal = diag.signal_detail("doorman_type", workbench.SignalChoice())
    assert len(signal["bins"]) == 10
    assert signal["more_bins"] == 4
    listed = [b["key"] for b in signal["list_bins"]]
    assert len(listed) == workbench.LIST_BINS
    assert "class_rare" not in listed
    assert all(b["ads"] >= workbench.MIN_BIN_ADS for b in signal["list_bins"])
    ratios = [b["ratio"] for b in signal["list_bins"]]
    assert ratios == sorted(ratios, reverse=True)
    left_out = [b for b in signal["bins"] if b["key"] not in listed]
    assert max(b["ratio"] for b in left_out if b["sized"]) <= min(ratios)
    # The attribute's own page orders the sized bins by |mean| / SE, and the bin
    # below the size floor follows them with no score.
    assert signal["bins"][-1]["key"] == "class_rare"
    assert signal["bins"][-1]["ratio"] is None
    all_ratios = [b["ratio"] for b in signal["bins"][:-1]]
    assert all_ratios == sorted(all_ratios, reverse=True)

    client = create_app(root).test_client()
    listing = client.get("/workbench/signals").get_data(as_text=True)
    assert '<a href="/workbench/signals/doorman_type">and 4 more</a>' in listing
    detail = client.get("/workbench/signals/doorman_type").get_data(as_text=True)
    assert detail.count("feature=doorman_type&amp;bin=class_") >= 10


def test_repeat_requests_read_the_cached_aggregates(tmp_path, monkeypatch):
    root = tmp_path / "site"
    write_diagnostics(root)
    diag = workbench.load(root)
    calls = []
    tabulate = diag.tabulate_feature

    def counting(*args, **kwargs):
        calls.append(args[1]["name"])
        return tabulate(*args, **kwargs)

    monkeypatch.setattr(diag, "tabulate_feature", counting)
    choice = workbench.SignalChoice()
    first = diag.signals(choice)
    assert len(calls) == len(FEATURES)
    assert diag.signals(workbench.SignalChoice()) is first
    assert diag.calibration() is diag.calibration()
    assert len(calls) == len(FEATURES)

    # The cache holds at most CACHE_ENTRIES aggregates.
    for i in range(workbench.CACHE_ENTRIES + 10):
        diag._cached(("filler", i), lambda: i)
    assert len(diag._cache) == workbench.CACHE_ENTRIES

    # A new publish of the folder gets a new object and an empty cache.
    write_diagnostics(root, ads=default_ads()[:3])
    again = workbench.load(root)
    assert again is not diag and not again._cache


def test_cluster_se_matches_building_clustered_formula(tmp_path):
    root = tmp_path / "site"
    # Construct 4 ads in bin 'yes' across 2 buildings:
    # Building A has 2 ads with gap +0.10 and +0.20 (b_n=2, b_sum=0.30).
    # Building B has 2 ads with gap -0.10 and -0.10 (b_n=2, b_sum=-0.20).
    # Total N=4, G=2, overall bin mean = (0.30 - 0.20) / 4 = 0.025.
    # Building residuals u_g = b_sum - b_n * mean:
    # u_A = 0.30 - 2 * 0.025 = 0.25
    # u_B = -0.20 - 2 * 0.025 = -0.25
    # Cluster SE = sqrt(2 / 1 * (0.25^2 + (-0.25)^2)) / 4 = 0.125 (12.5%).
    ads = [
        make_ad_row(
            "1",
            building=GROVE,
            unit_ads=0,
            ask=3315.5,
            model_median=3000.0,
            has_outdoor=True,
        ),
        make_ad_row(
            "2",
            building=GROVE,
            unit_ads=0,
            ask=3664.2,
            model_median=3000.0,
            has_outdoor=True,
        ),
        make_ad_row(
            "3",
            building=W23,
            unit_ads=0,
            ask=2714.5,
            model_median=3000.0,
            has_outdoor=True,
        ),
        make_ad_row(
            "4",
            building=W23,
            unit_ads=0,
            ask=2714.5,
            model_median=3000.0,
            has_outdoor=True,
        ),
    ]
    # Set exact gaps so arithmetic is exact.
    for row, g in zip(ads, (0.10, 0.20, -0.10, -0.10), strict=True):
        row["gap"] = g
    write_diagnostics(root, ads=ads)
    diag = workbench.load(root)
    assert diag is not None
    detail = diag.signal_detail("has_outdoor", workbench.SignalChoice())
    yes_bin = next(b for b in detail["bins"] if b["key"] == "yes")
    assert yes_bin["ads"] == 4
    assert yes_bin["buildings"] == 2
    assert yes_bin["raw_mean"] == pytest.approx(0.025)
    # Every ad is in the bin, so the bin's mean equals the reference mean.
    assert detail["ref_mean"] == pytest.approx(0.025)
    assert yes_bin["mean"] == pytest.approx(0.0)
    assert yes_bin["se"] == pytest.approx(0.125)
    assert yes_bin["se_pct"] == pytest.approx(12.5)
    # 4 ads in 2 buildings are below the size floor, so the bin has no score.
    assert yes_bin["sized"] is False and yes_bin["ratio"] is None
    assert detail["strength"] is None and detail["peak_bin"] is None


def test_signal_detail_page_links_bins_to_triage(wb_client):
    resp = wb_client.get("/workbench/signals/square_feet")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Square feet" in html
    assert "Missing" in html
    assert "/workbench/triage?" in html
    assert "feature=square_feet" in html
    assert "bin=q1" in html and "bin=missing" in html

    # Unknown feature returns 404; SQL injection attempt is rejected.
    assert wb_client.get("/workbench/signals/not_a_feature").status_code == 404
    assert wb_client.get("/workbench/signals/ask;DROP%20TABLE%20ads").status_code == 404


def test_triage_orders_by_miss_where_z_has_saturated(tmp_path):
    root = tmp_path / "site"
    ads = [
        make_ad_row("1", z=3.5, miss=4.0),
        make_ad_row("2", z=3.5, miss=-9.0),
        make_ad_row("3", z=-3.5, miss=6.5),
    ]
    write_diagnostics(root, ads=ads)
    client = create_app(root).test_client()
    assert _triage_ids(client.get("/workbench/triage").get_data(as_text=True)) == [
        "2",
        "3",
        "1",
    ]
    page = client.get("/workbench/triage?min_miss=5").get_data(as_text=True)
    assert _triage_ids(page) == ["2", "3"]
    assert "Min |miss|" in page and 'name="min_z"' not in page
    assert "−9.0" in page and "+6.5" in page


def test_triage_queue_orders_by_abs_miss_and_filters(wb_client):
    page = wb_client.get("/workbench/triage").get_data(as_text=True)
    # Ordered by |miss| desc: 1001, 1002, 1004, 1003, 1005, 1006
    assert _triage_ids(page) == ["1001", "1002", "1004", "1003", "1005", "1006"]
    assert "<h1>Triage</h1>" in page
    assert f'<a href="/workbench/buildings/{GROVE}">building page</a>' in page
    assert f">{GROVE}<" not in page
    assert "$4,100" in page and "1 BR" in page  # prev_ask and prev_bedrooms on 1001
    # Flag chips show labels, with the rule in the title.
    assert ">beds_jump<" not in page and ">ask_jump<" not in page
    assert ">bedrooms changed</a>" in page and ">ask jumped</a>" in page
    assert f'title="{workbench.FLAGS["ask_jump"][1]}"'.replace("'", "&#39;") in page
    # Days read as dates, and the basis as words.
    assert "Jun 1, 2026" in page and "2026-06-01" not in page
    assert ">unit history<" in page and ">area<" in page
    # A quick link narrows the queue to the ads on the market.
    assert '<a href="/workbench/triage?source=market">On the market only</a>' in page
    # Every row carries a tag slot, and the page loads the tag script.
    assert page.count('class="c-tag tag-slot"') == 6
    assert 'data-listing="1001"' in page
    assert "tags.js" in page and 'action="/tags"' in page

    # Filter by source
    assert _triage_ids(
        wb_client.get("/workbench/triage?source=market").get_data(as_text=True)
    ) == ["1004", "1005"]
    # Filter by flag
    assert _triage_ids(
        wb_client.get("/workbench/triage?flag=ppsf").get_data(as_text=True)
    ) == ["1003"]
    # Filter by basis
    assert _triage_ids(
        wb_client.get("/workbench/triage?basis=unit").get_data(as_text=True)
    ) == ["1001"]
    assert _triage_ids(
        wb_client.get("/workbench/triage?basis=area").get_data(as_text=True)
    ) == ["1005", "1006"]
    # Filter by sign
    assert _triage_ids(
        wb_client.get("/workbench/triage?sign=high").get_data(as_text=True)
    ) == ["1002", "1004", "1006"]
    assert _triage_ids(
        wb_client.get("/workbench/triage?sign=low").get_data(as_text=True)
    ) == ["1001", "1003", "1005"]
    # Filter by bedrooms and neighbourhood
    assert _triage_ids(
        wb_client.get("/workbench/triage?beds=2&nb=Chelsea").get_data(as_text=True)
    ) == ["1001", "1002"]
    assert _triage_ids(
        wb_client.get("/workbench/triage?nb=Brooklyn").get_data(as_text=True)
    ) == ["1005", "1006"]
    # Filter by the size of the miss
    assert _triage_ids(
        wb_client.get("/workbench/triage?min_miss=2.0").get_data(as_text=True)
    ) == ["1001", "1002"]
    # Filter by feature bin from page 2 (flag, category, number, missing)
    assert _triage_ids(
        wb_client.get("/workbench/triage?feature=has_outdoor&bin=yes").get_data(
            as_text=True
        )
    ) == ["1002", "1004"]
    assert _triage_ids(
        wb_client.get("/workbench/triage?feature=doorman_type&bin=none").get_data(
            as_text=True
        )
    ) == ["1003", "1005"]
    assert _triage_ids(
        wb_client.get("/workbench/triage?feature=square_feet&bin=missing").get_data(
            as_text=True
        )
    ) == ["1006"]
    assert _triage_ids(
        wb_client.get(
            "/workbench/triage?feature=square_feet&bin=q1&basis=non_unit"
        ).get_data(as_text=True)
    ) == ["1003", "1005"]


def test_triage_paging_and_csv_download(tmp_path):
    root = tmp_path / "site"
    ads = [
        make_ad_row(
            str(2000 + i),
            z=float(120 - i) / 20.0,
            ask=3000.0 + i,
            model_median=3000.0,
            unit_ads=0,
        )
        for i in range(120)
    ]
    write_diagnostics(root, ads=ads)
    app = create_app(root)
    client = app.test_client()

    first = client.get("/workbench/triage").get_data(as_text=True)
    assert _triage_ids(first) == [str(2000 + i) for i in range(50)]
    assert "Page 1 of 3" in first

    third = client.get("/workbench/triage?page=3").get_data(as_text=True)
    assert _triage_ids(third) == [str(2000 + i) for i in range(100, 120)]

    csv_resp = client.get("/workbench/triage.csv?min_miss=5.0")
    assert csv_resp.status_code == 200
    assert csv_resp.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(csv_resp.get_data(as_text=True))))
    assert rows[0][0] == "listing_id"
    # miss >= 5.0 means (120 - i) / 20 >= 5.0 -> i <= 20 (21 rows + 1 header = 22 rows)
    assert len(rows) == 22


def test_buildings_page_orders_filters_and_tabulates_levels(wb_client):
    page = wb_client.get("/workbench/buildings").get_data(as_text=True)
    # The default order is |mean held-out miss| * sqrt(held-out ads):
    # GROVE: 2.5 * sqrt(6) = 6.12
    # BANK: 1.9 * sqrt(5) = 4.25
    # W23: 1.2 * sqrt(2) = 1.70
    # BERRY: 0.6 * sqrt(2) = 0.85
    # The default list holds the buildings with at least 5 held-out ads.
    links = re.findall(r'href="/workbench/buildings/([^"]+)"', page)
    assert links == [GROVE, BANK]
    assert 'name="min_ads" inputmode="numeric" size="5" value="5"' in page
    assert escape(workbench.MISS_SCORE_TITLE) in page
    assert "standard error" in workbench.MISS_SCORE_TITLE

    every = wb_client.get("/workbench/buildings?min_ads=1").get_data(as_text=True)
    links = re.findall(r'href="/workbench/buildings/([^"]+)"', every)
    assert links == [GROVE, BANK, W23, BERRY]
    assert 'size="5" value="1"' in every
    paged = workbench.BuildingChoice(min_ads=1, page=2).args()
    assert paged == {"min_ads": 1, "page": 2}
    assert workbench.BuildingChoice(page=2).args() == {"page": 2}

    # Sort by level descending: BANK (0.18), GROVE (0.12), BERRY (-0.05), W23 (-0.08)
    by_level = wb_client.get("/workbench/buildings?sort=level&min_ads=1").get_data(
        as_text=True
    )
    assert re.findall(r'href="/workbench/buildings/([^"]+)"', by_level) == [
        BANK,
        GROVE,
        BERRY,
        W23,
    ]

    # Filter by neighbourhood and min_ads
    filtered = wb_client.get("/workbench/buildings?nb=Chelsea&min_ads=5").get_data(
        as_text=True
    )
    assert re.findall(r'href="/workbench/buildings/([^"]+)"', filtered) == [GROVE]

    # Building level tabulated against building-level features
    assert 'id="building-level-signals"' in page
    assert "Doorman" in page and "Year built" in page


def test_buildings_page_when_fit_keeps_no_building_levels(tmp_path):
    root = tmp_path / "site"
    folder = write_diagnostics(root)
    # Rewrite buildings.parquet without zone, level, level_sd columns.
    # does when a run's building levels cannot be rebuilt.
    slim_schema = {
        k: v
        for k, v in BUILDING_SCHEMA.items()
        if k not in ("zone", "level", "level_sd")
    }
    _write_parquet(folder / "buildings.parquet", slim_schema, default_buildings())
    meta = json.loads((folder / "meta.json").read_text())
    meta["sha256"]["buildings"] = _sha256(folder / "buildings.parquet")
    (folder / "meta.json").write_text(json.dumps(meta))

    app = create_app(root)
    client = app.test_client()
    assert client.get("/workbench/buildings").status_code == 200
    assert client.get("/workbench/buildings?sort=level").status_code == 200
    assert client.get(f"/workbench/buildings/{GROVE}").status_code == 200


def test_single_building_page_scatter_unit_conflicts_and_heldout_ads(wb_client):
    resp = wb_client.get(f"/workbench/buildings/{GROVE}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Row of buildings.parquet and building-level features
    assert "250 West 19th Street" in html
    assert "mn-chelsea-1" in html
    assert "+12.0%" in html
    assert "full time" in html and "1986" in html
    assert "full_time" not in html and f"<code>{GROVE}</code>" not in html

    # SVG scatter from history.parquet: log scale, bedrooms, held-out ring, unit line
    assert 'class="history-scatter"' in html
    assert 'class="unit-line"' in html
    assert 'class="heldout-ring"' in html
    assert "beds-1" in html and "beds-2" in html

    # Units table showing label mismatch (11c / 11-C) and bedroom conflict (1 BR, 2 BR)
    assert "11c / 11-C" in html
    assert "bedroom conflict" in html
    assert "label mismatch" in html

    # Held-out ads table
    assert 'href="/listings/1001"' in html and 'href="/listings/1002"' in html
    assert html.count('class="c-tag tag-slot"') == 2
    assert "tags.js" in html
    assert ">extreme miss</a>" in html

    # Unknown building is a 404
    assert wb_client.get("/workbench/buildings/no-such-building").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/workbench",
        "/workbench/signals",
        "/workbench/signals/square_feet",
        "/workbench/triage",
        "/workbench/triage.csv",
        "/workbench/buildings",
        f"/workbench/buildings/{GROVE}",
    ],
)
def test_missing_or_mismatched_diagnostics_folder_returns_503(tmp_path, path):
    root = tmp_path / "site"
    app = create_app(root)
    client = app.test_client()

    # Missing folder -> 503
    resp = client.get(path)
    assert resp.status_code == 503

    # Mismatched sha256 -> 503 Refused
    write_diagnostics(root, sha_override={"ads": "0" * 64})
    resp_bad = client.get(path)
    assert resp_bad.status_code == 503
    assert "do not match" in resp_bad.get_data(as_text=True)

    # Next valid publish -> 200
    write_diagnostics(root)
    assert client.get(path).status_code == 200


def test_workbench_files_and_pages_follow_prose_rules(wb_client):
    site_dir = Path(workbench.__file__).resolve().parent
    owned_files = [
        site_dir / "workbench.py",
        site_dir / "static" / "workbench.css",
        site_dir / "templates" / "_workbench.html",
        *sorted((site_dir / "templates").glob("workbench_*.html")),
    ]
    forbidden = re.compile(
        r"\b(honest|genuine|fair|surface|ship|land|today)\b", re.IGNORECASE
    )
    for path in owned_files:
        text = path.read_text()
        assert "\u2014" not in text, f"em dash in {path}"
        assert "\u2013" not in text, f"en dash in {path}"
        assert not forbidden.search(text), f"forbidden word in {path}"
        if path.suffix == ".html":
            assert "subnav" not in text, f"second subnav in {path}"

    for route in (
        "/workbench",
        "/workbench/signals",
        "/workbench/signals/square_feet",
        "/workbench/triage",
        "/workbench/buildings",
        f"/workbench/buildings/{GROVE}",
    ):
        body = wb_client.get(route).get_data(as_text=True)
        assert "\u2014" not in body, f"em dash rendered on {route}"
        assert not forbidden.search(body), f"forbidden word rendered on {route}"
        assert "meta.json" not in body and "basis !=" not in body
        assert ".parquet" not in body and "heldout_" not in body
        for f in FEATURES:
            assert f"<code>{f['name']}</code>" not in body


def _binned_ads(spec: dict[str, tuple[int, int, float]], **fixed) -> list[dict]:
    """Ads for a `doorman_type` category: class -> (ads, buildings, mean gap).

    Half of a class's buildings are 0.01 above its mean gap and half 0.01 below.
    """
    ads = []
    for k, (name, (n_ads, n_buildings, gap)) in enumerate(spec.items()):
        for i in range(n_ads):
            b = i % n_buildings
            row = make_ad_row(
                str(10000 + 1000 * k + i),
                building=f"{name}-b{b}",
                doorman_type=name,
                **fixed,
            )
            row["gap"] = gap + (0.01 if b % 2 else -0.01)
            ads.append(row)
    return ads


def test_gap_is_shown_as_the_percent_difference_of_the_ask(tmp_path):
    root = tmp_path / "site"
    ads = [make_ad_row("1", ask=971.0, model_median=6793.0, z=-3.5, miss=-21.0)]
    write_diagnostics(root, ads=ads)
    client = create_app(root).test_client()

    assert workbench._ratio_pct(math.log(971 / 6793)) == pytest.approx(
        -85.706, abs=1e-3
    )
    assert workbench._ratio_pct(None) is None

    triage = client.get("/workbench/triage").get_data(as_text=True)
    assert "−85.7%" in triage and "194.5" not in triage
    assert f'title="{escape(workbench.GAP_TITLE)}">Ask vs model</th>' in triage
    assert 'data-label="Ask vs model"' in triage

    building = client.get(f"/workbench/buildings/{GROVE}").get_data(as_text=True)
    assert "−85.7%" in building
    assert f'title="{escape(workbench.GAP_TITLE)}">Ask vs model</th>' in building
    # The building's mean held-out log gap of -0.18 reads as -16.5%.
    assert "Held-out ask vs model" in building and "−16.5%" in building

    buildings = client.get("/workbench/buildings").get_data(as_text=True)
    assert "−16.5%" in buildings
    assert f'title="{escape(workbench.MEAN_GAP_TITLE)}">Ask vs model' in buildings

    overview = client.get("/workbench").get_data(as_text=True)
    assert "−85.7%" in overview
    for page in (triage, building, buildings, overview):
        assert "Gap %" not in page and "Mean gap<" not in page

    # The CSV keeps the log gap.
    rows = list(
        csv.DictReader(
            io.StringIO(client.get("/workbench/triage.csv").get_data(as_text=True))
        )
    )
    assert float(rows[0]["gap"]) == pytest.approx(math.log(971 / 6793))


def test_signal_bins_are_centered_on_the_reference_population(tmp_path):
    root = tmp_path / "site"
    spec = {"full_time": (40, 10, 0.05), "virtual": (60, 12, 0.03)}
    write_diagnostics(root, ads=_binned_ads(spec))
    diag = workbench.load(root)
    signal = diag.signal_detail("doorman_type", workbench.SignalChoice())

    ref = (40 * 0.05 + 60 * 0.03) / 100
    assert signal["ref_ads"] == 100
    assert signal["ref_mean"] == pytest.approx(ref)
    assert signal["ref_mean_pct"] == pytest.approx(100 * math.expm1(ref))
    by_key = {b["key"]: b for b in signal["bins"]}
    full = by_key["full_time"]
    assert full["raw_mean"] == pytest.approx(0.05)
    assert full["mean"] == pytest.approx(0.05 - ref)
    assert full["mean_pct"] == pytest.approx(100 * math.expm1(0.05 - ref))
    assert full["ratio"] == pytest.approx(abs(0.05 - ref) / full["se"])
    assert by_key["virtual"]["mean"] == pytest.approx(0.03 - ref)
    assert signal["strength"] == pytest.approx(
        max(full["ratio"], by_key["virtual"]["ratio"])
    )
    # Uncentered, the larger bin would score 0.03 / SE.
    assert by_key["virtual"]["ratio"] < 0.03 / by_key["virtual"]["se"] / 2

    client = create_app(root).test_client()
    page = client.get("/workbench/signals/doorman_type").get_data(as_text=True)
    top = page[page.index('id="reference-population"') :][:600]
    assert "Reference population: 100 ads" in top
    assert "+3.9%" in top and "relative to that mean" in top
    assert "+1.2%" in page and "−0.8%" in page


def test_small_bins_get_no_score_and_do_not_rank(tmp_path):
    root = tmp_path / "site"
    spec = {
        "big_a": (40, 10, 0.00),
        "big_b": (40, 10, 0.04),
        # 40 ads in 5 buildings, and 5 ads, both with gaps far from the others.
        "few_buildings": (40, 5, 0.60),
        "few_ads": (5, 5, -0.70),
    }
    write_diagnostics(root, ads=_binned_ads(spec))
    diag = workbench.load(root)
    signal = diag.signal_detail("doorman_type", workbench.SignalChoice())

    keys = [b["key"] for b in signal["bins"]]
    assert set(keys[:2]) == {"big_a", "big_b"}
    assert set(keys[2:]) == {"few_buildings", "few_ads"}
    assert [b["sized"] for b in signal["bins"]] == [True, True, False, False]
    assert all(b["ratio"] is None for b in signal["bins"][2:])
    assert signal["small_bins"] == 2
    assert signal["peak_bin"]["key"] in ("big_a", "big_b")
    assert signal["strength"] == pytest.approx(signal["peak_bin"]["ratio"])

    client = create_app(root).test_client()
    page = client.get("/workbench/signals/doorman_type").get_data(as_text=True)
    table = page[page.index('id="bin-table"') :]
    table = table[table.index("<tbody>") :]
    assert table.count('<tr class="small-bin"') == 2
    assert table.index("big ") < table.index('<tr class="small-bin"')
    small_row = table[table.index('<tr class="small-bin"') :]
    small_row = small_row[: small_row.index("</tr>")]
    # A greyed row shows neither an SE nor a score.
    assert small_row.count('<td class="num">-</td>') == 2
    assert "2 greyed bins" in page

    # The overview, the signals index and the attribute's page show the same score.
    score = "{:.2f}".format(signal["strength"])
    assert f'<span class="figure-value">{score}</span>' in page
    index = client.get("/workbench/signals").get_data(as_text=True)
    overview = client.get("/workbench").get_data(as_text=True)
    for listing in (index, overview[overview.index('id="top-signals"') :]):
        row = listing[listing.index(">Doorman</a>") :]
        row = row[: row.index("</tr>")]
        assert f'<td class="num">{score}</td>' in row

    strip = str(signal["svg"])
    assert strip.count(" small") == 2
    assert strip.count('class="whisker"') == 2


def test_variance_explained_is_shown_up_to_20_bins(tmp_path):
    root = tmp_path / "site"
    many = {f"class_{k:02d}": (2, 2, 0.01 * k) for k in range(21)}
    write_diagnostics(root, ads=_binned_ads(many))
    diag = workbench.load(root)
    signal = diag.signal_detail("doorman_type", workbench.SignalChoice())
    assert len(signal["bins"]) == 21 > workbench.MAX_EXPLAINED_BINS
    assert signal["explained_share"] is None and signal["explained_pct"] is None
    flag = diag.signal_detail("has_outdoor", workbench.SignalChoice())
    assert flag["explained_share"] is not None

    client = create_app(root).test_client()
    page = client.get("/workbench/signals/doorman_type").get_data(as_text=True)
    assert 'id="variance-explained"' not in page
    page = client.get("/workbench/signals/has_outdoor").get_data(as_text=True)
    assert 'id="variance-explained"' in page
    index = client.get("/workbench/signals").get_data(as_text=True)
    row = index[index.index(">Doorman</a>") :]
    row = row[: row.index("</tr>")]
    assert row.count('<td class="num">-</td>') == 2


def test_signals_index_warns_about_multiple_comparisons(wb_client):
    page = wb_client.get("/workbench/signals").get_data(as_text=True)
    line = page[page.index('id="signals-reading"') :]
    line = line[: line.index("</p>")]
    assert f"With about {len(FEATURES)} attributes" in line
    assert "scores of 3 or so appear by chance" in line
    assert "lead to check" in line and "both readings" in line
    assert 'href="/workbench/buildings#building-level-signals"' in line


def test_calibration_lists_new_unit_rows_first(wb_client, tmp_path):
    cal = workbench.load(tmp_path / "site").calibration()
    assert [r["label"] for r in cal["new_units"]] == ["Building", "Area"]
    assert [r["label"] for r in cal["unit"]] == ["Unit history"]
    assert cal["main"] == cal["new_units"] + cal["unit"] + cal["rest"]
    assert cal["rest"][0]["label"] == "All held-out ads"

    page = wb_client.get("/workbench").get_data(as_text=True)
    table = page[page.index('id="calibration"') :]
    order = [
        "New units: the test of the model on apartments it has not met",
        'href="/workbench/triage?basis=building"',
        'href="/workbench/triage?basis=area"',
        "Units with earlier ads: the easier case",
        'href="/workbench/triage?basis=unit"',
        "All held-out ads, by source and bedrooms",
        'href="/workbench/triage?source=latest"',
    ]
    places = [table.index(text) for text in order]
    assert places == sorted(places)
    assert "Read calibration in the new-unit rows" in table


def test_miss_header_explains_miss_and_z(wb_client):
    assert "predictive spread" in workbench.MISS_TITLE
    assert "3.5" in workbench.MISS_TITLE and "finite" in workbench.MISS_TITLE
    header = f'title="{escape(workbench.MISS_TITLE)}">Miss</th>'
    assert header in wb_client.get("/workbench/triage").get_data(as_text=True)
    building = wb_client.get(f"/workbench/buildings/{GROVE}").get_data(as_text=True)
    assert header in building


def test_triage_untagged_filter_reads_the_ledger(tmp_path):
    root = tmp_path / "site"
    ads = [
        make_ad_row(str(2000 + i), z=float(120 - i) / 20.0, unit_ads=0)
        for i in range(120)
    ]
    write_diagnostics(root, ads=ads)
    client = create_app(root).test_client()

    # With an empty ledger the filter keeps every ad.
    page = client.get("/workbench/triage?untagged=1").get_data(as_text=True)
    assert "<strong>120</strong> held-out ads" in page
    assert 'name="untagged" value="1" checked' in page

    tags.append(root, "2000", "deal", "")
    tags.append(root, "2003", "wrong_price", "")
    tags.append(root, "2003", "clear", "")
    plain = client.get("/workbench/triage").get_data(as_text=True)
    assert _triage_ids(plain)[:2] == ["2000", "2001"]
    assert 'name="untagged" value="1">' in plain

    page = client.get("/workbench/triage?untagged=1").get_data(as_text=True)
    assert "<strong>119</strong> held-out ads" in page
    # 2000 carries a tag, and the tag on 2003 is cleared.
    assert _triage_ids(page)[:3] == ["2001", "2002", "2003"]
    assert 'href="/workbench/triage?untagged=1&amp;page=2"' in page
    assert 'href="/workbench/triage.csv?untagged=1"' in page

    second = client.get("/workbench/triage?untagged=1&page=2").get_data(as_text=True)
    assert _triage_ids(second)[0] == "2051"

    rows = list(
        csv.DictReader(
            io.StringIO(
                client.get("/workbench/triage.csv?untagged=1").get_data(as_text=True)
            )
        )
    )
    assert len(rows) == 119
    assert "2000" not in {r["listing_id"] for r in rows}


def test_triage_csv_link_carries_every_filter(wb_client):
    query = {
        "q": ["19th"],
        "source": ["latest"],
        "flag": ["any"],
        "basis": ["unit"],
        "sign": ["low"],
        "beds": ["1", "2"],
        "nb": ["chelsea"],
        "feature": ["has_outdoor"],
        "bin": ["no"],
        "min_miss": ["1.5"],
        "untagged": ["1"],
    }
    url = "/workbench/triage?" + "&".join(
        f"{k}={v}" for k, values in query.items() for v in values
    )
    page = wb_client.get(url + "&page=1").get_data(as_text=True)
    href = re.search(r'class="download" href="([^"]+)"', page).group(1)
    parts = urlsplit(html_lib.unescape(href))
    assert parts.path == "/workbench/triage.csv"
    assert parse_qs(parts.query) == query

    # The CSV applies the sign filter the link carries.
    low = wb_client.get("/workbench/triage.csv?sign=low").get_data(as_text=True)
    high = wb_client.get("/workbench/triage.csv?sign=high").get_data(as_text=True)
    low_gaps = [float(r["gap"]) for r in csv.DictReader(io.StringIO(low))]
    high_gaps = [float(r["gap"]) for r in csv.DictReader(io.StringIO(high))]
    assert low_gaps and all(g < 0 for g in low_gaps)
    assert high_gaps and all(g > 0 for g in high_gaps)


def test_triage_flag_list_shows_counts_rarest_first(tmp_path):
    root = tmp_path / "site"
    marks = [["beds_conflict"]] * 3 + [["beds_jump", "beds_conflict"]] * 2
    marks += [["extreme"], []]
    ads = [make_ad_row(str(3000 + i), flags=f) for i, f in enumerate(marks)]
    write_diagnostics(root, ads=ads)
    wb_client = create_app(root).test_client()
    counts = {f["code"]: f["count"] for f in workbench.load(root).flag_counts()}
    assert counts["beds_conflict"] == 5 and counts["extreme"] == 1
    page = wb_client.get("/workbench/triage").get_data(as_text=True)
    select = page[page.index('name="flag"') :]
    select = select[: select.index("</select>")]
    listed = re.findall(r'<option value="(\w+)"[^>]*>[^<(]*\(([\d,]+)\)', select)
    listed = [(code, int(n.replace(",", ""))) for code, n in listed]
    assert {code for code, _ in listed} == set(counts)
    assert all(counts[code] == n for code, n in listed)
    assert [code for code, _ in listed][:3] == ["extreme", "beds_jump", "beds_conflict"]
    shown = [n for _, n in listed if n > 0]
    assert shown == sorted(shown)
    # A flag marking no ad follows the others.
    assert [n for _, n in listed] == shown + [0] * (len(listed) - len(shown))


def test_building_level_table_reads_buildings_below_the_ads_floor(wb_client, tmp_path):
    diag = workbench.load(tmp_path / "site")
    signals = diag.building_level_signals(workbench.BuildingChoice())
    assert signals and all(s["total_ads"] == 4 for s in signals)


def test_long_bin_labels_carry_a_title_and_wrap(wb_client):
    label = "2,100 to 2,750 square feet of space"
    strip = str(
        workbench.signal_strip(
            [{"key": "q1", "label": label, "mean_pct": 1.0, "sized": True}]
        )
    )
    assert f"<title>{label}</title>" in strip
    assert label[: workbench.STRIP_LABEL_CHARS - 2] + "..</text>" in strip
    short = str(workbench.signal_strip([{"key": "a", "label": "Yes", "mean_pct": 1.0}]))
    assert "<title>Yes</title>Yes</text>" in short

    page = wb_client.get("/workbench/signals").get_data(as_text=True)
    assert '<td class="bin-label">' in page
    detail = wb_client.get("/workbench/signals/square_feet").get_data(as_text=True)
    assert '<th scope="row" class="bin-label">' in detail
    css = (
        Path(workbench.__file__).resolve().parent / "static" / "workbench.css"
    ).read_text()
    rule = css[css.index(".data .bin-label {") :]
    assert "white-space: normal" in rule[: rule.index("}")]


def test_phone_rules_shorten_triage_and_enlarge_controls(tmp_path):
    css = (
        Path(workbench.__file__).resolve().parent / "static" / "workbench.css"
    ).read_text()
    phone = css[css.index("@media (max-width: 599px)") :]
    assert f"tbody tr:nth-child(n + {workbench.PHONE_ROWS + 1})" in phone
    assert ".rows-toggle:not(:checked)" in phone
    assert css.count("min-height: 40px") >= 2
    assert "padding-block: 0.85rem" in css
    # A unit id on the building page stays on a line at phone widths.
    assert "#building-units tbody th code {" in css
    assert "grid-template-columns: repeat(3, 1fr)" in css

    root = tmp_path / "site"
    ads = [make_ad_row(str(2000 + i), z=float(60 - i) / 20.0) for i in range(60)]
    write_diagnostics(root, ads=ads)
    client = create_app(root).test_client()
    page = client.get("/workbench/triage").get_data(as_text=True)
    assert page.index('id="t-all-rows"') < page.index('<table class="data triage">')
    assert '<label class="rows-more" for="t-all-rows">' in page
    assert "Show the other 25 rows of this page" in page
    # The second page holds 10 rows, and a page of 25 or fewer has no control.
    second = client.get("/workbench/triage?page=2").get_data(as_text=True)
    assert "rows-more" not in second and "t-all-rows" not in second
