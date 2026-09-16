"""Local-only Flask frontend; cloud SDK credentials never reach the browser."""

from __future__ import annotations

import argparse
import secrets

from flask import Flask, jsonify, render_template, request, session


def create_app(backend=None):
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(
        MAX_CONTENT_LENGTH=131072,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    if backend is None:
        import modal

        function = modal.Function.from_name("chelsea-rental-review", "review")
        backend = lambda action, args: function.remote(action, args)

    @app.before_request
    def local_only():
        if request.host.partition(":")[0] not in ("localhost", "127.0.0.1", "[::1]"):
            return jsonify(error="Local access only"), 403
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin not in (
                "http://" + request.host,
                "https://" + request.host,
            ):
                return jsonify(error="Origin rejected"), 403
            if not request.is_json:
                return jsonify(error="JSON required"), 415
            if not isinstance(request.get_json(silent=True), dict):
                return jsonify(error="JSON object required"), 400
            token = session.get("csrf")
            if not token or not secrets.compare_digest(
                request.headers.get("X-Review-CSRF", ""), token
            ):
                return jsonify(error="Reload the page before submitting"), 403

    @app.get("/")
    def index():
        session.setdefault("csrf", secrets.token_hex(24))
        return render_template("rental_review.html", csrf_token=session["csrf"])

    def call(action, args):
        try:
            response = backend(action, args)
            if response.get("ok") is False:
                return jsonify(
                    error=response.get("error", "Cloud operation failed")
                ), 400
            return jsonify(response.get("result", response))
        except Exception as e:
            app.logger.exception("Cloud review operation failed")
            return jsonify(
                error="Cloud operation did not finish. Retry; approved correction requests are idempotent. Detail: "
                + str(e)[:350]
            ), 502

    @app.get("/api/overview")
    def overview():
        return call("overview", {})

    @app.get("/api/observations")
    def observations():
        return call("observations", dict(request.args))

    @app.get("/api/observation/<int:sid>")
    def observation(sid):
        return call("observation", {"snapshot_id": sid})

    @app.get("/api/events/<int:sid>")
    def events(sid):
        return call("events", dict(request.args, snapshot_id=sid))

    @app.get("/api/activity")
    def activity():
        return call("activity", {})

    for route, action in (
        ("/api/review", "review"),
        ("/api/corrections/preview", "preview"),
        ("/api/corrections/apply", "apply"),
        ("/api/cohort/preview", "cohort_preview"),
        ("/api/cohort/apply", "apply"),
        ("/api/parser-issues", "parser_issue"),
        ("/api/corrections/retract", "retract"),
    ):
        app.add_url_rule(
            route,
            route,
            lambda action=action: call(action, request.get_json()),
            methods=["POST"],
        )
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    from waitress import serve

    serve(create_app(), host="127.0.0.1", port=args.port, threads=4)


if __name__ == "__main__":
    main()
