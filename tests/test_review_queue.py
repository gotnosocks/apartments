import json
import math

import pytest

from apartments import main_analysis, review_queue as rq
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle


def interval(median, width=.02):
    return {'lower_95': median - width, 'median': median, 'upper_95': median + width, 'probability_positive': .5}


def make_rows():
    rows, residuals, effects = [], [], []
    # u0: singleton, large unit effect absorbs most of the deviation; u1: two observations
    spec = [('a0', 'u0', 'b0', '101', 2010.0, 4000., .05, .12),
            ('a1', 'u1', 'b0', '102', 2020.0, 5000., -.20, -.02),
            ('a2', 'u1', 'b0', '103', 2024.0, 5200., -.18, -.02),
            ('a3', 'u2', 'b1', '104', 2026.0, 3000., .01, .00)]
    for identity, unit, building, ad, year, ask, residual, unit_effect in spec:
        fitted = ask / math.exp(residual)
        rows.append({'audit_id': identity, 'source_listing_id': ad, 'unit_id': unit, 'building': building,
            'period': f'{int(year)}-01-01', 'asking_rent': ask, 'bedrooms': 1, 'bathrooms': 1., 'square_feet': None,
            'listed_floor': 3, 'analysis_price_basis': 'current_capture_gross_ask' if identity == 'a3'
            else 'historical_initial_own_advertisement_ask',
            'canonical_unit_url': f'https://streeteasy.com/building/example-slug/{unit.upper()}'})
        residuals.append({'audit_id': identity, 'source_listing_id': ad, 'unit_id': unit, 'building': building,
            'period': f'{int(year)}-01-01', 'asking_rent': ask, 'fitted_rent': fitted, 'residual_log': residual,
            'residual_dollars': ask - fitted, 'latent_rent_lower_95': fitted * .95, 'latent_rent_upper_95': fitted * 1.05})
    for unit, effect in [('u0', .12), ('u1', -.02), ('u2', .0)]:
        effects.append({'id': unit, 'kind': 'unit', 'log_effect': interval(effect), 'percent_effect': interval(100 * effect)})
    for building, effect in [('b0', .3), ('b1', -.1)]:
        effects.append({'id': building, 'kind': 'building', 'log_effect': interval(effect), 'percent_effect': interval(100 * effect)})
    return rows, residuals, effects


def test_rows_rank_on_unit_effect_plus_residual():
    rows, residuals, effects = make_rows()
    out = rq.build_rows(residuals, effects, rows, descriptions={'a0': 'Bright  studio ' * 40})
    by_id = {r['audit_id']: r for r in out}
    a0 = by_id['a0']
    assert a0['unit_deviation_log'] == pytest.approx(.17)
    assert a0['fitted_rent_without_unit'] == pytest.approx(a0['fitted_rent'] * math.exp(-.12))
    assert a0['unit_deviation_dollars'] == pytest.approx(4000 - a0['fitted_rent_without_unit'])
    assert a0['unit_deviation_percent'] == pytest.approx(100 * (math.exp(.17) - 1))
    assert a0['building_effect_log'] == .3 and a0['unit_observations'] == 1
    assert a0['unit_label'] == 'U0' and a0['advertisement_url'] == 'https://streeteasy.com/rental/101'
    assert a0['description'].endswith('…') and len(a0['description']) == 241
    # Residual ranking would put a1 first; deviation ranking puts a2/a1 (|−.20|,|−.22|) vs a0 (.17)
    assert [r['audit_id'] for r in out] == ['a1', 'a2', 'a0', 'a3']
    assert by_id['a1']['residual_rank'] == 1 and by_id['a0']['residual_rank'] == 3 and by_id['a3']['residual_rank'] == 4
    assert by_id['a3']['current_capture'] is True and by_id['a0']['current_capture'] is False
    assert list(out[0]) == rq.COLUMNS


def test_summary_reports_singleton_share_and_ranking_overlap():
    rows, residuals, effects = make_rows()
    out = rq.build_rows(residuals, effects, rows)
    summary = rq.summarize(out, top=2)
    assert summary['rows'] == 4 and summary['units'] == 3 and summary['current_rows'] == 1
    assert summary['single_observation_rows'] == 2
    assert summary['top_n_overlap_between_rankings'] == 2
    assert summary['median_residual_share_of_deviation_single_observation_units'] == pytest.approx((.05 / .17 + 1) / 2)


@pytest.mark.parametrize('missing', ['unit', 'building', 'source'])
def test_missing_bindings_fail_closed(missing):
    rows, residuals, effects = make_rows()
    if missing == 'unit':
        effects = [e for e in effects if e['id'] != 'u0']
    elif missing == 'building':
        effects = [e for e in effects if e['id'] != 'b1']
    else:
        rows = rows[1:]
    with pytest.raises(ValueError, match='no saved effect|no source row'):
        rq.build_rows(residuals, effects, rows)


def test_page_rows_keep_both_rankings_and_current_captures():
    rows, residuals, effects = make_rows()
    out = rq.build_rows(residuals, effects, rows)
    subset = rq.page_rows(out, 1)
    # a1 leads both rankings; a3 is the only current capture
    assert [r['audit_id'] for r in subset] == ['a1', 'a3']
    page = rq.render_page(subset, {}, {'experiment': 'x'}, total=len(out))
    assert 'embeds 2 of 4 fitted observations' in page and 'of 4 fitted observations' in page


def test_untrusted_links_are_dropped():
    rows, residuals, effects = make_rows()
    rows[0]['canonical_unit_url'] = 'http://evil.example/building/x/1A'
    residuals[0]['source_listing_id'] = '1; drop'
    out = {r['audit_id']: r for r in rq.build_rows(residuals, effects, rows)}
    assert out['a0']['unit_label'] is None and out['a0']['advertisement_url'] is None


def test_end_to_end_bundle_and_page(tmp_path):
    rows, residuals, effects = make_rows()
    dataset = tmp_path / 'dataset'
    publish_bundle(dataset, {'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows)}, {'version': 'x'})
    experiment = tmp_path / 'experiment'
    publish_bundle(experiment / 'protocol', {'protocol.json': '{}\n'}, {'version': 'x'})
    publish_bundle(experiment / 'fit', {'residuals.jsonl': ''.join(canonical(r) + '\n' for r in residuals),
        'group-effects.jsonl': ''.join(canonical(e) + '\n' for e in effects)}, {'version': 'x'})
    evidence = tmp_path / 'evidence'
    publish_bundle(evidence, {'evidence.jsonl': ''.join(canonical(e) + '\n' for e in [
        {'audit_id': 'a1', 'description': 'old text', 'source_collected_at': '2026-01-01'},
        {'audit_id': 'a1', 'description': 'newer   text </script>', 'source_collected_at': '2026-02-01'}])}, {'version': 'x'})
    selection = tmp_path / 'main.json'
    selection.write_text(json.dumps({'version': main_analysis.VERSION, 'model_family': 'pymc_bayesian',
        'experiment': str(experiment), 'dataset': str(dataset), 'evidence': str(evidence),
        'fit_manifest_sha256': digest(experiment / 'fit/complete.json'),
        'protocol_manifest_sha256': digest(experiment / 'protocol/complete.json'),
        'source_manifest_sha256': digest(dataset / 'complete.json'),
        'evidence_manifest_sha256': digest(evidence / 'complete.json')}))
    assert rq.locate(selection, root=tmp_path) is None
    output = rq.default_output(selection, root=tmp_path)
    assert output.parent == tmp_path / rq.QUEUE_ROOT and output.name.startswith('experiment-') and output.name.endswith('-v1')
    result = rq.build_review_queue(selection=selection, root=tmp_path, page_limit=1)
    assert result['rows'] == 4 and result['descriptions'] == 1 and result['warnings'] == []
    assert result['page_rows'] == 2
    manifest = json.loads((output / 'complete.json').read_text())
    assert manifest['version'] == rq.VERSION and set(manifest['files']) == {'queue.jsonl', 'summary.json', 'queue.html'}
    assert manifest['residuals_sha256'] == digest(experiment / 'fit/residuals.jsonl')
    queue = [json.loads(l) for l in (output / 'queue.jsonl').read_text().splitlines()]
    assert queue[0]['rank'] == 1 and {q['audit_id'] for q in queue if q['description']} == {'a1'}
    assert queue[[q['audit_id'] for q in queue].index('a1')]['description'] == 'newer text </script>'
    page = (output / 'queue.html').read_text()
    assert '</script>' in page and 'newer text <\\/script>' in page
    assert 'https://streeteasy.com/rental/102' in page and 'https://streeteasy.com/rental/101' not in page
    assert 'unit_deviation_percent' in page
    located, located_manifest = rq.locate(selection, root=tmp_path)
    assert located == output and located_manifest == manifest
    loaded_rows, loaded_summary, _ = rq.load_queue(located)
    assert loaded_rows == queue and loaded_summary['rows'] == 4
    # A bundle at the expected location that does not match the selection fails closed
    marker = output / 'complete.json'
    marker.write_text(json.dumps({**manifest, 'fit_manifest_sha256': 'x'}))
    with pytest.raises(ValueError, match='does not match'):
        rq.locate(selection, root=tmp_path)
    marker.write_text(json.dumps(manifest))
    # Identical rerun verifies and reuses; a changed fit is rejected
    assert rq.build_review_queue(selection=selection, root=tmp_path, page_limit=1)['rows'] == 4
    (experiment / 'fit/residuals.jsonl').write_text('')
    with pytest.raises(ValueError, match='integrity'):
        rq.build_review_queue(tmp_path / 'queue2', selection=selection, root=tmp_path)


def test_serve_follows_selection(tmp_path, monkeypatch):
    import flask
    captured = {}
    monkeypatch.setattr('waitress.serve', lambda app, **kw: captured.update(app=app, kw=kw))
    rows, residuals, effects = make_rows()
    dataset = tmp_path / 'dataset'
    publish_bundle(dataset, {'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows)}, {'version': 'x'})
    experiment = tmp_path / 'experiment'
    publish_bundle(experiment / 'protocol', {'protocol.json': '{}\n'}, {'version': 'x'})
    publish_bundle(experiment / 'fit', {'residuals.jsonl': ''.join(canonical(r) + '\n' for r in residuals),
        'group-effects.jsonl': ''.join(canonical(e) + '\n' for e in effects)}, {'version': 'x'})
    selection = tmp_path / 'main.json'
    selection.write_text(json.dumps({'version': main_analysis.VERSION, 'model_family': 'pymc_bayesian',
        'experiment': str(experiment), 'dataset': str(dataset),
        'fit_manifest_sha256': digest(experiment / 'fit/complete.json'),
        'protocol_manifest_sha256': digest(experiment / 'protocol/complete.json'),
        'source_manifest_sha256': digest(dataset / 'complete.json')}))
    with pytest.raises(ValueError, match='either'):
        rq.serve(tmp_path, selection=selection)
    rq.serve(selection=selection, root=tmp_path, listen='127.0.0.1:0')
    client = captured['app'].test_client()
    assert client.get('/').status_code == 503
    rq.build_review_queue(selection=selection, root=tmp_path, page_limit=1)
    page = client.get('/')
    assert page.status_code == 200 and b'Residual review queue' in page.data
    assert client.get('/complete.json').status_code == 200 and client.get('/other').status_code == 404
