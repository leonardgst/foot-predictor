"""Commandes du collecteur : `python -m foot_predictor.collect.api_football <commande>`.

    coverage          inventaire /status et /leagues -> couverture.md   (2 requêtes)
    plan --palier P   crée les tâches du palier dans la file            (0 requête)
    run               exécute la file                                   (--max-requests, --dry-run)
    refresh --season S remet en file les listes d'une saison en cours   (0 requête ; coût affiché)
    plan-profiles     titulaires sans date de naissance -> file         (0 requête ; 1 par joueur au run)
    plan-sidelined    lots de 20 titulaires du top 5 -> /sidelined (P4) (0 requête ; 1 par lot au run)
    t60 --date J      compositions annoncées avant le coup d'envoi      (--max-requests ; ~30 par jour)
    t60-report        bilan : titulaires annoncés = titulaires du détail (0 requête, lecture seule)
    lock-status       le dossier brut est-il libre ? (avant un git pull) (0 requête)
    freeze            gel : contrôle, sauvegarde, restauration, DATA_FREEZE (0 requête)
    status            quota du jour, files, échecs, progression         (0 requête)
    requeue           remet des tâches failed ou suspect en file        (0 requête)
    backup --dest D   copie data/raw/ et vérifie les sha256             (0 requête)
    rebuild-manifest  reconstruit le journal depuis les fichiers        (0 requête)

Les commandes sans requête n'ont pas besoin de la clé API.

Verrou : les commandes qui écrivent dans le dossier brut (tout sauf status,
backup, t60-report, lock-status et les --dry-run) prennent le verrou
`<raw_dir>/_lock/collecte.lock` ; une seconde commande échoue aussitôt, ou
attend `--wait-lock` minutes (tâches planifiées). Voir `rawstore/lock.py`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE
from foot_predictor.collect.api_football.client import ApiFootballClient
from foot_predictor.collect.api_football.coverage import coverage_from_body, render_markdown
from foot_predictor.collect.api_football.freeze import FreezeError, render_data_freeze, run_freeze
from foot_predictor.collect.api_football.plan import DEFAULT_CONFIG_PATH, CollectConfig, ConfigError, Planner, load_config
from foot_predictor.collect.api_football.profiles import (
    apply_profile_plan,
    build_profile_plan,
    plan_lines as profile_plan_lines,
    profile_blocks,
)
from foot_predictor.collect.api_football.queue import QUEUE_RELATIVE_PATH, WorkQueue
from foot_predictor.collect.api_football.refresh import apply_refresh, build_refresh_plan, plan_lines
from foot_predictor.collect.api_football.runner import (
    STATUS_REL_DIR,
    Runner,
    dry_run_lines,
    manifest_extra,
    store_response,
)
from foot_predictor.collect.api_football.sidelined import build_sidelined_plan
from foot_predictor.collect.api_football.sidelined import plan_lines as sidelined_plan_lines
from foot_predictor.collect.api_football.t60 import (
    DEFAULT_INTERVAL,
    DEFAULT_LEAD,
    KeepAwake,
    T60Collector,
    compare_lineups,
    comparison_lines,
    day_matches,
    expected_requests,
    report_lines,
)
from foot_predictor.collect.api_football.tasks import PRIORITY, fixtures_list_task, leagues_task
from foot_predictor.rawstore import backup as backup_mod
from foot_predictor.rawstore.lock import CollectLock, LockHeldError, is_stale, read_lock
from foot_predictor.rawstore.manifest import read_entries, rebuild
from foot_predictor.rawstore.store import latest_version, read_envelope

DEFAULT_RAW_DIR = Path("data") / "raw"
DEFAULT_COVERAGE_OUTPUT = Path("docs") / "realisation" / "03_collecte" / "couverture.md"

ClientFactory = Callable[[CollectConfig, "int | None"], ApiFootballClient]


class MissingKeyError(RuntimeError):
    pass


def default_client_factory(config: CollectConfig, max_requests: int | None) -> ApiFootballClient:
    from foot_predictor.config import get_settings

    key = get_settings().api_football_key
    if key is None or not key.get_secret_value():
        raise MissingKeyError("API_FOOTBALL_KEY absente : l'ajouter dans .env.dev (APP_ENV=dev).")
    return ApiFootballClient(key, reserve=config.reserve, max_requests=max_requests)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m foot_predictor.collect.api_football",
        description="Collecteur API-FOOTBALL v2 (ADR-0004). N'écrit que dans le dossier brut.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="dossier brut (défaut : data/raw)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="fichier des paliers")
    parser.add_argument("--wait-lock", type=float, default=0, metavar="MINUTES",
                        help="si le dossier brut est occupé, attendre au plus ce nombre de minutes (défaut : 0)")
    sub = parser.add_subparsers(dest="command", required=True)

    coverage = sub.add_parser("coverage", help="inventaire /status et /leagues (2 requêtes)")
    coverage.add_argument("--output", type=Path, default=DEFAULT_COVERAGE_OUTPUT)

    plan = sub.add_parser("plan", help="crée les tâches d'un palier (aucune requête)")
    plan.add_argument("--palier", required=True, help="P1, P2, P3 ou P4")

    run = sub.add_parser("run", help="exécute la file")
    run.add_argument("--max-requests", type=int, default=None, help="plafond d'appels HTTP pour ce lancement")
    run.add_argument("--dry-run", action="store_true", help="affiche ce qui serait fait, sans requête")

    refresh = sub.add_parser(
        "refresh", help="remet en file listes, équipes et blessures d'une saison en cours (aucune requête)")
    refresh.add_argument("--season", type=int, required=True, help="année de début de saison (2026 = 2026-27)")
    refresh.add_argument("--palier", action="append", dest="tiers",
                         help="palier concerné, répétable ; défaut : tous les paliers déjà planifiés")
    refresh.add_argument("--league", type=int, action="append", dest="leagues",
                         help="compétition concernée, répétable ; défaut : toutes celles des paliers")
    refresh.add_argument("--dry-run", action="store_true", help="affiche les tâches et le coût, sans rien modifier")
    refresh.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")

    profiles = sub.add_parser(
        "plan-profiles", help="met en file les profils des titulaires sans date de naissance (aucune requête)")
    profiles.add_argument("--palier", action="append", dest="tiers",
                          help="palier concerné, répétable ; défaut : tous ceux qui collectent des profils")
    profiles.add_argument("--limit", type=int, default=None, help="nombre maximal de tâches ajoutées")
    profiles.add_argument("--dry-run", action="store_true", help="affiche le décompte, sans modifier la file")

    sidelined = sub.add_parser(
        "plan-sidelined", help="met en file /sidelined pour les titulaires du top 5, par lots de 20 (aucune requête)")
    sidelined.add_argument("--limit", type=int, default=None, help="nombre maximal de lots ajoutés")
    sidelined.add_argument("--dry-run", action="store_true", help="affiche le décompte, sans modifier la file")

    t60 = sub.add_parser("t60", help="journal T-60 : compositions annoncées avant le coup d'envoi")
    t60.add_argument("--date", type=dt.date.fromisoformat, required=True, help="jour des matchs (AAAA-MM-JJ, UTC)")
    t60.add_argument("--max-requests", type=int, required=True, help="plafond d'appels HTTP de l'exécution")
    t60.add_argument("--league", type=int, action="append", dest="leagues",
                     help="compétition suivie, répétable ; défaut : bloc top5 du palier P1")
    t60.add_argument("--lead-minutes", type=float, default=DEFAULT_LEAD.total_seconds() / 60)
    t60.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL.total_seconds() / 60)
    t60.add_argument("--dry-run", action="store_true",
                     help="matchs prévus ce jour d'après les listes du brut (heures peut-être périmées), sans requête")

    sub.add_parser("t60-report", help="bilan du journal T-60 (lecture seule, aucune requête)")
    sub.add_parser("lock-status", help="état du verrou du dossier brut (0 : libre, 1 : occupé)")

    freeze = sub.add_parser("freeze", help="gel : raw_check, sauvegarde, test de restauration, brouillon DATA_FREEZE")
    freeze.add_argument("--dest", type=Path, required=True, help="sauvegarde : dossier absent ou vide (disque externe)")
    freeze.add_argument("--restore-to", type=Path, required=True, help="test de restauration : dossier absent ou vide")
    freeze.add_argument("--report-dir", type=Path, default=Path("reports") / "data_quality",
                        help="résumé raw_check (défaut : reports/data_quality)")
    freeze.add_argument("--doc", type=Path, default=Path("docs") / "DATA_FREEZE.md",
                        help="brouillon de DATA_FREEZE.md (défaut : docs/DATA_FREEZE.md)")
    freeze.add_argument("--allow-blocking", action="store_true",
                        help="geler malgré un verdict BLOQUANT (après décision écrite)")
    sub.add_parser("status", help="quota, files, échecs, progression (aucune requête)")

    requeue = sub.add_parser("requeue", help="remet des tâches failed ou suspect en pending")
    requeue.add_argument("--status", required=True, choices=["failed", "suspect"])
    requeue.add_argument("--type", dest="task_type", choices=sorted(PRIORITY), default=None)

    backup = sub.add_parser("backup", help="copie data/raw/ et vérifie les sha256")
    backup.add_argument("--dest", type=Path, required=True, help="dossier de destination, absent ou vide")

    sub.add_parser("rebuild-manifest", help="reconstruit le journal dans un nouveau fichier")
    return parser


def main(argv: list[str] | None = None, client_factory: ClientFactory = default_client_factory) -> int:
    for stream in (sys.stdout, sys.stderr):
        # Console Windows : un caractère non affichable ne doit pas faire planter la collecte.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        handler = COMMANDS[args.command]
        if args.command in LOCKED_COMMANDS and not getattr(args, "dry_run", False):
            label = " ".join(argv if argv is not None else sys.argv[1:])
            with CollectLock(args.raw_dir, label, wait=dt.timedelta(minutes=args.wait_lock)):
                return handler(args, config, client_factory)
        return handler(args, config, client_factory)
    except LockHeldError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 3
    except (ConfigError, MissingKeyError, FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


# --- commandes ----------------------------------------------------------------------


def cmd_coverage(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    client = client_factory(config, None)
    status_response = client.status()
    store_response(args.raw_dir, STATUS_REL_DIR, "status", status_response)
    task = leagues_task("P0")
    response = client.get(task.endpoint, task.params)
    stored = store_response(args.raw_dir, task.rel_dir, task.stem, response)
    if response.errors:
        print(f"/leagues a renvoyé des erreurs : {response.errors}", file=sys.stderr)
        return 1

    coverage = coverage_from_body(response.body)
    markdown = render_markdown(
        coverage,
        config.tiers,
        status_body=status_response.body,
        source_file=stored.relative_path,
        generated_at=dt.datetime.now(dt.timezone.utc),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown + "\n", encoding="utf-8")

    configured = {league for blocks in config.tiers.values() for block in blocks for league in block.leagues}
    missing = sorted(configured - set(coverage))
    print(f"{len(coverage)} compétitions dans /leagues ; {len(configured) - len(missing)}/{len(configured)} "
          f"identifiants configurés trouvés. Tableau écrit dans {args.output}")
    if missing:
        print(f"Identifiants absents de /leagues : {missing}")
    print(f"Requêtes envoyées : {client.requests_made}")
    return 0


def cmd_plan(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        report = Planner(config, args.raw_dir, queue).plan(args.palier)
    for warning in report.warnings:
        print(f"Attention : {warning}")
    print(f"Palier {report.tier} : {report.total_added} tâches ajoutées")
    for task_type, count in sorted(report.added.items(), key=lambda kv: PRIORITY[kv[0]]):
        print(f"  {task_type:<17}{count:>7}")
    if report.waiting:
        print("En attente de listes non encore collectées (créées automatiquement par run) :")
        for what, count in sorted(report.waiting.items()):
            print(f"  {what:<17}{count:>7} compétition-saison(s)")
    if report.skipped:
        print("Non planifié :")
        for reason, count in sorted(report.skipped.items()):
            if count:
                print(f"  {reason} : {count}")
    if report.deferred:
        print(f"Matchs non terminaux mis de côté : {report.deferred}")
    return 0


def cmd_run(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        if args.dry_run:
            print("\n".join(dry_run_lines(queue)))
            return 0
        client = client_factory(config, args.max_requests)
        report = Runner(client, queue, args.raw_dir, config).run()
    print(f"Requêtes envoyées : {report.requests}")
    for outcome, count in sorted(report.outcomes.items()):
        print(f"  {outcome} : {count}")
    if report.replanned:
        print(f"Tâches dérivées ajoutées pendant le run : {report.replanned}")
    print(f"Arrêt : {report.stop_reason}" if report.stop_reason else "File vide : rien d'autre à collecter pour l'instant.")
    return 0


def ask_confirmation(prompt: str) -> bool:
    """Oui seulement sur une réponse explicite ; entrée fermée (tâche planifiée) = non."""
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in ("o", "oui", "y", "yes")


def cmd_refresh(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        planned = queue.planned_tiers()
        tiers = args.tiers or planned
        if not tiers:
            print("Aucun palier planifié : lancer d'abord plan --palier P1.")
            return 0
        not_planned = [tier for tier in tiers if tier not in planned]
        if not_planned:
            raise ConfigError(f"Palier(s) jamais planifié(s) : {', '.join(not_planned)}. Lancer d'abord plan.")
        plan = build_refresh_plan(config, args.raw_dir, queue, args.season, tiers, leagues=args.leagues)
        print("\n".join(plan_lines(plan)))
        print()
        if not plan.to_queue:
            print("Rien à remettre en file.")
            return 0
        if args.dry_run:
            print("Simulation : file inchangée.")
            return 0
        if not args.yes and not ask_confirmation(f"Remettre ces {len(plan.to_queue)} tâche(s) en file ? [o/N] "):
            print("Annulé : file inchangée.")
            return 0
        added, reopened = apply_refresh(queue, plan)
    print(f"{reopened} tâche(s) remise(s) en file, {added} ajoutée(s).")
    print("Elles partiront au prochain run (un run déjà en cours les prendra à son prochain groupe).")
    return 0


def cmd_plan_profiles(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    tiers = args.tiers or list(config.tiers)
    unknown = [tier for tier in tiers if tier not in config.tiers]
    if unknown:
        raise ConfigError(f"Palier(s) inconnu(s) : {', '.join(unknown)}")
    if not profile_blocks(config, tiers):
        raise ConfigError("Aucun bloc de championnat avec « players » dans ces paliers.")
    plan = build_profile_plan(config, args.raw_dir, tiers)
    if args.dry_run:
        print("\n".join(profile_plan_lines(plan, limit=args.limit)))
        print("\nSimulation : file inchangée.")
        return 0
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        added = apply_profile_plan(queue, plan, args.limit)
    print("\n".join(profile_plan_lines(plan, queued=added, limit=args.limit)))
    print("Elles partiront au prochain run, après les autres tâches du même palier.")
    return 0


def cmd_plan_sidelined(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    if args.dry_run:
        # Simulation : la file n'est ouverte que si elle existe (l'ouvrir la créerait).
        if (args.raw_dir / QUEUE_RELATIVE_PATH).exists():
            with WorkQueue.in_raw_dir(args.raw_dir) as queue:
                plan = build_sidelined_plan(config, args.raw_dir, queue)
        else:
            plan = build_sidelined_plan(config, args.raw_dir, None)
        print("\n".join(sidelined_plan_lines(plan, args.limit)))
        print("Simulation : file inchangée.")
        return 0
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        plan = build_sidelined_plan(config, args.raw_dir, queue)
        added = queue.add(plan.tasks(args.limit))
    print("\n".join(sidelined_plan_lines(plan, args.limit, queued=added)))
    return 0


def top5_leagues(config: CollectConfig) -> list[int]:
    for block in config.tiers.get("P1", []):
        if block.name == "top5":
            return list(block.leagues)
    raise ConfigError("Bloc top5 absent du palier P1 : préciser --league.")


def cmd_t60(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    leagues = args.leagues or top5_leagues(config)
    lead, interval = dt.timedelta(minutes=args.lead_minutes), dt.timedelta(minutes=args.interval_minutes)
    if args.dry_run:
        # Saison qui contient ce jour : 2026 pour 2026-27 (année de début de saison).
        season = args.date.year if args.date.month >= 7 else args.date.year - 1
        matches = []
        for league in leagues:
            task = fixtures_list_task("P1", league, season)
            path = latest_version(args.raw_dir, task.rel_dir, task.stem)
            if path is not None:
                body = read_envelope(path)["body"]
                matches += [m for m in day_matches(body, leagues) if m.kickoff.date() == args.date]
        print(f"Simulation d'après les listes du brut (heures peut-être périmées) : {len(matches)} match(s) le {args.date}.")
        for kickoff, count in sorted(Counter(m.kickoff for m in matches).items()):
            print(f"  {kickoff:%H:%M} UTC : {count} match(s)")
        print(f"Requêtes au plus : {expected_requests(matches, lead, interval)} (plafond demandé : {args.max_requests}).")
        return 0
    client = client_factory(config, args.max_requests)
    with KeepAwake():
        report = T60Collector(client, args.raw_dir, args.date, leagues, lead=lead, interval=interval).run()
    print("\n".join(report_lines(report)))
    return 0


def cmd_t60_report(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    comparisons, without_detail = compare_lineups(args.raw_dir)
    print("\n".join(comparison_lines(comparisons, without_detail)))
    return 0


def cmd_lock_status(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    info = read_lock(args.raw_dir)
    if info is None:
        print("Verrou libre : aucune commande n'écrit dans le dossier brut. git pull possible.")
        return 0
    if is_stale(info, dt.datetime.now(dt.timezone.utc)):
        print(f"Verrou périmé (processus terminé ou trop ancien) : {info.describe()}.")
        print("Il sera remplacé par la prochaine commande. git pull possible.")
        return 0
    print(f"Verrou TENU : {info.describe()}. Ne pas faire de git pull maintenant.")
    return 1


def cmd_status(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    print("\n".join(status_lines(args.raw_dir)))
    return 0


def cmd_requeue(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        count = queue.requeue(args.status, args.task_type)
    print(f"{count} tâche(s) {args.status} remise(s) en pending.")
    return 0


def cmd_freeze(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    started = time.perf_counter()
    print(f"Gel de {args.raw_dir} : raw_check, sauvegarde vers {args.dest}, restauration vers {args.restore_to}.")
    try:
        report = run_freeze(config, args.raw_dir, args.dest, args.restore_to, args.report_dir,
                            allow_blocking=args.allow_blocking)
    except FreezeError as exc:
        print(f"ÉCHEC du gel : {exc}", file=sys.stderr)
        return 1
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_data_freeze(report, config), encoding="utf-8")
    print(f"raw_check : {report.check.verdict} ; résumé {report.summary_path}")
    print(f"Sauvegarde : {report.saved.verified} fichiers vérifiés ; restauration : {report.restored.verified}.")
    for step, seconds in report.durations.items():
        print(f"  {step} : {seconds:.0f} s")
    print(f"Durée totale : {time.perf_counter() - started:.0f} s. Brouillon : {args.doc} (à relire avant commit).")
    return 0


def cmd_backup(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    info = read_lock(args.raw_dir)
    if info is not None and not is_stale(info, dt.datetime.now(dt.timezone.utc)):
        raise ValueError(f"Copie refusée : une commande écrit dans le dossier brut ({info.describe()}).")
    report = backup_mod.backup(args.raw_dir, args.dest)
    print(f"Copie de {args.raw_dir} vers {args.dest}")
    print(f"Fichiers vérifiés (sha256 conforme) : {report.verified}")
    for label, items in (("sha256 différent", report.mismatched), ("absents", report.missing),
                         ("hors journal (avertissement)", report.unlisted)):
        if items:
            print(f"{label} : {len(items)}")
            for item in items[:20]:
                print(f"  {item}")
    print("Sauvegarde vérifiée." if report.ok else "ÉCHEC de la vérification : ne pas considérer la copie comme valide.")
    return 0 if report.ok else 1


def cmd_rebuild_manifest(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    target, entries = rebuild(args.raw_dir, SOURCE, extra_fields=manifest_extra)
    print(f"{len(entries)} lignes écrites dans {target} (journal existant inchangé).")
    return 0


# Commandes qui écrivent dans le dossier brut (fichiers, journal ou file) : verrou.
LOCKED_COMMANDS = frozenset({
    "coverage", "plan", "run", "refresh", "plan-profiles", "plan-sidelined", "requeue", "rebuild-manifest", "t60",
    "freeze",  # n'écrit pas dans le brut, mais aucune collecte ne doit tourner pendant la copie
})

COMMANDS = {
    "coverage": cmd_coverage,
    "plan": cmd_plan,
    "run": cmd_run,
    "refresh": cmd_refresh,
    "plan-profiles": cmd_plan_profiles,
    "plan-sidelined": cmd_plan_sidelined,
    "t60": cmd_t60,
    "t60-report": cmd_t60_report,
    "lock-status": cmd_lock_status,
    "freeze": cmd_freeze,
    "status": cmd_status,
    "requeue": cmd_requeue,
    "backup": cmd_backup,
    "rebuild-manifest": cmd_rebuild_manifest,
}


# --- status -----------------------------------------------------------------------------


def status_lines(raw_dir: Path, today: dt.date | None = None) -> list[str]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    lines = [quota_line(read_entries(raw_dir, SOURCE), today), ""]

    with WorkQueue.in_raw_dir(raw_dir) as queue:
        counts = queue.counts()
        problems = queue.problems(10)
        deferred = queue.deferred_summary()

    if not counts:
        return lines + ["File vide : lancer plan --palier P1."]

    statuses = ("pending", "done", "failed", "suspect")
    table: dict[tuple[str, str], Counter] = {}
    for tier, task_type, status, count in counts:
        table.setdefault((tier, task_type), Counter())[status] += count
    lines.append("File de travail :")
    lines.append(f"  {'Palier':<7}{'Type':<17}" + "".join(f"{s:>9}" for s in statuses))
    for (tier, task_type), counter in table.items():
        lines.append(f"  {tier:<7}{task_type:<17}" + "".join(f"{counter[s]:>9}" for s in statuses))

    lines += ["", "Progression par palier (tâches traitées / connues) :"]
    per_tier: dict[str, Counter] = {}
    for (tier, _), counter in table.items():
        per_tier.setdefault(tier, Counter()).update(counter)
    for tier, counter in sorted(per_tier.items()):
        total = sum(counter.values())
        treated = total - counter["pending"]
        lines.append(f"  {tier} : {treated}/{total} ({100 * treated / total:.1f} %) ; "
                     f"failed {counter['failed']}, suspect {counter['suspect']}")
    lines.append("  (les tâches dérivées s'ajoutent au fil de la collecte : le total grandit)")

    if problems:
        lines += ["", "Derniers échecs et suspects :"]
        for task in problems:
            lines.append(f"  #{task.id} [{task.tier}] {task.task_type} {task.params} : {task.status}, "
                         f"{task.attempts} tentative(s) ; {task.last_error}")
    if deferred:
        detail = ", ".join(f"{status or '?'} {count}" for status, count in deferred)
        lines += ["", f"Matchs non terminaux mis de côté : {sum(c for _, c in deferred)} ({detail})"]
    return lines


def quota_line(entries: list[dict], today: dt.date) -> str:
    """Quota du jour d'après la dernière réponse journalisée (aucune requête)."""
    for entry in reversed(entries):
        remaining = entry.get("quota_remaining_day")
        if remaining is None:
            continue
        stamp = dt.datetime.fromisoformat(entry["timestamp"])
        if stamp.date() == today:
            return f"Quota du jour restant : {remaining} (dernière réponse à {stamp:%H:%M} UTC)."
        return (f"Aucune requête aujourd'hui (UTC) : quota plein. "
                f"Dernière valeur connue : {remaining} le {stamp:%Y-%m-%d %H:%M} UTC.")
    return "Quota du jour : inconnu (aucune réponse journalisée)."
