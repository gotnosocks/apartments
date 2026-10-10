import io
import json
import urllib.parse

from rentfrontier import external


def test_fetch_noise_pages_a_year_over_a_page(monkeypatch):
    """A year with more complaints than a page is fetched in pages by
    `$offset`; every complaint is kept once."""
    complaints = [
        {
            "unique_key": str(i),
            "created_date": "2021-06-01T00:00:00",
            "complaint_type": "Noise - Street/Sidewalk",
            "descriptor": "Loud Music/Party",
            "latitude": "40.73",
            "longitude": "-73.98",
        }
        for i in range(5)
    ]
    calls = []

    def urlopen(url, timeout):
        if "/api/views/" in url:
            body = {"name": "x", "rowsUpdatedAt": 0}
        else:
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            calls.append(query)
            start, limit = int(query["$offset"]), int(query["$limit"])
            body = (
                complaints[start : start + limit]
                if ">= '2021-" in query["$where"]
                else []
            )
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    table, queries, _ = external.fetch_noise((40.74, -74.0, 40.72, -73.97), page=2)
    assert sorted(table.unique_key) == [str(i) for i in range(5)]
    assert [c["$offset"] for c in calls if ">= '2021-" in c["$where"]] == [
        "0",
        "2",
        "4",
    ]
    assert len(queries) == len(calls)
