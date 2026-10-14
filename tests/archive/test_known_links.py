import random

import pytest

from streeteasy_archive import cli, known_links, pacer, scope
from streeteasy_archive.oxylabs import OxylabsDownloadHandler
from streeteasy_archive.store import ArchiveStore

B = "https://streeteasy.com/building/"
URLS = [
    B + "a",
    B + "b",
    B + "a/4c",
    B + "a/rental/1300001",
    "https://streeteasy.com/rental/1300002",
    "https://streeteasy.com/rental/1300002?featured=1",
    "http://streeteasy.com/building/a/",
    B + "a/media_gallery",
    B + "a?archive_view=unavailable-rentals",
    "https://www.streeteasy.com/rental/1300003",
    "https://streeteasy.com/rental/1300003",
    "https://example.com/elsewhere",
]


EDITS = [
    "UPDATE frontier SET kind='sitemap' WHERE url=?",
    "UPDATE frontier SET listing_key='x' WHERE url=?",
    "UPDATE frontier SET state='deferred' WHERE url=?",
    "DELETE FROM scope_urls WHERE url=?",
    "DELETE FROM frontier WHERE url=?",
]


def dump(s):
    tables = {
        "frontier": "*",
        "scope_urls": "*",
        "scope_buildings": "*",
        "url_aliases": "generation,url,target_url,reason",
    }
    return [
        s.db.execute(f"SELECT rowid,{cols} FROM {t} ORDER BY rowid").fetchall()
        for t, cols in tables.items()
    ]


def replay(path, enroll, calls, edits):
    s = ArchiveStore(path)
    g = s.new_generation()
    for i, (urls, roots) in enumerate(calls):
        with s._tx():
            enroll(s, g, urls, roots)
        if i in edits:
            s.db.execute(*edits[i])
            s.db.commit()
    out = [[tuple(r) for r in t] for t in dump(s)]
    s.close()
    return out


def test_same_rows_as_scope_enroll(tmp_path):
    rng = random.Random(3)
    calls, edits = [], {}
    for i in range(60):
        # A call right after an edit enrolls every link, so each edit is tested.
        picked = (
            rng.sample(URLS, len(URLS))
            if i - 1 in edits
            else rng.sample(URLS, rng.randint(1, len(URLS)))
        )
        calls.append(
            (
                {u: f"reason {i}" for u in picked},
                rng.sample([B + "a", B + "b", B + "c"], rng.randint(0, 3)),
            )
        )
        if i % 3 == 0:
            # Each of the first five links gets one kind of edit, so no later edit undoes it.
            n = i // 3 % len(EDITS)
            edits[i] = [EDITS[n], (URLS[n],)]
    old = replay(tmp_path / "old", known_links.ORIGINAL_ENROLL, calls, edits)
    new = replay(tmp_path / "new", known_links.enroll_known_first, calls, edits)
    assert new == old
    assert len(old[0]) > 5


def test_unchanged_links_are_skipped(tmp_path, monkeypatch):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    urls = {B + "a": "r", B + "a/4c": "r", "https://streeteasy.com/rental/1300002": "r"}
    known_links.enroll_known_first(s, g, urls, [B + "a"])
    seen = []
    monkeypatch.setattr(
        known_links, "ORIGINAL_ENROLL", lambda *a: seen.append((a[2], list(a[3])))
    )
    known_links.enroll_known_first(s, g, {**urls, B + "b": "r"}, [B + "a", B + "b"])
    assert seen == [({B + "b": "r"}, [B + "b"])]
    s.close()


def test_known_links_is_scoped():
    original = scope._enroll
    with known_links.known_links():
        assert scope._enroll is known_links.enroll_known_first
    assert scope._enroll is original


def test_crawl_runs_inside_known_links(tmp_path, monkeypatch):
    seen = []

    class Started(Exception):
        pass

    class Process:
        def __init__(self, *a, **k):
            pass

        def create_crawler(self, spider):
            class Signals:
                def connect(self, *a, **k):
                    pass

            crawler = type("Crawler", (), {})()
            crawler.signals = Signals()
            return crawler

        def crawl(self, *a, **k):
            return type("Deferred", (), {"addErrback": lambda self, f: None})()

        def start(self):
            seen.append(scope._enroll)
            seen.append(OxylabsDownloadHandler._submission_slot)
            raise Started

    monkeypatch.setattr("scrapy.crawler.CrawlerProcess", Process)
    args = cli.argparse.Namespace(
        transport="oxylabs",
        oxylabs_render=False,
        api_rps=1,
        concurrency=1,
        data=str(tmp_path),
        max_requests=1,
        building=None,
        neighborhood=None,
        delay=0,
        include_unavailable=True,
    )
    with pytest.raises(Started):
        cli.run_crawler(args, 1)
    assert seen == [known_links.enroll_known_first, pacer.steady_slot]
    assert scope._enroll is known_links.ORIGINAL_ENROLL
    assert OxylabsDownloadHandler._submission_slot is pacer.ORIGINAL_SLOT


def test_form_memo_is_capped(monkeypatch):
    monkeypatch.setattr(known_links, "_FORMS", {})
    monkeypatch.setattr(known_links, "FORMS_LIMIT", 3)
    for url in URLS:
        known_links._form(url)
        assert len(known_links._FORMS) <= 3
