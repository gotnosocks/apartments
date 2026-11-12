import json

import pandas as pd
import pytest

from rentfrontier import b0chains
from rentfrontier.b0data import sha256

# Chain a -> b -> c, with every ad in the rows. Chain d -> e -> f, where f has no row.
# Chain g -> h shares unit u2 with the first chain. Chain p -> q -> r passes through two
# established unit ids. The link x -> y has no ad in the build.
LINKS = [
    ("a", "b"),
    ("b", "c"),
    ("d", "e"),
    ("e", "f"),
    ("g", "h"),
    ("p", "q"),
    ("q", "r"),
    ("x", "y"),
]
ON = {
    "a": "2024-01-01",
    "b": "2024-01-10",
    "c": "2024-01-20",
    "d": "2024-03-01",
    "e": "2024-03-05",
    "f": "2024-03-09",
    "g": "2025-01-01",
    "h": "2025-01-08",
    "k": "2023-06-01",
    "m": "2024-05-01",
    "n": "2022-02-01",
    "p": "2026-01-01",
    "q": "2026-01-05",
    "r": "2026-01-09",
}
ROWS = [
    # listing, unit, building, latest ask
    ("k", "u2", "one", 2800.0),
    ("a", "u1", "one", 3000.0),
    ("b", "u2", "one", 2950.0),
    ("c", "u3", "one", 2900.0),
    ("d", "u5", "two", 4000.0),
    ("e", "u4", "two", 3900.0),
    ("g", "u2", "one", 3100.0),
    ("h", "u6", "one", 3050.0),
    ("m", "u7", "two", 5000.0),
    ("n", "u8", "two", 4800.0),
    ("p", "u7", "two", 5200.0),
    ("q", "u9", "two", 5150.0),
    ("r", "u8", "two", 5100.0),
]


def write(tmp_path, links=LINKS, rows=ROWS):
    ads = tmp_path / "ads.parquet"
    pd.DataFrame(
        {
            "listing_id": list(ON),
            "on_day": [pd.Timestamp(d).date() for d in ON.values()],
            # Each ad closes 5 days after it opens, and m is still open.
            "off_day": [
                None if i == "m" else (pd.Timestamp(d) + pd.Timedelta(days=5)).date()
                for i, d in ON.items()
            ],
        }
    ).to_parquet(ads)
    path = tmp_path / "links.parquet"
    pd.DataFrame(links, columns=["earlier", "later"]).assign(cell="S1").to_parquet(path)
    frame = pd.DataFrame(rows, columns=["listing_id", "unit_id", "building", "ask"])
    frame = frame.rename(columns={"ask": "latest_ask"}).assign(
        latest_day_how="change", rent_stabilized=[i == 2 for i in range(len(rows))]
    )
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    frame.to_parquet(src / "rows.parquet")
    frame.iloc[:0].to_parquet(src / "set_aside.parquet")
    manifest = {
        "rows": len(frame),
        "rows_sha256": "abc",
        "flags": {"rent_stabilized": 1},
        "latest_day_how": {"change": len(frame)},
        "build": {"ads": {"path": str(ads), "sha256": sha256(ads)}},
    }
    (src / "manifest.json").write_text(json.dumps(manifest))
    return src, path


def test_chains_follows_links_from_each_first_ad():
    table = b0chains.chains(pd.DataFrame(LINKS[:5], columns=["earlier", "later"]))
    table = table.sort_values(["chain", "place"])
    assert table.values.tolist() == [
        ["a", "a", 0, 3],
        ["b", "a", 1, 3],
        ["c", "a", 2, 3],
        ["d", "d", 0, 3],
        ["e", "d", 1, 3],
        ["f", "d", 2, 3],
        ["g", "g", 0, 2],
        ["h", "g", 1, 2],
    ]


@pytest.mark.parametrize(
    "links",
    [
        [("a", "b"), ("a", "c")],
        [("a", "c"), ("b", "c")],
        [("a", "b"), ("b", "a"), ("c", "d")],
    ],
)
def test_chains_refuses_forks_and_rings(links):
    with pytest.raises(SystemExit):
        b0chains.chains(pd.DataFrame(links, columns=["earlier", "later"]))


def test_collapse_keeps_the_latest_row_of_each_chain_under_its_established_unit(
    tmp_path,
):
    src, links = write(tmp_path)
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    manifest = b0chains.collapse(src, links, out)
    rows = pd.read_parquet(out / "rows.parquet")
    assert rows.listing_id.tolist() == ["k", "c", "e", "h", "m", "n", "r"]
    assert rows.latest_ask.tolist() == [
        2800.0,
        2900.0,
        3900.0,
        3050.0,
        5000.0,
        4800.0,
        5100.0,
    ]
    # u2 holds rows outside the chain from a (k and g) and outside the chain from g, so c
    # and h take it. Neither u4 nor u5 holds a row outside the chain from d, so e keeps
    # u4. u7 and u8 both hold rows outside the chain from p, so r keeps u8.
    assert rows.unit_id.tolist() == ["u2", "u2", "u4", "u2", "u7", "u8", "u8"]
    assert rows.chain_ads.tolist() == [1, 3, 3, 2, 1, 1, 3]
    assert [str(d) for d in rows.on_day] == [
        "2023-06-01",
        "2024-01-01",
        "2024-03-01",
        "2025-01-01",
        "2024-05-01",
        "2022-02-01",
        "2026-01-01",
    ]
    assert [None if pd.isna(d) else str(d) for d in rows.off_day] == [
        "2023-06-06",
        "2024-01-25",
        "2024-03-14",
        "2025-01-13",
        None,
        "2022-02-06",
        "2026-01-14",
    ]
    # f, the last ad of the chain from d, has no row, and e carries f's off-market day.
    assert rows.replaced.tolist() == [False, False, True, False, False, False, False]
    dropped = pd.read_parquet(out / "collapsed.parquet")
    assert dropped.listing_id.tolist() == ["a", "b", "d", "g", "p", "q"]
    assert dropped.kept_listing_id.tolist() == ["c", "c", "e", "h", "r", "r"]
    assert dropped.unit_id.tolist() == ["u1", "u2", "u5", "u2", "u7", "u9"]
    entry = manifest["chains"]
    assert entry["source"] == str(src)
    assert entry["source_rows_sha256"] == "abc"
    assert entry["links_sha256"] == sha256(links)
    assert entry["links_read"] == 8
    assert entry["links_outside_build"] == 1
    assert entry["chains"] == 4
    assert entry["chains_with_rows"] == 4
    assert entry["rows_in_chains"] == 10
    assert entry["rows_dropped"] == 6
    assert entry["kept_rows_replaced"] == 1
    assert entry["kept_rows_moved"] == 2
    assert entry["chains_with_several_established"] == 1
    assert entry["unit_ids_before"] == 9
    assert entry["unit_ids_after"] == 4
    assert manifest["rows"] == 7
    assert manifest["latest_day_how"] == {"change": 7}
    assert manifest["flags"] == {"rent_stabilized": 0}
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert (src / "rows.parquet").read_bytes() == before
    assert (out / "set_aside.parquet").read_bytes() == (
        src / "set_aside.parquet"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        b0chains.collapse(src, links, out)


def test_collapse_with_no_link_in_the_build_copies_the_rows(tmp_path):
    src, links = write(tmp_path, links=[("x", "y")])
    manifest = b0chains.collapse(src, links, tmp_path / "out")
    rows = pd.read_parquet(tmp_path / "out" / "rows.parquet")
    assert rows.unit_id.tolist() == [r[1] for r in ROWS]
    assert rows.chain_ads.tolist() == [1] * len(ROWS)
    assert not rows.replaced.any()
    assert manifest["chains"]["rows_dropped"] == 0
    assert manifest["chains"]["kept_rows_moved"] == 0


def test_collapse_refuses_a_chain_across_buildings(tmp_path):
    src, links = write(tmp_path, links=[("c", "d")])
    with pytest.raises(SystemExit):
        b0chains.collapse(src, links, tmp_path / "out")


def test_collapse_refuses_a_changed_ads_file(tmp_path):
    src, links = write(tmp_path)
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["ads"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0chains.collapse(src, links, tmp_path / "out")
