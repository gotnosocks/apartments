import contextlib
import io
import json

import pandas as pd

from rentfrontier import external


def registry():
    return pd.DataFrame(
        {
            "bbl": ["1000010001", None, "1000020002"],
            "bin": ["1000001", None, "1000000"],
            "latitude": [40.70, 40.71, 40.72],
            "longitude": [-74.00, -74.01, -74.02],
        },
        index=["a", "cleared", "placeholder"],
    )


def where_clauses(monkeypatch):
    seen = []

    def socrata(dataset, params):
        seen.append(params["$where"])
        return [{"bin": "1000001", "base_bbl": "1000010001", "violationid": "1"}]

    @contextlib.contextmanager
    def urlopen(url, timeout):
        yield io.BytesIO(json.dumps({"rowsUpdatedAt": 0}).encode())

    monkeypatch.setattr(external, "_socrata", socrata)
    monkeypatch.setattr(external, "_urlopen", urlopen)
    return seen


def test_footprints_skip_a_building_with_no_bin(monkeypatch):
    seen = where_clauses(monkeypatch)
    external.fetch_footprints(registry())
    assert "bin in ('1000001')" in seen
    assert "base_bbl in ('1000020002')" in seen


def test_hpd_skips_a_building_with_no_bin(monkeypatch):
    seen = where_clauses(monkeypatch)
    external.fetch_hpd(registry())
    assert "bin in ('1000001')" in seen
    assert "bbl in ('1000020002')" in seen
