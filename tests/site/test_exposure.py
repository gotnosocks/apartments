"""Which way an apartment faces: Data improvements' labels on the site."""

import sqlite3

import duckdb

from apartments.site import build, exposure


def write_labels(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t(unit_id TEXT, exposure TEXT, source TEXT, street_kind TEXT,"
        " line_votes BIGINT, bedroom TEXT)"
    )
    con.executemany("INSERT INTO t VALUES (?,?,?,?,?,?)", rows)
    con.execute(f"COPY t TO '{path}' (FORMAT parquet)")
    con.close()


def first_listing(root):
    db = sqlite3.connect(root / "current" / "site.sqlite")
    db.row_factory = sqlite3.Row
    return db.execute(
        "SELECT audit_id, unit_id, building_id FROM listings "
        "ORDER BY is_current DESC, id LIMIT 1"
    ).fetchone()


def test_without_labels_the_pages_show_no_exposure(site_root, client):
    row = first_listing(site_root)
    page = f"/buildings/{row['building_id']}"
    html = client.get(page).get_data(as_text=True)
    assert "rear-facing" not in html
    # A faces filter on such a build is ignored, not an error.
    rear = client.get(page + "?faces=rear")
    assert rear.status_code == 200
    assert f'href="/listings/{row["audit_id"]}"' in rear.get_data(as_text=True)


def test_labels_show_in_the_listing_table_and_filter(
    tmp_path, bundle, exposure_file, client
):
    root = tmp_path / "site"
    build.build(bundle, root, scope="Chelsea")
    row = first_listing(root)
    write_labels(
        exposure_file,
        [
            (row["unit_id"], "rear", "line", "", 4, "rear"),
            ("unit:not-in-this-build", "street", "own", "avenue", 0, ""),
        ],
    )
    build.build(bundle, root, scope="Chelsea")
    page = f"/buildings/{row['building_id']}"
    rear = client.get(page + "?faces=rear&per=100").get_data(as_text=True)
    link = f'href="/listings/{row["audit_id"]}"'
    assert link in rear and "likely rear-facing" in rear
    street = client.get(page + "?faces=street&per=100").get_data(as_text=True)
    assert link not in street
    db = sqlite3.connect(root / "current" / "site.sqlite")
    assert db.execute("SELECT COUNT(*) FROM exposure").fetchone()[0] == 1


def test_describe_words():
    own = exposure.describe(
        {
            "exposure": "street",
            "source": "own",
            "street_kind": "avenue",
            "line_votes": 0,
            "bedroom": None,
        }
    )
    assert own["long"] == "Faces the street (avenue)"
    assert own["short"] == "street-facing" and own["bedroom"] is None
    both = exposure.describe(
        {
            "exposure": "both",
            "source": "line",
            "street_kind": None,
            "line_votes": 1,
            "bedroom": None,
        }
    )
    assert both["long"] == (
        "Likely faces both the street and the rear: 1 other apartment in its line "
        "(same letter or number) does"
    )
    assert both["short"] == "likely front and rear"


def test_manual_labels_install_and_read_as_set_by_hand(tmp_path):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    labels = [
        {
            "unit_id": "u1",
            "exposure": "street",
            "source": "manual",
            "street_kind": "",
            "line_votes": 0,
            "bedroom": "",
            "checked_by": "Ben, from the listing photos",
        },
        # A labels file from before manual labels has no checked_by column.
        {"unit_id": "u2", "exposure": "rear", "source": "own", "line_votes": 0},
    ]
    exposure.install(db, tmp_path / "labels.parquet", labels, {"u1", "u2"})
    row = db.execute("SELECT * FROM exposure WHERE unit_id = 'u1'").fetchone()
    words = exposure.describe(row)
    assert words["long"] == (
        "Faces the street (set by hand: Ben, from the listing photos)"
    )
    assert words["short"] == "street-facing" and words["own"]
    row = db.execute("SELECT * FROM exposure WHERE unit_id = 'u2'").fetchone()
    assert exposure.describe(row)["long"] == "Faces the rear or a courtyard"
