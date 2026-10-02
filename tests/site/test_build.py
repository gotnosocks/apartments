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
    assert grove["floors"] == 20 and grove["residential_units"] == 200
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


def _selection(tmp_path, bundle, **changes):
    record = {
        "version": "main-analysis-selection-v2",
        "model_family": "frontier_summary",
        "summary": str(bundle),
        "summary_manifest_sha256": build.sha256(bundle / "complete.json"),
    }
    record.update(changes)
    path = tmp_path / "main-analysis.json"
    path.write_text(json.dumps(record))
    return path


def test_build_publishes_the_selected_summary_by_default(bundle, tmp_path):
    selection = _selection(tmp_path, bundle)
    assert build.selected_summary(selection) == bundle
    build.main(["--selection", str(selection), "--root", str(tmp_path / "site")])
    info = json.loads((tmp_path / "site" / "current" / "build.json").read_text())
    assert info["summary"] == str(bundle.resolve())


def test_selection_must_name_an_unchanged_summary(bundle, tmp_path):
    with pytest.raises(build.BuildError, match="does not select a summary"):
        build.selected_summary(
            _selection(tmp_path, bundle, model_family="pymc_bayesian")
        )
    with pytest.raises(build.BuildError, match="differs from the selection"):
        build.selected_summary(
            _selection(tmp_path, bundle, summary_manifest_sha256="0")
        )
    with pytest.raises(SystemExit, match="build failed"):
        build.main(["--selection", str(_selection(tmp_path, bundle, version="v1"))])
    with pytest.raises(build.BuildError, match="cannot read the selection"):
        build.selected_summary(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    with pytest.raises(build.BuildError, match="cannot read the selection"):
        build.selected_summary(broken)
    keyless = _selection(tmp_path, bundle)
    record = json.loads(keyless.read_text())
    del record["summary"]
    keyless.write_text(json.dumps(record))
    with pytest.raises(build.BuildError, match="names no summary bundle"):
        build.selected_summary(keyless)


def test_the_repository_selects_a_summary_bundle():
    record = json.loads(build.SELECTION.read_text())
    assert record["version"] == build.SELECTION_VERSION
    assert record["model_family"] == "frontier_summary"
    assert record["gate"]["passes"] is True
    assert len(record["summary_manifest_sha256"]) == 64


def test_publish_never_prunes_staging(bundle, tmp_path):
    root = tmp_path / "site"
    staging = root / "builds" / "00000000T000000Z-other.tmp"
    staging.mkdir(parents=True)
    for _ in range(build.KEEP + 1):
        build.build(bundle, root)
    assert staging.is_dir()
    assert (
        len([p for p in (root / "builds").iterdir() if not p.name.endswith(".tmp")])
        == build.KEEP
    )


def test_quarantined_listings_are_kept_with_their_reason(site_root):
    rows = {r["audit_id"]: r for r in query(site_root, "SELECT * FROM quarantined")}
    assert set(rows) == {"q1", "q2"}
    q1 = rows["q1"]
    assert q1["action"] == "quarantine_nonresidential" and q1["rule"] == "quarantine-v1"
    assert q1["evidence"] == "ground floor retail space" and q1["ask"] == 8500.0
    assert q1["building"] == "The Grove" and q1["listing_url"].endswith("/rental/91")
    assert rows["q2"]["evidence"] is None and rows["q2"]["external_evidence"]
    info = json.loads((site_root / "current" / "build.json").read_text())
    assert info["stats"]["quarantined_listings"] == 2
    assert info["stats"]["listings"] == 6  # quarantined rows are not listings


def test_build_refuses_rows_missing_that_no_rule_drops(tmp_path, make_bundle):
    # The rule file names q1 only; q2 is missing from the bundle all the same.
    q1 = {"audit_id": "q1", "action": "quarantine_nonresidential", "reason": "Retail."}
    bundle = make_bundle(tmp_path / "inputs", rule_lines=[q1])
    with pytest.raises(build.BuildError, match="no data rule drops them"):
        build.build(bundle, tmp_path / "site")


def test_build_refuses_a_rule_row_still_in_the_bundle(tmp_path, make_bundle):
    # a1 is in the bundle: a rule that drops it disagrees with the bundle.
    lines = [
        {"audit_id": a, "action": "quarantine_nonresidential", "reason": "Retail."}
        for a in ("q1", "q2", "a1")
    ]
    bundle = make_bundle(tmp_path / "inputs", rule_lines=lines)
    with pytest.raises(build.BuildError, match="in the bundle or not in the dataset"):
        build.build(bundle, tmp_path / "site")


def test_quarantined_rows_are_in_a_stable_order(site_root):
    rows = query(site_root, "SELECT audit_id FROM quarantined ORDER BY rowid")
    assert [r["audit_id"] for r in rows] == ["q1", "q2"]


def test_selection_note_only_for_the_selected_bundle(bundle, tmp_path):
    sha = build.sha256(bundle / "complete.json")
    path = _selection(
        tmp_path, bundle, selected_by="autoselect", selection_reason="why"
    )
    assert build.selection_note(path, sha) == {
        "selected_by": "autoselect",
        "selection_reason": "why",
    }
    assert build.selection_note(path, "0" * 64) is None
    assert build.selection_note(tmp_path / "missing.json", sha) is None
    root = tmp_path / "site"
    build.build(bundle, root, selection=path)
    meta = {r["key"]: json.loads(r["value"]) for r in query(root, "SELECT * FROM meta")}
    assert meta["selection"]["selection_reason"] == "why"


def _map(maps, run, commit, named=None):
    folder = maps / f"{run}-{commit}"
    folder.mkdir(parents=True)
    (folder / "map.json").write_text(json.dumps({"run": named or run, "years": [2026]}))
    return folder / "map.json"


def test_rent_map_is_the_runs_newest_and_must_name_it(tmp_path):
    import os

    maps = tmp_path / "maps"
    assert build.rent_map("m-test-run", maps) is None
    old = _map(maps, "m-test-run", "aaaaaaa")
    new = _map(maps, "m-test-run", "bbbbbbb")
    os.utime(old, (1, 1))
    _map(maps, "m-test-run-longer", "ccccccc")  # another run's name starts with it
    assert build.rent_map("m-test-run", maps) == new
    _map(maps, "m-other", "ddddddd", named="m-test-run")
    wrong = _map(maps, "m-mixed", "eeeeeee", named="m-other")
    with pytest.raises(build.BuildError, match="is of m-other, not m-mixed"):
        build.rent_map("m-mixed", maps)
    assert wrong.exists()


def test_build_bundles_the_served_runs_map(bundle, tmp_path, monkeypatch):
    maps = tmp_path / "maps"
    source = _map(maps, "m-test-run", "1234567")
    monkeypatch.setattr(build, "MAPS", maps)
    root = tmp_path / "site"
    build.build(bundle, root)
    assert (
        json.loads((root / "current" / "map.json").read_text())["run"] == "m-test-run"
    )
    info = json.loads((root / "current" / "build.json").read_text())
    assert info["rent_map"] == str(source)


def test_listings_and_buildings_carry_their_neighbourhood(
    site_root, tmp_path, make_bundle
):
    rows = query(site_root, "SELECT DISTINCT neighbourhood FROM listings")
    assert [r[0] for r in rows] == ["Chelsea"]  # the scope, when the summary has none
    bundle = make_bundle(
        tmp_path / "nb", neighbourhoods={"134-west-23-street-new_york": "West Village"}
    )
    root = tmp_path / "nb-site"
    build.build(bundle, root)
    b = {r["id"]: r["neighbourhood"] for r in query(root, "SELECT * FROM buildings")}
    assert b["134-west-23-street-new_york"] == "West Village"
    meta = {r["key"]: json.loads(r["value"]) for r in query(root, "SELECT * FROM meta")}
    assert meta["stats"]["neighbourhoods"] == {"Chelsea": 4, "West Village": 2}
    # without --scope, the site is named for the neighbourhoods it covers
    assert meta["scope"] == "Chelsea and West Village"
    assert build.scope_of([{"neighbourhood": "Chelsea"}]) == "Chelsea"
    assert (
        build.scope_of(
            [{"neighbourhood": n} for n in ("West Village", "Chelsea", "Flatiron")]
        )
        == "Chelsea, Flatiron and West Village"
    )
