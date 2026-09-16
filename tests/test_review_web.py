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
