"""Référentiel : chargement du brut vers `staging` et contrôle J3 (partie 2 ; ADR-0008).

    python -m foot_predictor.ingestion load --raw-dir C:/foot-predictor/data/raw \\
        --external-raw-dir data/raw --confirm-db foot_predictor_travail
    python -m foot_predictor.ingestion check-referentiel

`load` reconstruit **entièrement** `staging` (et vide les tables `features` qui
en dépendent) dans la base de `.env.{APP_ENV}` : il faut confirmer le nom de la
base, et il refuse l'ancienne base dev (voir `load.check_target`). Le brut n'est
lu qu'en lecture seule. Mode d'emploi : `docs/realisation/04_referentiel/README.md`.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from foot_predictor.collect.api_football.plan import DEFAULT_CONFIG_PATH, load_config
from foot_predictor.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("load", help="reconstruit staging depuis le brut (lecture seule du brut)")
    load.add_argument("--raw-dir", type=Path, required=True, help="brut API-FOOTBALL")
    load.add_argument("--external-raw-dir", type=Path, help="bruts externes (CSV football-data) ; absent : API seule")
    load.add_argument("--confirm-db", required=True, help="nom de la base à reconstruire (garde-fou)")
    load.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="périmètre de collecte (compétitions)")
    check = sub.add_parser("check-referentiel", help="contrôle J3 : lit staging, écrit un rapport chiffré")
    check.add_argument("--output-dir", type=Path, default=Path("reports") / "data_quality")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if args.command == "check-referentiel":
        from foot_predictor.ingestion.referentiel_check import run_check

        path = run_check(create_engine(get_settings().database_url), args.output_dir)
        print(f"Rapport : {path}")
        return 0

    from foot_predictor.ingestion.pipeline import LoadRefused, run_load

    # Arguments vérifiés avant de lire la configuration de la base : une erreur de chemin
    # ne dépend pas de la présence d'un .env (le test tournait mal dans un clone sans .env).
    if not args.raw_dir.is_dir():
        print(f"Brut introuvable : {args.raw_dir}", file=sys.stderr)
        return 2
    engine = create_engine(get_settings().database_url)
    try:
        with tempfile.TemporaryDirectory(prefix="fp_load_") as tmp:
            summary = run_load(
                engine, args.raw_dir, args.external_raw_dir, args.confirm_db, load_config(args.config), Path(tmp),
                progress=lambda message: print(message, flush=True),
            )  # fmt: skip
    except LoadRefused as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return 3
    print(f"Chargement {summary['run_id']} terminé en {summary['duration_seconds']} s.")
    for table, fingerprint in summary["fingerprints"].items():
        print(f"  {table:<28} {fingerprint['rows']:>10}  {fingerprint['md5']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
