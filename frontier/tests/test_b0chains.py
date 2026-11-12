import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0chains, splits
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


def write(tmp_path, links=LINKS, rows=ROWS, still_open=("m",)):
    ads = tmp_path / "ads.parquet"
    pd.DataFrame(
        {
            "listing_id": list(ON),
            "on_day": [pd.Timestamp(d).date() for d in ON.values()],
            # Each ad closes 5 days after it opens, except the ads still open.
            "off_day": [
                None
                if i in still_open
                else (pd.Timestamp(d) + pd.Timedelta(days=5)).date()
                for i, d in ON.items()
            ],
        }
    ).to_parquet(ads)
    path = tmp_path / "links.parquet"
    pd.DataFrame(links, columns=["earlier", "later"]).assign(cell="S1").to_parquet(path)
    frame = pd.DataFrame(rows, columns=["listing_id", "unit_id", "building", "ask"])
    frame = frame.rename(columns={"ask": "latest_ask"}).assign(
        latest_day_how="change",
        rent_stabilized=[i == 2 for i in range(len(rows))],
        audit_id=frame.listing_id,
        price_at=[pd.Timestamp(ON[i], tz="UTC") for i in frame.listing_id],
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


def hold_out(monkeypatch, listings):
    """Make SRC's latest split hold out `listings`."""
    monkeypatch.setattr(
        splits, "latest_split", lambda frame: frame.listing_id.isin(listings).to_numpy()
    )


def test_collapse_keeps_the_latest_row_of_each_chain_under_its_established_unit(
    tmp_path, monkeypatch
):
    # g, p and r are the latest rows of u2, u7 and u8 in SRC.
    hold_out(monkeypatch, {"g", "p", "r"})
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
    assert [str(d) for d in rows.chain_on_day] == [
        "2023-06-01",
        "2024-01-01",
        "2024-03-01",
        "2025-01-01",
        "2024-05-01",
        "2022-02-01",
        "2026-01-01",
    ]
    assert [None if pd.isna(d) else str(d) for d in rows.chain_off_day] == [
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
    # g and p are dropped. r is still the latest row of u8.
    assert rows.carried_heldout.tolist() == [False] * 6 + [True]
    assert splits.SPLITS["carried"](rows).tolist() == rows.carried_heldout.tolist()
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
    assert entry["source_heldout"] == 3
    assert entry["source_heldout_dropped"] == 2
    assert entry["carried_heldout"] == 1
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


def test_collapse_leaves_the_off_day_missing_while_the_last_ad_is_open(tmp_path):
    """f, the last ad of the chain from d, has no row and is still open."""
    src, links = write(tmp_path, still_open=("m", "f"))
    b0chains.collapse(src, links, tmp_path / "out")
    rows = pd.read_parquet(tmp_path / "out" / "rows.parquet").set_index("listing_id")
    assert rows.replaced["e"]
    assert pd.isna(rows.chain_off_day["e"])
    assert str(rows.chain_off_day["c"]) == "2024-01-25"


def test_collapse_counts_a_row_of_another_chain_as_establishing_a_unit(tmp_path):
    """u1 holds a and c alone, each the first ad of a chain. Each chain finds the other's
    row outside itself, so b and d both take u1."""
    rows = [
        ("a", "u1", "one", 3000.0),
        ("b", "u2", "one", 2950.0),
        ("c", "u1", "one", 2900.0),
        ("d", "u3", "one", 2850.0),
    ]
    src, links = write(tmp_path, links=[("a", "b"), ("c", "d")], rows=rows)
    manifest = b0chains.collapse(src, links, tmp_path / "out")
    kept = pd.read_parquet(tmp_path / "out" / "rows.parquet")
    assert kept.listing_id.tolist() == ["b", "d"]
    assert kept.unit_id.tolist() == ["u1", "u1"]
    assert manifest["chains"]["kept_rows_moved"] == 2


def test_collapse_counts_no_move_between_missing_unit_ids(tmp_path):
    rows = [
        ("a", None, "one", 3000.0),
        ("b", None, "one", 2950.0),
        ("k", None, "one", 2800.0),
        ("n", "u1", "one", 2700.0),
    ]
    src, links = write(tmp_path, links=[("a", "b")], rows=rows)
    manifest = b0chains.collapse(src, links, tmp_path / "out")
    assert manifest["chains"]["rows_dropped"] == 1
    assert manifest["chains"]["kept_rows_moved"] == 0


def test_collapse_carries_a_held_out_row_only_while_it_is_its_units_latest(
    tmp_path, monkeypatch
):
    """b loses its unit's other row, a, to the collapse. e was the latest row of u2, and
    the chain from d brings the later f into u2. m's unit is outside every chain."""
    rows = [
        ("a", "u1", "one", 3000.0),
        ("b", "u1", "one", 2950.0),
        ("n", "u2", "two", 4800.0),
        ("d", "u2", "two", 4000.0),
        ("e", "u2", "two", 3900.0),
        ("f", "u4", "two", 3950.0),
        ("k", "u7", "one", 2800.0),
        ("m", "u7", "one", 5000.0),
    ]
    hold_out(monkeypatch, {"b", "e", "m"})
    src, links = write(tmp_path, links=[("a", "b"), ("d", "f")], rows=rows)
    manifest = b0chains.collapse(src, links, tmp_path / "out")
    kept = pd.read_parquet(tmp_path / "out" / "rows.parquet")
    assert kept.listing_id.tolist() == ["b", "n", "e", "f", "k", "m"]
    assert kept.unit_id.tolist() == ["u1", "u2", "u2", "u2", "u7", "u7"]
    assert kept.carried_heldout.tolist() == [False] * 5 + [True]
    assert manifest["chains"]["source_heldout"] == 3
    assert manifest["chains"]["source_heldout_dropped"] == 0
    assert manifest["chains"]["carried_heldout"] == 1


def test_carried_drops_a_row_tied_with_the_one_before_it():
    kept = pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u2", "u2", None],
            "audit_id": ["a", "b", "c", "d", "e"],
            "price_at": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-01-01", "2024-02-01", "2024-03-01"],
                utc=True,
            ),
        }
    )
    held = np.array([False, True, False, True, True])
    assert b0chains.carried(kept, held).tolist() == [False, False, False, True, False]


def test_carried_split_needs_the_column():
    with pytest.raises(ValueError):
        splits.carried_split(pd.DataFrame({"unit_id": ["u1"]}))


def test_carried_agrees_with_the_rows_latest_split_can_draw():
    rng = np.random.default_rng(0)
    for _ in range(50):
        n = int(rng.integers(1, 40))
        kept = pd.DataFrame(
            {
                "unit_id": rng.choice(["u1", "u2", "u3", "u4", None], size=n),
                "audit_id": [f"a{i:02d}" for i in rng.permutation(n)],
                "price_at": pd.to_datetime("2024-01-01", utc=True)
                + pd.to_timedelta(rng.integers(0, 6, size=n), unit="D"),
            },
            index=rng.permutation(n) * 3,
        )
        everything = np.ones(n, dtype=bool)
        assert (
            b0chains.carried(kept, everything).tolist()
            == splits.latest_split(kept, fraction=1.0).tolist()
        )
