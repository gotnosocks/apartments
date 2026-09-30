"""python -m apartments.site build|serve ...

build   publish a new database from a summary bundle (see `build`).
serve   run the site with waitress (see docs/site.md for the service unit).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def serve(argv):
    parser = argparse.ArgumentParser(prog="python -m apartments.site serve")
    parser.add_argument("--root", type=Path, default=None, help="site root (SITE_ROOT)")
    parser.add_argument(
        "--listen",
        action="append",
        default=None,
        help="host:port to listen on (repeatable; default 127.0.0.1:8600)",
    )
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=None,
        help="exact Host name to accept besides localhost (repeatable)",
    )
    args = parser.parse_args(argv)
    from waitress import serve as waitress_serve

    from .web import create_app

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    app = create_app(args.root, allowed_hosts=args.allowed_host)
    waitress_serve(
        app,
        listen=" ".join(args.listen or ["127.0.0.1:8600"]),
        threads=args.threads,
        ident="listings-site",
        channel_timeout=30,
        connection_limit=200,
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("build", "serve"):
        raise SystemExit(__doc__)
    if argv[0] == "build":
        from .build import main as build_main

        build_main(argv[1:])
    else:
        serve(argv[1:])


if __name__ == "__main__":
    main()
