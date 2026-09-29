"""Indisponibilités (`/sidelined`) des titulaires du top 5 : palier P4, facultatif.

`/sidelined` donne l'historique des blessures et suspensions d'un joueur, sur
toute sa carrière. Il complète `/injuries`, que l'API ne couvre qu'à partir de
2021 environ pour la plupart des championnats. La documentation v3 accepte
jusqu'à 20 joueurs par requête (`players=id-id-...`).

Pourquoi une commande à part (`plan-sidelined`) et pas un bloc du YAML : le
planificateur est relancé avant chaque groupe de tâches de `run`. Il relirait
alors tous les détails du top 5 (environ 40 s) à chaque fois ; après un
`refresh`, de nouveaux titulaires changeraient la composition des lots de
20, donc leurs clés, et des centaines de lots seraient redemandés. Ici, les
lots sont figés : un joueur déjà présent dans une tâche `sidelined` n'est
jamais remis en lot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football import tasks
from foot_predictor.collect.api_football.plan import CollectConfig, ConfigError
from foot_predictor.collect.api_football.profiles import starter_ids
from foot_predictor.collect.api_football.queue import WorkQueue

TIER = "P4"


@dataclass
class SidelinedPlan:
    starters: int = 0  # titulaires distincts du bloc source
    already: int = 0  # déjà présents dans une tâche sidelined
    new: list[int] = field(default_factory=list)  # à mettre en lot, triés

    def tasks(self, limit: int | None = None) -> list[tasks.Task]:
        size = tasks.SIDELINED_BATCH_MAX
        planned = [tasks.sidelined_batch_task(TIER, self.new[i:i + size]) for i in range(0, len(self.new), size)]
        return planned if limit is None else planned[:limit]


def queued_players(queue: WorkQueue) -> set[int]:
    """Joueurs déjà présents dans une tâche `sidelined` (seul ou en lot)."""
    players: set[int] = set()
    for params in queue.params_of_type("sidelined"):
        if "player" in params:
            players.add(int(params["player"]))
        players.update(tasks.parse_ids(str(params.get("players", ""))))
    return players


def build_sidelined_plan(config: CollectConfig, raw_dir: Path, queue: WorkQueue | None,
                         source_tier: str = "P1", block_name: str = "top5") -> SidelinedPlan:
    """Titulaires du bloc source (par défaut P1/top5, toutes ses saisons) pas encore demandés.

    `queue` à None : aucune file encore (simulation), personne n'a été demandé."""
    block = next((b for b in config.tiers.get(source_tier, []) if b.name == block_name), None)
    if block is None or block.seasons.first is None:
        raise ConfigError(f"Bloc {source_tier}/{block_name} introuvable, ou sans première saison.")
    seasons = range(block.seasons.first, block.seasons.last + 1)
    starters: set[int] = set()
    for league in block.leagues:
        starters |= starter_ids(raw_dir, league, seasons)
    already = queued_players(queue) if queue is not None else set()
    return SidelinedPlan(len(starters), len(starters & already), sorted(starters - already))


def plan_lines(plan: SidelinedPlan, limit: int | None = None, queued: int | None = None) -> list[str]:
    requests = len(plan.tasks(limit))
    lines = [f"Titulaires du bloc source : {plan.starters} ; déjà demandés : {plan.already} ; "
             f"nouveaux : {len(plan.new)}",
             f"Lots de {tasks.SIDELINED_BATCH_MAX} (1 requête chacun) : {requests}"
             + (f" (plafond --limit {limit})" if limit is not None else "")]
    if queued is not None:
        lines.append(f"Tâches ajoutées à la file (palier {TIER}) : {queued}.")
    return lines
