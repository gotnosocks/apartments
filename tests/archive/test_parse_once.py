import pytest

from apartments import granular_parse
from streeteasy_archive import parse_once

URL = "https://streeteasy.com/building/a/4c"


@pytest.fixture
def calls(monkeypatch):
    calls = []

    def parse(body, url):
        calls.append((body, url))
        if body == b"bad":
            raise ValueError("bad page")
        return {"url": url, "n": len(calls)}, [{"event": 1}, {"event": 2}]

    monkeypatch.setattr(parse_once, "ORIGINAL_PARSE", parse)
    return calls


def parse(body, url):
    # annotate imports parse_listing when it runs, as here.
    from apartments.granular_parse import parse_listing

    return parse_listing(body, url)


def test_repeat_parses_once(calls):
    body = b"<html>page</html>"
    with parse_once.parse_once():
        first = parse(body, URL)
        second = parse(bytes(body), URL)
    assert len(calls) == 1
    assert first == second
    first[0]["n"] = 99
    first[1][0]["event"] = 99
    with parse_once.parse_once():
        assert parse(body, URL) == ({"url": URL, "n": 2}, [{"event": 1}, {"event": 2}])


def test_other_body_or_url_parses_again(calls):
    with parse_once.parse_once():
        parse(b"a", URL)
        parse(b"b", URL)
        parse(b"b", URL + "x")
        parse(b"b", URL + "x")
    assert len(calls) == 3


def test_errors_are_not_stored(calls):
    with parse_once.parse_once():
        for _ in range(2):
            with pytest.raises(ValueError):
                parse(b"bad", URL)
    assert len(calls) == 2


def test_parse_once_is_scoped():
    with parse_once.parse_once():
        assert granular_parse.parse_listing is parse_once.parse_listing_once
    assert granular_parse.parse_listing is parse_once.ORIGINAL_PARSE
