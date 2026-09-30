"""Protocole d'évaluation et modèles du MVP (partie 4 ; ADR-0012, ADR-0037).

    python -m foot_predictor.modeling evaluate experiments/<nom>.yaml
    python -m foot_predictor.modeling index

`evaluate` exécute une expérience sur les 4 plis de validation (2021-22 à 2024-25), écrit
`reports/experiments/<id>.json`, les prédictions par match dans `data/experiments/<id>/`
(ignoré par Git) et régénère `reports/experiments/INDEX.md`. `index` ne fait que régénérer
l'index. Les matchs scellés sont refusés : `--sealed-test` est réservé au test scellé de la
phase B (4.16), une fois, sur une liste figée et tagguée ; il n'est pas ouvert ici.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.modeling")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="exécute une expérience (plis de validation, jamais le scellé)")
    evaluate.add_argument("experiment", type=Path, help="fichier experiments/<nom>.yaml")
    evaluate.add_argument(
        "--sealed-test",
        action="store_true",
        help="réservé au test scellé de la phase B (ADR-0012, règle 5) : refusé dans cette phase",
    )
    sub.add_parser("index", help="régénère reports/experiments/INDEX.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    from foot_predictor.modeling import experiment

    if args.command == "index":
        print(f"Index : {experiment.write_index()}")
        return 0
    if args.sealed_test:
        print(
            "--sealed-test : le test scellé se lance une seule fois, en phase B (4.16), sur la liste figée "
            "par le tag pre-scelle-h1. Refusé ici.",
            file=sys.stderr,
        )
        return 2
    report = experiment.run_experiment(args.experiment)
    print(f"Expérience {report['id']} : {report['status']}")
    if report["status"] != "ok":
        print(report.get("error", ""), file=sys.stderr)
        return 1
    for item in report.get("comparisons", []):
        if "log_loss" in item:
            p = item["log_loss"]["pooled"]
            print(f"  {item['a']} − {item['b']} (log-loss) : {p['mean']:+.4f} [{p['low']:+.4f} ; {p['high']:+.4f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
