import pytest
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from streeteasy_archive.cli import resolve_delay
from streeteasy_archive.crawler import ArchiveSpider


def test_api_migrates_legacy_delay_and_preserves_new_override():
    assert resolve_delay(None, 'oxylabs', 'chelsea', {'transport':'oxylabs','delay':35}) == 0
    assert resolve_delay(None, 'oxylabs', 'chelsea', {'transport':'oxylabs','delay':2,'pacing_version':2}) == 2
    assert resolve_delay(3, 'oxylabs', 'chelsea', {}) == 3
    assert resolve_delay(None, 'firefox', 'chelsea', {'transport':'oxylabs','delay':0,'pacing_version':2}) == 60
    with pytest.raises(ValueError): resolve_delay(0, 'firefox', 'chelsea', {})
    with pytest.raises(ValueError): resolve_delay(float('nan'), 'oxylabs', None, {})


def test_api_pacing_does_not_throttle_on_provider_latency(tmp_path):
    crawler = Crawler(ArchiveSpider, Settings())
    spider = ArchiveSpider.from_crawler(crawler, data_dir=tmp_path, transport='oxylabs', delay=0)
    assert spider.delay == 0
    assert crawler.settings.getfloat('DOWNLOAD_DELAY') == 0
    assert not crawler.settings.getbool('AUTOTHROTTLE_ENABLED')
    assert not crawler.settings.getbool('RANDOMIZE_DOWNLOAD_DELAY')
    spider.store.close()
