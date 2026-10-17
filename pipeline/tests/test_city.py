import ast
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CITY = REPO / "ops" / "pipeline" / "city.py"
TODAY = dt.date(2024, 2, 1)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


city = load("pipeline_city", CITY)


def zipped(text):
    """A zip holding a member named data.txt with the text, dated 2024-01-01 so two calls give
    the same bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(zipfile.ZipInfo("data.txt", date_time=(2024, 1, 1, 0, 0, 0)), text)
    return buffer.getvalue()


class Server:
    """A local stand-in for City Planning's file server and NYC Open Data:
    - `files` maps a URL path to its bytes and Last-Modified time;
    - `updated` maps a dataset to its rowsUpdatedAt;
    - `during` maps a URL path to a function the server calls once, between the file's headers
      and its bytes;
    - `faults` maps a URL path to a list of faults for its next requests, each taken once:
      "drop" closes the connection with no answer, and "short" sends half the file's bytes.
    The server answers 500 for each path in `errors`."""

    def __init__(self):
        self.files, self.updated, self.during, self.faults = {}, {}, {}, {}
        self.errors, self.asked = set(), []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                server.asked.append(path)
                fault = (server.faults.get(path) or [None]).pop(0)
                if fault == "drop":
                    self.close_connection = True
                    return
                if path in server.errors:
                    self.send_error(500)
                    return
                if path.startswith("/api/views/") and path.endswith(".json"):
                    dataset = path.removeprefix("/api/views/").removesuffix(".json")
                    body, modified = (
                        json.dumps({"rowsUpdatedAt": server.updated[dataset]}).encode(),
                        None,
                    )
                elif path in server.files:
                    body, modified = server.files[path]
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                if modified:
                    self.send_header("Last-Modified", modified)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if path in server.during:
                    server.during.pop(path)()
                self.wfile.write(body[: len(body) // 2] if fault == "short" else body)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()


@pytest.fixture
def server(tmp_path, monkeypatch):
    server = Server()
    table = tmp_path / "pluto_releases.csv"
    table.write_text(
        "release,file,published,evidence\n"
        "22v2,nyc_pluto_22v2_arc_csv.zip,,no dated document\n"
        "23v1,nyc_pluto_23v1_csv.zip,2023-03-31,March 2023 (README)\n"
    )
    monkeypatch.setattr(city, "DCP", f"{server.url}/dcp")
    monkeypatch.setattr(city, "OPEN_DATA", server.url)
    monkeypatch.setattr(city, "PLUTO_TABLE", table)
    monkeypatch.setattr(city, "DATASETS", {"footprints": "aaaa-1111"})
    monkeypatch.setattr(city, "WAIT", 0)
    day = "Wed, 19 Apr 2023 14:24:00 GMT"
    for name, body, modified in (
        ("pad/pad_23b.zip", "pad 23b", day),
        ("pad/pad_23c.zip", "pad 23c", "Tue, 11 Jul 2023 13:39:08 GMT"),
        ("pad/pad_24a.zip", "pad 24a", "Wed, 24 Jan 2024 13:48:46 GMT"),
        ("pluto/nyc_pluto_22v2_arc_csv.zip", "pluto 22v2", day),
        ("pluto/nyc_pluto_23v1_csv.zip", "pluto 23v1", day),
        ("pluto/nyc_pluto_23v3_csv.zip", "pluto 23v3", "Tue, 31 Oct 2023 10:00:00 GMT"),
    ):
        server.files[f"/dcp/{name}"] = (zipped(body), modified)
    server.files["/api/v3/views/aaaa-1111/query.csv"] = (
        b'":id","bin"\n"row-1","1"\n',
        None,
    )
    server.updated["aaaa-1111"] = 1760170679
    yield server
    server.http.shutdown()


def lines(archive):
    return [
        json.loads(line)
        for line in (archive / "manifest.ndjson").read_text().splitlines()
    ]


def test_fetch_lists_each_release_with_its_date(server, tmp_path):
    archive = tmp_path / "city"
    summary, status = city.run(archive, ["pad", "pluto", "footprints"], TODAY)
    assert status == 0 and not summary["failed"] and not summary["unlisted"]
    got = {(e["source"], e["release"]): e for e in lines(archive)}
    # 23d and 24b have no release, nor do 23v2, 23v4 and the four 24 names of MapPLUTO.
    assert sorted(got) == [
        ("footprints", "2025-10-11T08:17:59Z"),
        ("pad", "23b"),
        ("pad", "23c"),
        ("pad", "24a"),
        ("pluto", "22v2"),
        ("pluto", "23v1"),
        ("pluto", "23v3"),
    ]
    assert len(summary["absent"]) == 2 + 6
    assert got["pad", "23c"]["published"] == "2023-07-11T13:39:08Z"
    assert got["pad", "23c"]["published_from"] == "Last-Modified"
    assert got["pluto", "23v1"]["published"] == "2023-03-31"
    assert (
        got["pluto", "23v1"]["published_from"]
        == "pluto_releases.csv: March 2023 (README)"
    )
    assert got["pluto", "22v2"]["published"] is None
    assert got["pluto", "23v3"]["published"] == "2023-10-31T10:00:00Z"
    footprints = got["footprints", "2025-10-11T08:17:59Z"]
    assert footprints["path"] == "footprints/aaaa-1111-20251011T081759Z.csv.gz"
    assert footprints["published_from"] == "rowsUpdatedAt"
    body = server.files["/api/v3/views/aaaa-1111/query.csv"][0]
    copy = (archive / footprints["path"]).read_bytes()
    # The gzip header gives no file name and a modification time of 0.
    assert copy[3:8] == bytes(5) and gzip.decompress(copy) == body
    for entry in got.values():
        data = (archive / entry["path"]).read_bytes()
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert not list(archive.rglob("*.part"))
    assert city.verify(archive) == ({"listed": 7, "differ": []}, 0)


def test_fetch_again_takes_only_new_releases(server, tmp_path):
    archive = tmp_path / "city"
    city.run(archive, ["pad", "pluto", "footprints"], TODAY)
    first = (archive / "manifest.ndjson").read_text()
    server.asked.clear()
    summary, _ = city.run(archive, ["pad", "pluto", "footprints"], TODAY)
    assert not summary["fetched"]
    assert (archive / "manifest.ndjson").read_text() == first
    # The second run asks only for the absent names and the dataset's time.
    assert "/dcp/pad/pad_23b.zip" not in server.asked
    assert "/api/v3/views/aaaa-1111/query.csv" not in server.asked
    server.files["/dcp/pad/pad_24b.zip"] = (
        zipped("pad 24b"),
        "Mon, 15 Apr 2024 18:16:32 GMT",
    )
    server.updated["aaaa-1111"] += 86400
    summary, _ = city.run(archive, ["pad", "pluto", "footprints"], dt.date(2024, 4, 20))
    assert [(f["source"], f["release"]) for f in summary["fetched"]] == [
        ("pad", "24b"),
        ("footprints", "2025-10-12T08:17:59Z"),
    ]
    assert len(lines(archive)) == 9
    # Two copies of the same rows have the same bytes.
    copies = [e for e in lines(archive) if e["source"] == "footprints"]
    assert copies[0]["sha256"] == copies[1]["sha256"]


def test_fetch_drops_a_copy_when_the_rows_change_during_it(server, tmp_path):
    archive = tmp_path / "city"

    def change():
        server.updated["aaaa-1111"] += 60

    server.during["/api/v3/views/aaaa-1111/query.csv"] = change
    summary, status = city.run(archive, ["footprints"], TODAY)
    assert status == 0 and summary["moved"] and not summary["fetched"]
    assert not (archive / "manifest.ndjson").exists()
    assert not list(archive.rglob("*.gz*"))
    summary, _ = city.run(archive, ["footprints"], TODAY)
    assert [e["release"] for e in lines(archive)] == ["2025-10-11T08:18:59Z"]


def test_fetch_goes_on_after_a_failure(server, tmp_path):
    archive = tmp_path / "city"
    server.errors.add("/dcp/pad/pad_23c.zip")
    summary, status = city.run(archive, ["pad"], TODAY)
    assert status == 1
    assert [(f["release"], f["error"]) for f in summary["failed"]] == [
        ("23c", "<HTTPError 500: 'Internal Server Error'>")
    ]
    assert [e["release"] for e in lines(archive)] == ["23b", "24a"]
    assert server.asked.count("/dcp/pad/pad_23c.zip") == city.TRIES
    server.errors.clear()
    summary, status = city.run(archive, ["pad"], TODAY)
    assert status == 0 and [e["release"] for e in lines(archive)] == [
        "23b",
        "24a",
        "23c",
    ]


def test_fetch_tries_again_after_a_dropped_or_short_download(server, tmp_path):
    archive = tmp_path / "city"
    server.faults["/dcp/pad/pad_23c.zip"] = ["drop", "short"]
    server.faults["/api/v3/views/aaaa-1111/query.csv"] = ["short"]
    summary, status = city.run(archive, ["pad", "footprints"], TODAY)
    assert status == 0 and len(summary["fetched"]) == 4
    assert server.asked.count("/dcp/pad/pad_23c.zip") == 3
    assert server.asked.count("/api/v3/views/aaaa-1111/query.csv") == 2
    assert city.verify(archive) == ({"listed": 4, "differ": []}, 0)
    copy = archive / "pad" / "pad_23c.zip"
    assert copy.read_bytes() == server.files["/dcp/pad/pad_23c.zip"][0]


def test_fetch_lists_no_short_or_broken_file(server, tmp_path):
    archive = tmp_path / "city"
    server.faults["/dcp/pad/pad_23c.zip"] = ["short"] * city.TRIES
    # A page served with status 200 in place of the zip.
    server.files["/dcp/pad/pad_24a.zip"] = (b"<html>moved</html>", None)
    summary, status = city.run(archive, ["pad"], TODAY)
    assert status == 1 and [e["release"] for e in lines(archive)] == ["23b"]
    errors = [f["error"] for f in summary["failed"]]
    assert len(errors) == 2 and all(e.startswith("Incomplete(") for e in errors)
    assert not list(archive.rglob("*.part"))
    assert not (archive / "pad" / "pad_24a.zip").exists()


def test_fetch_goes_on_after_a_source_fails(server, tmp_path):
    archive = tmp_path / "city"
    server.errors.add("/api/views/aaaa-1111.json")
    summary, status = city.run(archive, ["footprints", "pad"], TODAY)
    assert status == 1 and summary["failed"][0]["source"] == "footprints"
    assert [e["release"] for e in lines(archive)] == ["23b", "23c", "24a"]


def test_pad_quarters_go_on_into_the_next_year():
    pad = [e["release"] for e in city.offers("pad", dt.date(2024, 12, 1))]
    assert pad[0] == "23b" and pad[-3:] == ["24c", "24d", "25a"]


def test_fetch_clears_what_a_stopped_run_left(server, tmp_path):
    archive = tmp_path / "city"
    (archive / "pad").mkdir(parents=True)
    # A stopped run left a part file, and a whole file without its manifest line.
    (archive / "pad" / "pad_23b.zip.part").write_bytes(b"pad 2")
    (archive / "pad" / "pad_23c.zip").write_bytes(b"old")
    (archive / "manifest.ndjson").write_text('{"path": "pad/pad_23d.zip", "by')
    summary, status = city.run(archive, ["pad"], TODAY)
    assert status == 0 and not list(archive.rglob("*.part"))
    assert (archive / "pad" / "pad_23c.zip").read_bytes() == zipped("pad 23c")
    assert sorted(e["release"] for e in city.manifest(archive).values()) == [
        "23b",
        "23c",
        "24a",
    ]


def test_fetch_waits_for_no_other_run(server, tmp_path):
    archive = tmp_path / "city"
    archive.mkdir()
    with open(archive / ".lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        summary, status = city.run(archive, ["pad"], TODAY)
    assert status == 0 and summary["note"].startswith("another run holds")
    assert not (archive / "manifest.ndjson").exists()


def test_verify_finds_a_changed_file(server, tmp_path):
    archive = tmp_path / "city"
    city.run(archive, ["pad"], TODAY)
    (archive / "pad" / "pad_23c.zip").write_bytes(b"pad 23C")
    (archive / "pad" / "pad_24a.zip").unlink()
    assert city.verify(archive) == (
        {"listed": 3, "differ": ["pad/pad_23c.zip", "pad/pad_24a.zip"]},
        1,
    )


def test_pluto_table_matches_frontier():
    source = (REPO / "frontier" / "src" / "rentfrontier" / "external.py").read_text()
    (table,) = [
        ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and getattr(node.targets[0], "id", None) == "PLUTO_RELEASES"
    ]
    with open(city.PLUTO_TABLE, newline="") as f:
        rows = list(csv.DictReader(f))
    assert {
        row["release"]: (row["file"], row["published"] or None, row["evidence"])
        for row in rows
    } == table
