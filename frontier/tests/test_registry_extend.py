import json

import pandas as pd
import pytest
from rentfrontier import registry_extend as m


def _base():
    frame = pd.DataFrame(
        {
            "building": ["a-new_york"],
            "method": ["address"],
            "query": ["1 West 1 Street"],
            "label": ["1 WEST 1 STREET"],
            "bbl": ["1000010001"],
            "bin": ["1000001"],
            "pad_version": ["25a"],
            "latitude": [40.7],
            "longitude": [-74.0],
            "distance_m": [3.0],
        }
    )
    return frame.astype({c: "string" for c in m.COLUMNS[:7]})


def _record(slug, city, lat=40.69, lon=-73.9):
    return json.dumps(
        {
            "slug": slug,
            "address": {"city": city},
            "geoCenter": {"latitude": lat, "longitude": lon},
        }
    )


def _catalog(tmp_path, records, rows):
    export = tmp_path / "export"
    (export / "buildings" / "run-0001").mkdir(parents=True)
    f = "buildings/run-0001/responses-1-2.parquet"
    pd.DataFrame(records).to_parquet(export / f)
    datasets = tmp_path / "datasets"
    datasets.mkdir()
    pd.DataFrame(rows).to_parquet(datasets / "rows-x.parquet")
    line = {
        "built": "2026-10-19T00:00:00+00:00",
        "export": str(export),
        "buildings": {"files": {f: "sha"}},
        "rows": {"path": "rows-x.parquet"},
    }
    (datasets / "catalog.ndjson").write_text(json.dumps(line) + "\n")
    return datasets / "catalog.ndjson"


def test_borough_of_maps_the_mail_city():
    assert m.borough_of("NEW YORK") == "Manhattan"
    assert m.borough_of("BROOKLYN") == "Brooklyn"
    assert m.borough_of("RIDGEWOOD") == "Ridgewood"
    assert m.borough_of(None) == "New York"


def test_export_keeps_each_buildings_latest_record(tmp_path):
    catalog = _catalog(
        tmp_path,
        {
            "building_id": [7, 7, 8],
            "fetched": pd.to_datetime(["2026-10-15", "2026-10-17", "2026-10-15"]),
            "record": [
                _record("old-slug-brooklyn", "BROOKLYN"),
                _record("new-slug-brooklyn", "BROOKLYN"),
                _record("b-new_york", "NEW YORK"),
            ],
        },
        {"building": ["b-new_york"], "building_id": [8]},
    )
    out = m.export_buildings(m.latest_build(catalog))
    assert sorted(out.building) == ["b-new_york", "new-slug-brooklyn"]


def test_rows_slug_missing_from_export_takes_its_ids_point():
    export = pd.DataFrame(
        {
            "building_id": [7],
            "building": ["new-slug"],
            "latitude": [40.69],
            "longitude": [-73.9],
            "city": ["BROOKLYN"],
        }
    )
    rows = pd.DataFrame(
        {"building": ["old-slug", "new-slug", None], "building_id": [7, 7, 9]}
    )
    out = m.wanted(export, rows).set_index("building")
    assert list(out.index) == ["new-slug", "old-slug"]
    assert out.loc["old-slug", "latitude"] == 40.69


def test_check_fails_while_a_listed_building_has_no_registry_row(tmp_path, monkeypatch):
    """The coverage check behind apartments-registry-extend: a building the pipeline's ads name
    and the registry lacks makes `--check` exit 1, as the ~900 buildings of 2026-10-15..17
    would have."""
    catalog = _catalog(
        tmp_path,
        {
            "building_id": [1, 2],
            "fetched": pd.to_datetime(["2026-10-15", "2026-10-16"]),
            "record": [
                _record("a-new_york", "NEW YORK"),
                _record("b-new_york", "NEW YORK"),
            ],
        },
        {"building": ["a-new_york", "b-new_york"], "building_id": [1, 2]},
    )
    base = tmp_path / "registry" / "base"
    base.mkdir(parents=True)
    _base().to_parquet(base / "registry.parquet")
    with pytest.raises(SystemExit) as e:
        m.main(["--check", "--base", str(base), "--catalog", str(catalog)])
    assert e.value.code == 1
    full = pd.concat([_base(), _base().assign(building="b-new_york")])
    full.to_parquet(base / "registry.parquet")
    with pytest.raises(SystemExit) as e:
        m.main(["--check", "--base", str(base), "--catalog", str(catalog)])
    assert e.value.code == 0


def test_extend_keeps_the_base_and_adds_a_row_per_building(monkeypatch):
    calls = []

    def fake_locate(slug, lat, lon, borough):
        calls.append((slug, borough))
        return {
            "building": slug,
            "method": "address",
            "query": "2 Grove Street",
            "label": "2 GROVE STREET",
            "bbl": "4034420040",
            "bin": "4000001",
            "pad_version": "26c",
            "latitude": lat,
            "longitude": lon,
            "distance_m": 5.0,
        }

    monkeypatch.setattr(m, "locate", fake_locate)
    todo = pd.DataFrame(
        {
            "building": ["c-ridgewood", "d-brooklyn"],
            "latitude": [40.70, None],
            "longitude": [-73.91, None],
            "city": ["RIDGEWOOD", "BROOKLYN"],
        }
    )
    table, added = m.extend(_base(), todo, pause=0)
    assert calls == [("c-ridgewood", "Ridgewood")]
    assert list(table.building) == ["a-new_york", "c-ridgewood", "d-brooklyn"]
    assert list(added.method) == ["address", "none"]
    assert table.dtypes.to_dict() == _base().dtypes.to_dict()
