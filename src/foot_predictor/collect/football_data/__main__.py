"""Commandes du collecteur football-data.

    python -m foot_predictor.collect.football_data download --max-requests 300 [--dry-run]
    python -m foot_predictor.collect.football_data check

Options communes : `--raw-dir` (dossier des bruts externes, `data/raw` par
défaut), `--division` (répétable), `--first-season`, `--last-season`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from foot_predictor.collect.football_data.check import check
from foot_predictor.collect.football_data.download import DIVISIONS, FIRST_SEASON, LAST_SEASON, download, plan
from foot_predictor.rawstore.lock import LockHeldError

# Tant que les bruts API-FOOTBALL et football-data n'ont pas été réunis après le gel,
# les CSV vont dans un autre dossier racine, pour ne pas fausser les décomptes et
# les sha256 du gel (partie 2, décision d.7 ; ADR-0024).
API_MARKERS = ("api_football", "_queue")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.collect.football_data")
    parser.add_argument("--raw-dir", type=Path, default=Path("data") / "raw", help="dossier des bruts externes")
    parser.add_argument("--division", action="append", dest="divisions", help=f"défaut : {' '.join(DIVISIONS)}")
    parser.add_argument("--first-season", type=int, default=FIRST_SEASON, help="année de début (2000 = 2000-01)")
    parser.add_argument("--last-season", type=int, default=LAST_SEASON)
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="télécharge les CSV manquants")
    dl.add_argument("--max-requests", type=int, required=True, help="plafond de téléchargements")
    dl.add_argument("--dry-run", action="store_true", help="affiche le plan ; n'écrit rien, n'envoie rien")
    dl.add_argument("--redownload", action="store_true", help="nouvelle version même si le fichier existe")
    dl.add_argument(
        "--allow-api-raw-dir",
        action="store_true",
        help="autorise un dossier qui contient déjà le brut API-FOOTBALL (après le gel seulement)",
    )
    sub.add_parser("check", help="lignes et colonnes par fichier, saisons vides (lecture seule)")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    divisions = tuple(args.divisions or DIVISIONS)
    seasons = range(args.first_season, args.last_season + 1)

    if args.command == "check":
        shapes = check(args.raw_dir, divisions, seasons)
        print("saison | " + " | ".join(divisions) + "   (matchs/colonnes ; « - » : absent)")
        for season in seasons:
            cells = [
                f"{s.matches}/{s.columns}" if s.path else "-"
                for s in shapes
                if s.season == season and s.division in divisions
            ]
            print(f"{season} | " + " | ".join(cells))
        missing = [s for s in shapes if s.path is None]
        empty = [s for s in shapes if s.path is not None and s.empty]
        print(
            f"Fichiers : {len(shapes) - len(missing)} présents sur {len(shapes)} ; absents : {len(missing)} ; vides : {len(empty)}"
        )
        for s in missing + empty:
            print(f"  {'absent' if s.path is None else 'vide'} : {s.division} {s.season}")
        return 1 if missing or empty else 0

    if not args.allow_api_raw_dir and any((args.raw_dir / marker).exists() for marker in API_MARKERS):
        print(
            f"Refusé : {args.raw_dir} contient le brut API-FOOTBALL. Les CSV vont dans le dossier des bruts "
            "externes jusqu'à leur recopie après le gel (--allow-api-raw-dir pour passer outre).",
            file=sys.stderr,
        )
        return 2
    todo, present = plan(args.raw_dir, divisions, seasons, redownload=args.redownload)
    print(f"{len(todo)} fichier(s) à télécharger, {len(present)} déjà présent(s) ; plafond : {args.max_requests}.")
    if args.dry_run:
        for target in todo[: args.max_requests]:
            print(f"  {target.url}")
        if len(todo) > args.max_requests:
            print(f"  ... et {len(todo) - args.max_requests} au-delà du plafond")
        return 0
    try:
        report = download(args.raw_dir, todo, max_requests=args.max_requests, command="football_data download")
    except LockHeldError as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return 3
    print(
        f"Stockés : {len(report.stored)} ; en échec : {len(report.failed)} ; au-delà du plafond : {len(report.skipped_cap)}"
    )
    for target, reason in report.failed:
        print(f"  échec : {target.url} ({reason})")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
