import pandas as pd

from rentfrontier import external


def test_registry_borough_takes_most_lots_digit():
    registry = pd.DataFrame({"bbl": ["3012340001", "3012340002", "1000010001", None]})
    assert external.registry_borough(registry) == "3"


def test_basemap_land_layer_reads_the_registry_borough(monkeypatch):
    seen = []

    def socrata(dataset, params):
        seen.append((dataset, params))
        return []

    monkeypatch.setattr(external, "_socrata", socrata)
    external.fetch_basemap((40.7, -74.0, 40.6, -73.9), "3")
    land = [p for d, p in seen if d == external.BOROUGHS_ID]
    assert land == [{"$select": "boroname, the_geom", "borocode": 3}]


def test_releases_read_every_borough_the_lots_lie_in(monkeypatch):
    import io
    import zipfile

    columns = ["bbl"] + [c for c in external.PLUTO_COLUMNS if c != "bbl"]

    def archive(files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, bbls in files.items():
                rows = [",".join([b] + ["x"] * (len(columns) - 1)) for b in bbls]
                z.writestr(name, "\n".join([",".join(columns), *rows]) + "\n")
        return buf.getvalue()

    zips = {
        "split.zip": archive(
            {"bk09v1.csv": ["3000010001"], "qn09v1.csv": ["4000010001"]}
        ),
        "city.zip": archive({"pluto.csv": ["3000010001", "4000010001"]}),
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        external,
        "PLUTO_RELEASES",
        {
            "09v1": ("split.zip", "2009-06-01", None),
            "26v2": ("city.zip", "2026-08-01", None),
        },
    )
    monkeypatch.setattr(
        external,
        "_urlopen",
        lambda request, timeout: Response(zips[request.full_url.rsplit("/", 1)[1]]),
    )
    table, files = external.fetch_pluto_releases(["3000010001", "4000010001"])
    assert sorted(zip(table.release, table.bbl)) == [
        ("09v1", "3000010001"),
        ("09v1", "4000010001"),
        ("26v2", "3000010001"),
        ("26v2", "4000010001"),
    ]
    assert len(files) == 3
