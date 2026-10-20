import json

import pandas as pd
import pytest

from rentfrontier import b0nyc
from test_b0 import frame_of


def test_nyc_only_sets_the_registry_buildings_aside(tmp_path):
    frame, _ = frame_of(n=1000, weeks=20, seed=3)
    frame = frame.assign(latest_day_how="change")
    nj = sorted(frame.building.unique())[:3]
    registry = tmp_path / "registry.parquet"
    pd.DataFrame({"building": nj, "lot": "x"}).to_parquet(registry)
    src = tmp_path / "src"
    src.mkdir()
    frame.to_parquet(src / "rows.parquet")
    (src / "manifest.json").write_text(
        json.dumps({"rows": len(frame), "rows_sha256": "abc", "flags": {}})
    )
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    m = b0nyc.nyc_only(src, out, registry)
    assert (src / "rows.parquet").read_bytes() == before
    kept = pd.read_parquet(out / "rows.parquet")
    aside = pd.read_parquet(out / "set_aside.parquet")
    assert set(aside.building) == set(nj)
    assert not kept.building.isin(nj).any()
    assert len(kept) + len(aside) == len(frame)
    assert m["rows"] == len(kept) and m["region"]["set_aside"] == len(aside)
    assert m["region"]["source_rows_sha256"] == "abc"
    assert m["rows_sha256"] == b0nyc.sha256(out / "rows.parquet")
    assert list(kept.columns) == list(frame.columns)
    with pytest.raises(FileExistsError):
        b0nyc.nyc_only(src, out, registry)
