import json
import sqlite3

import pytest

from apartments.site import build


def query(root, sql, params=()):
    db = sqlite3.connect(root / "current" / "site.sqlite")
    db.row_factory = sqlite3.Row
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


def test_build_publishes_a_complete_snapshot(site_root):
    assert (site_root / "current").is_symlink()
    info = json.loads((site_root / "current" / "build.json").read_text())
    assert info["run"] == "m-test-run" and info["stats"]["listings"] == 6
    assert [
        r[0]
        for r in query(site_root, "SELECT audit_id FROM listings ORDER BY audit_id")
    ] == [
        "a1",
        "a2",
        "a3",
        "a4",
        "a5",
        "a6",
    ]
    meta = {
        r["key"]: json.loads(r["value"]) for r in query(site_root, "SELECT * FROM meta")
    }
    assert meta["scope"] == "Chelsea"
    assert meta["provenance"]["gate"]["passes"] is True
    stats = meta["stats"]
    assert stats["current_listings"] == 1 and stats["units"] == 3
    assert stats["buildings"] == 2 and stats["unreliable_estimates"] == 1
    cal = stats["calibration"]
    assert (
        cal["heldout"]["n"] == 1 and cal["single"]["n"] == 1 and cal["multi"]["n"] == 4
    )
    assert cal["multi"]["cover95"] == 1.0


def test_listing_rows_carry_the_estimate_bands_and_contributions(site_root):
    rows = {r["audit_id"]: r for r in query(site_root, "SELECT * FROM listings")}
    assert rows["a2"]["price_band"] == "below" and rows["a2"]["method"] == "heldout"
    assert rows["a4"]["price_band"] == "above" and rows["a1"]["price_band"] == "typical"
    assert rows["a3"]["reliable"] == 0 and rows["a2"]["pareto_k"] is None
    assert rows["a3"]["is_current"] == 1 and rows["a3"]["listing_url"].endswith(
        "/rental/3000"
    )
    assert rows["a3"]["unit_label"] == "11-C" and rows["a3"]["floor"] == 11
    assert json.loads(rows["a1"]["views"]) == ["city"]
    parts = json.loads(rows["a1"]["contributions"])
    assert [p["term"] for p in parts] == ["market", "bedrooms", "building", "unit"]
    assert sum(p["usd"] for p in parts) == pytest.approx(
        rows["a1"]["estimate"], abs=0.05
    )


def test_units_follow_the_summary_unit_ids_and_latest_listing(site_root):
    units = {r["id"]: r for r in query(site_root, "SELECT * FROM units")}
    assert set(units) == {"u1", "u2", "u3"}
    u1 = units["u1"]
    assert u1["listings"] == 3 and u1["label"] == "11-C" and u1["last_ask"] == 3500.0
    assert u1["square_feet"] == 650.0 and u1["first_period"] == "2019-03-01"


def test_buildings_get_names_addresses_and_lot_facts(site_root):
    b = {r["id"]: r for r in query(site_root, "SELECT * FROM buildings")}
    grove = b["the-grove-250-west-19th-street-new_york"]
    assert grove["name"] == "The Grove" and grove["address"] == "250 West 19th Street"
    assert grove["year_built"] == 1986 and grove["current_listings"] == 1
    assert grove["level_pct"] == pytest.approx(10.4) and grove["units"] == 2
    plain = b["134-west-23-street-new_york"]
    assert plain["name"] is None and plain["address"] == "134 West 23rd Street"
    assert plain["year_built"] is None  # no MapPLUTO row for its lot


@pytest.mark.parametrize(
    "label, expected",
    [
        ("100 10 AVENUE, New York, NY, USA", "100 10th Avenue"),
        ("134 WEST 23 STREET, New York", "134 West 23rd Street"),
        ("61 7 AVENUE", "61 7th Avenue"),
        ("550A WEST 29 STREET", "550A West 29th Street"),
        ("1 WEST 11 STREET", "1 West 11th Street"),
        ("64 NINTH AVENUE", "64 Ninth Avenue"),
        (None, None),
    ],
)
def test_title_address(label, expected):
    assert build.title_address(label) == expected


def test_building_names():
    assert build.building_names("the-caledonia", "100 10th Avenue") == (
        "The Caledonia",
        "100 10th Avenue",
    )
    assert build.building_names("777-6th-avenue", "777 6th Avenue") == (
        None,
        "777 6th Avenue",
    )
    assert build.building_names("ohm-312-11th-avenue-new_york", "312 11th Avenue") == (
        "Ohm",
        "312 11th Avenue",
    )
    assert build.building_names("some-place", None) == (None, "Some Place")


def test_build_refuses_a_changed_bundle_file(bundle, tmp_path):
    rows = bundle / "terms.json"
    rows.write_text(rows.read_text().replace("The market.", "Changed."))
    with pytest.raises(build.BuildError, match="terms.json differs"):
        build.build(bundle, tmp_path / "site")
    assert not (tmp_path / "site" / "current").exists()


def test_build_refuses_a_changed_dataset(bundle, tmp_path):
    record = json.loads((bundle / "complete.json").read_text())
    source = tmp_path / "inputs" / "dataset" / "observations.jsonl"
    source.write_text(source.read_text().replace("3500.0", "3600.0"))
    assert record["dataset"] == str(source.parent)
    with pytest.raises(build.BuildError, match="dataset differs"):
        build.build(bundle, tmp_path / "site")
    # a failed build leaves no staging directory behind
    assert list((tmp_path / "site" / "builds").iterdir()) == []


def test_build_refuses_a_run_that_fails_the_gate(tmp_path, make_bundle):
    bundle = make_bundle(tmp_path / "failing", gate=False)
    with pytest.raises(build.BuildError, match="fails the convergence gate"):
        build.build(bundle, tmp_path / "site")


def test_publish_swaps_current_and_keeps_the_newest_builds(
    bundle, tmp_path, monkeypatch
):
    root = tmp_path / "site"
    stamps = iter(f"20260926T0000{i:02d}Z" for i in range(10))

    class Clock:
        @staticmethod
        def now(tz=None):
            class Stamp:
                def strftime(self, fmt):
                    return next(stamps)

                def isoformat(self, timespec=None):
                    return "2026-09-26T00:00:00+00:00"

            return Stamp()

    monkeypatch.setattr(build.dt, "datetime", Clock)
    built = [build.build(bundle, root) for _ in range(5)]
    remaining = sorted(p.name for p in (root / "builds").iterdir())
    assert remaining == [p.name for p in built[-build.KEEP :]]
    assert (root / "current").resolve() == built[-1].resolve()
