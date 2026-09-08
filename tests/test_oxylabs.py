from __future__ import annotations

import asyncio

import pytest
from scrapy import Request

from streeteasy_archive import oxylabs


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def run(handler, request):
    return asyncio.run(handler.download_request(request))


def test_handler_sends_realtime_request_and_preserves_envelope(monkeypatch):
    calls = []
    envelope = {"results": [{"status_code": 201, "content": "<html>raw ✓</html>", "headers": {"Content-Type": "text/html"}, "job_id": "safe-id"}], "bb": "safe"}
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: (calls.append((args, kwargs)) or FakeResponse(envelope)))

    request = Request("https://streeteasy.com/building/example")
    response = run(oxylabs.OxylabsDownloadHandler(), request)

    assert calls[0][0] == (oxylabs.API_URL,)
    assert calls[0][1]["json"] == {"source": "universal", "url": request.url, "render": "html"}
    assert calls[0][1]["auth"] == ("user", "password")
    assert calls[0][1]["timeout"] == 180
    assert response.status == 201
    assert bytes(response.body) == "<html>raw ✓</html>".encode()
    assert response.meta["archive_provider"] == {"results": envelope["results"]}


def test_handler_strips_wire_length_encoding_and_sensitive_provider_fields(monkeypatch):
    calls = []
    envelope = {"results": [{"status_code": 200, "content": "<html>raw</html>",
                              "_request": {"headers": {"Authorization": "SECRET"}},
                              "session_info": {"cookies": "SECRET"},
                              "_response": {"headers": {"Content-Type": "text/html",
                                                           "Content-Encoding": "gzip",
                                                           "Content-Length": "999",
                                                           "Set-Cookie": "SECRET"}}}]}
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: (calls.append(kwargs) or FakeResponse(envelope)))

    response = run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))

    assert calls[0]["allow_redirects"] is False
    assert "content-encoding" not in {str(k).lower() for k in response.headers}
    assert "content-length" not in {str(k).lower() for k in response.headers}
    provider = response.meta["archive_provider"]
    assert "_request" not in provider["results"][0]
    assert "session_info" not in provider["results"][0]
    assert "SECRET" not in str(provider)


@pytest.mark.parametrize("status", [True, 99, 600])
def test_handler_rejects_invalid_status_values(monkeypatch, status):
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    payload = {"results": [{"status_code": status, "content": "body"}]}
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="missing status"):
        run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))


def test_handler_rejects_oversized_body(monkeypatch):
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    payload = {"results": [{"status_code": 200, "content": "x" * (oxylabs.MAX_BODY + 1)}]}
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="exceeds 32 MiB"):
        run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))


@pytest.mark.parametrize("url", ["https://example.com/building/example", "https://streeteasy.com/building/example?utm_source=x"])
def test_handler_rejects_noncanonical_targets(monkeypatch, url):
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    with pytest.raises(ValueError):
        run(oxylabs.OxylabsDownloadHandler(), Request(url))


def test_provider_http_error_is_secret_safe(monkeypatch):
    monkeypatch.setenv("OXYLABS_USERNAME", "SECRET_USER")
    monkeypatch.setenv("OXYLABS_PASSWORD", "SECRET_PASSWORD")
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: FakeResponse({}, status=401))
    with pytest.raises(RuntimeError, match="Oxylabs request failed") as exc:
        run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize("payload", [{"results": [{"status_code": 403, "content": "denied"}]}, {"results": []}, {"results": [{"status_code": 200}]}])
def test_result_validation_and_error_status(monkeypatch, payload):
    monkeypatch.setenv("OXYLABS_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "password")
    monkeypatch.setattr(oxylabs.requests, "post", lambda *args, **kwargs: FakeResponse(payload))
    if payload["results"] and payload["results"][0].get("status_code") == 403:
        response = run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))
        assert response.status == 403
    else:
        with pytest.raises(RuntimeError):
            run(oxylabs.OxylabsDownloadHandler(), Request("https://streeteasy.com/building/example"))
