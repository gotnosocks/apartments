"""Socrata queries: a timed-out read or a server error is tried again."""

import io
import urllib.error

import pytest
from rentfrontier import external


def _error(code):
    return urllib.error.HTTPError("u", code, "e", {}, io.BytesIO())


def test_socrata_retries_timeouts_and_server_errors_but_not_client_errors(
    monkeypatch,
):
    replies = [TimeoutError(), _error(500), io.BytesIO(b'[{"a": 1}]')]

    def urlopen(url, timeout):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(external.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(external.time, "sleep", lambda s: None)
    assert external._socrata("x", {}, tries=3) == [{"a": 1}]
    replies[:] = [_error(400)]
    with pytest.raises(urllib.error.HTTPError):
        external._socrata("x", {}, tries=3)
    replies[:] = [_error(503), _error(503)]
    with pytest.raises(urllib.error.HTTPError):
        external._socrata("x", {}, tries=2)
