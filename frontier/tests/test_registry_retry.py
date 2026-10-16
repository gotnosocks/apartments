import io
import json
import urllib.error

from rentfrontier import external, registry


def test_geosearch_retries_a_server_error(monkeypatch):
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "busy", {}, None)
        return io.BytesIO(json.dumps({"features": []}).encode())

    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(external.time, "sleep", lambda s: None)
    assert registry._get("search", {"text": "1 Main St"}) == {"features": []}
    assert len(calls) == 2
