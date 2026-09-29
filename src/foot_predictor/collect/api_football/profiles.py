"""Profils ciblés : titulaires sans date de naissance dans le brut (ADR-0008).

Les pages `/players?league&season` ne contiennent pas tous les joueurs d'une
saison : des titulaires n'y figurent pas, et leur âge est alors inconnu. Tant
que l'abonnement est actif, on demande leur profil un par un avec
`/players/profiles?player=<id>` (une requête par joueur).

Règle de sélection (`plan-profiles`) :

- titulaires (`startXI`) des matchs détaillés des blocs de championnat qui
  collectent les profils (`players` dans leurs `endpoints`), dans l'ordre du
  fichier de paliers : P1 top 5, P1 D2, puis P3 ;
- sans date de naissance dans **aucun** profil du brut, tous paliers et toutes
  saisons confondus (pages `/players` et profils ciblés déjà reçus) ;
- identifiants absents (`null`) ou nuls (`0`, joueur inconnu de l'API) écartés.

Un joueur est rattaché au premier bloc où il est titulaire : la tâche porte
le palier de ce bloc, et les tâches sont ajoutées bloc par bloc, ce qui fixe
l'ordre de traitement par `run`.

Lecture seule du brut ; seule la file de travail est modifiée.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from foot_predictor.collect.api_football import SOURCE, tasks
from foot_predictor.collect.api_football.plan import Block, CollectConfig
from foot_predictor.collect.api_football.queue import WorkQueue
from foot_predictor.rawstore.store import SUFFIX, read_envelope

UNKNOWN_PLAYER_ID = 0  # identifiant donné par l'API à un joueur qu'elle ne connaît pas


@dataclass
class ProfilePlan:
    """Titulaires sans date de naissance, par bloc, dans l'ordre de priorité."""

    known_births: int = 0  # identifiants ayant une date de naissance dans le brut
    starters: Counter = field(default_factory=Counter)  # « P1/top5 » -> titulaires distincts
    missing: dict[str, list[int]] = field(default_factory=dict)  # « P1/top5 » -> identifiants, triés
    tiers: dict[str, str] = field(default_factory=dict)  # « P1/top5 » -> palier
    unreadable: list[str] = field(default_factory=list)

    @property
    def total_missing(self) -> int:
        return sum(len(ids) for ids in self.missing.values())

    def tasks(self, limit: int | None = None) -> list[tasks.Task]:
        """Tâches à ajouter, bloc par bloc ; `limit` garde les premières."""
        planned = [tasks.player_profile_task(self.tiers[label], player)
                   for label, ids in self.missing.items() for player in ids]
        return planned if limit is None else planned[:limit]


def profile_blocks(config: CollectConfig, tiers: Iterable[str]) -> list[tuple[str, Block]]:
    """Blocs de championnat qui collectent les profils, dans l'ordre du YAML."""
    return [(tier, block) for tier in tiers for block in config.tiers.get(tier, [])
            if block.kind == "league" and "players" in block.endpoints]


def _bodies(directory: Path) -> Iterator[tuple[Path, dict | None]]:
    """Corps de tous les fichiers d'un dossier, récursivement (toutes versions)."""
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob(f"*{SUFFIX}")):
        try:
            body = read_envelope(path).get("body")
        except (OSError, EOFError, ValueError):
            yield path, None
            continue
        yield path, body if isinstance(body, dict) and not body.get("errors") else {}


def known_birth_ids(raw_dir: Path, unreadable: list[str] | None = None) -> set[int]:
    """Identifiants ayant une date de naissance dans au moins un profil du brut.

    Toutes les versions de tous les fichiers comptent : une date donnée une
    fois suffit à ne pas redemander le profil.
    """
    known: set[int] = set()
    for folder in ("players", "player_profiles"):
        for path, body in _bodies(Path(raw_dir) / SOURCE / folder):
            if body is None:
                if unreadable is not None:
                    unreadable.append(path.relative_to(raw_dir).as_posix())
                continue
            for entry in body.get("response") or []:
                player = (entry or {}).get("player") or {}
                if player.get("id") and ((player.get("birth") or {}).get("date")):
                    known.add(int(player["id"]))
    return known


def starter_ids(raw_dir: Path, league: int, seasons: Iterable[int],
                unreadable: list[str] | None = None) -> set[int]:
    """Titulaires des matchs détaillés d'une compétition, pour ces saisons
    (toutes versions des lots confondues).

    Le filtre sur les saisons compte : un même dossier `league=39` contient
    aussi les saisons antérieures à 2015 du palier P2, qui n'a pas de profils.
    """
    ids: set[int] = set()
    base = Path(raw_dir) / SOURCE / "fixtures_detail" / f"league={league}"
    for season in seasons:
        for path, body in _bodies(base / f"season={season}"):
            if body is None:
                if unreadable is not None:
                    unreadable.append(path.relative_to(raw_dir).as_posix())
                continue
            for item in body.get("response") or []:
                for lineup in (item or {}).get("lineups") or []:
                    for entry in (lineup or {}).get("startXI") or []:
                        player_id = ((entry or {}).get("player") or {}).get("id")
                        if player_id is not None and player_id != UNKNOWN_PLAYER_ID:
                            ids.add(int(player_id))
    return ids


def build_profile_plan(config: CollectConfig, raw_dir: Path, tiers: Iterable[str]) -> ProfilePlan:
    plan = ProfilePlan()
    known = known_birth_ids(raw_dir, plan.unreadable)
    plan.known_births = len(known)
    seen: set[int] = set()
    for tier, block in profile_blocks(config, tiers):
        label = f"{tier}/{block.name}"
        starters: set[int] = set()
        # Bornes du bloc ; une saison sans dossier est simplement vide. Un bloc
        # sans première saison (toutes celles de /leagues) n'a pas de profils.
        seasons = range(block.seasons.first or block.seasons.last, block.seasons.last + 1)
        for league in block.leagues:
            starters |= starter_ids(raw_dir, league, seasons, plan.unreadable)
        plan.starters[label] = len(starters)
        plan.tiers[label] = tier
        plan.missing[label] = sorted(starters - known - seen)
        seen |= starters
    return plan


def plan_lines(plan: ProfilePlan, queued: int | None = None, limit: int | None = None) -> list[str]:
    """Résumé chiffré, sans identifiant de joueur."""
    lines = [f"Identifiants ayant une date de naissance dans le brut : {plan.known_births}", "",
             f"{'Bloc':<28}{'Titulaires':>11}{'Sans date':>11}"]
    for label, ids in plan.missing.items():
        lines.append(f"{label:<28}{plan.starters[label]:>11}{len(ids):>11}")
    lines.append(f"{'Total (1 requête par joueur)':<39}{plan.total_missing:>11}")
    if limit is not None and limit < plan.total_missing:
        lines.append(f"Plafond --limit : seules les {limit} premières tâches sont retenues (ordre des blocs).")
    if plan.unreadable:
        lines.append(f"Fichiers illisibles ignorés : {len(plan.unreadable)}")
    if queued is not None:
        lines += ["", f"Tâches ajoutées à la file : {queued} (déjà présentes : ignorées)."]
    return lines


def apply_profile_plan(queue: WorkQueue, plan: ProfilePlan, limit: int | None = None) -> int:
    return queue.add(plan.tasks(limit))
