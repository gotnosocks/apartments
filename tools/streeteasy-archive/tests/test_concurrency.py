from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from streeteasy_archive.crawler import ArchiveSpider
from streeteasy_archive.oxylabs import RetryableOxylabsError
from twisted.python.failure import Failure


def spider(tmp_path, budget=0, transport='oxylabs'):
    s = ArchiveSpider.from_crawler(Crawler(ArchiveSpider, Settings()), data_dir=tmp_path, transport=transport, max_requests=budget)
    s.store.enqueue(s.generation, [{'url':f'https://streeteasy.com/rental/{n}', 'kind':'listing'} for n in range(100,110)])
    return s


def test_five_slots_refilled_without_duplicates(tmp_path):
    s=spider(tmp_path)
    batch=list(s.start_requests())
    assert len(batch)==5 and len({r.url for r in batch})==5
    assert s.crawler.settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')==5
    assert list(s.start_requests())==[]
    more=list(s.parse(HtmlResponse(url=batch[2].url,body=b'<html>Listing</html>',request=batch[2])))
    assert len(more)==1 and more[0].url not in {r.url for r in batch}
    assert s.outstanding==5
    s.store.close()


def test_budget_less_than_concurrency(tmp_path):
    s=spider(tmp_path,budget=3)
    batch=list(s.start_requests());assert len(batch)==3
    assert list(s.parse(HtmlResponse(url=batch[0].url,body=b'<html/>',request=batch[0])))==[]
    assert s.sent==3
    s.store.close()


def test_challenge_stops_refills_but_saves_other_inflight_results(tmp_path):
    s=spider(tmp_path);batch=list(s.start_requests())
    assert list(s.parse(HtmlResponse(url=batch[0].url,status=403,body=b'denied',request=batch[0])))==[]
    assert list(s.parse(HtmlResponse(url=batch[1].url,body=b'<html>Listing</html>',request=batch[1])))==[]
    assert s.store.latest_response(batch[1].url)
    assert s.sent==5 and s.stopped
    s.store.close()


def test_direct_transport_stays_sequential(tmp_path):
    s=spider(tmp_path,transport='firefox')
    assert len(list(s.start_requests()))==1
    s.store.close()


def test_configured_twenty_slots_respect_budget(tmp_path):
    s=ArchiveSpider.from_crawler(Crawler(ArchiveSpider, Settings()),data_dir=tmp_path,transport='oxylabs',concurrency=20,max_requests=17)
    s.store.enqueue(s.generation,[{'url':f'https://streeteasy.com/rental/{n}','kind':'listing'} for n in range(100,130)])
    batch=list(s.start_requests())
    assert len(batch)==17 and len({r.url for r in batch})==17
    assert s.crawler.settings.getint('CONCURRENT_REQUESTS')==20
    s.store.close()


def test_exhausted_provider_job_defers_one_url_and_refills_slot(tmp_path):
    s = spider(tmp_path)
    batch = list(s.start_requests())
    failed = batch[0]
    failure = Failure(RetryableOxylabsError('incomplete result'))
    failure.request = failed

    replacement = list(s.errback(failure))

    row = s.store.db.execute(
        'SELECT state,next_attempt FROM frontier WHERE generation=? AND url=?',
        (s.generation, failed.url)).fetchone()
    assert row['state'] == 'pending' and row['next_attempt'] > 0
    assert len(replacement) == 1
    assert not s.stopped
    assert s.store.status(s.generation)['status'] != 'paused'
    s.store.close()
