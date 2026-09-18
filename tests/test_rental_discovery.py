import json
from pathlib import Path

import pytest

from apartments import rental_discovery as discovery
from apartments.rental_search import parse_page
from apartments.research_pipeline import digest, publish_bundle
from streeteasy_archive.oxylabs import build_payload


def body(url, *, terminal=False, hostile=False):
    path, number = discovery.rental_search._route(url)
    area = discovery.rental_search.AREAS[path]
    heading = f'2 {area}, Manhattan NY Apartments for Rent' + (f' - Page {number}' if number > 1 else '')
    links = f'<span class="Pagination_currentPage">{number}</span>'
    if number > 1:
        links += f'<a aria-labelledby="previous-arrow-label" href="{path}?page={number-1}">Previous</a>'
    if not terminal:
        next_url = 'https://evil.example/for-rent/chelsea?page=2' if hostile else f'{path}?page={number+1}'
        links += f'<a aria-labelledby="next-arrow-label" href="{next_url}">Next</a>'
    node = {'id': '123', 'urlPath': '/building/example/1a', 'street': '1 Main', 'price': 5000,
            'areaName': area, 'status': 'ACTIVE'}
    stream = 'a:' + json.dumps({'listingType': 'rentals', 'searchMetadata': {'totalResults': 2},
                              'listings': [{'__typename': 'OrganicRentalEdge', 'node': node}]}) + '\n'
    return (f'<main><h1>{heading}</h1><ul class="ListingCardsList_listContainer"><li data-testid="listing-card">'
            '<a class="addressTextAction" href="/building/example/1a">1 Main #1A</a></li></ul>'
            f'<ul class="Pagination_paginationList">{links}</ul></main><script>self.__next_f.push('
            + json.dumps([1,stream]) + ')</script>').encode()


def saved_probe(url, mode, output, *, timeout=180, terminal=False, hostile=False):
    output = Path(output); output.mkdir(parents=True)
    data = body(url, terminal=terminal, hostile=hostile)
    metadata = {'url': url, 'mode': mode, 'request_count': 1, 'replay': None, 'ok': True,
                'api_status': 200, 'target_status': 200, 'body_bytes': len(data),
                'started_at': '2026-09-18T00:00:00+00:00', 'elapsed_seconds': 1}
    (output/'body.html').write_bytes(data)
    (output/'request.json').write_text(json.dumps(build_payload(url)))
    (output/'response.json').write_text(json.dumps({'results':[{'status_code':200,'content':data.decode()}]}))
    (output/'extracted.json').write_text('{}')
    (output/'metadata.json').write_text(json.dumps(metadata))
    return metadata


def preflight(tmp_path, urls=None):
    urls = urls or list(discovery.SEEDS)
    rows = []
    for index,url in enumerate(urls):
        target = tmp_path/'supplied'/str(index)
        saved_probe(url,'html',target)
        row = parse_page((target/'body.html').read_bytes(),url)
        row['probe_evidence'] = {'directory':str(target), 'file_sha256':discovery._hashes(target)}
        rows.append(row)
    target=tmp_path/'preflight-bundle'
    publish_bundle(target, {'pages.jsonl': ''.join(json.dumps(r)+'\n' for r in rows)}, {'version':'test'})
    return target


def no_network(*a,**k):
    pytest.fail('Unexpected provider call')


def test_global_budget_includes_reused_and_resume_never_exceeds(tmp_path, monkeypatch):
    bundle = preflight(tmp_path)
    calls=[]
    def fake(url,mode,output,**kw):
        calls.append(url)
        # Intent and protocol are already durable visible files before transport.
        intent=json.loads((Path(output).parent/'intent.json').read_text())
        assert intent['url']==url and intent['budget_slot_reserved']
        return saved_probe(url,mode,output,**kw)
    monkeypatch.setattr(discovery.capture_probe,'probe',fake)
    result=discovery.run(tmp_path/'run',max_requests=3,preflight_bundle=bundle)
    assert calls==[discovery.SEEDS[0]+'?page=2']
    assert result['reused_provider_submissions']==2
    assert result['new_request_intents']==1 and result['global_reserved_requests']==3
    assert result['stop_reason']=='request_ceiling' and result['complete_inventory'] is False
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    replay=discovery.run(tmp_path/'run',resume=True,replay_only=True)
    assert replay['report_directory']==result['report_directory']
    assert discovery.run(tmp_path/'run',resume=True)['report_directory']==result['report_directory']
    with pytest.raises(ValueError,match='Resume protocol differs'):
        discovery.run(tmp_path/'run',resume=True,max_requests=4)


def test_offline_checkpoint_then_resume_follows_observed_urls(tmp_path,monkeypatch):
    bundle=preflight(tmp_path)
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    first=discovery.run(tmp_path/'run',max_requests=6,preflight_bundle=bundle,replay_only=True)
    first_hash=digest(Path(first['report_directory'])/'complete.json')
    assert first['stop_reason']=='offline_replay_only' and first['new_request_intents']==0
    calls=[]
    def fake(url,mode,output,**kw):
        calls.append(url); return saved_probe(url,mode,output,terminal=True,**kw)
    monkeypatch.setattr(discovery.capture_probe,'probe',fake)
    final=discovery.run(tmp_path/'run',resume=True)
    assert calls==[seed+'?page=2' for seed in discovery.SEEDS]
    assert final['stop_reason']=='pagination_pass_finished_inventory_unverified'
    assert final['complete_inventory'] is False
    assert digest(Path(first['report_directory'])/'complete.json')==first_hash
    assert final['report_directory'] != first['report_directory']
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    assert discovery.run(tmp_path/'run',resume=True,replay_only=True)['report_directory']==final['report_directory']


def test_uncertain_request_intent_is_never_retried(tmp_path,monkeypatch):
    def interrupted(*a,**k): raise KeyboardInterrupt()
    monkeypatch.setattr(discovery.capture_probe,'probe',interrupted)
    with pytest.raises(KeyboardInterrupt):
        discovery.run(tmp_path/'run',max_requests=4)
    assert len(list((tmp_path/'run'/'reports').glob('*/complete.json')))==1
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    result=discovery.run(tmp_path/'run',resume=True)
    assert result['stop_reason']=='uncertain' and result['global_reserved_requests']==1
    assert result['attempts'][0]['outcome']['file_sha256']=={}


def test_capture_finished_before_process_crash_is_replayed_not_retried(tmp_path,monkeypatch):
    def interrupted(url,mode,output,**kw):
        saved_probe(url,mode,output,**kw); raise KeyboardInterrupt()
    monkeypatch.setattr(discovery.capture_probe,'probe',interrupted)
    with pytest.raises(KeyboardInterrupt):
        discovery.run(tmp_path/'run',max_requests=1)
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    result=discovery.run(tmp_path/'run',resume=True)
    assert result['stop_reason']=='request_ceiling'
    assert result['attempts'][0]['outcome']['status']=='accepted'


@pytest.mark.parametrize('kind',['http_failure','hostile_next','ambiguous_next','inconsistent_response'])
def test_failed_and_rejected_raw_evidence_preserved_no_retry(tmp_path,monkeypatch,kind):
    def fake(url,mode,output,**kw):
        metadata=saved_probe(url,mode,output,hostile=kind=='hostile_next',**kw)
        output=Path(output)
        if kind=='http_failure':
            metadata.update(ok=False,target_status=503,error_type='ValueError')
            (output/'metadata.json').write_text(json.dumps(metadata))
        if kind=='inconsistent_response':
            (output/'response.json').write_text(json.dumps({'results':[{'status_code':200,'content':'different'}]}))
        if kind=='ambiguous_next':
            data=(output/'body.html').read_text().replace('</ul></main>', '<a aria-labelledby="next-arrow-label" href="/for-rent/chelsea?page=2">Next</a></ul></main>')
            (output/'body.html').write_text(data)
            metadata['body_bytes']=len(data.encode())
            (output/'metadata.json').write_text(json.dumps(metadata))
            (output/'response.json').write_text(json.dumps({'results':[{'status_code':200,'content':data}]}))
        return metadata
    monkeypatch.setattr(discovery.capture_probe,'probe',fake)
    result=discovery.run(tmp_path/'run',max_requests=8)
    assert result['stop_reason'] in ('capture_failed','capture_rejected')
    assert set(result['attempts'][0]['outcome']['file_sha256'])==set(discovery.RAW_FILES)
    assert result['new_request_intents']==1
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    assert discovery.run(tmp_path/'run',resume=True)['report_directory']==result['report_directory']


def test_tampered_capture_cannot_be_reused(tmp_path,monkeypatch):
    bundle=preflight(tmp_path)
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    (tmp_path/'supplied'/'0'/'body.html').write_text('changed')
    with pytest.raises(ValueError,match='integrity'):
        discovery.run(tmp_path/'run',max_requests=4,preflight_bundle=bundle,replay_only=True)


def test_preflight_page_gap_rejected(tmp_path,monkeypatch):
    bundle=preflight(tmp_path,[discovery.SEEDS[0]+'?page=2'])
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    with pytest.raises(ValueError,match='prefixes'):
        discovery.run(tmp_path/'run',max_requests=4,preflight_bundle=bundle,replay_only=True)


@pytest.mark.parametrize('limit',[None,0,-1,True,1.5])
def test_explicit_positive_ceiling_required(tmp_path,monkeypatch,limit):
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    with pytest.raises(ValueError,match='ceiling'):
        discovery.run(tmp_path/'run',max_requests=limit)


def test_reused_captures_cannot_exceed_ceiling(tmp_path,monkeypatch):
    bundle=preflight(tmp_path)
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    with pytest.raises(ValueError,match='exceed request ceiling'):
        discovery.run(tmp_path/'run',max_requests=1,preflight_bundle=bundle)


def test_local_evidence_is_self_contained_and_tampering_stops_resume(tmp_path,monkeypatch):
    bundle=preflight(tmp_path)
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    first=discovery.run(tmp_path/'run',max_requests=2,preflight_bundle=bundle,replay_only=True)
    rows=[json.loads(s) for s in (Path(first['report_directory'])/'pages.jsonl').read_text().splitlines()]
    assert all(row['capture_reference']['file_sha256']['body.html']==row['body_sha256'] for row in rows)
    # Resume uses copied, verified evidence rather than the original probe tree.
    for item in (tmp_path/'supplied').glob('*/*'): item.unlink()
    assert discovery.run(tmp_path/'run',resume=True,replay_only=True)['report_directory']==first['report_directory']
    (tmp_path/'run'/'preflights'/'0001'/'body.html').write_text('tampered')
    with pytest.raises(ValueError,match='integrity'):
        discovery.run(tmp_path/'run',resume=True)


def test_exclusive_run_lock_prevents_concurrent_submissions(tmp_path,monkeypatch):
    import fcntl
    root=tmp_path/'run';root.mkdir()
    monkeypatch.setattr(discovery.capture_probe,'probe',no_network)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            discovery.run(root,max_requests=1)
