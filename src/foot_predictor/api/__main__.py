"""Lancement de l'API locale (ADR-0040).

    python -m foot_predictor.api serve [--host 127.0.0.1] [--port 8000]

Liaison **locale seulement** : `127.0.0.1` ou `localhost` ; toute autre adresse (dont `0.0.0.0`, qui
exposerait l'API au réseau) est refusée. Documentation interactive : http://127.0.0.1:8000/docs.
"""

from __future__ import annotations

import argparse
import sys

LOCAL_HOSTS = ("127.0.0.1", "localhost")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.api")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="démarre l'API sur l'hôte local")
    serve.add_argument("--host", default="127.0.0.1", choices=LOCAL_HOSTS, help="adresse locale seulement")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import uvicorn

    from foot_predictor.api.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
