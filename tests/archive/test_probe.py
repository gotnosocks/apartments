from streeteasy_archive.probe import probe


def test_local_replay_does_not_make_requests(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline replay must not access network or credentials')
    monkeypatch.setattr('streeteasy_archive.probe.requests.post', forbidden)
    monkeypatch.setattr('streeteasy_archive.probe._credentials', forbidden)
    body = tmp_path/'body.html'
    body.write_text('<div role="dialog"><button aria-pressed="true">For rent</button>'
                    '<button role="tab">All (1)</button><table><tbody><tr><td>'
                    '<a href="/rental/123">1A</a></td></tr></tbody></table></div>')
    result = probe('https://streeteasy.com/building/example', 'rentals', tmp_path/'out', body)
    assert result['ok'] and result['inventory_count'] == 1
    assert result['request_count'] == 0
    assert not (tmp_path/'out'/'archive.sqlite3').exists()


def test_incomplete_inventory_keeps_diagnostic(tmp_path):
    body = tmp_path/'body.html'; body.write_text('<div role="dialog"></div>')
    result = probe('https://streeteasy.com/building/example', 'rentals', tmp_path/'out', body)
    assert not result['ok']
    assert 'category was not selected' in result['error']
    assert (tmp_path/'out'/'metadata.json').exists()
