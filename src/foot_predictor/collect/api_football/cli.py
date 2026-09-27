"""Commandes du collecteur : `python -m foot_predictor.collect.api_football <commande>`.

    coverage          inventaire /status et /leagues -> couverture.md   (2 requêtes)
    plan --palier P   crée les tâches du palier dans la file            (0 requête)
    run               exécute la file                                   (--max-requests, --dry-run)
    status            quota du jour, files, échecs, progression         (0 requête)
    requeue           remet des tâches failed ou suspect en file        (0 requête)
    backup --dest D   copie data/raw/ et vérifie les sha256             (0 requête)
    rebuild-manifest  reconstruit le journal depuis les fichiers        (0 requête)

Les commandes sans requête n'ont pas besoin de la clé API.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE
from foot_predictor.collect.api_football.client import ApiFootballClient
from foot_predictor.collect.api_football.coverage import coverage_from_body, render_markdown
from foot_predictor.collect.api_football.plan import DEFAULT_CONFIG_PATH, CollectConfig, ConfigError, Planner, load_config
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.runner import (
    STATUS_REL_DIR,
    Runner,
    dry_run_lines,
    manifest_extra,
    store_response,
)
from foot_predictor.collect.api_football.tasks import PRIORITY, leagues_task
from foot_predictor.rawstore import backup as backup_mod
from foot_predictor.rawstore.manifest import read_entries, rebuild

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
    sub = parser.add_subparsers(dest="command", required=True)

    coverage = sub.add_parser("coverage", help="inventaire /status et /leagues (2 requêtes)")
    coverage.add_argument("--output", type=Path, default=DEFAULT_COVERAGE_OUTPUT)

    plan = sub.add_parser("plan", help="crée les tâches d'un palier (aucune requête)")
    plan.add_argument("--palier", required=True, help="P1, P2, P3 ou P4")

    run = sub.add_parser("run", help="exécute la file")
    run.add_argument("--max-requests", type=int, default=None, help="plafond d'appels HTTP pour ce lancement")
    run.add_argument("--dry-run", action="store_true", help="affiche ce qui serait fait, sans requête")

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
        return handler(args, config, client_factory)
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


def cmd_status(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    print("\n".join(status_lines(args.raw_dir)))
    return 0


def cmd_requeue(args, config: CollectConfig, client_factory: ClientFactory) -> int:
    with WorkQueue.in_raw_dir(args.raw_dir) as queue:
        count = queue.requeue(args.status, args.task_type)
    print(f"{count} tâche(s) {args.status} remise(s) en pending.")
    return 0


def cmd_backup(args, config: CollectConfig, client_factory: ClientFactory) -> int:
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


COMMANDS = {
    "coverage": cmd_coverage,
    "plan": cmd_plan,
    "run": cmd_run,
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
