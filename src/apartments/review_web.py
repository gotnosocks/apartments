"""Private review frontend; explicit listeners and hostnames control access."""

from __future__ import annotations

import argparse
import atexit
import os
import secrets
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, session


def _enabled(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(backend=None, *, dataset_root=None, review_state=None, read_only=None, allowed_hosts=None):
    app = Flask(__name__)
    if allowed_hosts is None:
        allowed_hosts = os.environ.get("REVIEW_ALLOWED_HOSTS", "").split(",")
    trusted_hosts = {"localhost", "127.0.0.1", "::1"}
    trusted_hosts.update(host.strip().lower() for host in allowed_hosts if host.strip())
    app.secret_key = secrets.token_hex(32)
    app.config.update(
        MAX_CONTENT_LENGTH=131072,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    local_mode = dataset_root is not None or review_state is not None
    if dataset_root is None:
        dataset_root = os.environ.get("REVIEW_DATASET_ROOT")
    if review_state is None:
        review_state = os.environ.get("REVIEW_STATE")
    local_mode = local_mode or dataset_root is not None or review_state is not None
    if local_mode:
        if not dataset_root or not review_state:
            raise ValueError("Local mode requires both dataset root and review state")
        from apartments.review_service import ReviewService

        service_lock = threading.RLock()
        service = ReviewService(dataset_root, review_state)

        def local_backend(action, args):
            # ReviewService owns one DuckDB connection and its JSONL ledger.
            try:
                with service_lock:
                    result = service.dispatch(action, args)
                return {"ok": True, "result": result}
            except (ValueError, KeyError, TypeError) as e:
                return {"ok": False, "error": str(e)}

        atexit.register(service.close)
        if backend is None:
            backend = local_backend
    if backend is None:
        import modal

        function = modal.Function.from_name("chelsea-rental-review", "review")
        backend = lambda action, args: function.remote(action, args)

    @app.before_request
    def private_access():
        hostname = urlsplit("//" + request.host).hostname
        if hostname not in trusted_hosts:
            return jsonify(error="Host not allowed"), 403
        if request.method == "POST":
            if _enabled(read_only if read_only is not None else os.environ.get("REVIEW_READ_ONLY")):
                return jsonify(error="Review app is read-only"), 403
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
            app.logger.exception("Review operation failed")
            return jsonify(
                error="Review operation did not finish. Retry; approved correction requests are idempotent. Detail: "
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
        ("/api/events/price/preview", "event_price_preview"),
        ("/api/identity/confirm", "identity_confirm"),
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
    parser.add_argument(
        "--listen", default=os.environ.get("REVIEW_LISTEN"),
        help="Explicit space-separated host:port listeners; defaults to loopback",
    )
    parser.add_argument("--dataset-root", default=os.environ.get("REVIEW_DATASET_ROOT"))
    parser.add_argument("--review-state", default=os.environ.get("REVIEW_STATE"))
    parser.add_argument(
        "--read-only", action="store_true",
        default=_enabled(os.environ.get("REVIEW_READ_ONLY")),
        help="Reject all mutating POST requests",
    )
    args = parser.parse_args()
    from waitress import serve

    serve(
        create_app(
            dataset_root=args.dataset_root,
            review_state=args.review_state,
            read_only=args.read_only,
        ),
        threads=4,
        **({"listen": args.listen} if args.listen else {"host": "127.0.0.1", "port": args.port}),
    )


if __name__ == "__main__":
    main()
