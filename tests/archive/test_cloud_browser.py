"""Loopback gateway tests with no Modal/network/archive operations."""
from streeteasy_archive.cloud_browser import create_app,allowed_path


def test_gateway_forwards_only_path_query():
    calls=[]
    def remote(path,query):
        calls.append((path,query))
        return {'status':200,'headers':{'Content-Type':'application/json','Set-Cookie':'secret','Location':'https://external.test'},'body':b'{"storage_mode":"cloud"}'}
    client=create_app(remote).test_client()
    response=client.get('/api/summary?generation=2',headers={'Authorization':'secret','Cookie':'secret'})
    assert calls==[('/api/summary','generation=2')]
    assert response.status_code==200 and response.json['storage_mode']=='cloud'
    assert 'Set-Cookie' not in response.headers and 'Location' not in response.headers
    assert response.headers['X-Content-Type-Options']=='nosniff'


def test_invalid_hosts_methods_paths_never_reach_cloud():
    def forbidden(*args): raise AssertionError('Remote call not allowed')
    client=create_app(forbidden).test_client()
    assert client.get('/api/summary',headers={'Host':'evil.test'}).status_code==400
    assert client.post('/api/summary').status_code==405
    assert client.head('/api/summary').status_code==405
    assert client.get('/api/../secret').status_code==404
    assert client.get('/outside').status_code==404
    assert client.get('/api/summary',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert not allowed_path('/api/%252e') and not allowed_path('/static/../secret')


def test_remote_failure_does_not_expose_credentials():
    def bad(*args): raise RuntimeError('secret-token')
    response=create_app(bad).test_client().get('/')
    assert response.status_code==502 and b'secret-token' not in response.data


def test_serve_cloud_does_not_open_local_archive(monkeypatch,tmp_path):
    from streeteasy_archive import cli
    import waitress
    calls=[]
    monkeypatch.setattr(cli,'ArchiveStore',lambda *args: (_ for _ in ()).throw(AssertionError('local archive opened')))
    monkeypatch.setattr(waitress,'serve',lambda app,**kwargs: calls.append(kwargs))
    assert cli.main(['--data',str(tmp_path/'missing'),'serve-cloud'])==0
    assert calls[0]['host']=='127.0.0.1' and calls[0]['port']==8765
    assert not (tmp_path/'missing').exists()
