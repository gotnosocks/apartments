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
