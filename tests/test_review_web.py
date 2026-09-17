from apartments.review_web import create_app


def test_local_csrf_and_routes():
    calls = []

    def backend(action, args):
        calls.append((action, args))
        return {"ok": True, "result": {"action": action}}

    app = create_app(backend)
    client = app.test_client()
    assert client.get("/", headers={"Host": "evil.com"}).status_code == 403
    assert client.get("/").status_code == 200
    assert client.post("/api/review", json={}).status_code == 403
    with client.session_transaction() as session:
        token = session["csrf"]
    headers = {"X-Review-CSRF": token}
    assert (
        client.post(
            "/api/review",
            json={"snapshot_id": 1},
            headers=dict(headers, Origin="https://evil.com"),
        ).status_code
        == 403
    )
    assert client.post(
        "/api/review", json={"snapshot_id": 1}, headers=headers
    ).json == {"action": "review"}
    assert calls[-1] == ("review", {"snapshot_id": 1})
    assert client.get("/api/events/42?offset=100").status_code == 200
    assert calls[-1] == ("events", {"snapshot_id": 42, "offset": "100"})


def test_cloud_validation_is_user_error():
    app = create_app(lambda a, b: {"ok": False, "error": "stale preview"})
    assert app.test_client().get("/api/overview").status_code == 400


def test_local_service_mode_and_read_only(monkeypatch):
    import apartments.review_service

    instances = []

    class FakeService:
        def __init__(self, root, state):
            self.root = root
            self.state = state
            self.calls = []
            instances.append(self)

        def dispatch(self, action, args):
            self.calls.append((action, args))
            return {"action": action}

        def close(self):
            pass

    registered = []
    monkeypatch.setattr(apartments.review_service, "ReviewService", FakeService)
    monkeypatch.setattr("apartments.review_web.atexit.register", registered.append)

    app = create_app(dataset_root="/archive/dataset", review_state="/archive/state")
    assert len(instances) == 1
    assert instances[0].root == "/archive/dataset"
    assert registered == [instances[0].close]
    client = app.test_client()
    assert client.get("/api/overview").json == {"action": "overview"}
    assert instances[0].calls == [("overview", {})]

    ro = create_app(
        dataset_root="/archive/dataset", review_state="/archive/state", read_only=True
    ).test_client()
    assert ro.get("/").status_code == 200
    with ro.session_transaction() as session:
        token = session["csrf"]
    response = ro.post(
        "/api/review", json={}, headers={"X-Review-CSRF": token}
    )
    assert response.status_code == 403
    assert response.json == {"error": "Review app is read-only"}


def test_local_mode_requires_both_paths():
    import pytest

    with pytest.raises(ValueError, match="both dataset root and review state"):
        create_app(dataset_root="/archive/dataset")


def test_tailnet_host_keeps_csrf_and_origin_protection(monkeypatch):
    import re

    hostname = 'thelio.example.ts.net'
    origin = f'http://{hostname}:8766'
    monkeypatch.setenv('REVIEW_ALLOWED_HOSTS', hostname)
    calls = []
    app = create_app(lambda action, args: calls.append((action, args)) or {'ok': True, 'result': {'saved': True}})
    client = app.test_client()
    page = client.get('/', base_url=origin)
    assert page.status_code == 200
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)
    assert client.get('/', base_url='http://other.example.ts.net:8766').status_code == 403
    assert client.post('/api/review', base_url=origin, json={}).status_code == 403
    assert client.post('/api/review', base_url=origin, json={}, headers={
        'X-Review-CSRF': token, 'Origin': 'http://evil.example',
    }).status_code == 403
    assert calls == []
    response = client.post('/api/review', base_url=origin, json={'snapshot_id': 1}, headers={
        'X-Review-CSRF': token, 'Origin': origin,
    })
    assert response.status_code == 200
    assert calls == [('review', {'snapshot_id': 1})]


def test_tailnet_host_is_opt_in(monkeypatch):
    monkeypatch.delenv('REVIEW_ALLOWED_HOSTS', raising=False)
    client = create_app(lambda *args: {}).test_client()
    assert client.get('/', base_url='http://thelio.example.ts.net:8766').status_code == 403


def test_identity_batch_routes_require_csrf():
    calls = []
    app = create_app(lambda action, args: calls.append((action, args)) or {"result": {"count": 2}})
    client = app.test_client()
    assert b'Confirm selected' in client.get('/').data
    with client.session_transaction() as session:
        token = session['csrf']
    for path, action in [('confirm', 'identity_confirm')]:
        url = '/api/identity/' + path
        assert client.post(url, json={}).status_code == 403
        assert client.post(url, json={}, headers={'X-Review-CSRF': token}).status_code == 200
        assert calls[-1] == (action, {})
