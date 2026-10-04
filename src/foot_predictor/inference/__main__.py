"""Inférence en ligne de commande (partie 5, ADR-0040).

    python -m foot_predictor.inference predict --date 2024-05-19 --mode replay [--competition <id>] [--match <id>] [--json]
    python -m foot_predictor.inference models
    python -m foot_predictor.inference check [--only rows|replay|predictions|live]

`predict` : réponses d'un jour (disponibilité, prédiction ou raisons), en rejeu (saisons 2021-22 à
2024-25) ou en live ; les dates à partir du 1er juillet 2025 sont refusées tant que le test scellé
n'est pas fait. `models` : modèle actif et modèles de rejeu en cache, avec leur carte. `check` :
contrôles sur données réelles, rapports dans `reports/inference/`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foot_predictor.inference")
    sub = parser.add_subparsers(dest="command", required=True)
    predict = sub.add_parser("predict", help="prédictions d'un jour (rejeu ou live)")
    predict.add_argument("--date", required=True, type=dt.date.fromisoformat, help="jour des matchs (AAAA-MM-JJ)")
    predict.add_argument("--mode", choices=["replay", "live"], default="replay")
    predict.add_argument("--competition", type=int, action="append", help="identifiant interne de championnat")
    predict.add_argument("--match", type=int, action="append", help="identifiant interne de match")
    predict.add_argument("--json", action="store_true", help="sortie JSON complète")
    predict.add_argument("--save", action="store_true", help="écrit les réponses dans ops.prediction (idempotent)")
    predict.add_argument("--force", action="store_true", help="avec --save : nouvelle ligne même si elle existe déjà")
    models = sub.add_parser("models", help="modèle actif et modèles de rejeu en cache")
    models.add_argument(
        "--register", action="store_true",
        help="inscrit dans ops.model_registry le modèle actif (actif s'il n'y en a pas) et les modèles de rejeu en cache",
    )  # fmt: skip
    check = sub.add_parser("check", help="contrôles sur données réelles (période de développement)")
    check.add_argument("--only", choices=["rows", "replay", "predictions", "live"], help="un seul contrôle")
    return parser


def _line(result: dict) -> str:
    teams = f"{result['home_team'] or result['home_team_id']} – {result['away_team'] or result['away_team_id']}"
    head = f"{result['date']} [{result['competition'] or result['competition_id']}] {teams}"
    if result["prediction"] is None:
        return f"{head} : {result['status']} ({' ; '.join(result['reasons'][:2])})"
    p = result["prediction"]
    interval = p["interval"]
    score = result["actual_score"]
    real = f" ; score réel {score['home']}-{score['away']}" if score else ""
    return (
        f"{head} : E[T] = {p['expected_total']:.2f}, P(T > 2,5) = {p['p_over_2_5']:.1%}, "
        f"[{interval['low']} ; {interval['high_label']}] à {interval['announced_coverage']:.1%}{real}"
    )


def cmd_predict(args) -> int:
    from foot_predictor.inference.context import build_context
    from foot_predictor.inference.predict import ReferenceDateRefused, predict_day

    context = build_context()
    try:
        results = predict_day(args.date, args.mode, context, args.competition, args.match)
    except ReferenceDateRefused as error:
        print(str(error), file=sys.stderr)
        return 3
    if args.save:
        from sqlalchemy.orm import Session

        from foot_predictor.db.session import get_engine
        from foot_predictor.inference.store import LivePredictionTooLate, save_prediction

        reference = args.date if args.mode == "replay" else context.today
        created = kept = refused = 0
        with Session(get_engine()) as session:
            for result in results:
                try:
                    saved = save_prediction(session, result, reference, force=args.force)
                except LivePredictionTooLate as error:
                    refused += 1
                    print(str(error), file=sys.stderr)
                    continue
                created += saved.created
                kept += not saved.created
            session.commit()
        print(f"ops.prediction : {created} écrite(s), {kept} déjà présente(s), {refused} refusée(s)")
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            print(_line(result))
        available = sum(r["status"] == "available" for r in results)
        print(f"{len(results)} match(s), {available} prédit(s) ; données {context.data_version}")
    return 0


def cmd_models(register: bool = False) -> int:
    from foot_predictor.inference import models

    if register:
        from sqlalchemy.orm import Session

        from foot_predictor.db.session import get_engine
        from foot_predictor.inference.store import active_version, register_model

        with Session(get_engine()) as session:
            active = models.load_active()
            make_active = active_version(session) is None
            register_model(session, active.version, active.card, str(active.path.relative_to(models.REPO_ROOT)),
                           activate=make_active)  # fmt: skip
            for folder in sorted(models.REPLAY_ROOT.glob("*")) if models.REPLAY_ROOT.exists() else []:
                replay = models.load_model(folder)
                register_model(session, replay.version, replay.card, str(folder.relative_to(models.REPO_ROOT)))
            session.commit()
            print(f"ops.model_registry : actif = {active_version(session)}")

    try:
        active = models.load_active()
        print(f"actif : {active.version} (apprentissage {active.card['training']['first_season']} à "
              f"{active.card['training']['last_season']}, horizon {active.card['horizon']})")  # fmt: skip
    except models.ModelUnavailable as error:
        print(f"actif : {error}")
    for folder in sorted(models.REPLAY_ROOT.glob("*")) if models.REPLAY_ROOT.exists() else []:
        card = json.loads((folder / "model_card.json").read_text(encoding="utf-8"))
        print(f"rejeu {folder.name} : {card['version']} (dernière saison apprise {card['training']['last_season']}, "
              f"demi-vie {card['model']['params'].get('half_life')})")  # fmt: skip
    return 0


def cmd_check(args) -> int:
    from foot_predictor.inference import check

    today = dt.datetime.now(dt.UTC).date().isoformat()
    ok = True
    if args.only in (None, "rows"):
        report = check.run_rows_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"lignes_{today}", check.render_rows(report))
        print(f"Lignes : {'identiques' if report['all_identical'] else 'ÉCART'} ({report['rows_compared']} lignes) ; "
              f"{md_path}")  # fmt: skip
        ok &= report["all_identical"]
    if args.only in (None, "replay"):
        report = check.run_replay_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"rejeu_{today}", check.render_replay(report))
        print(f"Rejeu : {'reproduit' if report['all_reproduced'] else 'ÉCART'} ; {md_path}")
        ok &= report["all_reproduced"]
    if args.only in (None, "predictions"):
        report = check.run_predictions_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"predictions_{today}", check.render_predictions(report))
        print(f"Prédictions : {'reproduites' if report['all_reproduced'] else 'ÉCART'} ; {md_path}")
        ok &= report["all_reproduced"]
    if args.only in (None, "live"):
        report = check.run_live_rehearsal()
        report["date"] = today
        _, md_path = check.write_report(report, f"live_repetition_{today}", check.render_live(report))
        verdict = report["goals_and_elo_identical"] and report["score_mismatches"] == 0
        print(f"Répétition du live : {'buts et Elo identiques' if verdict else 'ÉCART'} ; {md_path}")
        ok &= verdict
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if args.command == "predict":
        return cmd_predict(args)
    if args.command == "models":
        return cmd_models(args.register)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
