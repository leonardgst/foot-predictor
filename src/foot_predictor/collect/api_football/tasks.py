"""Types de tâches : endpoint appelé, emplacement du fichier brut, résultats attendus.

Une tâche = une requête HTTP. Sa clé canonique (endpoint + paramètres triés,
passés dans sha256, rapport G.6) garantit qu'une même requête n'entre qu'une
fois dans la file.

Arborescence (rapport G.7, versions horodatées ajoutées par `rawstore`) :

    api_football/leagues/all__<ts>.json.gz
    api_football/fixtures_list/league=39/season=2023__<ts>.json.gz
    api_football/fixtures_detail/league=39/season=2023/<hash12>__<ts>.json.gz
    api_football/players/league=39/season=2023/page=01__<ts>.json.gz
    api_football/coachs/team=33__<ts>.json.gz
    api_football/player_profiles/player=276__<ts>.json.gz
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from foot_predictor.collect.api_football import SOURCE

ENDPOINTS = {
    "status": "/status",
    "leagues": "/leagues",
    "fixtures_list": "/fixtures",
    "fixtures_detail": "/fixtures",
    "teams": "/teams",
    "injuries": "/injuries",
    "players": "/players",
    "coachs": "/coachs",
    "transfers": "/transfers",
    "standings": "/standings",
    "sidelined": "/sidelined",
    "player_profile": "/players/profiles",
}

# Ordre de traitement dans un palier : les listes d'abord (les autres tâches
# en dépendent), puis les détails de matchs, les plus précieux (compositions),
# puis le reste. Les joueurs, nombreux (~35 pages par championnat-saison),
# passent en dernier : si le quota s'arrête, c'est eux qui attendent.
PRIORITY = {
    "leagues": 0,
    "fixtures_list": 1,
    "teams": 2,
    "fixtures_detail": 3,
    "injuries": 4,
    "coachs": 5,
    "transfers": 6,
    "standings": 7,
    "players": 8,
    "sidelined": 9,
    # Profils ciblés (ADR-0008) : titulaires sans date de naissance dans le
    # brut. Planifiés à part (`plan-profiles`), après tout le reste.
    "player_profile": 10,
}

# results = 0 est anormal pour ces types. Un club peut n'avoir aucun
# transfert enregistré, un joueur aucune indisponibilité : pas de « suspect ».
EXPECTS_RESULTS = {
    "leagues": True,
    "fixtures_list": True,
    "teams": True,
    "fixtures_detail": True,
    "injuries": True,
    "coachs": True,
    "transfers": False,
    "standings": True,
    "players": True,
    "sidelined": False,
    "player_profile": True,  # 0 résultat : identifiant inconnu de /players/profiles, à examiner
}

DETAIL_BATCH_MAX = 20  # limite de l'API pour /fixtures?ids=


def request_key(endpoint: str, params: dict) -> str:
    canonical = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Task:
    tier: str
    task_type: str
    params: dict = field(hash=False)
    rel_dir: str
    stem: str

    @property
    def endpoint(self) -> str:
        return ENDPOINTS[self.task_type]

    @property
    def key(self) -> str:
        return request_key(self.endpoint, self.params)

    @property
    def expects_results(self) -> bool:
        return EXPECTS_RESULTS[self.task_type]

    @property
    def priority(self) -> int:
        return PRIORITY[self.task_type]

    def params_json(self) -> str:
        return json.dumps(self.params, sort_keys=True)


def _dir(*parts: str) -> str:
    return "/".join((SOURCE, *parts))


def leagues_task(tier: str) -> Task:
    """`/leagues` sans paramètre : toutes les compétitions et leur couverture, en 1 requête."""
    return Task(tier, "leagues", {}, _dir("leagues"), "all")


def fixtures_list_task(tier: str, league: int, season: int) -> Task:
    return Task(
        tier, "fixtures_list", {"league": league, "season": season},
        _dir("fixtures_list", f"league={league}"), f"season={season}",
    )


def fixtures_detail_task(tier: str, league: int, season: int, fixture_ids: list[int]) -> Task:
    if not 0 < len(fixture_ids) <= DETAIL_BATCH_MAX:
        raise ValueError(f"Un lot contient de 1 à {DETAIL_BATCH_MAX} matchs, reçu {len(fixture_ids)}.")
    ids = "-".join(str(i) for i in sorted(fixture_ids))
    stem = hashlib.sha256(ids.encode("ascii")).hexdigest()[:12]
    return Task(
        tier, "fixtures_detail", {"ids": ids},
        _dir("fixtures_detail", f"league={league}", f"season={season}"), stem,
    )


def league_season_task(tier: str, task_type: str, league: int, season: int) -> Task:
    """teams, injuries, standings : un appel par (compétition, saison)."""
    return Task(
        tier, task_type, {"league": league, "season": season},
        _dir(task_type, f"league={league}"), f"season={season}",
    )


def players_task(tier: str, league: int, season: int, page: int = 1) -> Task:
    return Task(
        tier, "players", {"league": league, "season": season, "page": page},
        _dir("players", f"league={league}", f"season={season}"), f"page={page:02d}",
    )


def team_task(tier: str, task_type: str, team: int) -> Task:
    """coachs, transfers : un appel par équipe, toutes saisons confondues."""
    return Task(tier, task_type, {"team": team}, _dir(task_type), f"team={team}")


def sidelined_task(tier: str, player: int) -> Task:
    return Task(tier, "sidelined", {"player": player}, _dir("sidelined"), f"player={player}")


SIDELINED_BATCH_MAX = 20  # « Maximum of 20 players ids » (documentation v3, /sidelined)


def sidelined_batch_task(tier: str, players: list[int]) -> Task:
    """`/sidelined?players=id-id-...` : indisponibilités de 20 joueurs au plus,
    en une requête. Nom de fichier : hash des identifiants, comme les lots de détails."""
    if not 0 < len(players) <= SIDELINED_BATCH_MAX:
        raise ValueError(f"Un lot contient de 1 à {SIDELINED_BATCH_MAX} joueurs, reçu {len(players)}.")
    ids = "-".join(str(i) for i in sorted(players))
    stem = hashlib.sha256(ids.encode("ascii")).hexdigest()[:12]
    return Task(tier, "sidelined", {"players": ids}, _dir("sidelined", "lots"), stem)


def player_profile_task(tier: str, player: int) -> Task:
    """`/players/profiles?player=` : le profil d'un joueur (date de naissance
    comprise), toutes saisons confondues. Une requête par joueur : ce point
    d'accès n'accepte pas plusieurs identifiants."""
    return Task(tier, "player_profile", {"player": player}, _dir("player_profiles"), f"player={player}")


def parse_ids(ids: str) -> list[int]:
    return [int(i) for i in ids.split("-") if i]
