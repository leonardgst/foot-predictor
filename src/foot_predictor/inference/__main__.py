"""Inférence en ligne de commande (partie 5, ADR-0040).

    python -m foot_predictor.inference predict --date 2024-05-19 --mode replay [--horizon H1|H2] [--competition <id>] [--match <id>] [--json]
    python -m foot_predictor.inference live [--days 7] [--save] [--json]
    python -m foot_predictor.inference models [--register] [--activate <version>]
    python -m foot_predictor.inference check [--only rows|replay|predictions|live|rows-h2|replay-h2|predictions-h2|rows-scelle]

`predict` : réponses d'un jour (disponibilité, prédiction ou raisons), en rejeu (saisons 2021-22 à
2024-25, jusqu'au test scellé de H2) ou en live ; `--horizon H2` (rejeu seulement, 6.10) ajoute la qualité
du onze, et vaut `h2_unavailable` en live ; les dates à partir du 1er juillet 2025 sont
refusées tant que le test scellé H1 n'est pas fait (ADR-0045). `models` : modèle actif et modèles
de rejeu en cache, avec leur carte ; `--activate` inscrit un modèle de `models/` et en fait le
modèle actif. `live` (5.14) : prochains jours en live, football-data superposé, rapport de
disponibilité dans `reports/inference/live_<date>.md`, et avec `--save` les réponses du top 5 dans
`ops.prediction` (avant le coup d'envoi). `check` : contrôles sur données réelles, rapports dans `reports/inference/` ;
`rows-scelle` (seulement sur demande, lecture du jeu scellé journalisée) compare les lignes de
l'inférence au jeu scellé sur la période scellée.
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
    predict.add_argument("--horizon", choices=["H1", "H2"], default="H1", help="H2 : avec composition, rejeu seulement")
    predict.add_argument("--competition", type=int, action="append", help="identifiant interne de championnat")
    predict.add_argument("--match", type=int, action="append", help="identifiant interne de match")
    predict.add_argument("--json", action="store_true", help="sortie JSON complète")
    predict.add_argument("--save", action="store_true", help="écrit les réponses dans ops.prediction (idempotent)")
    predict.add_argument("--force", action="store_true", help="avec --save : nouvelle ligne même si elle existe déjà")
    live = sub.add_parser("live", help="live des prochains jours : disponibilité, rapport, traçage (5.14)")
    live.add_argument("--days", type=int, default=7, help="nombre de jours à partir d'aujourd'hui (UTC)")
    live.add_argument("--save", action="store_true", help="écrit les prédictions disponibles du top 5 (mode live)")
    live.add_argument("--json", action="store_true", help="réponses complètes du top 5")
    models = sub.add_parser("models", help="modèle actif et modèles de rejeu en cache")
    models.add_argument(
        "--register", action="store_true",
        help="inscrit dans ops.model_registry le modèle actif (actif s'il n'y en a pas) et les modèles de rejeu en cache",
    )  # fmt: skip
    models.add_argument(
        "--activate", metavar="VERSION",
        help="inscrit le modèle models/<VERSION>/ dans ops.model_registry et en fait le seul modèle actif",
    )  # fmt: skip
    check = sub.add_parser("check", help="contrôles sur données réelles")
    check.add_argument(
        "--only", choices=["rows", "replay", "predictions", "live", "rows-h2", "replay-h2", "predictions-h2", "rows-scelle"],
        help="un seul contrôle ; les contrôles H2 (6.10) et rows-scelle ne sont lancés que sur demande "
        "(rows-scelle : lecture du jeu scellé, journalisée)",
    )  # fmt: skip
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


def save_answers(results: list[dict], reference: dt.date, force: bool = False) -> dict[str, int]:
    """Écrit des réponses dans `ops.prediction` (idempotent) ; une prédiction live tardive est refusée et comptée."""
    from sqlalchemy.orm import Session

    from foot_predictor.db.session import get_engine
    from foot_predictor.inference.store import LivePredictionRefused, save_prediction

    counts = {"created": 0, "kept": 0, "refused": 0}
    with Session(get_engine()) as session:
        for result in results:
            try:
                saved = save_prediction(session, result, reference, force=force)
            except LivePredictionRefused as error:  # trop tard, ou réponse live indisponible
                counts["refused"] += 1
                print(str(error), file=sys.stderr)
                continue
            counts["created" if saved.created else "kept"] += 1
        session.commit()
    return counts


def cmd_live(args) -> int:
    """Prochains jours en live : réponses des matchs du top 5, rapport de disponibilité, traçage facultatif."""
    from foot_predictor.inference import live_report
    from foot_predictor.inference.availability import AVAILABLE, OUT_OF_SCOPE
    from foot_predictor.inference.check import write_report
    from foot_predictor.inference.context import build_context
    from foot_predictor.inference.predict import predict_day

    context = build_context()
    if not context.history_opened:
        print("Live fermé : le test scellé H1 n'est pas terminé (ADR-0045).", file=sys.stderr)
        return 3
    days = [context.today + dt.timedelta(days=offset) for offset in range(args.days)]
    answers = {day: predict_day(day, "live", context) for day in days}
    report = live_report.summarize(answers, context)
    in_scope = [a for day in days for a in answers[day] if a["status"] != OUT_OF_SCOPE]
    if args.save:  # prédictions disponibles du top 5 : la preuve prospective (ADR-0011, règle 6)
        # Jamais une réponse indisponible : l'écriture est idempotente par match, et cette ligne empêcherait
        # d'écrire plus tard la prédiction devenue disponible (historique complété).
        report["saved"] = save_answers([a for a in in_scope if a["status"] == AVAILABLE], context.today)
    _, md_path = write_report(report, f"live_{context.today.isoformat()}", live_report.render(report))
    if args.json:
        print(json.dumps(in_scope, indent=2, ensure_ascii=False))
    else:
        for answer in in_scope:
            print(_line(answer))
    share = report["unavailable_share"]
    print(f"{report['matches']} match(s) du top 5 sur {args.days} jour(s), {report['available']} disponible(s)"
          f"{'' if share is None else f' ; {share:.0%} indisponibles'}"
          f"{' (au-delà du critère : un sur cinq)' if report['over_limit'] else ''} ; {md_path}")  # fmt: skip
    if "saved" in report:
        s = report["saved"]
        print(
            f"ops.prediction (live) : {s['created']} écrite(s), {s['kept']} déjà présente(s), {s['refused']} refusée(s)"
        )
    return 0


def cmd_predict(args) -> int:
    from foot_predictor.inference.context import build_context
    from foot_predictor.inference.predict import ReferenceDateRefused, predict_day

    context = build_context()
    try:
        results = predict_day(args.date, args.mode, context, args.competition, args.match, horizon=args.horizon)
    except ReferenceDateRefused as error:
        print(str(error), file=sys.stderr)
        return 3
    if args.save:
        reference = args.date if args.mode == "replay" else context.today
        saved = save_answers(results, reference, force=args.force)
        print(f"ops.prediction : {saved['created']} écrite(s), {saved['kept']} déjà présente(s), "
              f"{saved['refused']} refusée(s)")  # fmt: skip
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            print(_line(result))
        available = sum(r["status"] == "available" for r in results)
        print(f"{len(results)} match(s), {available} prédit(s) ; données {context.data_version}")
    return 0


def replay_folders() -> list:
    """Dossiers des modèles de rejeu en cache : H1 (`<saison>/`) puis H2 (`h2/<saison>/`), sans dossier vide."""
    from foot_predictor.inference import models

    folders = []
    for root in (models.REPLAY_ROOT, models.REPLAY_ROOT / "h2"):
        if root.exists():
            folders += [f for f in sorted(root.glob("*")) if (f / "model_card.json").exists()]
    return folders


def cmd_models(register: bool = False, activate: str | None = None) -> int:
    from foot_predictor.inference import models

    if activate:
        from sqlalchemy.orm import Session

        from foot_predictor.db.session import get_engine
        from foot_predictor.inference.store import active_version, register_model

        try:
            chosen = models.load_active(activate)
        except models.ModelUnavailable as error:
            print(str(error), file=sys.stderr)
            return 2
        with Session(get_engine()) as session:
            register_model(session, chosen.version, chosen.card, str(chosen.path.relative_to(models.REPO_ROOT)),
                           activate=True)  # fmt: skip
            session.commit()
            print(f"ops.model_registry : actif = {active_version(session)}")
    if register:
        from sqlalchemy.orm import Session

        from foot_predictor.db.session import get_engine
        from foot_predictor.inference.store import active_version, register_model

        with Session(get_engine()) as session:
            active = models.load_active()
            make_active = active_version(session) is None
            register_model(session, active.version, active.card, str(active.path.relative_to(models.REPO_ROOT)),
                           activate=make_active)  # fmt: skip
            for folder in replay_folders():
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
    for folder in replay_folders():
        card = json.loads((folder / "model_card.json").read_text(encoding="utf-8"))
        print(f"rejeu {card['horizon']} {folder.name} : {card['version']} (dernière saison apprise "
              f"{card['training']['last_season']}, demi-vie {card['model']['params'].get('half_life')})")  # fmt: skip
    return 0


def cmd_check(args) -> int:
    from foot_predictor.inference import check

    today = dt.datetime.now(dt.UTC).date().isoformat()
    ok = True
    if args.only in (None, "rows"):
        report = check.run_rows_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"lignes_{today}", check.render_rows(report))
        same = report["same_load_run"] is not False  # E-058 : jeu et staging du même chargement
        print(f"Lignes : {'identiques' if report['all_identical'] else 'ÉCART'} ({report['rows_compared']} lignes)"
              f"{'' if same else ', CHARGEMENTS DIFFÉRENTS'} ; {md_path}")  # fmt: skip
        ok &= report["all_identical"] and same
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
    if args.only == "rows-h2":  # contrôles H2 (6.10) : sur demande, plus longs que ceux de H1
        report = check.run_rows_check(horizon="H2")
        report["date"] = today
        _, md_path = check.write_report(report, f"lignes_h2_{today}", check.render_rows(report))
        same = report["same_load_run"] is not False
        print(f"Lignes H2 : {'identiques' if report['all_identical'] else 'ÉCART'} ({report['rows_compared']} lignes)"
              f"{'' if same else ', CHARGEMENTS DIFFÉRENTS'} ; {md_path}")  # fmt: skip
        ok &= report["all_identical"] and same
    if args.only == "replay-h2":
        report = check.run_replay_check(horizon="H2")
        report["date"] = today
        _, md_path = check.write_report(report, f"rejeu_h2_{today}", check.render_replay(report))
        print(f"Rejeu H2 : {'reproduit' if report['all_reproduced'] else 'ÉCART'} ; {md_path}")
        ok &= report["all_reproduced"]
    if args.only == "predictions-h2":
        report = check.run_predictions_check(horizon="H2")
        report["date"] = today
        _, md_path = check.write_report(report, f"predictions_h2_{today}", check.render_predictions(report))
        print(f"Prédictions H2 : {'reproduites' if report['all_reproduced'] else 'ÉCART'} ; {md_path}")
        ok &= report["all_reproduced"]
    if args.only == "rows-scelle":  # jamais dans la série par défaut : lecture du jeu scellé, journalisée
        report = check.run_sealed_rows_check()
        report["date"] = today
        _, md_path = check.write_report(report, f"lignes_scelle_{today}", check.render_sealed_rows(report))
        print(f"Lignes (période scellée) : {'identiques' if report['all_identical'] else 'ÉCART'} "
              f"({report['rows_compared']} lignes) ; {md_path}")  # fmt: skip
        ok &= report["all_identical"]
    if args.only in (None, "live"):
        from foot_predictor.inference import models as model_store

        # Modèle du pli de la saison de la répétition : il mesure l'écart de λ de la règle par équipe (ADR-0046).
        model = model_store.replay_model(model_store.season_of(check.LIVE_TODAY)).model
        report = check.run_live_rehearsal(model=model)
        report["date"] = today
        _, md_path = check.write_report(report, f"live_repetition_{today}", check.render_live(report))
        verdict = report["goals_and_elo_identical"] and report["score_mismatches"] == 0 and report["following_ok"]
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
    if args.command == "live":
        return cmd_live(args)
    if args.command == "models":
        return cmd_models(args.register, args.activate)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
