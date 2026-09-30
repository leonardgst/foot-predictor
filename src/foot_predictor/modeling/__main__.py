"""Protocole d'évaluation, modèles et entraînement final du MVP (partie 4 ; ADR-0012, ADR-0037, ADR-0039).

    python -m foot_predictor.modeling evaluate experiments/<nom>.yaml
    python -m foot_predictor.modeling index
    python -m foot_predictor.modeling summary reports/experiments/<id>.json [--output <fichier.md>]
    python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2
    # phase B seulement (après le gel, une seule fois) :
    python -m foot_predictor.modeling evaluate experiments/scelle_h1.yaml --sealed-test --dataset <version scellée>
    python -m foot_predictor.modeling train --final experiments/scelle_h1.yaml --model M3_G0G2 --include-sealed ...

`evaluate` exécute une expérience sur les 4 plis de validation (2021-22 à 2024-25), écrit
`reports/experiments/<id>.json`, les prédictions par match dans `data/experiments/<id>/` (ignoré
par Git) et régénère `reports/experiments/INDEX.md`. `index` régénère l'index ; `summary` imprime
les tableaux Markdown d'un rapport.

`evaluate --sealed-test` : test scellé (ADR-0012, règle 5), seulement pour un fichier qui déclare
`sealed_test: true`, si le code et les expériences n'ont pas changé depuis le tag `pre-scelle-h1`
et si le journal `reports/sealed_tests.md` ne contient pas déjà une évaluation terminée.

`train --final` : entraîne un modèle d'une expérience selon sa procédure, écrit
`models/<version>/` (jamais écrasé) et copie la carte d'identité dans `reports/model_cards/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.modeling")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="exécute une expérience (plis de validation, ou test scellé)")
    evaluate.add_argument("experiment", type=Path, help="fichier experiments/<nom>.yaml")
    evaluate.add_argument(
        "--sealed-test",
        action="store_true",
        help="test scellé (ADR-0012, règle 5) : une seule fois, après le tag pre-scelle-h1, journalisé",
    )
    evaluate.add_argument("--dataset", help="version du jeu (défaut : celle du fichier, sinon la plus récente)")
    sub.add_parser("index", help="régénère reports/experiments/INDEX.md")
    summary = sub.add_parser("summary", help="tableaux Markdown d'un rapport d'expérience")
    summary.add_argument("report", type=Path, help="reports/experiments/<id>.json")
    summary.add_argument("--output", type=Path, help="fichier Markdown (UTF-8, fins de ligne LF) au lieu de la console")
    train = sub.add_parser("train", help="entraînement final d'un modèle et de sa carte d'identité")
    train.add_argument("--final", action="store_true", required=True, help="entraînement final (obligatoire)")
    train.add_argument("experiment", type=Path, help="fichier d'expérience qui décrit la procédure")
    train.add_argument("--model", required=True, help="identifiant du modèle dans le fichier")
    train.add_argument("--dataset", help="version du jeu de données")
    train.add_argument("--validation-report", type=Path, help="rapport JSON dont la carte reprend les métriques")
    train.add_argument("--validation-model", help="identifiant du modèle dans ce rapport (défaut : --model)")
    train.add_argument(
        "--include-sealed",
        action="store_true",
        help="après le test scellé seulement : apprend aussi sur les matchs scellés (lecture journalisée)",
    )
    return parser


def _print_report(report: dict) -> int:
    print(f"Expérience {report['id']} : {report['status']}")
    if report["status"] != "ok":
        print(report.get("error", ""), file=sys.stderr)
        return 1
    for item in report.get("comparisons", []):
        if "log_loss" in item:
            p = item["log_loss"]["pooled"]
            print(f"  {item['a']} − {item['b']} (log-loss) : {p['mean']:+.4f} [{p['low']:+.4f} ; {p['high']:+.4f}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    from foot_predictor.modeling import experiment

    if args.command == "summary":
        from foot_predictor.modeling.summary import summarize

        text = summarize(args.report)
        if args.output:
            args.output.write_text(text, encoding="utf-8", newline="\n")
            print(f"Tableaux : {args.output}")
        else:
            print(text)
        return 0
    if args.command == "index":
        print(f"Index : {experiment.write_index()}")
        return 0
    if args.command == "train":
        from foot_predictor.modeling.final import FinalTrainingError, train_final

        try:
            card = train_final(
                args.experiment, args.model, dataset=args.dataset, include_sealed=args.include_sealed,
                validation_report=args.validation_report, validation_model=args.validation_model,
            )  # fmt: skip
        except FinalTrainingError as error:
            print(str(error), file=sys.stderr)
            return 2
        print(f"Modèle {card['version']} : models/{card['version']}/, carte reports/model_cards/{card['version']}.json")
        return 0
    if args.sealed_test:
        from foot_predictor.modeling.sealed import SealedTestRefused, check_sealed_test_allowed

        try:
            check_sealed_test_allowed(args.experiment.as_posix())
        except SealedTestRefused as error:
            print(str(error), file=sys.stderr)
            return 2
    try:
        report = experiment.run_experiment(args.experiment, sealed_test=args.sealed_test, dataset=args.dataset)
    except experiment.ExperimentError as error:
        print(str(error), file=sys.stderr)
        return 2
    return _print_report(report)


if __name__ == "__main__":
    sys.exit(main())
