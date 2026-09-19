"""Discovery identities and paid-request boundaries survive collection and replay."""
import asyncio
import json

import pytest
from scrapy.http import HtmlResponse

from apartments import discovery_detail_refresh as m
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from tests.test_candidate_refresh import html


def fixture(tmp_path):
    cards = []
    for identifier, url in [('100', 'https://streeteasy.com/building/demo/1d'),
                            ('101', 'https://streeteasy.com/building/demo/rental/101')]:
        cards.append({'source_listing_id': identifier, 'canonical_url': url, 'href': url,
                      'in_chelsea_scope': True, 'source_fields': {'furnished': True, 'monthsFree': 1}})
    # Out-of-scope advertised inventory is not silently included.
    cards.append({'source_listing_id': '102', 'canonical_url': 'https://streeteasy.com/building/elsewhere/3d',
                  'href': 'https://streeteasy.com/building/elsewhere/3d', 'in_chelsea_scope': False})
    page = {'seed_path': '/for-rent/chelsea', 'page': 1,
            'source_url': 'https://streeteasy.com/for-rent/chelsea',
            'source_clock': {'capture_started_at': '2026-09-18T20:00:00Z'},
            'body_sha256': 'a' * 64, 'capture_reference': {'example': True}, 'cards': cards}
    report = tmp_path / 'discovery'
    publish_bundle(report, {'pages.jsonl': canonical(page) + '\n'}, {'version': 'test-discovery'})
    rows = []
    for c in cards[:2]:
        observation = {'seed': page['seed_path'], 'page': 1, 'source_url': page['source_url'],
                       'source_clock': page['source_clock'], 'body_sha256': page['body_sha256'],
                       'capture_reference': page['capture_reference'], 'card': c}
        rows.append({'source_listing_id': c['source_listing_id'], 'canonical_unit_url': c['canonical_url'],
                     'observed_detail_urls': [c['href']], 'observations': [observation]})
    review = tmp_path / 'review'
    manifest = {'version': 'bounded-rental-discovery-review-v1',
                'discovery_report_manifest_sha256': digest(report / 'complete.json')}
    publish_bundle(review, {'detail-review-queue.jsonl': ''.join(canonical(r) + '\n' for r in rows)}, manifest)
    return review, report, rows, manifest


def test_plan_keeps_all_in_scope_products_and_defers_unknown_unit_identity(tmp_path):
    review, report, _, _ = fixture(tmp_path)
    plan, _ = m.prepare(review, report, tmp_path / 'out', max_targets=2)
    assert len(plan['targets']) == 2  # furnished/concession cards still collected
    assert plan['max_provider_submissions'] == 6
    known, unresolved = plan['targets']
    assert known['canonical_unit_url'].endswith('/1d')
    assert unresolved['canonical_unit_url'] is None and unresolved['unit_id'] is None
    assert unresolved['url'] == 'https://streeteasy.com/rental/101'
    assert unresolved['expected_building_path'] == '/building/demo'
    with pytest.raises(ValueError, match='no silent truncation'):
        m.prepare(review, report, tmp_path / 'small', max_targets=1)
    assert not (tmp_path / 'small/archive').exists()


def test_preflight_resume_and_no_refetch_establish_detail_identity(tmp_path):
    review, report, _, _ = fixture(tmp_path); output = tmp_path / 'out'; calls = []
    async def fetch(request):
        calls.append(request.url)
        identifier = request.url.rsplit('/', 1)[1]
        row = {'source_listing_id': identifier, 'canonical_unit_url': 'https://streeteasy.com/building/demo/' + ('1d' if identifier == '100' else '2d')}
        return HtmlResponse(request.url, request=request, body=html(row, status='RENTED' if identifier == '101' else 'ACTIVE'))
    paused = asyncio.run(m.collect(review, report, output, fetch=fetch, max_new_requests=1))
    assert paused['status'] == 'paused_at_declared_limit' and len(calls) == 1
    result = asyncio.run(m.collect(review, report, output, fetch=fetch))
    assert result['report']['listing_status_counts'] == {'ACTIVE': 1, 'RENTED': 1}
    assert len(calls) == 2
    rows = [json.loads(l) for l in (output / 'snapshot/candidates.jsonl').read_text().splitlines()]
    assert rows[1]['canonical_unit_url'].endswith('/2d')
    assert rows[1]['discovery_provenance']['unit_identity_established_from_detail'] is True
    assert rows[0]['discovery_provenance']['unit_identity_established_from_detail'] is False
    changes = [json.loads(l) for l in (output / 'snapshot/changes.jsonl').read_text().splitlines()]
    assert all(r['changes'] == {} for r in changes)
    assert asyncio.run(m.collect(review, report, output, fetch=fetch)) == result
    assert len(calls) == 2


@pytest.mark.parametrize('damage', ['known_unit', 'unknown_building', 'advertisement'])
def test_mismatched_detail_never_inherits_search_identity(tmp_path, damage):
    review, report, _, _ = fixture(tmp_path)
    async def fetch(request):
        identifier = request.url.rsplit('/', 1)[1]
        url = 'https://streeteasy.com/building/demo/' + ('1d' if identifier == '100' else '2d')
        if damage == 'known_unit' and identifier == '100': url = 'https://streeteasy.com/building/demo/wrong'
        if damage == 'unknown_building' and identifier == '101': url = 'https://streeteasy.com/building/other/2d'
        row = {'source_listing_id': '999' if damage == 'advertisement' else identifier, 'canonical_unit_url': url}
        return HtmlResponse(request.url, request=request, body=html(row))
    result = asyncio.run(m.collect(review, report, tmp_path / 'out', fetch=fetch))
    assert result['report']['failed'] == (2 if damage == 'advertisement' else 1)


def test_source_block_pauses_durably_before_next_request(tmp_path):
    review, report, _, _ = fixture(tmp_path); calls = []
    async def fetch(request):
        calls.append(request.url)
        return HtmlResponse(request.url, request=request, status=403, body=b'blocked')
    output = tmp_path / 'out'
    first = asyncio.run(m.collect(review, report, output, fetch=fetch))
    assert first['status'] == 'paused_after_blocked_response'
    assert len(calls) == 1
    assert asyncio.run(m.collect(review, report, output, fetch=fetch)) == first
    assert len(calls) == 1


def test_republished_queue_cannot_change_verified_card_evidence(tmp_path):
    review, report, rows, manifest = fixture(tmp_path)
    rows[0]['observations'][0]['card']['source_fields']['furnished'] = False
    changed = tmp_path / 'changed'
    publish_bundle(changed, {'detail-review-queue.jsonl': ''.join(canonical(r) + '\n' for r in rows)}, manifest)
    with pytest.raises(ValueError, match='evidence or identity differs'):
        m.prepare(changed, report, tmp_path / 'out')


def test_interrupted_request_is_not_repeated(tmp_path):
    review, report, _, _ = fixture(tmp_path); output = tmp_path / 'out'
    plan, ph = m.prepare(review, report, output)
    publish_bundle(output / 'requests/0000', {'intent.json': '{}\n'},
                   {'version': m.VERSION, 'plan_sha256': ph,
                    'target_sha256': m.refresh._hash(plan['targets'][0]), 'index': 0})
    calls = []
    async def fetch(request):
        calls.append(request.url)
        return HtmlResponse(request.url, request=request, status=404, body=b'not found')
    result = asyncio.run(m.collect(review, report, output, fetch=fetch))
    assert calls == ['https://streeteasy.com/rental/101']
    assert result['report']['failure_reasons']['interrupted_request_outcome_unknown'] == 1
