import json

import pandas as pd
import pytest

from rentfrontier import b0labeljoin, splits
from rentfrontier.b0data import sha256

# listing, SRC's unit, price month, then split17 and split18 in UNITS. v18 splits U into U and
# Q, and V into V and W. UNITS gives g and h another split17 than SRC's unit, and lacks k.
ROWS = [
    ("a", "U", "2024-01", "U", "U"),
    ("b", "U", "2024-03", "U", "U"),
    ("c", "U", "2024-05", "U", "Q"),
    ("d", "U", "2024-07", "U", "Q"),
    ("e", "V", "2024-01", "V", "V"),
    ("f", "V", "2024-02", "V", "W"),
    ("g", "Y", "2024-01", "Y2", "Y2"),
    ("h", "Y", "2024-02", "Y2", "Z"),
    ("k", "K", "2024-01", None, None),
]


def write(tmp_path, monkeypatch, held=("d", "f", "h")):
    monkeypatch.setattr(
        splits, "latest_split", lambda frame: frame.listing_id.isin(held).to_numpy()
    )
    frame = pd.DataFrame(
        {
            "listing_id": [r[0] for r in ROWS],
            "audit_id": [r[0] for r in ROWS],
            "building": "one",
            "unit_id": [r[1] for r in ROWS],
            "price_at": [pd.Timestamp(r[2] + "-01", tz="UTC") for r in ROWS],
            "latest_ask": 3000.0,
        }
    )
    src = tmp_path / "src"
    src.mkdir()
    frame.to_parquet(src / "rows.parquet")
    frame.iloc[:0].to_parquet(src / "set_aside.parquet")
    (src / "manifest.json").write_text(
        json.dumps({"rows": len(frame), "rows_sha256": "abc"})
    )
    units = tmp_path / "units.parquet"
    pd.DataFrame(
        [(r[0], r[3], r[4]) for r in ROWS if r[3]],
        columns=["listing_id", "split17", "split18"],
    ).to_parquet(units)
    return src, units


def test_label_join_moves_rows_to_their_v18_units(tmp_path, monkeypatch):
    src, units = write(tmp_path, monkeypatch)
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    manifest = b0labeljoin.label_join(src, units, out)
    rows = pd.read_parquet(out / "rows.parquet")
    assert list(rows.listing_id) == [r[0] for r in ROWS]
    assert list(rows.unit_id) == ["U", "U", "Q", "Q", "V", "W", "Y", "Y", "K"]
    # d stays the latest of two rows in Q; f is alone in W; h keeps its unit.
    assert list(rows.listing_id[rows.carried_heldout]) == ["d", "h"]
    assert (src / "rows.parquet").read_bytes() == before
    assert (out / "set_aside.parquet").exists()
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    entry = manifest["label_join"]
    assert entry["source_rows_sha256"] == "abc"
    assert entry["units"]["sha256"] == sha256(units)
    assert {k: entry[k] for k in list(entry)[4:]} == {
        "rows": 9,
        "rows_missing_from_units": 1,
        "rows_unmatched": 2,
        "rows_changing_unit": 3,
        "source_units_changed": 2,
        "units_after_change": 2,
        "heldout": 3,
        "carried_heldout": 2,
        "heldout_changing_unit": 2,
    }
    written = json.loads((out / "manifest.json").read_text())
    assert written["label_join"] == entry


def test_label_join_refuses_an_existing_out(tmp_path, monkeypatch):
    src, units = write(tmp_path, monkeypatch)
    (tmp_path / "out").mkdir()
    with pytest.raises(FileExistsError):
        b0labeljoin.label_join(src, units, tmp_path / "out")


def test_label_join_refuses_a_listing_twice_in_units(tmp_path, monkeypatch):
    src, units = write(tmp_path, monkeypatch)
    lines = pd.read_parquet(units)
    pd.concat([lines, lines.iloc[:1]]).to_parquet(units)
    with pytest.raises(SystemExit):
        b0labeljoin.label_join(src, units, tmp_path / "out")
    assert not (tmp_path / "out").exists()
