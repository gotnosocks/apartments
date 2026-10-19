import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0, b0trim
from test_b0 import frame_of


def test_dense_start_skips_early_stragglers_and_a_thin_gap():
    day = pd.Series(
        [pd.Timestamp("2010-07-28"), pd.Timestamp("2012-03-01")]
        + [pd.Timestamp("2014-01-06")] * 150
        + [pd.Timestamp("2014-01-13")] * 50  # a thin week after the first dense one
        + [pd.Timestamp("2014-01-20")] * 120
        + [pd.Timestamp("2014-01-27")] * 100
    )
    assert b0trim.dense_start(day, 100) == pd.Timestamp("2014-01-20")
    assert b0trim.dense_start(day, 50) == pd.Timestamp("2014-01-06")
    with pytest.raises(ValueError):
        b0trim.dense_start(day, 101)


def test_trim_writes_a_new_dataset_and_leaves_the_source(tmp_path):
    frame, _ = frame_of(n=4000, weeks=30, seed=7)
    early = frame.iloc[:3].assign(latest_day=pd.Timestamp("2015-02-11"))
    frame = pd.concat([early, frame.iloc[3:]], ignore_index=True).assign(
        latest_day_how="change"
    )
    src = tmp_path / "src"
    src.mkdir()
    frame.to_parquet(src / "rows.parquet")
    (src / "manifest.json").write_text(
        json.dumps(
            {"rows": len(frame), "rows_sha256": "abc", "flags": {"shared_space": 0}}
        )
    )
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    m = b0trim.trim(src, out, min_rows=50)
    assert (src / "rows.parquet").read_bytes() == before
    kept = pd.read_parquet(out / "rows.parquet")
    aside = pd.read_parquet(out / "set_aside.parquet")
    assert len(kept) + len(aside) == len(frame) and len(aside) == 3
    assert m["rows"] == len(kept) and m["trim"]["set_aside"] == 3
    assert m["trim"]["source_rows_sha256"] == "abc"
    assert m["rows_sha256"] == b0trim.sha256(out / "rows.parquet")
    start = pd.Timestamp(m["trim"]["dense_start"])
    assert pd.to_datetime(kept.latest_day).min() >= start
    assert b0.design(kept).start == start
    with pytest.raises(FileExistsError):
        b0trim.trim(src, out, min_rows=50)
    assert np.all(kept.columns == frame.columns)
