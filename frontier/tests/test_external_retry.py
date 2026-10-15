import urllib.error

import pytest

from rentfrontier import external


def failing(codes):
    """urlopen that raises HTTPError for each code in turn, then answers."""
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        if len(calls) <= len(codes):
            raise urllib.error.HTTPError(url, codes[len(calls) - 1], "x", {}, None)
        return "ok"

    return urlopen, calls


def test_server_errors_are_retried(monkeypatch):
    urlopen, calls = failing([503, 500])
    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    assert external._urlopen("u", timeout=1, wait=0) == "ok"
    assert len(calls) == 3


def test_client_errors_and_the_last_try_raise(monkeypatch):
    urlopen, calls = failing([404])
    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        external._urlopen("u", timeout=1, wait=0)
    assert len(calls) == 1
    urlopen, calls = failing([503] * 3)
    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        external._urlopen("u", timeout=1, tries=3, wait=0)
    assert len(calls) == 3
