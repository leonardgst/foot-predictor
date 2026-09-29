"""Variables du MVP : construction, contrôle et catalogue du jeu de données (ADR-0030).

    python -m foot_predictor.features build [--output-root data/datasets] [--no-db]
    python -m foot_predictor.features check [--version ds-...] [--report-dir reports/variables] [--invariance]
    python -m foot_predictor.features catalogue [--output docs/realisation/06_variables/catalogue.md]

`build` lit les matchs par la porte unique (`features/sources.py`, scellé en SQL), calcule
G0 à G3, écrit `data/datasets/<version>/` (Parquet et manifeste) et une ligne dans
`features.dataset_version`. Mode d'emploi : `docs/realisation/06_variables/README.md`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.features")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="construit un jeu de données versionné (lecture seule de staging)")
    build.add_argument("--output-root", type=Path, help="dossier des versions (défaut : data/datasets)")
    build.add_argument("--no-db", action="store_true", help="ne pas écrire la ligne de features.dataset_version")
    check = sub.add_parser("check", help="contrôle un jeu de données : registre, valeurs vides, distributions, scellé")
    check.add_argument("--version", help="version à contrôler (défaut : la plus récente)")
    check.add_argument("--output-root", type=Path, help="dossier des versions (défaut : data/datasets)")
    check.add_argument("--report-dir", type=Path, default=Path("reports") / "variables")
    check.add_argument(
        "--invariance",
        action="store_true",
        help="contrôle anti-fuite n° 2 sur les données réelles (deux dates de coupe)",
    )
    catalogue = sub.add_parser("catalogue", help="régénère le catalogue des variables depuis le registre")
    catalogue.add_argument(
        "--output", type=Path, help="fichier Markdown (défaut : docs/realisation/06_variables/catalogue.md)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if args.command == "catalogue":
        from foot_predictor.features.catalogue import CATALOGUE_PATH, write_catalogue

        path = write_catalogue(args.output or CATALOGUE_PATH)
        print(f"Catalogue : {path}")
        return 0
    if args.command == "build":
        from foot_predictor.features.build import run_build

        summary = run_build(output_root=args.output_root, record=not args.no_db)
        print(f"Version {summary['version']} : {summary['rows']} lignes en {summary['seconds']:.0f} s")
        print(f"Dossier : {summary['path']}")
        return 0
    from foot_predictor.features.check import run_check

    path = run_check(
        version=args.version, output_root=args.output_root, report_dir=args.report_dir, with_invariance=args.invariance
    )
    print(f"Rapport : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
