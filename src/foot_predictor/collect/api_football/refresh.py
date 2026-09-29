"""Rafraîchissement d'une saison en cours (commande `refresh`).

Problème (signalé dans la PR #6) : la liste des matchs d'une compétition-saison
n'est demandée qu'une fois. Pour la saison en cours, les matchs joués après
cette date restent « non terminaux » dans la dernière liste stockée. Ils
n'entrent donc jamais dans un lot de détails.

Solution : remettre en `pending` les tâches `fixtures_list`, `teams` et
`injuries` de la saison, pour les blocs des paliers déjà planifiés. Au `run`
suivant :

1. chaque réponse est stockée comme une **nouvelle version** du fichier
   (`rawstore` n'écrase jamais) ; l'ancienne reste sur le disque et dans le journal ;
2. la relance automatique du plan lit la liste la plus récente et crée des lots
   pour les seuls matchs devenus terminaux. Un match déjà reçu (journal) ou
   déjà mis en lot (file) n'est jamais redemandé (`plan.py`).

Cette commande n'envoie aucune requête : elle modifie la file, et c'est `run`
qui consomme le quota. Elle affiche d'abord ce coût.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from foot_predictor.collect.api_football.plan import CollectConfig, Planner
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.collect.api_football.tasks import DETAIL_BATCH_MAX, PRIORITY, Task

REFRESH_ENDPOINTS = ("fixtures_list", "teams", "injuries")
REOPENABLE = frozenset({"done", "suspect"})


@dataclass(frozen=True)
class RefreshItem:
    task: Task
    status: str | None  # statut actuel dans la file ; None si la tâche n'y est pas

    @property
    def queued_by_refresh(self) -> bool:
        """Vrai si la commande ajoute ou remet en file cette tâche."""
        return self.status is None or self.status in REOPENABLE

    @property
    def action(self) -> str:
        if self.status is None:
            return "ajoutée"
        if self.status in REOPENABLE:
            return "remise en file"
        if self.status == "pending":
            return "déjà en attente"
        return "ignorée (failed)"


@dataclass
class RefreshPlan:
    season: int
    tiers: list[str]
    items: list[RefreshItem]
    overdue: dict[int, int]  # compétition -> matchs non terminaux dont la date est passée

    @property
    def to_queue(self) -> list[RefreshItem]:
        """Tâches que la commande remet en file (ou ajoute)."""
        return [item for item in self.items if item.queued_by_refresh]

    @property
    def list_requests(self) -> int:
        return len(self.to_queue)

    @property
    def max_detail_batches(self) -> int:
        """Au plus un lot par tranche de 20 matchs passés, par compétition.

        Estimation haute : un match reporté reste non terminal, et, dans une
        coupe, seuls les matchs d'une équipe suivie sont demandés.
        """
        return sum(math.ceil(count / DETAIL_BATCH_MAX) for count in self.overdue.values())

    @property
    def max_requests(self) -> int:
        """Coût maximal du prochain `run` dû au rafraîchissement, `/status` compris."""
        if not self.to_queue:
            return 0
        return self.list_requests + self.max_detail_batches + 1


def build_refresh_plan(
    config: CollectConfig,
    raw_dir: Path,
    queue: WorkQueue,
    season: int,
    tiers: list[str],
    now: dt.datetime | None = None,
    leagues: list[int] | None = None,
) -> RefreshPlan:
    """Ce que `refresh` ferait, sans rien modifier.

    `leagues` limite le rafraîchissement à ces compétitions : par exemple
    redemander une seule liste (MLS 2017) sans refaire toutes celles de la
    saison.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    planner = Planner(config, raw_dir, queue)
    candidates: dict[str, Task] = {}
    for tier in tiers:
        for task in planner.season_tasks(tier, season, REFRESH_ENDPOINTS):
            if leagues is not None and task.params.get("league") not in leagues:
                continue
            candidates.setdefault(task.key, task)  # une même requête n'existe qu'une fois dans la file
    items = [RefreshItem(task, queue.status_of(task)) for task in candidates.values()]
    refreshed_leagues = {item.task.params["league"] for item in items
                         if item.task.task_type == "fixtures_list" and item.queued_by_refresh}
    return RefreshPlan(season, tiers, items, queue.overdue_deferred(season, refreshed_leagues, now))


def apply_refresh(queue: WorkQueue, plan: RefreshPlan) -> tuple[int, int]:
    """Ajoute les tâches absentes et remet en file les tâches `done` ou `suspect`.
    Renvoie (ajoutées, remises en file)."""
    added = queue.add(item.task for item in plan.items if item.status is None)
    reopened = queue.reopen(item.task.key for item in plan.items if item.status in REOPENABLE)
    return added, reopened


def plan_lines(plan: RefreshPlan) -> list[str]:
    """Résumé affiché avant confirmation : tâches concernées et coût estimé."""
    lines = [f"Rafraîchissement de la saison {plan.season} ({', '.join(plan.tiers)}) : "
             "cette commande n'envoie aucune requête ; c'est le prochain run qui les enverra.", ""]
    if not plan.items:
        return lines + ["Aucune tâche concernée : saison hors des blocs de ces paliers, ou non couverte d'après /leagues."]

    table: dict[tuple[str, str], Counter] = {}
    for item in plan.items:
        table.setdefault((item.task.tier, item.task.task_type), Counter())[item.action] += 1
    actions = ("remise en file", "ajoutée", "déjà en attente", "ignorée (failed)")
    lines.append(f"  {'Palier':<7}{'Type':<15}" + "".join(f"{a:>18}" for a in actions))
    for (tier, task_type), counter in sorted(table.items(), key=lambda kv: (kv[0][0], PRIORITY[kv[0][1]])):
        lines.append(f"  {tier:<7}{task_type:<15}" + "".join(f"{counter[a]:>18}" for a in actions))

    overdue = sum(plan.overdue.values())
    lines += [
        "",
        "Coût estimé du prochain run :",
        f"  listes, équipes, blessures : {plan.list_requests} requête(s)",
        f"  lots de détails            : au plus {plan.max_detail_batches} "
        f"({overdue} match(s) non terminaux à date passée d'après les dernières listes)",
        "  /status au démarrage       : 1",
        f"  total                      : au plus {plan.max_requests} requête(s)",
    ]
    failed = [item for item in plan.items if item.status == "failed"]
    if failed:
        lines += ["", f"{len(failed)} tâche(s) failed non reprise(s) : les examiner, puis requeue --status failed."]
    return lines
