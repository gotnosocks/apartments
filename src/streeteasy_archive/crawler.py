"""Scrapy handles HTTP; SQLite owns the resumable work queue."""
from __future__ import annotations

import asyncio
import email.utils
import math
import re
import time

import scrapy

from .extract import canonical_url, discover, extract, kind_for
from .store import ArchiveStore


def approved_links(items, base):
    result = []
    for item in items:
        url = canonical_url(item.get('url') or '', base)
        kind = kind_for(url) if url else None
        if url and kind:
            result.append({'url': url, 'kind': kind, 'lastmod': item.get('lastmod')})
    return result


def retry_after(headers):
    value = next((v for k, v in headers.items() if str(k).lower() == 'retry-after'), None)
    if not value:
        return 300.0
    try:
        seconds = float(value)
        return max(1.0, seconds) if math.isfinite(seconds) else 300.0
    except (TypeError, ValueError):
        try:
            return max(1.0, email.utils.parsedate_to_datetime(str(value)).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return 300.0


def is_challenge(body):
    text = body[:30000].lower()
    title = re.search(br'<title[^>]*>\s*([^<]+)', text)
    return bool(title and any(marker in title.group(1) for marker in
                (b'captcha', b'access denied', b'access to this page has been denied', b'just a moment'))) or any(
                marker in text for marker in (b'id="px-captcha"', b'id="challenge-form"',
                                             b'verify you are human', b'are you a robot'))


class ArchiveSpider(scrapy.Spider):
    name = 'streeteasy_archive'
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'CONCURRENT_REQUESTS': 1,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'COOKIES_ENABLED': False,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
        'AUTOTHROTTLE_START_DELAY': 10.0,
        'DOWNLOAD_DELAY': 10.0,  # Scrapy randomizes to [0.5, 1.5] times this.
        'RANDOMIZE_DOWNLOAD_DELAY': True,
        'REDIRECT_ENABLED': False,
        'METAREFRESH_ENABLED': False,
        'RETRY_ENABLED': False,
        'TELNETCONSOLE_ENABLED': False,
        'HTTPPROXY_ENABLED': False,
        'DOWNLOAD_TIMEOUT': 45,
        'DOWNLOAD_MAXSIZE': 32 * 1024 * 1024,
        'DOWNLOAD_VERIFY_CERTIFICATES': True,
        'USER_AGENT': 'StreetEasyArchive/0.1 (personal archival research)',
    }

    def __init__(self, data_dir='data', generation=None, max_requests=0, building=None, neighborhood=None, delay=None, transport='http', **kwargs):
        super().__init__(**kwargs)
        self.store = ArchiveStore(data_dir)
        self.generation = int(generation or self.store.current_generation() or self.store.new_generation())
        self.max_requests = int(max_requests)
        self.building = building
        self.neighborhood = neighborhood
        self.transport = transport
        self.delay = float(delay if delay is not None else (0 if transport == 'oxylabs' else 10))
        self.concurrency = 5 if transport == 'oxylabs' else 1
        self.outstanding = 0
        self.sent = 0
        self.stopped = False

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider.transport == 'oxylabs':
            crawler.settings.set('CONCURRENT_REQUESTS', spider.concurrency, priority='cmdline')
            crawler.settings.set('CONCURRENT_REQUESTS_PER_DOMAIN', spider.concurrency, priority='cmdline')
            # API latency includes provider rendering/retries, not origin load.
            crawler.settings.set('DOWNLOAD_TIMEOUT', 200, priority='cmdline')
            crawler.settings.set('AUTOTHROTTLE_ENABLED', False, priority='cmdline')
            crawler.settings.set('RANDOMIZE_DOWNLOAD_DELAY', False, priority='cmdline')
        crawler.settings.set('DOWNLOAD_DELAY', spider.delay, priority='cmdline')
        crawler.settings.set('AUTOTHROTTLE_START_DELAY', spider.delay, priority='cmdline')
        return spider

    def _request(self):
        if self.stopped or (self.max_requests and self.sent >= self.max_requests):
            return None
        while True:
            row = self.store.claim(self.generation, url_prefix=self.building, scoped=bool(self.neighborhood))
            if not row:
                return None
            canonical = canonical_url(row['url'])
            kind = kind_for(canonical) if canonical else None
            if canonical == row['url'] and kind:
                break
            self.store.resolve_obsolete_url(self.generation, row['url'], canonical if kind else None, kind)
        self.sent += 1
        self.outstanding += 1
        return scrapy.Request(row['url'], headers=self.store.conditional_headers(self.generation, row['url']),
                              callback=self.parse, errback=self.errback, dont_filter=True,
                              meta={'archive_url': row['url'], 'archive_kind': row['kind'], 'dont_redirect': True, 'handle_httpstatus_all': True})

    def start_requests(self):
        while self.outstanding < self.concurrency:
            request = self._request()
            if request is None:
                break
            yield request

    async def start(self):
        # Across process restarts, Scrapy's in-memory download slot is new.
        if self.transport != 'oxylabs':
            await asyncio.sleep(self.store.request_delay())
        for request in self.start_requests():
            yield request

    def parse(self, response):
        self.outstanding = max(0, self.outstanding - 1)
        self.store.note_response(self.delay / 2)
        url = response.meta['archive_url']
        headers = response.meta.get('archive_response_headers', dict(response.headers.to_unicode_dict()))
        lower = {k.lower(): v for k, v in headers.items()}
        content_type = lower.get('content-type', '')
        body = bytes(response.body)
        status = response.status
        if status in (401, 403, 408, 429) or status >= 500 or is_challenge(body):
            self.store.record_gap(self.generation, url, status, headers,
                                  f'blocked/challenge or transient HTTP {status}', body=body,
                                  content_type=content_type, complete=False, pause_seconds=retry_after(headers))
            self.stopped = True
            return
        if 300 <= status < 400 and status != 304:
            location = lower.get('location')
            links = approved_links([{'url': location}], url) if location else []
            self.store.record_gap(self.generation, url, status, headers,
                                  'redirect observed' if links else 'redirect coverage gap',
                                  discovered=links, body=body if response.meta.get('archive_body_captured', True) else None, content_type=content_type)
            if self.neighborhood and links:
                from .scope import enroll
                enroll(self.store, self.generation, {link['url']: 'property history redirect from ' + url for link in links})
        elif status >= 400:
            self.store.record_gap(self.generation, url, status, headers,
                                  f'HTTP {status} coverage gap', body=body, content_type=content_type)
        else:
            try:
                if status == 304:
                    previous = self.store.latest_response(url)
                    if not previous:
                        raise ValueError('304 has no previous successful body')
                    body = self.store.get_body(previous['body_hash'])
                    content_type = content_type or previous['content_type'] or ''
                data = extract(body, url, content_type)
                if response.meta.get('archive_browser'):
                    data['browser_capture'] = response.meta['archive_browser']
                if response.meta.get('archive_provider'):
                    data['provider_capture'] = response.meta['archive_provider']
                links = approved_links(data['links'], url)
            except Exception as exc:
                self.store.record_gap(self.generation, url, status, headers,
                                      f'parser coverage gap: {type(exc).__name__}: {exc}',
                                      body=body, content_type=content_type)
            else:
                self.store.record(self.generation, url, status, headers, body,
                                  content_type, data, discovered=links)
                if self.neighborhood:
                    from .scope import expand
                    expand(self.store, self.generation, data, url)
        transport_errors = response.meta.get('archive_browser', {}).get('interception', {}).get('errors', [])
        if transport_errors:
            # The main response above remains archived. Halt further traffic when
            # browser interception fails rather than silently accepting instability.
            with self.store._tx():
                self.store.db.execute("UPDATE generations SET status='paused',cooldown=? WHERE id=?", (time.time() + 300, self.generation))
            self.logger.error('Browser interception errors; response saved and crawl paused: %s', transport_errors)
            self.stopped = True
        else:
            yield from self.start_requests()

    def errback(self, failure):
        self.outstanding = max(0, self.outstanding - 1)
        self.store.note_response(self.delay / 2)
        self.store.record_gap(self.generation, failure.request.meta['archive_url'], None, {},
                              f'transient failure: {failure.value}', complete=False, pause_seconds=300)
        self.stopped = True

    def closed(self, reason):
        self.store.finish(self.generation)
        self.store.close()
