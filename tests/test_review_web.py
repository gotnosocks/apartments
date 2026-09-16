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
